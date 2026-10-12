"""Validated public boundaries around unchanged LeRobot motion methods."""

from __future__ import annotations

import math

from ._vendor.so_follower import SOFollower as UpstreamFollower
from ._vendor.so_leader import SOLeader as UpstreamLeader
from ._vendor.utils.errors import DeviceAlreadyConnectedError
from .config import JOINTS
from .device import CalibrationError


def _connect(device: UpstreamLeader | UpstreamFollower, calibrate: bool) -> None:
    if device.is_connected:
        raise DeviceAlreadyConnectedError("Already connected")
    if not device.calibration and not calibrate:
        raise CalibrationError("No saved calibration; run lerobot-lite calibrate first")
    configuring = False
    try:
        device.bus.connect()
        if not device.is_calibrated:
            if not calibrate:
                raise CalibrationError("Motor calibration mismatch; calibrate locally first")
            device.calibrate()
        configuring = True
        device.configure()
    except BaseException as exc:
        # A read-only mismatch must not enable torque or configure an uncalibrated arm.
        if device.bus.is_connected:
            if configuring or calibrate:
                try:
                    device.bus.disable_torque()
                except Exception as cleanup_error:
                    exc.add_note(f"Torque-off cleanup failed: {cleanup_error}")
            try:
                device.bus.port_handler.closePort()
            except Exception as cleanup_error:
                exc.add_note(f"Serial close failed: {cleanup_error}")
        raise


def validate_action(action: object) -> dict[str, float]:
    if not isinstance(action, dict) or set(action) != set(JOINTS):
        raise ValueError("An action must contain exactly the six joint.pos keys")
    result = {}
    for name in JOINTS:
        value = action[name]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(f"{name} must be a finite number")
        value = float(value)
        if not math.isfinite(value):
            raise ValueError(f"{name} must be a finite number")
        result[name] = value
    return result


class SOLeader(UpstreamLeader):
    def connect(self, calibrate: bool = False) -> None:
        """Require saved matching calibration unless explicitly asked to calibrate."""
        _connect(self, calibrate)

    def disconnect(self) -> None:
        try:
            super().disconnect()
        finally:
            if self.bus.is_connected:
                self.bus.port_handler.closePort()


class SOFollower(UpstreamFollower):
    def connect(self, calibrate: bool = False) -> None:
        _connect(self, calibrate)

    def send_action(self, action: dict[str, float]) -> dict[str, float]:
        # Validate the whole frame before any reads/writes; no partial application.
        return super().send_action(validate_action(action))

    def hold(self) -> None:
        """Best-effort hold at the measured pose, not an emergency-stop guarantee."""
        observation = self.get_observation()
        self.send_action({name: observation[name] for name in JOINTS})

    def disconnect(self) -> None:
        try:
            super().disconnect()
        finally:
            if self.bus.is_connected:
                self.bus.port_handler.closePort()


SO100Leader = SO101Leader = SOLeader
SO100Follower = SO101Follower = SOFollower
