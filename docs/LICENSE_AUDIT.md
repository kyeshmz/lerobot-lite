# License review

## Project and extracted source: Apache-2.0

The extracted hardware files at LeRobot commit
`7e241bd630a3719a56157a497ce5d08f244784f1` carry Apache License 2.0 notices.
LeRobot Lite also declares `Apache-2.0` in `pyproject.toml`. Apache-2.0 permits
modification, redistribution, and commercial use, subject to its conditions.
It does not require this project to adopt GPL or publish private application code.

The review checked Apache-2.0 section 4's redistribution requirements:

| Requirement | Repository handling |
| --- | --- |
| Provide a copy of the license | `LICENSE` preserves the complete pinned upstream license file; packaged in wheel and sdist |
| Prominently identify changed files | Generated files carry modification/extraction comments; helpers explicitly state that imports were reduced |
| Retain copyright and attribution | Original file-level copyright/license headers remain; provenance records each upstream source path and hash |
| Preserve applicable upstream NOTICE content | The pinned upstream tree has no root `NOTICE`; this project adds its own `NOTICE` with attribution and a change summary |

The upstream `LICENSE` includes additional notices for Diffusion Policy, FOWM,
simxarm, ALOHA, and DETR. That file is retained verbatim, conservatively preserving
those notices; their model/training implementations are **not** copied into this
hardware extraction. Every extracted source file reviewed has an Apache-2.0
header. Those appended notices are not a reason to claim this hardware package
is wholly MIT-licensed.

## Runtime dependencies have their own licenses

These versions were checked from the installed distributions, their license
files, and the matching upstream pyserial release. They are dependencies, not
source vendored or relicensed by this project.

| Dependency | Version reviewed | License evidence |
| --- | --- | --- |
| `feetech-servo-sdk` | 1.0.0 | Distributed `LICENSE` contains The Unlicense; metadata declares `UNLICENSE` / The Unlicense classifier |
| `pyserial` | 3.5 | Source headers identify `BSD-3-Clause`; release `LICENSE.txt` contains the BSD three-clause terms |
| `tqdm` | 4.70.1 | Distributed `LICENCE` and metadata identify **MPL-2.0 AND MIT**, with file/author-specific notices |

Important distinctions:

- Calling the project Apache-2.0 does not relicense its dependencies.
- `tqdm` is **not simply MIT-only**, nor is its declaration an unrestricted
  choice of MIT *or* MPL for all files. Its license document identifies the
  portions under each license.
- MPL-2.0 has file-level obligations for covered source. An ordinary dependency
  does not by itself make our separate Apache-licensed files MPL-licensed. If
  you redistribute tqdm, preserve its notices/license and satisfy the covered
  source availability requirements; if you modify covered files, evaluate the
  requirements for those modifications too.
- If distributing an appliance, container, standalone executable, or other
  bundle containing dependency code, include the applicable dependency license
  notices. Preserve the BSD copyright, conditions, and disclaimer. A wheel of
  **our package only** does not contain these dependencies; an installation or
  deployment bundle may.
- `tqdm` and `pyserial` have version ranges in the package configuration. This
  review is for the versions above, not a permanent certification of every
  future resolver result. Recheck licenses when updating or releasing a bundle.

Development/build tools, the separate WebRTC application's dependencies,
mechanical/CAD designs, model weights, and datasets are outside this audit.

## Automated checks

`tests/test_licenses.py` checks package license metadata, the upstream license
copy, attribution/modification headers, and the recorded dependency versions'
license declarations. Build inspection verifies that both wheel and sdist
contain `LICENSE` and `NOTICE`; the sdist also includes this review and provenance.

This is an engineering review of the identified materials, not a legal opinion
or verification of the full historical ownership of every dependency.

## Sources

- [Pinned LeRobot LICENSE](https://github.com/huggingface/lerobot/blob/7e241bd630a3719a56157a497ce5d08f244784f1/LICENSE)
- [Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0)
- [Feetech SDK 1.0.0 package metadata](https://pypi.org/project/feetech-servo-sdk/1.0.0/)
- [pyserial 3.5 LICENSE.txt](https://github.com/pyserial/pyserial/blob/v3.5/LICENSE.txt)
- [tqdm 4.70.1 package metadata](https://pypi.org/project/tqdm/4.70.1/)
- [Mozilla MPL FAQ](https://www.mozilla.org/en-US/MPL/2.0/FAQ/)
