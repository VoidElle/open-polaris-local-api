"""Tests for models.py — parse helpers, PolarisZone, PolarisDevice."""
import unittest

from models import (
    PolarisDevice,
    PolarisZone,
    _decode_error_bitmask,
    _parse_bool,
    _parse_int,
    _parse_temp,
    _CU_ERROR_MESSAGES,
    _ZONE_ERROR_MESSAGES,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

class TestParseTemp(unittest.TestCase):

    def test_none_returns_none(self):
        self.assertIsNone(_parse_temp(None))

    def test_small_int_returned_as_float(self):
        self.assertAlmostEqual(_parse_temp(20), 20.0)

    def test_large_int_divided_by_ten(self):
        self.assertAlmostEqual(_parse_temp(195), 19.5)

    def test_large_int_negative(self):
        self.assertAlmostEqual(_parse_temp(-200), -20.0)

    def test_string_int(self):
        self.assertAlmostEqual(_parse_temp("195"), 19.5)

    def test_float_small(self):
        self.assertAlmostEqual(_parse_temp(22.5), 22.5)

    def test_float_large(self):
        self.assertAlmostEqual(_parse_temp(225.0), 22.5)

    def test_invalid_string_returns_none(self):
        self.assertIsNone(_parse_temp("nope"))

    def test_exactly_100_divided(self):
        self.assertAlmostEqual(_parse_temp(100), 10.0)


class TestParseBool(unittest.TestCase):

    def test_none_returns_default(self):
        self.assertFalse(_parse_bool(None))
        self.assertTrue(_parse_bool(None, default=True))

    def test_true_bool(self):
        self.assertTrue(_parse_bool(True))

    def test_false_bool(self):
        self.assertFalse(_parse_bool(False))

    def test_int_nonzero(self):
        self.assertTrue(_parse_bool(1))

    def test_int_zero(self):
        self.assertFalse(_parse_bool(0))

    def test_string_true(self):
        self.assertTrue(_parse_bool("true"))
        self.assertTrue(_parse_bool("1"))
        self.assertTrue(_parse_bool("True"))

    def test_string_false(self):
        self.assertFalse(_parse_bool("false"))
        self.assertFalse(_parse_bool("0"))
        self.assertFalse(_parse_bool("no"))


class TestParseInt(unittest.TestCase):

    def test_none_returns_default(self):
        self.assertEqual(_parse_int(None), 0)
        self.assertEqual(_parse_int(None, default=5), 5)

    def test_int(self):
        self.assertEqual(_parse_int(42), 42)

    def test_float_truncated(self):
        self.assertEqual(_parse_int(3.9), 3)

    def test_string(self):
        self.assertEqual(_parse_int("7"), 7)

    def test_invalid_string(self):
        self.assertEqual(_parse_int("bad"), 0)

    def test_bool_true(self):
        self.assertEqual(_parse_int(True), 1)

    def test_bool_false(self):
        self.assertEqual(_parse_int(False), 0)


class TestDecodeErrorBitmask(unittest.TestCase):

    def test_zero_mask_no_errors(self):
        self.assertEqual(_decode_error_bitmask(0, _CU_ERROR_MESSAGES), [])

    def test_bit0_cu(self):
        result = _decode_error_bitmask(1, _CU_ERROR_MESSAGES)
        self.assertIn("E0 - No Master", result)

    def test_bit4_cu(self):
        result = _decode_error_bitmask(0b00010000, _CU_ERROR_MESSAGES)
        self.assertIn("PIN error", result)

    def test_empty_bit_skipped(self):
        # Bit 1 is empty string in _CU_ERROR_MESSAGES — should be skipped
        result = _decode_error_bitmask(0b00000010, _CU_ERROR_MESSAGES)
        self.assertEqual(result, [])

    def test_zone_bit0(self):
        result = _decode_error_bitmask(1, _ZONE_ERROR_MESSAGES)
        self.assertIn("E0 - No communication", result)

    def test_multiple_bits(self):
        # bits 0 and 1 → index 0 "E0 - No communication", index 1 "E2 - Chrono-Actuator association"
        result = _decode_error_bitmask(0b00000011, _ZONE_ERROR_MESSAGES)
        self.assertIn("E0 - No communication", result)
        self.assertIn("E2 - Chrono-Actuator association", result)


# ─── PolarisZone ──────────────────────────────────────────────────────────────

_ZONE_RIDOTTO = {
    "id_zona": 1,
    "n": "Living",
    "co": 210,    # 21.0°C current
    "ts": 220,    # 22.0°C set
    "off": 0,
    "cl": 1,
    "fan": 2,
    "fan_set": 2,
    "shu": 3,
    "shu_set": 3,
    "EV": 1,
    "man_crono": 0,
    "is_crono": 0,
    "m_nr": 1,
    "u": 500,
    "us": 600,
    "err": 0,
}

_ZONE_FULL = {
    "id_zona": 2,
    "name": "Bedroom",
    "t": 19.5,
    "t_set": 20.0,
    "is_off": 1,
    "is_cool": 0,
    "fan": 1,
    "fan_set": 1,
    "Serranda": 2,
    "shu_set": 2,
    "EV": 0,
    "man_crono": 1,
    "is_crono": 1,
    "master_nr": 0,
    "u": 45.0,
    "u_set": 50.0,
    "err": 3,
}

_ZONE_PASCAL = {
    "ZoneId": 3,
    "Name": "Kitchen",
    "Temp": 230,
    "SetTemp": 215,
    "IsOFF": 0,
    "isCooling": 1,
    "Fancoil": 3,
    "FancoilSet": 3,
    "Serranda": 0,
    "SerrandaSet": 0,
    "ev": 0,
    "ManCrono": 0,
    "IsCronoMode": 0,
    "isMaster": True,
    "Umd": 55.0,
    "SetUmd": 60.0,
    "Errors": 4,
}


class TestPolarisZone(unittest.TestCase):

    def test_ridotto_basic(self):
        z = PolarisZone.from_local(_ZONE_RIDOTTO)
        self.assertEqual(z.zone_id, 1)
        self.assertEqual(z.name, "Living")
        self.assertAlmostEqual(z.current_temp, 21.0)
        self.assertAlmostEqual(z.set_temp, 22.0)
        self.assertFalse(z.is_off)
        self.assertTrue(z.is_cooling)
        self.assertEqual(z.fancoil, 2)
        self.assertEqual(z.serranda, 3)
        self.assertEqual(z.ev, 1)

    def test_ridotto_is_master(self):
        z = PolarisZone.from_local(_ZONE_RIDOTTO)
        self.assertTrue(z.is_master)

    def test_full_format(self):
        z = PolarisZone.from_local(_ZONE_FULL)
        self.assertEqual(z.zone_id, 2)
        self.assertEqual(z.name, "Bedroom")
        self.assertAlmostEqual(z.current_temp, 19.5)
        self.assertAlmostEqual(z.set_temp, 20.0)
        self.assertTrue(z.is_off)
        self.assertFalse(z.is_cooling)
        self.assertTrue(z.is_crono_mode)
        self.assertTrue(z.man_crono)

    def test_full_errors(self):
        z = PolarisZone.from_local(_ZONE_FULL)
        self.assertEqual(z.num_error, 3)
        self.assertTrue(z.has_error)
        errors = z.active_errors
        self.assertIn("E0 - No communication", errors)
        self.assertIn("E2 - Chrono-Actuator association", errors)

    def test_pascal_format(self):
        z = PolarisZone.from_local(_ZONE_PASCAL)
        self.assertEqual(z.zone_id, 3)
        self.assertEqual(z.name, "Kitchen")
        self.assertAlmostEqual(z.current_temp, 23.0)
        self.assertAlmostEqual(z.set_temp, 21.5)
        self.assertFalse(z.is_off)
        self.assertTrue(z.is_cooling)
        self.assertTrue(z.is_master)

    def test_pascal_errors(self):
        z = PolarisZone.from_local(_ZONE_PASCAL)
        self.assertEqual(z.num_error, 4)
        self.assertTrue(z.has_error)

    def test_is_on_property(self):
        z = PolarisZone.from_local(_ZONE_RIDOTTO)
        self.assertTrue(z.is_on)
        z2 = PolarisZone.from_local(_ZONE_FULL)
        self.assertFalse(z2.is_on)

    def test_from_api_delegates(self):
        z1 = PolarisZone.from_local(_ZONE_RIDOTTO)
        z2 = PolarisZone.from_api(_ZONE_RIDOTTO)
        self.assertEqual(z1.zone_id, z2.zone_id)
        self.assertEqual(z1.name, z2.name)

    def test_defaults_empty_dict(self):
        z = PolarisZone.from_local({})
        self.assertEqual(z.zone_id, 0)
        self.assertEqual(z.name, "Unknown")
        self.assertIsNone(z.current_temp)
        self.assertIsNone(z.set_temp)
        self.assertFalse(z.has_error)

    def test_raw_data_preserved(self):
        z = PolarisZone.from_local(_ZONE_RIDOTTO)
        self.assertEqual(z.raw_data["id_zona"], 1)


# ─── PolarisDevice ────────────────────────────────────────────────────────────

_DEVICE_RIDOTTO = {
    "off": 0,
    "cl": 1,
    "cl_m": 1,
    "tc": 220,
    "fi": 3,
    "fe": 2,
    "ir": 1,
    "err_cu": 0,
    "serial": "ABC123",
    "name": "MyPolaris",
    "fw_ver": "1.2.3",
    "ip": "192.168.1.50",
    "zone": [],
}

_DEVICE_FULL = {
    "is_off": 1,
    "is_cool": 0,
    "cool_mod": 0,
    "t_can": 200,
    "f_inv": 4,
    "f_est": 5,
    "ir_present": 0,
    "err_cu": 32,
    "serial": "XYZ999",
    "name": "Office",
    "fw_ver": "2.0.0",
    "ip": "10.0.0.1",
}

_DEVICE_PASCAL = {
    "IsOFF": 0,
    "IsCooling": 1,
    "OperatingModeCooling": 2,
    "TempCan": 250,
    "FInv": 1,
    "FEst": 1,
    "IrPresent": 1,
    "NumErrors": 0,
    "Serial": "PAS001",
    "Name": "PascalUnit",
    "FWVer": "3.0.0",
    "IP": "172.16.0.5",
}


class TestPolarisDevice(unittest.TestCase):

    def test_ridotto_basic(self):
        d = PolarisDevice.from_local(_DEVICE_RIDOTTO)
        self.assertFalse(d.is_off)
        self.assertTrue(d.is_cooling)
        self.assertEqual(d.operating_mode, 1)
        self.assertEqual(d.t_can, 22)  # 220 // 10
        self.assertEqual(d.f_inv, 3)
        self.assertEqual(d.f_est, 2)
        self.assertEqual(d.ir_present, 1)
        self.assertEqual(d.serial, "ABC123")
        self.assertEqual(d.name, "MyPolaris")
        self.assertEqual(d.fw_ver, "1.2.3")
        self.assertEqual(d.ip, "192.168.1.50")

    def test_ridotto_is_on(self):
        d = PolarisDevice.from_local(_DEVICE_RIDOTTO)
        self.assertTrue(d.is_on)

    def test_full_format(self):
        d = PolarisDevice.from_local(_DEVICE_FULL)
        self.assertTrue(d.is_off)
        self.assertFalse(d.is_cooling)
        self.assertEqual(d.operating_mode, 0)
        self.assertEqual(d.t_can, 20)
        self.assertEqual(d.serial, "XYZ999")
        self.assertEqual(d.name, "Office")

    def test_full_errors(self):
        d = PolarisDevice.from_local(_DEVICE_FULL)
        self.assertEqual(d.num_errors, 32)
        self.assertTrue(d.has_error)
        errors = d.active_errors
        self.assertIn("E6 - Server Error", errors)

    def test_pascal_format(self):
        d = PolarisDevice.from_local(_DEVICE_PASCAL)
        self.assertFalse(d.is_off)
        self.assertTrue(d.is_cooling)
        self.assertEqual(d.operating_mode, 2)
        self.assertEqual(d.t_can, 25)
        self.assertEqual(d.serial, "PAS001")
        self.assertEqual(d.ip, "172.16.0.5")

    def test_cooling_mode_name_heating(self):
        d = PolarisDevice.from_local(_DEVICE_FULL)
        self.assertEqual(d.cooling_mode_name, "Heating")

    def test_cooling_mode_name_cooling(self):
        d = PolarisDevice.from_local(_DEVICE_RIDOTTO)
        self.assertEqual(d.cooling_mode_name, "Cooling")

    def test_cooling_mode_name_dehumidification(self):
        d = PolarisDevice.from_local(_DEVICE_PASCAL)
        self.assertEqual(d.cooling_mode_name, "Dehumidification")

    def test_cooling_mode_name_ventilation(self):
        data = dict(_DEVICE_RIDOTTO)
        data["cl_m"] = 3
        d = PolarisDevice.from_local(data)
        self.assertEqual(d.cooling_mode_name, "Ventilation")

    def test_cooling_mode_unknown_when_heating(self):
        data = dict(_DEVICE_RIDOTTO)
        data["cl"] = 0  # not cooling → op_mode forced to 0 = Heating
        d = PolarisDevice.from_local(data)
        self.assertEqual(d.operating_mode, 0)

    def test_no_errors(self):
        d = PolarisDevice.from_local(_DEVICE_RIDOTTO)
        self.assertFalse(d.has_error)
        self.assertEqual(d.active_errors, [])

    def test_from_get_home_delegates(self):
        d1 = PolarisDevice.from_local(_DEVICE_RIDOTTO)
        d2 = PolarisDevice.from_get_home(_DEVICE_RIDOTTO)
        self.assertEqual(d1.serial, d2.serial)
        self.assertEqual(d1.name, d2.name)

    def test_defaults_empty_dict(self):
        d = PolarisDevice.from_local({})
        self.assertFalse(d.is_off)
        self.assertFalse(d.is_cooling)
        self.assertEqual(d.operating_mode, 0)
        self.assertEqual(d.t_can, 0)
        self.assertEqual(d.serial, "")
        self.assertEqual(d.name, "Unknown")
        self.assertFalse(d.has_error)


if __name__ == "__main__":
    unittest.main()
