"""LeRobot-compatible calibration paths/JSON, implemented with the standard library."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path

from ._vendor.motors import MotorCalibration
from .config import MOTOR_NAMES, SOLeaderConfig

type RobotAction = dict[str, float]
type RobotObservation = dict[str, float]


class CalibrationError(ValueError):
    """Calibration is missing, malformed, or does not match the motor registers."""


def calibration_root() -> Path:
    cache = Path(os.getenv("XDG_CACHE_HOME", "~/.cache")).expanduser()
    hf_home = Path(os.getenv("HF_HOME", str(cache / "huggingface"))).expanduser()
    home = Path(os.getenv("HF_LEROBOT_HOME", str(hf_home / "lerobot"))).expanduser()
    return Path(os.getenv("HF_LEROBOT_CALIBRATION", str(home / "calibration"))).expanduser()


def validate_calibration(data: object) -> dict[str, MotorCalibration]:
    if not isinstance(data, dict) or set(data) != set(MOTOR_NAMES):
        raise CalibrationError("Calibration must contain exactly the six SO-100/SO-101 motors")
    result = {}
    fields = {"id", "drive_mode", "homing_offset", "range_min", "range_max"}
    for expected_id, name in enumerate(MOTOR_NAMES, 1):
        values = data[name]
        if not isinstance(values, dict) or set(values) != fields:
            raise CalibrationError(f"Invalid calibration fields for {name}")
        if any(type(value) is not int for value in values.values()):
            raise CalibrationError(f"Calibration values must be integers: {name}")
        if values["id"] != expected_id or values["drive_mode"] not in (0, 1):
            raise CalibrationError(f"Invalid motor id or drive_mode: {name}")
        if not -2047 <= values["homing_offset"] <= 2047:
            raise CalibrationError(f"Homing offset outside STS3215 range: {name}")
        if not 0 <= values["range_min"] < values["range_max"] <= 4095:
            raise CalibrationError(f"Invalid encoder range: {name}")
        result[name] = MotorCalibration(**values)
    return result


class Device:
    """The calibration portion of Robot/Teleoperator, without their ML imports."""

    name: str

    def __init__(self, config: SOLeaderConfig):
        self.id = config.id
        role = "robots" if self.name == "so_follower" else "teleoperators"
        self.calibration_dir = (
            Path(config.calibration_dir).expanduser()
            if config.calibration_dir is not None
            else calibration_root() / role / self.name
        )
        self.calibration_fpath = self.calibration_dir / f"{self.id}.json"
        self.calibration: dict[str, MotorCalibration] = {}
        if self.calibration_fpath.is_file():
            self._load_calibration()

    def __str__(self) -> str:
        return f"{self.id} {self.__class__.__name__}"

    def _load_calibration(self) -> None:
        try:
            self.calibration = validate_calibration(json.loads(self.calibration_fpath.read_text()))
        except (OSError, ValueError) as exc:
            raise CalibrationError(f"Cannot load {self.calibration_fpath}: {exc}") from exc

    def _save_calibration(self) -> None:
        data = {name: asdict(value) for name, value in self.calibration.items()}
        validate_calibration(data)
        self.calibration_dir.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", dir=self.calibration_dir, suffix=".tmp", delete=False
            ) as file:
                temporary = Path(file.name)
                json.dump(data, file, indent=4)
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, self.calibration_fpath)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
