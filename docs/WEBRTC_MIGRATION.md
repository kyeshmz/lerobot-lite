# Migration for `lerobot-webrtc`

This package replaces the **hardware dependency**, not the WebRTC transport.
Do this in a separate branch and isolated virtual environment after bench
qualification. Do not uninstall LeRobot from a working deployment first.

## Minimal changes

In `src/lerobot_webrtc/arms.py`:

```diff
-from lerobot.teleoperators import so_leader as module
+from lerobot_lite.teleoperators import so_leader as module

-from lerobot.robots import so_follower as module
+from lerobot_lite.robots import so_follower as module
```

All the existing adapter's configuration fields are available:
`port`, `id`, `use_degrees`, `max_relative_target`, and
`disable_torque_on_disconnect`. The selected SO100/SO101 class aliases remain.
The adapter's `connect(calibrate=False)`, `calibration`, `is_calibrated`,
`get_action()`, `get_observation()`, `send_action()`, `bus.is_connected`, and
`disconnect()` calls remain supported.

Also update `LeRobotArm.calibrate()` in the same file. The lightweight public
`connect()` deliberately refuses missing/mismatched calibration; an explicit
calibration command must bypass that runtime gate, **not** weaken it:

```diff
 def calibrate(self) -> None:
-    self.device.connect(calibrate=False)
+    self.device.bus.connect()
     self.device.calibrate()
```

This opens the bus for the existing interactive calibration procedure without
first running follower configuration or enabling torque. Keep the calibration
CLI's torque-off cleanup, and support the arm while calibrating.

Keep `use_degrees=False` on both endpoints. Keep the measured-pose hold in
`LeRobotArm.hold()` and the serialized `AsyncArm` worker. Update the install
error message and hardware adapter tests for the new namespace.

For a local trial, remove `lerobot[feetech]==0.6.1` from the bridge's `hardware`
extra **in the trial branch**, then install both projects in the same isolated env:

```bash
python -m pip install -e '/path/to/lerobot-lite'
python -m pip install -e '/path/to/lerobot-webrtc[dev]'
python -m pip check
```

Do not replace the extra with a PyPI dependency until this project is actually
published there. The public Git source is at
[kyeshmz/lerobot-lite](https://github.com/kyeshmz/lerobot-lite); after qualification,
a Git dependency can be pinned to an immutable published commit. Reading or
cloning the public repository does not require authentication. There is no PyPI release yet.

## Checks before switching

1. Back up each arm's calibration; validate with `inspect-calibration`.
2. Run the bridge's existing full test suite and simulated WebRTC demo. The
   four hardware adapter variants must use the new namespace in their fakes.
3. Compare both drivers' raw and normalized leader reads at a few fixed poses
   on the **same hardware and calibration**, one process/driver at a time.
   Never let two processes share the serial port.
4. Start with a supported unloaded follower, clear workspace, physical stop,
   low loop rate, and conservative delta. Compare the returned applied targets
   and actual motion. Verify PID/protection registers and calibration mismatch
   refusal. Record firmware, voltage variant, and SDK version.
5. Verify network watchdog, transport loss, hold-on-exit, and torque-off modes
   on a supervised bench. Software hold can fail when power or serial fails.

Keep the bridge's permits, sequence numbers, expiry checks, latest-only mailbox,
thread ownership, and watchdog. Those are not bloat: they are part of remote
teleoperation correctness. Hardware/source parity alone cannot validate them.

An optional no-hardware integration test loads an in-memory copy of your bridge
adapter with only these import/calibration edits and exercises its API against
the lightweight classes and a fake bus. It never edits the bridge checkout:

```bash
LEROBOT_WEBRTC_CHECKOUT=/path/to/lerobot-webrtc \
  python -m unittest tests.test_bridge -v
```
