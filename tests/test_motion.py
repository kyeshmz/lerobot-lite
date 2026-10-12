import unittest
from unittest.mock import Mock

from lerobot_lite._vendor.motors import Motor, MotorCalibration, MotorNormMode
from lerobot_lite._vendor.motors.encoding_utils import decode_sign_magnitude, encode_sign_magnitude
from lerobot_lite._vendor.motors.feetech import FeetechMotorsBus
from lerobot_lite._vendor.safety import ensure_safe_goal_position


def bus(mode=MotorNormMode.RANGE_M100_100, inverted=0):
    device = FeetechMotorsBus(
        "/dev/never-opened",
        {"joint": Motor(1, "sts3215", mode)},
        {"joint": MotorCalibration(1, inverted, -100, 500, 3500)},
    )
    return device


class MotionTests(unittest.TestCase):
    def test_body_normalization_and_clamping(self):
        driver = bus()
        for raw, expected in [(0, -100), (500, -100), (2000, 0), (3500, 100), (4095, 100)]:
            with self.subTest(raw=raw):
                self.assertEqual(driver._normalize({1: raw}), {1: expected})

    def test_gripper_normalization(self):
        driver = bus(MotorNormMode.RANGE_0_100)
        for raw, expected in [(0, 0), (500, 0), (2000, 50), (3500, 100), (4095, 100)]:
            with self.subTest(raw=raw):
                self.assertEqual(driver._normalize({1: raw}), {1: expected})

    def test_drive_mode_inversion(self):
        self.assertEqual(bus(inverted=1)._normalize({1: 500}), {1: 100})
        self.assertEqual(bus(inverted=1)._unnormalize({1: -100}), {1: 3500})
        gripper = bus(MotorNormMode.RANGE_0_100, inverted=1)
        self.assertEqual(gripper._normalize({1: 500}), {1: 100})
        self.assertEqual(gripper._unnormalize({1: 25}), {1: 2750})

    def test_unnormalization_exact_integer_truncation(self):
        driver = bus()
        for normalized, expected in [
            (-200, 500),
            (-100, 500),
            (0, 2000),
            (12.345, 2185),
            (100, 3500),
            (200, 3500),
        ]:
            with self.subTest(normalized=normalized):
                self.assertEqual(driver._unnormalize({1: normalized}), {1: expected})

    def test_degrees_uses_4095_and_does_not_apply_drive_mode(self):
        for inverted in (0, 1):
            driver = bus(MotorNormMode.DEGREES, inverted)
            self.assertEqual(driver._normalize({1: 2000}), {1: 0})
            self.assertAlmostEqual(driver._normalize({1: 2500})[1], 500 * 360 / 4095)
            self.assertEqual(driver._unnormalize({1: 90}), {1: 3023})

    def test_normalized_round_trip_with_encoder_quantization(self):
        for mode in (MotorNormMode.RANGE_M100_100, MotorNormMode.RANGE_0_100):
            for inverted in (0, 1):
                driver = bus(mode, inverted)
                for raw in range(500, 3501, 7):
                    restored = driver._unnormalize(driver._normalize({1: raw}))[1]
                    self.assertLessEqual(abs(raw - restored), 1)

    def test_signed_register_encoding_and_limits(self):
        for sign_bit in (10, 11, 15):
            maximum = (1 << sign_bit) - 1
            for value in (-maximum, -123, 0, 123, maximum):
                with self.subTest(sign_bit=sign_bit, value=value):
                    encoded = encode_sign_magnitude(value, sign_bit)
                    self.assertEqual(decode_sign_magnitude(encoded, sign_bit), value)
            with self.assertRaises(ValueError):
                encode_sign_magnitude(maximum + 1, sign_bit)
        self.assertEqual(encode_sign_magnitude(-100, 11), 0x0864)

    def test_sync_write_goal_position_matches_raw_register_and_bytes(self):
        driver = bus()
        driver.port_handler.is_open = True  # Only mock state; no openPort call.
        driver._sync_write = Mock()
        driver.sync_write("Goal_Position", {"joint": 0.0})
        args, kwargs = driver._sync_write.call_args
        self.assertEqual(args, (42, 2, {1: 2000}))
        self.assertEqual(driver._serialize_data(2000, 2), [0xD0, 0x07])
        self.assertTrue(kwargs["raise_on_error"])

    def test_sync_read_decodes_and_normalizes_at_present_position_register(self):
        driver = bus()
        driver.port_handler.is_open = True
        driver._sync_read = Mock(return_value=({1: 3500}, 0))
        self.assertEqual(driver.sync_read("Present_Position", num_retry=2), {"joint": 100})
        args, kwargs = driver._sync_read.call_args
        self.assertEqual(args, (56, 2, [1]))
        self.assertEqual(kwargs["num_retry"], 2)

    def test_relative_target_scalar_and_per_joint(self):
        values = {"a": (80.0, 10.0), "b": (-80.0, -10.0), "c": (1.0, 0.0)}
        self.assertEqual(ensure_safe_goal_position(values, 5.0), {"a": 15, "b": -15, "c": 1})
        self.assertEqual(
            ensure_safe_goal_position(values, {"a": 2, "b": 3, "c": 4}), {"a": 12, "b": -13, "c": 1}
        )

    def test_relative_target_mismatched_keys_rejected(self):
        with self.assertRaises(ValueError):
            ensure_safe_goal_position({"a": (1, 0)}, {"b": 5})

    def test_invalid_zero_width_calibration_rejected(self):
        driver = bus()
        driver.calibration["joint"].range_max = 500
        with self.assertRaises(ValueError):
            driver._normalize({1: 500})
        with self.assertRaises(ValueError):
            driver._unnormalize({1: 0})

    def test_half_turn_homing_resets_ranges_and_writes_original_offset(self):
        driver = bus()
        driver.write = Mock()
        driver.sync_read = Mock(return_value={"joint": 2000})
        self.assertEqual(driver.set_half_turn_homings(), {"joint": -47})
        self.assertEqual(
            [call.args for call in driver.write.call_args_list],
            [
                ("Homing_Offset", "joint", 0),
                ("Min_Position_Limit", "joint", 0),
                ("Max_Position_Limit", "joint", 4095),
                ("Homing_Offset", "joint", -47),
            ],
        )
        self.assertEqual(driver.calibration, {})

    def test_read_calibration_uses_limits_and_signed_homing_register(self):
        driver = bus()
        values = {"Min_Position_Limit": 500, "Max_Position_Limit": 3500, "Homing_Offset": -100}
        driver.read = Mock(side_effect=lambda register, motor, **kwargs: values[register])
        self.assertEqual(driver.read_calibration(), driver.calibration)
        for call in driver.read.call_args_list:
            self.assertFalse(call.kwargs["normalize"])

    def test_write_calibration_registers_and_cache_flag(self):
        driver = bus()
        original = driver.calibration
        updated = {"joint": MotorCalibration(1, 0, 123, 700, 3200)}
        driver.write = Mock()
        driver.write_calibration(updated, cache=False)
        self.assertIs(driver.calibration, original)
        self.assertEqual(
            [call.args for call in driver.write.call_args_list],
            [
                ("Homing_Offset", "joint", 123),
                ("Min_Position_Limit", "joint", 700),
                ("Max_Position_Limit", "joint", 3200),
            ],
        )
        driver.write_calibration(updated)
        self.assertIs(driver.calibration, updated)

    def test_bus_configuration_keeps_acceleration_and_clears_phase_bit(self):
        driver = bus()
        driver.read = Mock(return_value=0x13)
        driver.write = Mock()
        driver.configure_motors()
        self.assertEqual(
            [call.args for call in driver.write.call_args_list],
            [
                ("Return_Delay_Time", "joint", 0),
                ("Maximum_Acceleration", "joint", 254),
                ("Acceleration", "joint", 254),
                ("Phase", "joint", 0x03),
            ],
        )

    def test_sdk_timeout_fix_keeps_original_packet_budget(self):
        driver = bus()
        driver.port_handler.getCurrentTime = Mock(return_value=1234)
        driver.port_handler.tx_time_per_byte = 0.01
        driver.port_handler.setPacketTimeout(20)
        self.assertEqual(driver.port_handler.packet_start_time, 1234)
        self.assertAlmostEqual(driver.port_handler.packet_timeout, 50.23)
