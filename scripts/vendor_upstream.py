#!/usr/bin/env python3
"""Regenerate a reviewed, pinned source snapshot. Never runs during installation."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import subprocess
from pathlib import Path

REVISION = "7e241bd630a3719a56157a497ce5d08f244784f1"
ROOT = Path(__file__).resolve().parents[1]
PREFIX = "src/lerobot/"
FILES = {
    "motors/motors_bus.py": "motors/motors_bus.py",
    "motors/encoding_utils.py": "motors/encoding_utils.py",
    "motors/feetech/feetech.py": "motors/feetech/feetech.py",
    "motors/feetech/tables.py": "motors/feetech/tables.py",
    "utils/decorators.py": "utils/decorators.py",
    "utils/errors.py": "utils/errors.py",
    "robots/so_follower/so_follower.py": "so_follower.py",
    "teleoperators/so_leader/so_leader.py": "so_leader.py",
}


def replace_once(source: str, old: str, new: str) -> str:
    if source.count(old) != 1:
        raise ValueError(f"Upstream transformation no longer matches: {old!r}")
    return source.replace(old, new, 1)


def function_source(source: str, name: str) -> str:
    node = next(
        n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == name
    )
    return "\n".join(source.splitlines()[node.lineno - 1 : node.end_lineno]) + "\n"


def fingerprints(source: str) -> dict[str, str]:
    result = {}
    for node in ast.parse(source).body:
        nodes = [(node.name, node)] if isinstance(node, ast.FunctionDef) else []
        if isinstance(node, ast.ClassDef):
            nodes = [
                (f"{node.name}.{n.name}", n) for n in node.body if isinstance(n, ast.FunctionDef)
            ]
        for name, function in nodes:
            result[name] = hashlib.sha256(ast.dump(function).encode()).hexdigest()
    return result


def translate(path: str, source: str) -> str:
    if path == "motors/motors_bus.py":
        start = source.index("from lerobot.utils.import_utils")
        end = source.index("type NameOrID")
        source = (
            source[:start]
            + (
                "import serial\n\n"
                "from lerobot_lite._vendor.utils.decorators import "
                "check_if_already_connected, check_if_not_connected\n"
                "from lerobot_lite._vendor.utils.terminal import enter_pressed, move_cursor_up\n\n"
            )
            + source[end:]
        )
        source = replace_once(
            source, "from typing import TYPE_CHECKING, Protocol", "from typing import Protocol"
        )
        source = replace_once(
            source,
            '        require_package("pyserial", extra="pyserial-dep", import_name="serial")\n',
            "",
        )
        source = replace_once(
            source, '        require_package("deepdiff", extra="deepdiff-dep")\n', ""
        )
        source = replace_once(
            source,
            "DeepDiff(first_table, get_ctrl_table(self.model_ctrl_table, model))",
            "first_table != get_ctrl_table(self.model_ctrl_table, model)",
        )
    elif path == "motors/feetech/feetech.py":
        source = replace_once(source, "from typing import TYPE_CHECKING\n", "")
        source = replace_once(
            source,
            "from lerobot.utils.import_utils import _feetech_sdk_available, require_package\n",
            "import scservo_sdk as scs\n",
        )
        start = source.index("if TYPE_CHECKING or _feetech_sdk_available:")
        end = source.index("DEFAULT_PROTOCOL_VERSION")
        source = source[:start] + source[end:]
        source = replace_once(
            source,
            '        require_package("feetech-servo-sdk", extra="feetech", '
            'import_name="scservo_sdk")\n',
            "",
        )
    elif path.endswith("so_follower.py"):
        source = replace_once(source, "from lerobot.cameras import make_cameras_from_configs\n", "")
        source = replace_once(
            source,
            "from lerobot.lerobot_types import RobotAction, RobotObservation",
            "from lerobot_lite.device import RobotAction, RobotObservation",
        )
        source = replace_once(
            source, "from ..robot import Robot", "from lerobot_lite.device import Device as Robot"
        )
        source = replace_once(
            source,
            "from ..utils import ensure_safe_goal_position",
            "from lerobot_lite._vendor.safety import ensure_safe_goal_position",
        )
        source = replace_once(
            source,
            "from .config_so_follower import SOFollowerRobotConfig",
            "from lerobot_lite.config import SOFollowerConfig as SOFollowerRobotConfig",
        )
        source = replace_once(
            source, "        self.cameras = make_cameras_from_configs(config.cameras)\n", ""
        )
        start = source.index("    @property\n    def _cameras_ft")
        end = source.index("    @cached_property\n    def observation_features", start)
        source = source[:start] + source[end:]
        source = replace_once(
            source, "return {**self._motors_ft, **self._cameras_ft}", "return self._motors_ft"
        )
        source = replace_once(
            source,
            "return self.bus.is_connected and "
            "all(cam.is_connected for cam in self.cameras.values())",
            "return self.bus.is_connected",
        )
        source = replace_once(
            source, "        for cam in self.cameras.values():\n            cam.connect()\n\n", ""
        )
        source = replace_once(
            source, "        for cam in self.cameras.values():\n            cam.disconnect()\n", ""
        )
        start = source.index("        # Capture images from cameras")
        end = source.index("        return obs_dict", start)
        source = source[:start] + source[end:]
    elif path.endswith("so_leader.py"):
        source = replace_once(
            source,
            "from ..teleoperator import Teleoperator",
            "from lerobot_lite.device import Device as Teleoperator",
        )
        source = replace_once(
            source,
            "from .config_so_leader import SOLeaderTeleopConfig",
            "from lerobot_lite.config import SOLeaderConfig as SOLeaderTeleopConfig",
        )
    source = source.replace("from lerobot.", "from lerobot_lite._vendor.")
    # Comments leave future imports legal and retain all original copyright notices.
    notice = "# Generated from LeRobot v0.6.1; modified for hardware-only imports/cameras.\n"
    if source.startswith("#!/"):
        first, rest = source.split("\n", 1)
        return first + "\n" + notice + rest
    return notice + source


def generate(checkout: Path) -> dict[Path, str]:
    def blob(path: str) -> str:
        return subprocess.check_output(
            ["git", "show", f"{REVISION}:{path}"], cwd=checkout, text=True
        )

    generated = {ROOT / "LICENSE": blob("LICENSE")}
    manifest = {
        "repository": "https://github.com/huggingface/lerobot",
        "version": "0.6.1",
        "commit": REVISION,
        "files": {},
    }
    destination = ROOT / "src/lerobot_lite/_vendor"
    for source_path, target_path in FILES.items():
        original = blob(PREFIX + source_path)
        translated = translate(source_path, original)
        original_ast = fingerprints(original)
        translated_ast = fingerprints(translated)
        preserved = {k: v for k, v in original_ast.items() if translated_ast.get(k) == v}
        manifest["files"][target_path] = {
            "upstream_path": PREFIX + source_path,
            "source_sha256": hashlib.sha256(original.encode()).hexdigest(),
            "generated_sha256": hashlib.sha256(translated.encode()).hexdigest(),
            "preserved_functions": preserved,
        }
        generated[destination / target_path] = translated

    # Extract only stdlib helpers instead of importing the original utils module.
    helpers = [
        (
            "utils/utils.py",
            "utils/terminal.py",
            "import platform\nimport select\nimport sys\n",
            ["enter_pressed", "move_cursor_up"],
        ),
        (
            "robots/utils.py",
            "safety.py",
            "import logging\nfrom pprint import pformat\n",
            ["ensure_safe_goal_position"],
        ),
    ]
    for source_path, target_path, imports, names in helpers:
        original = blob(PREFIX + source_path)
        header_lines = []
        for line in original.splitlines():
            if line and not line.startswith("#"):
                break
            header_lines.append(line)
        header = "\n".join(header_lines) + "\n"
        translated = (
            "# Modified for LeRobot Lite: extracted stdlib-only helpers; imports reduced.\n"
            + header
            + imports
            + "\n\n"
        )
        translated += "\n\n".join(function_source(original, name) for name in names)
        manifest["files"][target_path] = {
            "upstream_path": PREFIX + source_path,
            "source_sha256": hashlib.sha256(original.encode()).hexdigest(),
            "generated_sha256": hashlib.sha256(translated.encode()).hexdigest(),
            "preserved_functions": {name: fingerprints(original)[name] for name in names},
        }
        generated[destination / target_path] = translated

    required = {
        "motors/motors_bus.py": [
            "SerialMotorsBus._normalize",
            "SerialMotorsBus._unnormalize",
            "SerialMotorsBus.sync_read",
            "SerialMotorsBus.sync_write",
        ],
        "so_follower.py": [
            "SOFollower.configure",
            "SOFollower.calibrate",
            "SOFollower.send_action",
        ],
        "so_leader.py": ["SOLeader.configure", "SOLeader.calibrate", "SOLeader.get_action"],
    }
    for path, names in required.items():
        for name in names:
            if name not in manifest["files"][path]["preserved_functions"]:
                raise ValueError(f"Motion contract changed: {path}:{name}")
    generated[ROOT / "upstream.lock.json"] = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    return generated


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "checkout", type=Path, help="Local LeRobot git checkout containing the pinned commit"
    )
    parser.add_argument("--check", action="store_true", help="Compare without changing files")
    args = parser.parse_args()
    generated = generate(args.checkout)
    mismatches = []
    for path, content in generated.items():
        if args.check:
            if not path.is_file() or path.read_text() != content:
                mismatches.append(str(path.relative_to(ROOT)))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
    if mismatches:
        print("Vendored snapshot differs: " + ", ".join(mismatches))
        return 1
    print(f"{'Verified' if args.check else 'Generated'} {len(generated)} pinned files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
