from micropython import const # type: ignore

from ..core import ModemCore
from ..coreEnums import (
    Enum,
    WalterModemState,
    WalterModemRspType,
    WalterModemCmdType
)
from ..coreStructs import (
    ModemRsp
)
from ..utils import (
    mro_chain_init,
    modem_string,
    modem_bool
)

#region Enums

class WalterModemSocketState(Enum):
    FREE = 0
    RESERVED = 1
    CREATED = 2
    CONFIGURED = 3
    OPENED = 4
    LISTENING = 5
    CLOSED = 6

class WalterModemSocketProto(Enum):
    TCP = 0
    UDP = 1

class WalterModemSocketAcceptAnyRemote(Enum):
    DISABLED = 0
    REMOTE_RX_ONLY = 1
    REMOTE_RX_AND_TX = 2

class WalterModemRai(Enum):
    NO_INFO = 0
    NO_FURTHER_RXTX_EXPECTED = 1
    ONLY_SINGLE_RXTX_EXPECTED = 2

class WalterModemSocketRingMode(Enum):
    NORMAL = 0
    """Only ctx_id"""
    DATA_AMOUNT = 1
    """ctx_id & data length"""
    DATA_VIEW = 2
    """ctx_id, data length & data"""

class WalterModemSocketRecvMode(Enum):
    TEXT_OR_RAW = 0
    HEX_BYTES_SEQUENCE = 1

class WalterModemSocketListenMode(Enum):
    DISABLED = 0
    ENABLED = 1

class WalterModemSocketSendMode(Enum):
    TEXT_OR_RAW = 0
    HEX_BYTES_SEQUENCE = 1

#endregion
#region Structs

class ModemSocketContextState:
    def __init__(self):
        self.connected = False
        self.configured = False
        self.rings: list[ModemSocketRing] = []
        self.accept_any_remote = WalterModemSocketAcceptAnyRemote.DISABLED

class ModemSocketRing:
    def __init__(self, ctx_id, length = None, data = None):
        self.ctx_id: int = ctx_id
        self.length: int | None = length
        self.data = data

class ModemSocketResponse:
    def __init__(self, ctx_id, max_bytes, payload, addr = None, port = None):
        self.ctx_id: int = ctx_id
        self.max_bytes: int = max_bytes
        self.addr: str | None = addr
        self.port: int | None = port
        self.payload: bytearray = payload

#endregion
#region Constants

_SOCKET_MIN_CTX_ID = const(1)
_SOCKET_MAX_CTX_ID = const(6)
_SOCKET_SEND_MIN_BYTES_LEN = const(1)
_SOCKET_SEND_MAX_BYTES_LEN = const(16777216)
_SOCKET_RECV_MIN_BYTES_LEN = const(1)
_SOCKET_RECV_MAX_BYTES_LEN = const(1500)

_TLS_MIN_CTX_ID = const(1)
_TLS_MAX_CTX_ID = const(6)

_PDP_MIN_CTX_ID = const(0)
_PDP_MAC_CTX_ID = const(6)

#endregion
#region MixinClass

class SocketMixin(ModemCore):
    MODEM_RSP_FIELDS = (
        ('socket_rcv_response', None),
    )

    def __init__(self, *args, **kwargs):
        def init():
            self.socket_context_states = tuple(
                ModemSocketContextState()
                for _ in range(_SOCKET_MIN_CTX_ID, _SOCKET_MAX_CTX_ID + 1)
            )

            self.__queue_rsp_rsp_handlers = (
                self.__queue_rsp_rsp_handlers + (
                    (b'+SQNSH: ', self._handle_socket_closed),
                    (b'+SQNSRING: ', self._handle_socket_ring),
                    (b'+SQNSRECV: ', self._handle_socket_rcv),
                    (b'+SQNSCFG: ', self.__handle_sqnscfg),
                )
            )

            self.__mirror_state_reset_callables = (
                self.__mirror_state_reset_callables + (self._socket_mirror_state_reset,)
            )
        
        mro_chain_init(self, super(), init, SocketMixin, *args, **kwargs)

    #region PublicMethods

    async def socket_close(self,
        ctx_id: int,
        rsp: ModemRsp = None
    ) -> bool:
        if ctx_id < _SOCKET_MIN_CTX_ID or _SOCKET_MAX_CTX_ID < ctx_id:
            if rsp: rsp.result = WalterModemState.NO_SUCH_PROFILE
            return False

        return await self._run_cmd(
            rsp=rsp,
            at_cmd=f'AT+SQNSH={ctx_id}',
            at_rsp=b'OK'
        )

    async def socket_send(self,
        ctx_id: int,
        data: bytes | bytearray | str | None,
        length: int = None,
        rai: int = WalterModemRai.NO_INFO,
        remote_addr: str = None,
        remote_port: int = None,
        rsp: ModemRsp = None
    ) -> bool:
        if ctx_id < _SOCKET_MIN_CTX_ID or _SOCKET_MAX_CTX_ID < ctx_id:
            if rsp: rsp.result = WalterModemState.NO_SUCH_PROFILE
            return False
        
        if self.socket_context_states[ctx_id].accept_any_remote != WalterModemSocketAcceptAnyRemote.REMOTE_RX_AND_TX:
            if remote_addr is not None or remote_port is not None:
                if rsp: rsp.result = WalterModemState.ERROR
                return False
        
        if isinstance(data, str):
            data = data.encode('utf-8')
        elif data is not None and not isinstance(data, (bytes, bytearray)):
            if rsp: rsp.result = WalterModemState.ERROR
            return False
        
        if length is None:
            length = 0 if data is None else len(data)
        
        if length < _SOCKET_SEND_MIN_BYTES_LEN or _SOCKET_SEND_MAX_BYTES_LEN < length:
            if rsp: rsp.result = WalterModemState.ERROR
            return False

        return await self._run_cmd(
            rsp=rsp,
            at_cmd='AT+SQNSSENDEXT={},{},{},{},{}'.format(
                ctx_id, length, rai,
                modem_string(remote_addr) if remote_addr is not None else '',
                remote_port
            ),
            at_rsp=b'OK',
            cmd_type=WalterModemCmdType.DATA_TX_WAIT,
            data=data
        )

    async def socket_receive_data(self,
        ctx_id: int,
        length: int,
        max_bytes: int,
        rsp: ModemRsp = None
    ) -> bool:
        if ctx_id < _SOCKET_MIN_CTX_ID or _SOCKET_MAX_CTX_ID < ctx_id:
            if rsp: rsp.result = WalterModemState.NO_SUCH_PROFILE
            return False
        
        if max_bytes < _SOCKET_RECV_MIN_BYTES_LEN or _SOCKET_RECV_MAX_BYTES_LEN < max_bytes:
            if rsp: rsp.result = WalterModemState.ERROR
            return False
        
        if length < 0:
            if rsp: rsp.result = WalterModemState.ERROR
            return False
        
        self.__parser_data.raw_chunk_size = min(length, max_bytes)

        return await self._run_cmd(
            rsp=rsp,
            at_cmd=f'AT+SQNSRECV={ctx_id},{max_bytes}',
            at_rsp=b'OK'
        )

    async def socket_config_secure(self,
        ctx_id: int,
        enable: bool,
        secure_profile_id: int,
        rsp: ModemRsp = None
    ) -> bool:
        if ctx_id < _SOCKET_MIN_CTX_ID or _SOCKET_MAX_CTX_ID < ctx_id:
            if rsp: rsp.result = WalterModemState.NO_SUCH_PROFILE
            return False
        
        if secure_profile_id < _TLS_MIN_CTX_ID or _TLS_MAX_CTX_ID < ctx_id:
            if rsp: rsp.result = WalterModemState.ERROR
            return False
        
        return await self._run_cmd(
            rsp=rsp,
            at_cmd=f'AT+SQNSSCFG={ctx_id},{modem_bool(enable)},{secure_profile_id}',
            at_rsp=b'OK'
        )
    
    async def socket_config_extended(self,
        ctx_id: int,
        ring_mode: int = WalterModemSocketRingMode.DATA_AMOUNT,
        recv_mode: int = WalterModemSocketRecvMode.TEXT_OR_RAW,
        keepalive: int = 60,
        listen_mode: int = WalterModemSocketListenMode.DISABLED,
        send_mode: int = WalterModemSocketSendMode.TEXT_OR_RAW,
        rsp: ModemRsp = None
    ) -> bool:
        if ctx_id < _SOCKET_MIN_CTX_ID or _SOCKET_MAX_CTX_ID < ctx_id:
            if rsp: rsp.result = WalterModemState.NO_SUCH_PROFILE
            return False
        
        return await self._run_cmd(
            rsp=rsp,
            at_cmd='AT+SQNSCFGEXT={},{},{},{},{},{}'.format(
                ctx_id, ring_mode, recv_mode, keepalive, listen_mode, send_mode
            ),
            at_rsp=b'OK'
        )
    
    async def socket_config(self,
        ctx_id: int,
        pdp_ctx_id: int,
        mtu: int = 300,
        exchange_timeout: int = 90,
        connection_timeout: int = 60,
        send_delay_ms: int = 5000,
        rsp: ModemRsp = None
    ) -> bool:
        if ctx_id < _SOCKET_MIN_CTX_ID or _SOCKET_MAX_CTX_ID < ctx_id:
            if rsp: rsp.result = WalterModemState.NO_SUCH_PROFILE
            return False

        if pdp_ctx_id < _PDP_MIN_CTX_ID or _PDP_MAC_CTX_ID < pdp_ctx_id:
            if rsp: rsp.result = WalterModemState.NO_SUCH_PDP_CONTEXT
            return False
        
        return await self._run_cmd(
            rsp=rsp,
            at_cmd='AT+SQNSCFG={},{},{},{},{},{}'.format(
                ctx_id, pdp_ctx_id, mtu, exchange_timeout,
                connection_timeout * 10, send_delay_ms // 100
            ),
            at_rsp=b'OK'
        )
    
    async def socket_accept(self,
        ctx_id: int,
        command_mode: bool = True,
        rsp: ModemRsp = None
    ) -> bool:
        if ctx_id < _SOCKET_MIN_CTX_ID or _SOCKET_MAX_CTX_ID < ctx_id:
            if rsp: rsp.result = WalterModemState.NO_SUCH_PROFILE
            return False
        
        return await self._run_cmd(
            rsp=rsp,
            at_cmd=f'AT+SQNSA={ctx_id},{modem_bool(command_mode)}',
            at_rsp=b'OK',
            cmd_type=WalterModemCmdType.DATA_TX_WAIT
        )

    #endregion
    #region PrivateMethods

    def _socket_mirror_state_reset(self):
        self.socket_context_states = tuple(
            ModemSocketContextState()
            for _ in range(_SOCKET_MIN_CTX_ID, _SOCKET_MAX_CTX_ID + 1)
        )

    #endregion
    #region QueueResponseHandlers

    async def _handle_socket_closed(self, tx_stream, cmd, at_rsp):
        ctx_id = int(at_rsp.split(b':').decode())
        self.socket_context_states[ctx_id].connected = False

        return WalterModemState.OK
    
    async def _handle_socket_ring(self, tx_stream, cmd, at_rsp):
        parts = at_rsp.split(b': ', 1)[1].split(b',')
        ctx_id = int(parts[0].decode())

        self.socket_context_states[ctx_id].rings.append(ModemSocketRing(
            ctx_id=ctx_id,
            length=int(parts[1].decode()) if len(parts) >= 2 else None,
            data=parts[2] if len(parts) == 3 else None
        ))

        return WalterModemState.OK
    
    async def _handle_socket_rcv(self, tx_stream, cmd, at_rsp):
        header, payload = at_rsp.split(b': ', 1)[1].split(b'\r')
        header = header.split(b',')

        ctx_id, max_bytes = int(header[0].decode()), int(header[1].decode())
        addr = None
        port = None
        if len(header) == 4:
            addr = header[2].decode()
            port = int(header[3].decode())
        
        cmd.rsp.type = WalterModemRspType.SOCKET
        cmd.rsp.socket_rcv_response = ModemSocketResponse(
            ctx_id=ctx_id,
            max_bytes=max_bytes,
            payload=payload,
            addr=addr,
            port=port
        )

        return WalterModemState.OK

    #endregion
#endregion
