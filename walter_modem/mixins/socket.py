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
    modem_string
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

class ModemSocket:
    def __init__(self, id):
        self.state = WalterModemSocketState.FREE
        self.id = id
        self.pdp_context_id = 1
        self.mtu = 300
        self.exchange_timeout = 90
        self.conn_timeout = 60
        self.send_delay_ms = 5000
        self.protocol = WalterModemSocketProto.UDP
        self.accept_any_remote = WalterModemSocketAcceptAnyRemote.DISABLED
        self.remote_host = ""
        self.remote_port = 0
        self.local_port = 0

#endregion
#region Constants

_SOCKET_MIN_CTX_ID = const(1)
_SOCKET_MAX_CTX_ID = const(6)
_SOCKET_SEND_MIN_BYTES_LEN = const(1)
_SOCKET_SEND_MAX_BYTES_LEN = const(16777216)
_SOCKET_RECV_MIN_BYTES_LEN = const(1)
_SOCKET_RECV_MAX_BYTES_LEN = const(1500)

_PDP_DEFAULT_CTX_ID = const(1)
_PDP_MIN_CTX_ID = const(1)
_PDP_MAX_CTX_ID = const(8)

#endregion
#region MixinClass

class SocketMixin(ModemCore):
    MODEM_RSP_FIELDS = (
        ('socket_id', None),
        ('socket_rcv_response', None),
    )

    def __init__(self, *args, **kwargs):
        def init():
            self.socket_context_states = tuple(
                ModemSocketContextState()
                for _ in range(_SOCKET_MIN_CTX_ID, _SOCKET_MAX_CTX_ID + 1)
            )

            self._socket_list = [ModemSocket(idx + 1) for idx in range(_SOCKET_MAX_CTX_ID + 1)]
            """The list of sockets"""

            self._socket = None
            """The socket which is currently in use by the library or None when no socket is in use."""

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
        if ctx_id < _SOCKET_MIN_CTX_ID or  _SOCKET_MAX_CTX_ID < ctx_id:
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
        

    async def socket_create(self,
        pdp_context_id: int = _PDP_DEFAULT_CTX_ID,
        mtu: int = 300,
        exchange_timeout: int = 90,
        conn_timeout: int = 60,
        send_delay_ms: int = 5000,
        rsp: ModemRsp = None
    ) -> bool:
        if pdp_context_id < _PDP_MIN_CTX_ID or pdp_context_id > _PDP_MAX_CTX_ID:
            if rsp: rsp.result = WalterModemState.NO_SUCH_PDP_CONTEXT
            return False

        socket = None
        for _socket in self._socket_list:
            if _socket.state == WalterModemSocketState.FREE:
                _socket.state = WalterModemSocketState.RESERVED
                socket = _socket
                break

        if socket == None:
            if rsp: rsp.result = WalterModemState.NO_FREE_SOCKET
            return False

        self._socket = socket

        socket.pdp_context_id = pdp_context_id
        socket.mtu = mtu
        socket.exchange_timeout = exchange_timeout
        socket.conn_timeout = conn_timeout
        socket.send_delay_ms = send_delay_ms

        async def complete_handler(result, rsp, complete_handler_arg):
            sock = complete_handler_arg
            rsp.type = WalterModemRspType.SOCKET
            rsp.socket_id = sock.id

            if result == WalterModemState.OK:
                sock.state = WalterModemSocketState.CREATED
        
        return await self._run_cmd(
            rsp=rsp,
            at_cmd='AT+SQNSCFG={},{},{},{},{},{}'.format(
                socket.id, socket.pdp_context_id, socket.mtu, socket.exchange_timeout,
                socket.conn_timeout * 10, socket.send_delay_ms // 100
            ),
            at_rsp=b'OK',
            complete_handler=complete_handler,
            complete_handler_arg=socket
        )
    
    async def socket_connect(self,
        remote_host: str,
        remote_port: int,
        local_port: int = 0,
        socket_id: int = -1,
        protocol: int = WalterModemSocketProto.UDP,
        accept_any_remote: int = WalterModemSocketAcceptAnyRemote.DISABLED,
        rsp: ModemRsp = None
    ) -> bool:
        try:
            socket = self._socket if socket_id == -1 else self._socket_list[socket_id - 1]
        except Exception:
            if rsp: rsp.result = WalterModemState.NO_SUCH_SOCKET
            return False
        
        self._socket = socket

        socket.protocol = protocol
        socket.accept_any_remote = accept_any_remote
        socket.remote_host = remote_host
        socket.remote_port = remote_port
        socket.local_port = local_port

        async def complete_handler(result, rsp, complete_handler_arg):
            sock = complete_handler_arg
            if result == WalterModemState.OK:
                sock.state = WalterModemSocketState.OPENED

        return await self._run_cmd(
            rsp=rsp,
            at_cmd='AT+SQNSD={},{},{},{},0,{},1,{},0'.format(
                socket.id, socket.protocol, socket.remote_port,
                modem_string(socket.remote_host), socket.local_port,
                socket.accept_any_remote
            ),
            at_rsp=b'OK',
            complete_handler=complete_handler,
            complete_handler_arg=socket
        )

    #endregion
    #region PrivateMethods

    def _socket_mirror_state_reset(self):
        self._socket_list = [ModemSocket(idx + 1) for idx in range(_SOCKET_MAX_CTX_ID + 1)]
        self._socket = None

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


    async def __handle_sqnscfg(self, tx_stream, cmd, at_rsp):
        conn_id, cid, pkt_sz, max_to, conn_to, tx_to = map(int, at_rsp.split(b': ')[1].split(b','))

        socket = self._socket_list[conn_id - 1]
        socket.id = conn_id
        socket.pdp_context_id = cid
        socket.mtu = pkt_sz
        socket.exchange_timeout = max_to
        socket.conn_timeout = conn_to / 10
        socket.send_delay_ms = tx_to * 100

    #endregion
#endregion
