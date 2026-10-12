import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lerobot_lite import SO101FollowerConfig, SO101Leader, SO101LeaderConfig
from lerobot_lite.device import CalibrationError, calibration_root, validate_calibration

from .helpers import calibration_data


class CalibrationTests(unittest.TestCase):
    def test_schema_matches_lerobot_json(self):
        calibration = validate_calibration(calibration_data())
        self.assertEqual(calibration["shoulder_pan"].homing_offset, -100)
        self.assertEqual(calibration["gripper"].id, 6)

    def test_malformed_calibration_rejected(self):
        for field, value in [
            ("id", 2),
            ("drive_mode", 2),
            ("homing_offset", 2048),
            ("range_min", 3500),
            ("range_max", 4096),
            ("id", True),
        ]:
            data = calibration_data()
            data["shoulder_pan"][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(CalibrationError):
                validate_calibration(data)
        with self.assertRaises(CalibrationError):
            validate_calibration({})

    def test_environment_precedence_matches_huggingface_cache(self):
        with patch.dict(os.environ, {"XDG_CACHE_HOME": "/cache"}, clear=True):
            self.assertEqual(calibration_root(), Path("/cache/huggingface/lerobot/calibration"))
            os.environ["HF_HOME"] = "/hf"
            self.assertEqual(calibration_root(), Path("/hf/lerobot/calibration"))
            os.environ["HF_LEROBOT_HOME"] = "/robot"
            self.assertEqual(calibration_root(), Path("/robot/calibration"))
            os.environ["HF_LEROBOT_CALIBRATION"] = "/calibration"
            self.assertEqual(calibration_root(), Path("/calibration"))

    def test_shared_so_leader_path_not_so101_leader(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch.dict(os.environ, {"HF_LEROBOT_CALIBRATION": directory}),
        ):
            device = SO101Leader(SO101LeaderConfig(port="/dev/never-opened", id="test"))
            self.assertEqual(
                device.calibration_fpath, Path(directory) / "teleoperators/so_leader/test.json"
            )
            self.assertFalse(device.calibration_fpath.parent.exists())

    def test_atomic_json_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            config = SO101LeaderConfig(
                port="/dev/never-opened", id="test", calibration_dir=directory
            )
            device = SO101Leader(config)
            device.calibration = validate_calibration(calibration_data())
            device._save_calibration()
            self.assertEqual(json.loads(device.calibration_fpath.read_text()), calibration_data())
            self.assertEqual(SO101Leader(config).calibration, device.calibration)
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])

    def test_invalid_new_calibration_does_not_overwrite_existing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.json"
            path.write_text(json.dumps(calibration_data()))
            before = path.read_text()
            device = SO101Leader(
                SO101LeaderConfig(port="/dev/never-opened", id="test", calibration_dir=directory)
            )
            device.calibration["shoulder_pan"].range_max = 500
            with self.assertRaises(CalibrationError):
                device._save_calibration()
            self.assertEqual(path.read_text(), before)

    def test_invalid_config_rejected(self):
        for identifier in ("", "../test", "/test", "a/b", "a\\b"):
            with self.subTest(identifier=identifier), self.assertRaises(ValueError):
                SO101LeaderConfig(port="/dev/never-opened", id=identifier)
        for limit in (0, -5, True, float("nan"), float("inf"), {"shoulder_pan": 5}):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                SO101FollowerConfig(port="/dev/never-opened", id="test", max_relative_target=limit)
