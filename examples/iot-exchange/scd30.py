from machine import I2C, Pin
import time

# SCD30 MicroPython driver adapted from SparkFun_SCD30_Arduino_Library
# https://github.com/sparkfun/SparkFun_SCD30_Arduino_Library
class SCD30:
    DEFAULT_I2C_ADDR = 0x61

    def __init__(self, i2c, auto_calibrate=False, meas_begin=True):
        self.i2c = i2c
        self.address = self.DEFAULT_I2C_ADDR
        self._use_stale_data = False
        self.co2 = 0.0
        self.temperature = 0.0
        self.humidity = 0.0
        self._co2_reported = True
        self._temp_reported = True
        self._hum_reported = True
        self.auto_calibrate = auto_calibrate
        self.meas_begin = meas_begin

    def _delay_ms(self, ms):
        try:
            time.sleep_ms(ms)
        except AttributeError:
            time.sleep(ms / 1000)

    def begin(self):
        """
        Initialize the sensor.
        Only starts measurements if none are running.
        Must wait at least one interval (default 2s) after first start.
        """
        if not self.is_connected():
            return False
        if self.meas_begin:
            if not self.data_available():
                if not self.begin_measuring():
                    return False
                self.set_measurement_interval(2)
                self.set_auto_self_calibration(self.auto_calibrate)
                self._delay_ms(2000)
        return True

    def is_connected(self):
        return self.get_firmware_version() is not None

    def get_firmware_version(self):
        return self._read_register(COMMAND_READ_FW_VER)

    def set_use_stale_data(self, enable):
        self._use_stale_data = enable

    def get_co2(self, timeout_ms=5000):
        """
        Returns CO2 in ppm, waiting until data is available or timeout.
        """
        if self._co2_reported:
            if not self._wait_for_data(timeout_ms) and not self._use_stale_data:
                return None
            if not self.read_measurement():
                return None
        self._co2_reported = True
        return int(self.co2)

    def get_humidity(self, timeout_ms=5000):
        """
        Returns humidity in %RH, waiting until data is available or timeout.
        """
        if self._hum_reported:
            if not self._wait_for_data(timeout_ms) and not self._use_stale_data:
                return None
            if not self.read_measurement():
                return None
        self._hum_reported = True
        return self.humidity

    def get_temperature(self, timeout_ms=5000):
        """
        Returns temperature in °C, waiting until data is available or timeout.
        """
        if self._temp_reported:
            if not self._wait_for_data(timeout_ms) and not self._use_stale_data:
                return None
            if not self.read_measurement():
                return None
        self._temp_reported = True
        return self.temperature

    def _wait_for_data(self, timeout_ms):
        """
        Polls data_available() until True or timeout (ms). Returns True if data ready.
        """
        start = time.ticks_ms()
        while True:
            ready = self.data_available()
            if ready:
                return True
            if time.ticks_diff(time.ticks_ms(), start) > timeout_ms:
                return False
            self._delay_ms(50)

    def set_auto_self_calibration(self, enable=True):
        return self._send_command(COMMAND_AUTOMATIC_SELF_CALIBRATION, 1 if enable else 0)

    def get_auto_self_calibration(self):
        val = self._read_register(COMMAND_AUTOMATIC_SELF_CALIBRATION)
        return bool(val) if val is not None else None

    def set_forced_recalibration(self, ppm):
        if ppm < 400 or ppm > 2000:
            return False
        return self._send_command(COMMAND_SET_FORCED_RECALIBRATION_FACTOR, ppm)

    def get_forced_recalibration(self):
        return self._read_register(COMMAND_SET_FORCED_RECALIBRATION_FACTOR)

    def get_temperature_offset(self):
        raw = self._read_register(COMMAND_SET_TEMPERATURE_OFFSET)
        if raw is None:
            return None
        if raw & 0x8000:
            raw -= 1 << 16
        return raw / 100.0

    def set_temperature_offset(self, offset):
        if offset < 0:
            return False
        val = int(offset * 100)
        return self._send_command(COMMAND_SET_TEMPERATURE_OFFSET, val)

    def get_altitude_compensation(self):
        return self._read_register(COMMAND_SET_ALTITUDE_COMPENSATION)

    def set_altitude_compensation(self, alt):
        return self._send_command(COMMAND_SET_ALTITUDE_COMPENSATION, alt)

    def set_ambient_pressure(self, mbar):
        if mbar < 700 or mbar > 1200:
            return False
        return self._send_command(COMMAND_SET_AMBIENT_PRESSURE, mbar)

    def reset(self):
        return self._send_command(COMMAND_RESET)

    def begin_measuring(self):
        return self._send_command(COMMAND_CONTINUOUS_MEASUREMENT)

    def stop_measurement(self):
        return self._send_command(COMMAND_STOP_MEAS)

    def set_measurement_interval(self, interval):
        return self._send_command(COMMAND_SET_MEASUREMENT_INTERVAL, interval)

    def get_measurement_interval(self):
        return self._read_register(COMMAND_SET_MEASUREMENT_INTERVAL)

    def data_available(self):
        val = self._read_register(COMMAND_GET_DATA_READY)
        return val == 1 if val is not None else False

    def read_measurement(self):
        try:
            self.i2c.writeto(self.address, bytes([COMMAND_READ_MEASUREMENT >> 8,
                                                   COMMAND_READ_MEASUREMENT & 0xFF]))
        except OSError:
            return False
        self._delay_ms(3)
        raw = self.i2c.readfrom(self.address, 18)
        if len(raw) != 18:
            return False
        vals = []
        for i in range(0, 18, 6):
            block = raw[i:i+6]
            if self._crc8(block[0:2]) != block[2] or self._crc8(block[3:5]) != block[5]:
                return False
            data_bytes = bytes([block[0], block[1], block[3], block[4]])
            import struct
            vals.append(struct.unpack('>f', data_bytes)[0])
        self.co2, self.temperature, self.humidity = vals
        self._co2_reported = False
        self._temp_reported = False
        self._hum_reported = False
        return True

    # === Low-level helpers ===
    def _send_command(self, cmd, arg=None):
        buf = bytearray([cmd >> 8, cmd & 0xFF])
        if arg is not None:
            data = bytearray([arg >> 8, arg & 0xFF])
            buf += data + bytearray([self._crc8(data)])
        try:
            self.i2c.writeto(self.address, buf)
        except OSError:
            return False
        self._delay_ms(2)
        return True

    def _read_register(self, reg):
        try:
            self.i2c.writeto(self.address, bytes([reg >> 8, reg & 0xFF]))
        except OSError:
            return None
        self._delay_ms(3)
        raw = self.i2c.readfrom(self.address, 3)
        if len(raw) != 3 or self._crc8(raw[0:2]) != raw[2]:
            return None
        return (raw[0] << 8) | raw[1]

    def _crc8(self, data):
        crc = 0xFF
        for b in data:
            crc ^= b
            for _ in range(8):
                if crc & 0x80:
                    crc = (crc << 1) ^ 0x31
                else:
                    crc <<= 1
                crc &= 0xFF
        return crc

COMMAND_CONTINUOUS_MEASUREMENT       = 0x0010
COMMAND_SET_MEASUREMENT_INTERVAL    = 0x4600
COMMAND_GET_DATA_READY              = 0x0202
COMMAND_READ_MEASUREMENT            = 0x0300
COMMAND_AUTOMATIC_SELF_CALIBRATION  = 0x5306
COMMAND_SET_FORCED_RECALIBRATION_FACTOR = 0x5204
COMMAND_SET_AMBIENT_PRESSURE        = 0x5204  # pressure uses same command as forced recalibration
COMMAND_SET_TEMPERATURE_OFFSET      = 0x5403
COMMAND_SET_ALTITUDE_COMPENSATION   = 0x5102
COMMAND_RESET                       = 0xD304
COMMAND_STOP_MEAS                   = 0x0104
COMMAND_READ_FW_VER                 = 0xD100

# Example usage:
# i2c = I2C(1, scl=Pin(22), sda=Pin(21))
# scd = SCD30(i2c, auto_calibrate=True)
# if scd.begin():
#     while True:
#         print('CO2:', scd.get_co2())
#         print('Temp:', scd.get_temperature())
#         print('RH:', scd.get_humidity())
#         time.sleep(2)
