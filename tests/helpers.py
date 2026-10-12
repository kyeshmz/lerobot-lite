from __future__ import annotations

from dataclasses import asdict
from types import SimpleNamespace

from lerobot_lite._vendor.motors import MotorCalibration
from lerobot_lite.config import MOTOR_NAMES


def calibration_data() -> dict:
    return {
        name: asdict(MotorCalibration(index, 0, -100, 500, 3500))
        for index, name in enumerate(MOTOR_NAMES, 1)
    }


class FakeBus:
    def __init__(self, calibrated=True):
        self.port_handler = SimpleNamespace(is_open=False, closePort=self.close)
        self.is_calibrated = calibrated
        self.motors = dict.fromkeys(MOTOR_NAMES)
        self.calls = []
        self.positions = dict.fromkeys(MOTOR_NAMES, 0.0)

    @property
    def is_connected(self):
        return self.port_handler.is_open

    def close(self):
        self.calls.append(("close",))
        self.port_handler.is_open = False

    def connect(self):
        self.calls.append(("connect",))
        self.port_handler.is_open = True

    def disconnect(self, disable_torque=True):
        self.calls.append(("disconnect", disable_torque))
        self.close()

    def disable_torque(self):
        self.calls.append(("disable_torque",))

    def sync_read(self, register, **kwargs):
        self.calls.append(("read", register, kwargs))
        return self.positions.copy()

    def sync_write(self, register, values):
        self.calls.append(("write", register, values.copy()))

    def write(self, register, motor, value):
        self.calls.append(("register", register, motor, value))

    def configure_motors(self):
        self.calls.append(("configure_motors",))

    def torque_disabled(self):
        bus = self

        class Context:
            def __enter__(self):
                bus.calls.append(("disable_torque",))

            def __exit__(self, *args):
                bus.calls.append(("enable_torque",))

        return Context()
