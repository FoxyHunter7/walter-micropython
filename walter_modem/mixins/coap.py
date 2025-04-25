from micropython import const # type: ignore

from ..core import ModemCore
from ..enums import (
    WalterModemState
)
from ..structs import (
    ModemRsp,
    ModemCoapContextState
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
