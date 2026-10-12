# Extraction plan

## Decision

Extract the small hardware dependency graph from the **exact LeRobot 0.6.1
release currently pinned in `lerobot-webrtc`**. Do not fork the whole project,
install it with `--no-deps`, or copy only the position conversion formula.
Those alternatives leave hidden imports or lose calibration/configuration
behavior. Keep networking outside the hardware library.

Target assumption: SO-101/SO-100 with six STS3215 motors and upstream IDs 1–6.
"B 601" has not been independently confirmed as a hardware model. No physical
arm was connected or commanded while creating this repository.

## Initial extraction implemented

- Pinned serial bus, Feetech implementation/tables, encoding functions.
- Camera-free leader/follower wrappers with upstream configure, calibration,
  action read/write, and relative-target limiter functions intact.
- Standard-library configuration/calibration, correct existing cache paths.
- Validated complete command frames; calibration mismatch gates before torque.
- Local calibration/teleop CLI and no-serial limiter simulation.
- Source provenance, regression tests, package build, migration instructions.

## Next gates (not completed by initial extraction)

1. **Confirm hardware.** SO-101 motor model, IDs, firmware, supply voltage,
   calibration location, payload, and desired disconnect behavior.
2. **Hardware differential test.** Same raw targets/poses under upstream and
   lite versions; check ranges, inversions, integer quantization, gripper,
   PID/protection writes, read retries, and observed control rate.
3. **Bridge integration branch.** Only replace hardware dependency/imports.
   Run full bridge simulation and supervised fault tests; keep deployed project
   unchanged until those pass.
4. **Release/integrate.** The public GitHub source is available at
    [kyeshmz/lerobot-lite](https://github.com/kyeshmz/lerobot-lite), without CI by
    user choice. After qualification, pin the bridge dependency to an immutable
    published commit. PyPI release, if desired, is a separate decision.

## Additional slimming after parity is established

- Move motor ID setup/scanning and interactive calibration into optional tooling.
  Then `tqdm` can leave the core dependency set.
- Limit the public motor interface to the supported STS3215/protocol-0 path;
  remove other-model tables and abstract/protocol scaffolding only after tests
  demonstrate the same transmitted bytes and failure behavior.
- Measure installed package size, dependency download size, import time, and
  RSS on the actual arm computers. Removing ML dependencies is the large win;
  fewer source lines alone is not a useful performance metric.
- Keep cameras or future transport adapters as separate optional packages.
- Do not "optimize" PID gains, acceleration, normalization, polling cadence,
  torque behavior, or calibration conventions in the dependency-removal change.

## Safety and scope

This is best-effort Python control, not a safety-rated controller. There is no
independent watchdog, collision checking, force limit, or physical e-stop here.
Blocking serial calls are not forcibly interrupted. Hardware protections and a
physical power cutoff are required. WebRTC session safety belongs to the existing
bridge and must not be slimmed out with the ML stack.
