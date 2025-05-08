import asyncio
import sys
import machine # type: ignore
import time
import json

from hdc1080 import HDC1080 # type: ignore
from lps22hb import LPS22HB
from ltc4015 import LTC4015
from scd30 import SCD30

from walter_modem import Modem
from walter_modem.enums import (
    WalterModemNetworkRegState,
    WalterModemOpState,
    WalterModemTlsValidation,
    WalterModemTlsVersion,
    WalterModemCoapType,
    WalterModemCoapMethod,
    WalterModemPSMMode,
    WalterModemEDRXMODE
)
from walter_modem.structs import (
    ModemRsp,
)

import config

PDP_CTX_ID = 1
TLS_CTX_ID = 1
COAP_CTX_ID = 0

PRIVATE_KEY_ID = 10
CA_CERT_ID = 11
CLIENT_CERT_ID = 12

IOT_EXCHANGE_ADDR = '35.153.43.192'
IOT_EXCHANGE_PORT = 5684

SLEEP_TIME = 60

modem = Modem()
modem_rsp = ModemRsp()
wdt = machine.WDT(timeout=60000)

hdc1080: HDC1080
lps22hb: LPS22HB
ltc4015: LTC4015
scd30: SCD30

data = None

async def setup_pdp_ctx() -> bool:
    return await modem.create_PDP_context(
        context_id=PDP_CTX_ID,
        apn=config.APN
    )

async def setup_secure_profile() -> bool:
    return (
        await modem.tls_write_credential(
            is_private_key=True,
            slot_idx=PRIVATE_KEY_ID,
            credential=config.PRIVATE_KEY
        ) and
        await modem.tls_write_credential(
            is_private_key=False,
            slot_idx=CLIENT_CERT_ID,
            credential=config.CERT
        ) and
        await modem.tls_config_profile(
            profile_id=TLS_CTX_ID,
            tls_version=WalterModemTlsVersion.TLS_VERSION_12,
            tls_validation=WalterModemTlsValidation.NONE,
            client_certificate_id=CLIENT_CERT_ID,
            client_private_key=PRIVATE_KEY_ID
        )
    )

async def setup_modem_power_saving() -> bool:
    return (
        await modem.config_PSM(
            mode=WalterModemPSMMode.ENABLE_PSM,
            periodic_TAU_s=3600,
            active_time_s=5
        ) and
        await modem.config_EDRX(
            mode=WalterModemEDRXMODE.ENABLE_EDRX,
            req_edrx_val='0010',
            req_ptw='0001'
        )
    )

def walter_feels_data_readout():
    global data

    #scd30_co2 = None
    #while scd30_co2 is None:
    #    if scd30.get_status_ready() == 1:
    #        co2, _, _ = scd30.read_measurement()
    #        if co2 > 0:
    #            scd30_co2 = co2
    #            break
    #    else:
    #        time.sleep_ms(200)
    


    data = json.dumps([
        hdc1080.temperature(),
        hdc1080.humidity(),
        lps22hb.read_pressure(),
        scd30.get_co2(),
        ltc4015.get_input_voltage(),
        ltc4015.get_input_current(),
        ltc4015.get_system_voltage(),
        ltc4015.get_battery_voltage(),
        ltc4015.get_charge_current(),
        ltc4015.get_estimated_battery_percentage()
    ])

    print(data)

async def ltc4015_setup():
    ltc4015.initialize()
    ltc4015.suspend_charging()
    ltc4015.enable_force_telemetry()
    await asyncio.sleep_ms(100)
    ltc4015.disable_force_telemetry()
    ltc4015.start_charging()
    ltc4015.enable_mppt()

async def sensors_setup():
    global hdc1080
    global lps22hb
    global ltc4015
    global scd30

    # Output pins
    PWR_3V3_EN_PIN     = machine.Pin(0,  machine.Pin.OUT, value=0) # 0: enabled
    PWR_12V_EN_PIN     = machine.Pin(43, machine.Pin.OUT, value=0) # 0: disabled
    I2C_BUS_PWR_EN_PIN = machine.Pin(1,  machine.Pin.OUT, value=1) # 1: enabled
    CAN_EN_PIN         = machine.Pin(44, machine.Pin.OUT, value=1) # 1: disabled
    SDI12_TX_EN_PIN    = machine.Pin(10, machine.Pin.OUT, value=0) # 0: disabled
    SDI12_RX_EN_PIN    = machine.Pin(9,  machine.Pin.OUT, value=0) # 0: disabled
    RS232_TX_EN_PIN    = machine.Pin(17, machine.Pin.OUT, value=0) # 0: disabled
    RS232_RX_EN_PIN    = machine.Pin(16, machine.Pin.OUT, value=1) # 1: disabled
    RS485_TX_EN_PIN    = machine.Pin(18, machine.Pin.OUT, value=0) # 0: disabled
    RS485_RX_EN_PIN    = machine.Pin(8,  machine.Pin.OUT, value=1) # 1: disabled
    CO2_EN_PIN         = machine.Pin(13, machine.Pin.OUT, value=0, hold=True) # 0: enabled
    CO2_SCL_PIN        = machine.Pin(11)

    # Input pins
    I2C_SDA_PIN = machine.Pin(42)
    I2C_SCL_PIN = machine.Pin(2)
    SD_CMD_PIN  = machine.Pin(6,  machine.Pin.IN)
    SD_CLK_PIN  = machine.Pin(5,  machine.Pin.IN)
    SD_DAT0_PIN = machine.Pin(4,  machine.Pin.IN)
    GPIO_A_PIN  = machine.Pin(39, machine.Pin.IN)
    GPIO_B_PIN  = machine.Pin(38, machine.Pin.IN)
    SER_RX_PIN  = machine.Pin(41, machine.Pin.IN)
    SER_TX_PIN  = machine.Pin(40, machine.Pin.IN)
    CAN_RX_PIN  = machine.Pin(7,  machine.Pin.IN)
    CAN_TX_PIN  = machine.Pin(15, machine.Pin.IN)
    CO2_SDA_PIN = machine.Pin(12, machine.Pin.IN)

    # Initialize I2C
    await asyncio.sleep(1)
    i2c = machine.I2C(0, scl=I2C_SCL_PIN, sda=I2C_SDA_PIN)
    co2_i2c = machine.I2C(1, scl=CO2_SCL_PIN, sda=CO2_SDA_PIN, freq=40000)

    # Initialize ltc4015 (charging)
    ltc4015 = LTC4015(i2c, 3, 4)
    ltc4015.initialize()
    ltc4015.enable_coulomb_counter()

    # Initialize the sensors
    hdc1080 = HDC1080(i2c)
    hdc1080.config(mode=1)
    lps22hb = LPS22HB(i2c)
    lps22hb.begin()
    scd30 = SCD30(co2_i2c)
    scd30.begin()

    await ltc4015_setup()
    return True

async def await_connection():
    for _ in range(180):
        if modem.get_network_reg_state() in (
            WalterModemNetworkRegState.REGISTERED_HOME,
            WalterModemNetworkRegState.REGISTERED_ROAMING
        ):
            return
        await asyncio.sleep(1)
        wdt.feed()
    raise Exception('Connection Timed-out')

async def ensure_network_connection() -> bool:
    if not await modem.get_op_state(modem_rsp):
        return False
    
    if modem_rsp.op_state is not WalterModemOpState.FULL:
        print('Establishing network connection...')
        if not await modem.set_op_state(WalterModemOpState.FULL):
            return False

        await await_connection()
    return True

async def send_data():
    if not await ensure_network_connection():
        raise Exception('Unable to connect / verify network connection')
    
    if not modem.coap_context_states[COAP_CTX_ID].configured:
        if not await modem.coap_context_create(
            ctx_id=COAP_CTX_ID,
            server_address=IOT_EXCHANGE_ADDR,
            server_port=IOT_EXCHANGE_PORT,
            dtls=True,
            secure_profile_id=TLS_CTX_ID
        ):
            raise Exception('Failure during coap context creation')
    wdt.feed()

    if modem.coap_context_states[COAP_CTX_ID].connected:
        if not await modem.coap_send(
            ctx_id=COAP_CTX_ID,
            m_type=WalterModemCoapType.CON,
            method=WalterModemCoapMethod.POST,
            length=len(data),
            data=data
        ):
            raise Exception('Failure during sending of data over coap')
    
    if modem.coap_context_states[COAP_CTX_ID].connected:
        if not await modem.coap_context_close(COAP_CTX_ID):
            raise Exception('Failure during closing of coap context')

async def main():
    try:
        wdt.feed()
        await modem.begin()

        reset_cause = machine.reset_cause()
        if reset_cause not in (
            machine.DEEPSLEEP_RESET,
            machine.WDT_RESET,
            machine.HARD_RESET
        ):
            if not ( # Relying on short-circuiting
                await setup_pdp_ctx() and
                await setup_secure_profile() and
                await setup_modem_power_saving()
            ):
                raise Exception('Failure in setup of persistent configurations')
        wdt.feed()

        await sensors_setup()
        wdt.feed()

        walter_feels_data_readout()
        wdt.feed()

        await send_data()
        wdt.feed()

        await modem.sleep(sleep_time_ms=SLEEP_TIME * 1000)
        
    except Exception as err:
        print('Exception caught: ')
        sys.print_exception(err)
        print('=======\nHard resetting in 5sec...')
        time.sleep(5)
        machine.reset()

asyncio.run(main())