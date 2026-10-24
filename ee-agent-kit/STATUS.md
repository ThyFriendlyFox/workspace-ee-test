# STATUS.md — where the project actually stands

The single source of truth for project state. Claims require evidence: a
passing gate, a linked run, a tag. Updated in the same commit as the
behavior change. The weekly cycle (WEEKLY.md step 5) refreshes it.

| Area | State | Evidence |
|---|---|---|
| `install.sh` on Ubuntu 24.04 | ✅ | CI run 1 on PR #1 green in 69 s; runs end to end in the cloud session. |
| Gates ERC, DRC, SIM, EXPORT | ✅ | `make verify`: fixture `pass-rc-divider` GREEN with `--strict`, `fail-drc-clearance` red at DRC, `fail-sim-spec` red at SIM. |
| `kicadgen` design generator | ✅ | `tests/test_kicadgen.py` (21 tests; the suite is 33): parser, derived symbols, open-pin nets, DSN with planes and fixed wiring, session scale and echo handling, pours filled and stitched, hand routes, rounded corners, per-part 3D bodies, `wrlgen` bodies. Three real boards GREEN in their own repository; the latest is 1 x 0.5 in with parts on both faces and a vertical USB-C. |
| Autoroute, generated designs | ✅ | `workcenter design --route --rounds`: DSN writer, FreeRouting, session merge, pour islands stitched or re-routed; two round-trip tests make DRC GREEN when FreeRouting is installed. |
| Autoroute, hand-drawn boards | 🚧 | Produces a session from a KiCad-exported DSN; import is manual. ROADMAP item 1. |
| `workcenter render` | ✅ | Schematic, board top and bottom, 3D top, bottom and isometric images with part bodies when `kicad-packages3d` is installed, plus the project's own `wrlgen` bodies; PNG through librsvg. |
| Skills | ✅ | 6 skills with frontmatter, checked by `make verify`. |
| Mistake log and processes | ✅ | `MISTAKES.md` M1 to M18, `PROCESSES.md` P1 to P14; `make verify` checks every entry names an existing process and every process has a "Done when" line. |
| Cloud environment | 🚧 | `environment/setup.sh` written; not yet set on an environment by a human. |
| Docker image | 🚧 | `Dockerfile` written; `release.yml` builds it on the first tag. |
| CI | ✅ | `ci.yml` green on PR #1; runs on every PR and push to `main`. |

States: ✅ done (gated) · 🚧 in progress · ❌ not started · 🧊 frozen/won't do.

## Current week

- **Shipping:** out-of-band — pours, hand routes and island stitching in `kicadgen`, built while shrinking the first board to an inch.
- **Last release:** none
- **Known red:** none locally. The cloud setup script and the Docker build have not run yet.
