# STATUS.md — where the project actually stands

The single source of truth for project state. Claims require evidence: a
passing gate, a linked run, a tag. Updated in the same commit as the
behavior change. The weekly cycle (WEEKLY.md step 5) refreshes it.

| Area | State | Evidence |
|---|---|---|
| `install.sh` on Ubuntu 24.04 | ✅ | CI run 1 on PR #1 green in 69 s; runs end to end in the cloud session. |
| Gates ERC, DRC, SIM, EXPORT | ✅ | `make verify`: fixture `pass-rc-divider` GREEN with `--strict`, `fail-drc-clearance` red at DRC, `fail-sim-spec` red at SIM. |
| `kicadgen` design generator | ✅ | `tests/test_kicadgen.py` (72 tests; the suite is 93): wired schematics (pin positions at each angle as KiCad's ERC reports them, crossings and ends the router keeps, a wired divider ERC-clean with its declared netlist and no parity warning, labels where asked, off-grid pins refused, the stub-and-label default unchanged), parser, derived symbols, open-pin nets, DSN with planes and fixed wiring, session scale and echo handling, pours filled and stitched, hand routes, rounded corners and stadiums, a radius per corner, board thickness and the two-layer stackup, project footprints, keep-outs in both via placers, non-plated holes in the via check and in the router file, four-layer boards (inner layers, stackup, a plane the router never sees, a real route on three layers, island vias to the plane and clear of tracks on the layers they pass), custom pads mirrored onto the bottom face and sized from their shapes, the hand-via check and the design command's refusal, via sizes against the board's rules, the no-`cd` hook and its installer, the hook against scripted test edits, per-part 3D bodies, `wrlgen` bodies. Real boards GREEN in their own repository; the latest is 38.0 x 12.7 mm on four layers, two 510 connectors and a 10440 cell in a line, keep-outs under the collars, every chip on the bottom face, and a two-layer 0.8 mm display board standing on its flat end. |
| Autoroute, generated designs | ✅ | `workcenter design --route --rounds`: DSN writer, FreeRouting, session merge, pour islands stitched or re-routed; two round-trip tests make DRC GREEN when FreeRouting is installed. |
| Autoroute, hand-drawn boards | 🚧 | Produces a session from a KiCad-exported DSN; import is manual. ROADMAP item 1. |
| `workcenter render` | ✅ | Schematic, board top and bottom, 3D top, bottom and isometric images with part bodies when `kicad-packages3d` is installed, plus the project's own `wrlgen` bodies; every layer with something on it, one PNG each, and an overview sheet; on request a GIF of the 3D board turning round (FFmpeg). PNG through librsvg. `tests/test_gates.py` (21 tests): layers drawn and empty ones skipped on the fixture, the view list, the GIF's frames and loop, the skip without FFmpeg, the parts drawn without a 3D body and `--strict` failing on one. |
| Skills | ✅ | 6 skills with frontmatter, checked by `make verify`. |
| Mistake log and processes | ✅ | `MISTAKES.md` M1 to M53, `PROCESSES.md` P1 to P24; `make verify` checks every entry names an existing process and every process has a "Done when" line. |
| Cloud environment | 🚧 | `environment/setup.sh` written; not yet set on an environment by a human. |
| Docker image | 🚧 | `Dockerfile` written; `release.yml` builds it on the first tag. |
| CI | ✅ | `ci.yml` green on PR #1; runs on every PR and push to `main`. |

States: ✅ done (gated) · 🚧 in progress · ❌ not started · 🧊 frozen/won't do.

## Current week

- **Shipping:** out-of-band — pours, hand routes and island stitching in `kicadgen`, built while shrinking the first board to an inch.
- **Last release:** none
- **Known red:** none locally. The cloud setup script and the Docker build have not run yet.
