"""Optional check against a real bridge checkout, without modifying it or using motors."""

import ast
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock, patch

from lerobot_lite.config import JOINTS
from lerobot_lite.device import CalibrationError

from .helpers import FakeBus, calibration_data


class Migration(ast.NodeTransformer):
    def visit_ImportFrom(self, node):
        if node.module in ("lerobot.teleoperators", "lerobot.robots"):
            node.module = node.module.replace("lerobot.", "lerobot_lite.", 1)
        return node

    def visit_FunctionDef(self, node):
        if node.name == "calibrate":
            first = node.body[0].value
            self_call = ast.unparse(first)
            if self_call != "self.device.connect(calibrate=False)":
                raise ValueError(f"Bridge calibration adapter changed: {self_call}")
            first.func.value = ast.Attribute(value=first.func.value, attr="bus", ctx=ast.Load())
            first.keywords = []
        return self.generic_visit(node)


@unittest.skipUnless(
    os.getenv("LEROBOT_WEBRTC_CHECKOUT"), "Set LEROBOT_WEBRTC_CHECKOUT for bridge check"
)
class BridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(os.environ["LEROBOT_WEBRTC_CHECKOUT"]) / "src"
        sys.path.insert(0, str(source))
        try:
            tree = ast.parse((source / "lerobot_webrtc/arms.py").read_text())
            tree = ast.fix_missing_locations(Migration().visit(tree))
            cls.module = ModuleType("lerobot_webrtc.lite_migration_check")
            cls.module.__package__ = "lerobot_webrtc"
            exec(compile(tree, "<in-memory migrated bridge>", "exec"), cls.module.__dict__)
        finally:
            sys.path.remove(str(source))

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.environment = patch.dict(os.environ, {"HF_LEROBOT_CALIBRATION": self.directory.name})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        for role, category in (("leader", "teleoperators"), ("follower", "robots")):
            path = Path(self.directory.name) / category / f"so_{role}" / "bridge.json"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(calibration_data()))

    def arm(self, role="follower", model="so101", arm_id="bridge"):
        arm = self.module.LeRobotArm(role, model, "/dev/never-opened", arm_id, 5.0, "hold")
        arm.device.bus = FakeBus()
        return arm

    def test_all_four_model_and_role_configurations(self):
        for role in ("leader", "follower"):
            for model in ("so100", "so101"):
                with self.subTest(role=role, model=model):
                    arm = self.arm(role, model)
                    self.assertFalse(arm.device.config.use_degrees)
                    arm.connect()
                    if role == "follower":
                        self.assertEqual(arm.device.config.max_relative_target, 5.0)
                        self.assertFalse(arm.device.config.disable_torque_on_disconnect)
                    arm.disconnect()

    def test_get_send_hold_and_disconnect(self):
        leader, follower = self.arm("leader"), self.arm("follower")
        leader.connect()
        follower.connect()
        action = leader.get_action()
        self.assertEqual(action, dict.fromkeys(JOINTS, 0.0))
        self.assertEqual(follower.send_action(action), action)
        follower.hold()
        leader.disconnect()
        follower.disconnect()
        self.assertFalse(follower.device.bus.is_connected)

    def test_missing_and_mismatched_calibration_remain_runtime_errors(self):
        missing = self.arm(arm_id="missing")
        with self.assertRaisesRegex(RuntimeError, "No saved calibration"):
            missing.connect()
        self.assertEqual(missing.device.bus.calls, [])
        mismatch = self.arm()
        mismatch.device.bus.is_calibrated = False
        with self.assertRaises(CalibrationError):
            mismatch.connect()
        self.assertFalse(mismatch.device.bus.is_connected)

    def test_explicit_calibration_opens_bus_without_runtime_gate(self):
        arm = self.arm(arm_id="uncalibrated")
        arm.device.calibrate = Mock()
        arm.calibrate()
        self.assertEqual(arm.device.bus.calls, [("connect",)])
        arm.device.calibrate.assert_called_once_with()
        arm.disconnect()
