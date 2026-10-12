import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from lerobot_lite import SO101Follower, SO101FollowerConfig, SO101Leader, SO101LeaderConfig
from lerobot_lite.config import JOINTS, MOTOR_NAMES
from lerobot_lite.device import CalibrationError

from .helpers import FakeBus, calibration_data


class ArmTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)
        (self.path / "test.json").write_text(json.dumps(calibration_data()))

    def follower(self, calibrated=True, **kwargs):
        config = SO101FollowerConfig(
            port="/dev/never-opened",
            id="test",
            calibration_dir=self.path,
            use_degrees=False,
            max_relative_target=5,
            **kwargs,
        )
        device = SO101Follower(config)
        device.bus = FakeBus(calibrated)
        return device

    def test_follower_connect_configures_exact_pid_and_gripper_settings(self):
        device = self.follower()
        device.connect()
        calls = device.bus.calls
        self.assertEqual(calls[:3], [("connect",), ("disable_torque",), ("configure_motors",)])
        self.assertEqual(calls[-1], ("enable_torque",))
        for motor in MOTOR_NAMES:
            for register, value in [
                ("Operating_Mode", 0),
                ("P_Coefficient", 16),
                ("I_Coefficient", 0),
                ("D_Coefficient", 32),
            ]:
                self.assertIn(("register", register, motor, value), calls)
        for register, value in [
            ("Max_Torque_Limit", 500),
            ("Protection_Current", 250),
            ("Overload_Torque", 25),
        ]:
            self.assertIn(("register", register, "gripper", value), calls)

    def test_missing_calibration_refuses_before_open(self):
        device = self.follower()
        device.calibration = {}
        with self.assertRaises(CalibrationError):
            device.connect()
        self.assertEqual(device.bus.calls, [])

    def test_mismatch_never_configures_or_enables_torque(self):
        device = self.follower(calibrated=False)
        with self.assertRaises(CalibrationError):
            device.connect()
        self.assertEqual(device.bus.calls, [("connect",), ("close",)])
        self.assertFalse(device.is_connected)

    def test_connection_failure_closes_half_open_serial(self):
        device = self.follower()

        def failing_connect():
            device.bus.port_handler.is_open = True
            raise OSError("handshake failed")

        device.bus.connect = failing_connect
        with self.assertRaisesRegex(OSError, "handshake failed"):
            device.connect()
        self.assertFalse(device.bus.is_connected)

    def test_configuration_failure_attempts_torque_off_and_closes(self):
        device = self.follower()
        device.configure = Mock(side_effect=OSError("configuration failed"))
        with self.assertRaisesRegex(OSError, "configuration failed"):
            device.connect()
        self.assertIn(("disable_torque",), device.bus.calls)
        self.assertFalse(device.bus.is_connected)

    def test_send_action_reads_current_pose_then_limits_and_writes(self):
        device = self.follower()
        device.bus.port_handler.is_open = True
        action = dict.fromkeys(JOINTS, 80.0)
        self.assertEqual(device.send_action(action), dict.fromkeys(JOINTS, 5.0))
        self.assertEqual(device.bus.calls[0], ("read", "Present_Position", {"num_retry": 2}))
        self.assertEqual(
            device.bus.calls[1], ("write", "Goal_Position", dict.fromkeys(MOTOR_NAMES, 5.0))
        )

    def test_invalid_actions_rejected_before_any_io(self):
        device = self.follower()
        device.bus.port_handler.is_open = True
        frames = [dict.fromkeys(JOINTS[:-1], 0.0), {**dict.fromkeys(JOINTS, 0.0), "camera": 0}]
        frames.extend(
            {**dict.fromkeys(JOINTS, 0.0), JOINTS[0]: value}
            for value in (True, "0", float("nan"), float("inf"))
        )
        for frame in frames:
            with self.subTest(frame=frame), self.assertRaises(ValueError):
                device.send_action(frame)
        self.assertEqual(device.bus.calls, [])

    def test_hold_uses_measured_positions(self):
        device = self.follower()
        device.bus.port_handler.is_open = True
        device.bus.positions = dict.fromkeys(MOTOR_NAMES, 12.0)
        device.hold()
        self.assertEqual(
            device.bus.calls[-1], ("write", "Goal_Position", dict.fromkeys(MOTOR_NAMES, 12.0))
        )

    def test_hold_and_torque_off_disconnect_modes(self):
        for disable in (False, True):
            device = self.follower(disable_torque_on_disconnect=disable)
            device.bus.port_handler.is_open = True
            device.disconnect()
            self.assertIn(("disconnect", disable), device.bus.calls)
            self.assertFalse(device.is_connected)

    def test_disconnect_failure_still_closes_serial(self):
        device = self.follower()
        device.bus.port_handler.is_open = True
        device.bus.disconnect = Mock(side_effect=OSError("torque-off failed"))
        with self.assertRaises(OSError):
            device.disconnect()
        self.assertFalse(device.is_connected)

    def test_leader_configuration_keeps_torque_off(self):
        device = SO101Leader(
            SO101LeaderConfig(
                port="/dev/never-opened", id="test", calibration_dir=self.path, use_degrees=False
            )
        )
        device.bus = FakeBus()
        device.connect()
        self.assertIn(("disable_torque",), device.bus.calls)
        self.assertNotIn(("enable_torque",), device.bus.calls)
        self.assertEqual(device.get_action(), dict.fromkeys(JOINTS, 0.0))
