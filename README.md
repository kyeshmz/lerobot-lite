# LeRobot Lite

A small **SO-100/SO-101 hardware library**, extracted from the **LeRobot 0.6.1**
release used by `kyeshmz/lerobot-webrtc`. It retains the existing movement
mechanics rather than inventing another servo controller.

**Status: initial extraction, tested without hardware. Not yet qualified on a
physical arm.** The target is assumed to be Seeed Studio's SO-101 with six
Feetech STS3215 motors; confirm the model, motor IDs, and voltage variant before
using it. This is independent of Hugging Face and Seeed Studio.

## How it is slimmer

| Keep | Leave out |
| --- | --- |
| Feetech serial bus and SDK timeout fix | PyTorch, torchvision, model inference/training |
| Six-joint IDs and action dictionaries | Datasets, recording, Hugging Face Hub |
| LeRobot calibration JSON and normalization | Cameras, OpenCV, video codecs |
| Position PID and gripper protection settings | Robot/plugin registries and config framework |
| Sync reads/writes and relative-target limiter | WebRTC, signaling, UI, network transport |

**Three runtime dependencies:** `feetech-servo-sdk==1.0.0`, `pyserial`, and `tqdm`.
DeepDiff is replaced by standard-library equality for the flat register tables.
The small progress dependency is retained for the original motor-setup tools.
There is no dependency on the `lerobot` distribution, and no install-time
download of upstream source. The generated hardware snapshot is checked in.

This is the hardware layer only. Your WebRTC application stays separate and
keeps ownership of freshness permits, sequence checks, latest-only queues,
watchdog, authentication, and serialized I/O.

## Install and try without motors

Use Python **3.12 or later**:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
lerobot-lite simulate --steps 10
python -m unittest discover -s tests -t . -v
ruff check .
ruff format --check .
```

If the OS Python cannot create a pip-enabled environment, install the matching
Python venv package, or use your existing `uv` installation:

```bash
uv venv --python 3.12
uv pip install -e '.[dev]'
```

`simulate` exercises the real extracted relative-target limiter with generated
positions. It opens no serial ports and is not a physical safety or network test.
For an arm host, `python -m pip install -e .` omits development tools.

## Same movement contract

The pinned upstream code retains:

- Motor names/IDs: `shoulder_pan=1`, `shoulder_lift=2`, `elbow_flex=3`,
  `wrist_flex=4`, `wrist_roll=5`, `gripper=6`, all `sts3215`.
- Action keys: the six motor names with a `.pos` suffix.
- With `use_degrees=False`, body joints are `[-100, 100]` and gripper `[0, 100]`.
  Range clipping, `drive_mode` inversion, and raw integer truncation are unchanged.
- The API default remains `use_degrees=True`, as in LeRobot 0.6.1. **Set it to
  `False` on both arms to match your current WebRTC project.** Degree mode and
  its upstream handling of drive mode are retained, not redesigned.
- Calibrated encoder limits, homing offsets, sign-magnitude encoding, register
  addresses, little-endian servo data, and SDK packet-timeout workaround.
- Position mode, default PID `P=16, I=0, D=32`, motor acceleration settings, and
  gripper limits (`Max_Torque_Limit=500`, `Protection_Current=250`,
  `Overload_Torque=25`).
- Reads use the original two extra attempts on failure. Limiting reads the
  follower's measured pose, clips the target delta, then sync-writes the target.

`upstream.lock.json` records source hashes and exact AST fingerprints of preserved
functions. Tests check the snapshot and movement contract. This establishes
source-level continuity; it does **not** establish identical physical timing,
successful writes on a real bus, or safe behavior for your load.

### Intentional public-boundary changes

- `connect()` defaults to `calibrate=False`: saved, matching calibration is
  required. Missing calibration refuses before opening serial; a register
  mismatch refuses before configuration or enabling torque.
- `send_action()` requires a complete six-joint finite numeric frame. Extra or
  missing keys, booleans, NaN, and infinity are rejected before motor I/O. The
  original driver still performs normalization/range clipping.
- Invalid calibration files, motor IDs, encoder ranges, configuration limits,
  and unsafe calibration filenames are rejected early. JSON saves are atomic.
- Public connection/disconnection failures attempt serial cleanup. Configuration
  failures additionally attempt torque-off; this may let an unsupported arm fall.
- No camera configuration, automatic destructor disconnect, device registry,
  or general LeRobot training/recording compatibility is supplied.

## Calibration

Existing LeRobot 0.6.1 calibration is read from the **same paths**, honoring
`HF_LEROBOT_CALIBRATION`, `HF_LEROBOT_HOME`, `HF_HOME`, and `XDG_CACHE_HOME`:

```text
~/.cache/huggingface/lerobot/calibration/teleoperators/so_leader/<id>.json
~/.cache/huggingface/lerobot/calibration/robots/so_follower/<id>.json
```

The shared `so_leader`/`so_follower` names are deliberate: those are the names in
your pinned release, even when selecting SO-101. For older calibration directories,
pass `calibration_dir` explicitly. Never silently substitute calibration from a
different physical arm.

Inspect a file without opening serial:

```bash
lerobot-lite inspect-calibration /path/to/follower.json
```

New calibration is an explicit, interactive command. Support the arm throughout:

```bash
lerobot-lite calibrate --role leader --port /dev/ttyACM0 --id remote_leader
lerobot-lite calibrate --role follower --port /dev/ttyACM1 --id remote_follower
```

Use the upstream assembly and motor-ID setup process before calibration.
The original `setup_motors()` API is retained, but has not been hardware-tested
here. Calibration disables torque, records the manually traversed ranges, and
retains the original full-range wrist-roll convention. Calibration may update
your existing file and motor registers; back up working calibration first.

## Python API

```python
from lerobot_lite import (
    SO101Follower,
    SO101FollowerConfig,
    SO101Leader,
    SO101LeaderConfig,
)

leader = SO101Leader(
    SO101LeaderConfig(
        port="/dev/ttyACM0",
        id="remote_leader",
        use_degrees=False,
    )
)
follower = SO101Follower(
    SO101FollowerConfig(
        port="/dev/ttyACM1",
        id="remote_follower",
        use_degrees=False,
        max_relative_target=5.0,
        disable_torque_on_disconnect=False,  # Leaves torque on; not an automatic hold.
    )
)

# These calls may configure/enable motors. Run only on a supported, clear bench.
# In an application, put connection and control inside try/finally cleanup.
follower.connect(calibrate=False)
leader.connect(calibrate=False)
action = leader.get_action()
applied_action = follower.send_action(action)
# Your existing runtime should own pacing, freshness checks, and error cleanup.
```

Full lifecycle handling is included in the local CLI; the fragment above only
illustrates the API. `disconnect()` with torque enabled does not first command
the current pose. Call `hold()` explicitly, then disconnect, with best-effort
cleanup on failure—exactly as your existing WebRTC runtime already does.

Two arms on **one computer**, with explicit motion consent:

```bash
lerobot-lite teleoperate \
  --leader-port /dev/ttyACM0 --leader-id remote_leader \
  --follower-port /dev/ttyACM1 --follower-id remote_follower \
  --fps 30 --max-relative-target 5 --on-exit hold --arm
```

This local CLI is **not** a remote/WebRTC replacement and contains no network
watchdog. Motion starts on the first command; `--arm` is startup consent, not a
dead-man switch. It attempts a measured-pose hold on normal exit/Ctrl+C, then
leaves follower torque enabled by default. `--on-exit torque-off` instead disables
torque, which can drop the arm. Blocking serial I/O and process crashes can
prevent cleanup. Always use an independent physical stop/power cutoff.

The 5-unit limiter is **per write**, not degrees/second, acceleration, force, or
collision protection. At a higher loop rate the arm can move faster. Keep the
same loop rate and limits for the first comparison with LeRobot.

## Integrating your WebRTC bridge

See [docs/WEBRTC_MIGRATION.md](docs/WEBRTC_MIGRATION.md). The hardware imports can
change to the compatible `lerobot_lite.robots.so_follower` and
`lerobot_lite.teleoperators.so_leader` paths. The explicit calibration adapter
also needs to open the bus directly, as documented there. Do not change the
protocol/runtime or remove its safety machinery. The existing repository has
not been edited.

## Provenance and development

Upstream: [LeRobot v0.6.1](https://github.com/huggingface/lerobot/tree/7e241bd630a3719a56157a497ce5d08f244784f1)
at `7e241bd630a3719a56157a497ce5d08f244784f1`, Apache-2.0. Original notices,
the upstream license, and a modification notice are included.

The project is **Apache-2.0**; runtime dependencies retain their separate
Unlicense, BSD-3-Clause, and MPL-2.0/MIT terms. See
[docs/LICENSE_AUDIT.md](docs/LICENSE_AUDIT.md) for the review and distribution
obligations, especially when bundling dependencies into a deployment image.

Generated source lives under `src/lerobot_lite/_vendor/`. Do not hand-edit it;
change the reviewed transformation and regenerate from the pinned git blobs:

```bash
python scripts/vendor_upstream.py /path/to/lerobot-checkout
python scripts/vendor_upstream.py /path/to/lerobot-checkout --check
python -m unittest discover -s tests -t . -v
python -m build
```

The generator reads `git show <pinned-commit>:<path>`, not the checkout's working
files. It is a development tool only; installed packages work offline.

See [docs/PLAN.md](docs/PLAN.md) for the extraction boundary, validation gates,
and further slimming work, and [docs/VALIDATION.md](docs/VALIDATION.md) for the
initial test/build results and measured package footprint.
