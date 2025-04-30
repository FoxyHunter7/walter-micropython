from minimal_unittest import (
    AsyncTestCase,
    WalterModemAsserts,
    NetworkConnectivity
)

from walter_modem import Modem
from walter_modem.structs import (
    ModemRsp,
    ModemCoapContextState
)
from walter_modem.enums import WalterModemState

# To avoid disconnecting & reconnecting from the network too frequently;
# A single modem library instance is re-used, keeping a network connection open
# from the moment RequireNetworkConnection was first inheriteed.
modem = Modem()

class TestCoapContextCreate(
    AsyncTestCase,
    WalterModemAsserts,
    NetworkConnectivity
):  
    async def async_setup(self):
        await modem.begin()
        await self.ensure_network_connection(modem_instance=modem)

    # Context ID range validation

    async def test_fails_below_min_ctx_id(self):
        self.assert_false(await modem.coap_context_create(ctx_id=-1))

    async def test_fails_above_max_ctx_id(self):
        self.assert_false(await modem.coap_context_create(ctx_id=3))

    async def test_rsp_result_no_such_profile_on_invalid_ctx_id(self):
        modem_rsp = ModemRsp()
        await modem.coap_context_create(ctx_id=7, rsp=modem_rsp)
        self.assert_equal(WalterModemState.NO_SUCH_PROFILE, modem_rsp.result)

    # Timeout range validation

    async def test_fails_below_min_timeout(self):
        self.assert_false(await modem.coap_context_create(timeout=0))

    async def test_fails_above_max_timeout(self):
        self.assert_false(await modem.coap_context_create(timeout=121))

    async def test_rsp_result_error_on_invalid_timeout(self):
        modem_rsp = ModemRsp()
        await modem.coap_context_create(timeout=142, rsp=modem_rsp)
        self.assert_equal(WalterModemState.ERROR, modem_rsp.result)

    # AT command format

    async def test_sends_expected_at_cmd(self):
        modem.debug_log = True
        await self.assert_sends_at_command(
            modem,
            'AT+SQNCOAPCREATE=0,"test",5683,5683,0,60',
            lambda: modem.coap_context_create(
                ctx_id=0,
                server_address='test',
                server_port=5683,
                local_port=5683,
                timeout=60,
                dtls=False
            )
        )

    # Method run

    async def test_fails_on_unreachable_server(self):
        self.assert_false(await modem.coap_context_create(
            ctx_id=0,
            server_address='totally_valid_address',
            server_port=5555
        ))

    async def test_succeeds_on_reachable_server(self):
        self.assert_true(await modem.coap_context_create(
            ctx_id=0,
            server_address='coap.me',
            server_port=5683
        ))

    async def test_succeeds_on_listen_mode(self):
        self.assert_true(await modem.coap_context_create(
            ctx_id=1,
            local_port=5683
        ))

    # Mirror state

    async def test_ctx_0_mirror_state_set(self):
        self.assert_is_instance(modem.coap_context_states[0], ModemCoapContextState)
    
    async def test_ctx_1_mirror_state_set(self):
        self.assert_is_instance(modem.coap_context_states[1], ModemCoapContextState)
    
    async def test_ctx_2_mirror_state_set(self):
        self.assert_is_instance(modem.coap_context_states[2], ModemCoapContextState)
    
    async def test_ctx_state_not_configured_after_failed_run(self):
        await modem.coap_context_create(
            ctx_id=2,
            server_address='totally_valid_address',
            server_port=5556
        )
        self.assert_false(modem.coap_context_states[2].configured)
    
    async def test_ctx_state_configured_after_successful_run(self):
        await modem.coap_context_create(
            ctx_id=2,
            server_address='coap.me',
            server_port=5683
        )
        self.assert_true(modem.coap_context_states[2].configured)
    
    async def test_ctx_state_configured_mirrors_connected(self):
        self.assert_is(
            modem.coap_context_states[0].configured,
            modem.coap_context_states[0].connected
        )

class TestCoapContextClose(
    AsyncTestCase,
    WalterModemAsserts,
    NetworkConnectivity
):
    def __init__(self):
        modem = modem
        super().__init__()

class TestCoapSend(
    AsyncTestCase,
    WalterModemAsserts,
    NetworkConnectivity
):
    def __init__(self):
        modem = modem
        super().__init__()

class TestCoapReceiveData(
    AsyncTestCase,
    WalterModemAsserts,
    NetworkConnectivity
):
    def __init__(self):
        modem = modem
        super().__init__()

testcases = [testcase() for testcase in (
    TestCoapContextCreate,
    #TestCoapContextClose,
    #TestCoapSend,
    #TestCoapReceiveData
)]

for testcase in testcases:
    testcase.run()