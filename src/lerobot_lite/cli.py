"""Local teleoperation and explicit calibration; no network or training runtime."""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

from . import SO101Follower, SO101FollowerConfig, SO101Leader, SO101LeaderConfig
from ._vendor.safety import ensure_safe_goal_position
from .config import JOINTS, positive_number
from .device import validate_calibration


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)
    simulate = commands.add_parser(
        "simulate", help="Exercise the actual limiter without serial I/O"
    )
    simulate.add_argument("--steps", type=int, default=10)
    inspect = commands.add_parser(
        "inspect-calibration", help="Validate a JSON file without opening motors"
    )
    inspect.add_argument("path", type=Path)
    calibrate = commands.add_parser(
        "calibrate", help="Interactive physical calibration; support the arm"
    )
    calibrate.add_argument("--role", choices=("leader", "follower"), required=True)
    calibrate.add_argument("--port", required=True)
    calibrate.add_argument("--id", required=True)
    calibrate.add_argument("--calibration-dir", type=Path)
    teleop = commands.add_parser("teleoperate", help="Two local serial arms (requires --arm)")
    for role in ("leader", "follower"):
        teleop.add_argument(f"--{role}-port", required=True)
        teleop.add_argument(f"--{role}-id", required=True)
        teleop.add_argument(f"--{role}-calibration-dir", type=Path)
    teleop.add_argument(
        "--arm", action="store_true", help="Consent to enable physical follower motion"
    )
    teleop.add_argument("--fps", type=float, default=30)
    teleop.add_argument("--duration", type=float)
    teleop.add_argument("--max-relative-target", type=float, default=5)
    teleop.add_argument("--on-exit", choices=("hold", "torque-off"), default="hold")
    return result


def close_devices(leader: SO101Leader | None, follower: SO101Follower | None, hold: bool) -> None:
    errors = []
    if follower is not None and follower.bus.is_connected:
        if hold:
            try:
                follower.hold()
            except Exception as exc:
                errors.append(exc)
        try:
            follower.disconnect()
        except Exception as exc:
            errors.append(exc)
    if leader is not None and leader.bus.is_connected:
        try:
            leader.disconnect()
        except Exception as exc:
            errors.append(exc)
    if errors:
        raise ExceptionGroup("Arm cleanup failed; use the physical stop if necessary", errors)


def teleoperate(args: argparse.Namespace) -> None:
    fps = positive_number(args.fps, "fps")
    delta = positive_number(args.max_relative_target, "max_relative_target")
    if args.duration is not None:
        positive_number(args.duration, "duration")
    leader = follower = None
    primary = None
    try:
        leader = SO101Leader(
            SO101LeaderConfig(
                port=args.leader_port,
                id=args.leader_id,
                calibration_dir=args.leader_calibration_dir,
                use_degrees=False,
            )
        )
        follower = SO101Follower(
            SO101FollowerConfig(
                port=args.follower_port,
                id=args.follower_id,
                calibration_dir=args.follower_calibration_dir,
                use_degrees=False,
                max_relative_target=delta,
                disable_torque_on_disconnect=args.on_exit == "torque-off",
            )
        )
        follower.connect(calibrate=False)
        leader.connect(calibrate=False)
        start = next_frame = time.monotonic()
        while args.duration is None or time.monotonic() - start < args.duration:
            follower.send_action(leader.get_action())
            next_frame = max(next_frame + 1 / fps, time.monotonic())
            time.sleep(max(0, next_frame - time.monotonic()))
    except BaseException as exc:
        primary = exc
        raise
    finally:
        try:
            close_devices(leader, follower, args.on_exit == "hold")
        except Exception as exc:
            if primary is None:
                raise
            raise BaseExceptionGroup("Control and cleanup both failed", [primary, exc]) from None


def calibrate_arm(args: argparse.Namespace) -> None:
    options = dict(
        port=args.port, id=args.id, calibration_dir=args.calibration_dir, use_degrees=False
    )
    device = (
        SO101Leader(SO101LeaderConfig(**options))
        if args.role == "leader"
        else SO101Follower(SO101FollowerConfig(**options))
    )
    print(
        "Support the arm: calibration disables torque. Keep a physical power cutoff within reach."
    )
    primary = None
    try:
        # Unlike connect(), this does not enable follower torque before calibration.
        device.bus.connect()
        device.calibrate()
    except BaseException as exc:
        primary = exc
        raise
    finally:
        if device.bus.is_connected:
            try:
                device.bus.disconnect(disable_torque=True)
            except Exception as exc:
                if primary is None:
                    raise
                raise BaseExceptionGroup(
                    "Calibration and cleanup both failed", [primary, exc]
                ) from None
            finally:
                if device.bus.is_connected:
                    device.bus.port_handler.closePort()


def main(argv: list[str] | None = None) -> int:
    command_parser = parser()
    args = command_parser.parse_args(argv)
    if args.command == "teleoperate" and not args.arm:
        command_parser.error("Physical motion requires --arm; use simulate for a no-hardware check")
    try:
        if args.command == "simulate":
            if not 1 <= args.steps <= 100_000:
                raise ValueError("steps must be between 1 and 100000")
            positions = dict.fromkeys(JOINTS, 0.0)
            for step in range(args.steps):
                goals = dict.fromkeys(JOINTS, 0.0)
                goals["shoulder_pan.pos"] = 15 * math.sin(step / 10)
                goals["gripper.pos"] = 25.0
                positions = ensure_safe_goal_position(
                    {name: (goals[name], positions[name]) for name in JOINTS}, 5.0
                )
            print(json.dumps({"steps": args.steps, "positions": positions, "serial_opened": False}))
        elif args.command == "inspect-calibration":
            calibration = validate_calibration(json.loads(args.path.read_text()))
            print(f"Valid SO-100/SO-101 calibration: {len(calibration)} motors")
        elif args.command == "calibrate":
            calibrate_arm(args)
        else:
            teleoperate(args)
    except KeyboardInterrupt:
        return 130
    except (Exception, BaseExceptionGroup) as exc:
        print(f"lerobot-lite: {exc}", file=sys.stderr)
        return 1
    return 0
