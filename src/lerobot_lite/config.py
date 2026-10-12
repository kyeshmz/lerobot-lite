"""Small dataclasses instead of LeRobot's camera/config/plugin dependency graph."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

MOTOR_NAMES = ("shoulder_pan", "shoulder_lift", "elbow_flex", "wrist_flex", "wrist_roll", "gripper")
JOINTS = tuple(f"{name}.pos" for name in MOTOR_NAMES)


def positive_number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite positive number")
    result = float(value)
    if not math.isfinite(result) or result <= 0:
        raise ValueError(f"{name} must be a finite positive number")
    return result


@dataclass(kw_only=True)
class SOLeaderConfig:
    port: str
    id: str
    calibration_dir: Path | str | None = None
    use_degrees: bool = True
    num_read_retries: int = 2

    def __post_init__(self) -> None:
        if not isinstance(self.port, str) or not self.port:
            raise ValueError("port must be a nonempty serial-port name")
        if not isinstance(self.id, str) or not re.fullmatch(
            r"[A-Za-z0-9_-][A-Za-z0-9_.-]*", self.id
        ):
            raise ValueError("id must be a nonempty filename-safe calibration identifier")
        if not isinstance(self.use_degrees, bool):
            raise ValueError("use_degrees must be a bool")
        if type(self.num_read_retries) is not int or self.num_read_retries < 0:
            raise ValueError("num_read_retries must be a nonnegative integer")


@dataclass(kw_only=True)
class SOFollowerConfig(SOLeaderConfig):
    # Match LeRobot's Python API defaults. The teleop CLI explicitly overrides these.
    disable_torque_on_disconnect: bool = True
    max_relative_target: float | dict[str, float] | None = None
    position_p_coefficient: int = 16
    position_i_coefficient: int = 0
    position_d_coefficient: int = 32

    def __post_init__(self) -> None:
        super().__post_init__()
        if not isinstance(self.disable_torque_on_disconnect, bool):
            raise ValueError("disable_torque_on_disconnect must be a bool")
        limit = self.max_relative_target
        if isinstance(limit, dict):
            if set(limit) != set(MOTOR_NAMES):
                raise ValueError(
                    "max_relative_target must contain all six motor names (without .pos)"
                )
            self.max_relative_target = {
                key: positive_number(value, f"max_relative_target[{key}]")
                for key, value in limit.items()
            }
        elif limit is not None:
            self.max_relative_target = positive_number(limit, "max_relative_target")
        for name in ("position_p_coefficient", "position_i_coefficient", "position_d_coefficient"):
            value = getattr(self, name)
            if type(value) is not int or not 0 <= value <= 255:
                raise ValueError(f"{name} must be an integer in [0, 255]")


SO100LeaderConfig = SO101LeaderConfig = SOLeaderConfig
SO100FollowerConfig = SO101FollowerConfig = SOFollowerConfig
