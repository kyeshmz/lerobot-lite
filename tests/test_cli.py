import contextlib
import io
import json
import unittest
from unittest.mock import Mock

from lerobot_lite.cli import close_devices, main

from .helpers import FakeBus


class CLITests(unittest.TestCase):
    def test_simulation_does_not_open_serial(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["simulate", "--steps", "3"]), 0)
        data = json.loads(output.getvalue())
        self.assertFalse(data["serial_opened"])
        self.assertEqual(data["positions"]["gripper.pos"], 15.0)

    def test_physical_teleop_requires_startup_consent(self):
        arguments = [
            "teleoperate",
            "--leader-port",
            "/dev/not-real",
            "--leader-id",
            "leader",
            "--follower-port",
            "/dev/not-real2",
            "--follower-id",
            "follower",
        ]
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            main(arguments)
        self.assertEqual(raised.exception.code, 2)

    def test_cleanup_disconnects_both_devices_even_if_hold_fails(self):
        leader, follower = Mock(), Mock()
        leader.bus = follower.bus = FakeBus()
        leader.bus.port_handler.is_open = True
        follower.hold.side_effect = OSError("hold failed")
        with self.assertRaises(ExceptionGroup):
            close_devices(leader, follower, hold=True)
        leader.disconnect.assert_called_once()
        follower.disconnect.assert_called_once()

    def test_cleanup_does_not_hold_when_torque_off_requested(self):
        follower = Mock()
        follower.bus = FakeBus()
        follower.bus.port_handler.is_open = True
        close_devices(None, follower, hold=False)
        follower.hold.assert_not_called()
        follower.disconnect.assert_called_once()
