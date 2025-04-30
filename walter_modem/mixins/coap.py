from micropython import const # type: ignore

from ..core import ModemCore
from ..enums import (
    WalterModemState,
    WalterModemCmdType,
    WalterModemCoapType
)
from ..structs import (
    ModemRsp,
    ModemCoapContextState,
    WalterModemCoapMethod
)
from ..utils import (
    modem_bool,
    modem_string,
    log
)

COAP_MIN_CTX_ID = const(0)
COAP_MAX_CTX_ID = const(2)
COAP_MIN_TIMEOUT = const(1)
COAP_MAX_TIMEOUT = const(120)
COAP_MIN_BYTES_LENGTH = const(0)
COAP_MAX_BYTES_LENGTH = const(1024)

class ModemCoap(ModemCore):
    def __init__(self):
        self.coap_context_states = tuple(
            ModemCoapContextState()
            for _ in range(COAP_MIN_CTX_ID, COAP_MAX_CTX_ID + 1)
        )
        """Index maps to the profile ID"""

        super().__init__()

    async def coap_context_create(self,
        ctx_id: int = 0,
        server_address: str = None,
        server_port: int = None,
        local_port: int = None,
        timeout: int = 20,
        dtls: bool = False,
        secure_profile_id: int = None,
        rsp: ModemRsp = None
    ) -> bool:
        """
        Create a CoAP context, required to send, receive & set CoAP options.

        If the server_address & server_port are provided, a connection attempt is made.

        If server_address & server_port are omitted and only local_port is provided,
        the context is created in listen mode, waiting for an incoming connection.

        :param ctx_id: Context profile identifier (0, 1, 2)
        :param server_address: IP addr/hostname of the CoAP server.
        :param server_port: The UDP remote port of the CoAP server;
        :param local_port: The UDP local port, if omitted, a randomly available port is assigned
        (recommended)
        :param timeout: The time (in seconds) to wait for a response from the CoAP server
        before aborting: 1-120. (independent of the ACK_TIMEOUT used for retransmission)
        :param dtls: Whether or not to use DTLS encryption
        :param secure_profile_id: The SSL/TLS security profile configuration (ID) to use.
        :param rsp: Reference to a modem response instance

        :return bool: True on success, False on failure
        """

        if ctx_id < COAP_MIN_CTX_ID or COAP_MAX_CTX_ID < ctx_id:
            if rsp: rsp.result = WalterModemState.NO_SUCH_PROFILE
            return False

        if timeout < COAP_MIN_TIMEOUT or COAP_MAX_TIMEOUT < timeout:
            log('WARNING', f'coap_context_create: invalid timeout: {timeout}s ',
            f'(min: {COAP_MIN_TIMEOUT}, max: {COAP_MAX_TIMEOUT})')
            if rsp: rsp.result = WalterModemState.ERROR
            return False

        def complete_handler(result, rsp, complete_handler_arg):
            if result == WalterModemState.OK:
                self.coap_context_states[complete_handler_arg].connected = True

        return await self._run_cmd(
            rsp=rsp,
            at_cmd='AT+SQNCOAPCREATE={},{},{},{},{},{}{}'.format(
                ctx_id,
                modem_string(server_address) if server_address else '',
                server_port, local_port,
                modem_bool(dtls), timeout,
                f',,{secure_profile_id}' if secure_profile_id else ''
            ),
            at_rsp=(b'+SQNCOAPCONNECTED:', b'+SQNCOAP: ERROR'),
            complete_handler=complete_handler,
            complete_handler_arg=ctx_id
        )

    async def coap_context_close(self,
        ctx_id: int = 0,
        rsp: ModemRsp = None
    ) -> bool:
        """
        Close a CoAP context.

        :param ctx_id: Context profile identifier (0, 1, 2)
        :param rsp: Reference to a modem response instance

        :return bool: True on success, False on failure
        """

        if ctx_id < COAP_MIN_CTX_ID or COAP_MAX_CTX_ID < ctx_id:
            if rsp: rsp.result = WalterModemState.NO_SUCH_PROFILE
            return False

        return await self._run_cmd(
            rsp=rsp,
            at_cmd=f'AT+SQNCOAPCLOSE={ctx_id}',
            at_rsp=b'OK'
        )
    
    async def coap_send(self,
        ctx_id: int,
        m_type: WalterModemCoapType,
        method: WalterModemCoapMethod,
        length: int,
        rsp: ModemRsp = None
    ) -> bool:
        """
        Send data over CoAP, if no data is sent, length must be set to zero.

        :param ctx_id: Context profile identifier (0, 1, 2)
        :param m_type: CoAP message type
        :type m_type: WalterModemCoapType
        :param method: method (GET, POST, PUT, DELETE)
        :type method: WalterModemCoapMethod
        :param length: Length of the payload
        :param rsp: Reference to a modem response instance

        :return bool: True on success, False on failure
        """

        if ctx_id < COAP_MIN_CTX_ID or COAP_MAX_CTX_ID < ctx_id:
            if rsp: rsp.result = WalterModemState.NO_SUCH_PROFILE
            return False
        
        if length < COAP_MIN_BYTES_LENGTH or COAP_MAX_BYTES_LENGTH < length:
            if rsp: rsp.result = WalterModemState.ERROR
            return False
        
        return await self._run_cmd(
            rsp=rsp,
            at_cmd=f'AT+SQNCOAPSEND={ctx_id},{m_type},{method},{length}',
            at_rsp=b'OK',
            cmd_type=WalterModemCmdType.DATA_TX_WAIT
        )
    
    async def coap_receive_data(self,
        ctx_id: int,
        msg_id: int,
        max_bytes = 1024,
        rsp: ModemRsp = None
    ) -> bool:
        """
        Read the contents of a CoAP message after it's ring has been received.

        :param ctx_id: Context profile identifier (0, 1, 2)
        :param msg_id: CoAP message id
        :param max_bytes: How many bytes of the message to payload to read at once
        :param rsp: Reference to a modem response instance

        :return bool: True on success, False on failure
        """

        if ctx_id < COAP_MIN_CTX_ID or COAP_MAX_CTX_ID < ctx_id:
            if rsp: rsp.result = WalterModemState.NO_SUCH_PROFILE
            return False

        if max_bytes < COAP_MIN_BYTES_LENGTH or COAP_MAX_BYTES_LENGTH < max_bytes:
            if rsp: rsp.result = WalterModemState.ERROR
            return False
        
        return await self._run_cmd(
            rsp=rsp,
            at_cmd=f'AT+SQNCOAPRCV={ctx_id},{msg_id},{max_bytes}',
            at_rsp=b'OK'
        )
        

