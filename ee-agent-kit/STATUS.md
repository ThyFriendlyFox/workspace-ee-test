# STATUS.md — where the project actually stands

The single source of truth for project state. Claims require evidence: a
passing gate, a linked run, a tag. Updated in the same commit as the
behavior change. The weekly cycle (WEEKLY.md step 5) refreshes it.

| Area | State | Evidence |
|---|---|---|
| `install.sh` on Ubuntu 24.04 | ✅ | CI run 1 on PR #1 green in 69 s; runs end to end in the cloud session. |
| Gates ERC, DRC, SIM, EXPORT | ✅ | `make verify`: fixture `pass-rc-divider` GREEN with `--strict`, `fail-drc-clearance` red at DRC, `fail-sim-spec` red at SIM. |
| `kicadgen` design generator | ✅ | `tests/test_kicadgen.py`: parser, derived symbols, open-pin nets, DSN, session scale; generated divider passes ERC strict. First real board, 39 parts, GREEN in its own repository. |
| Autoroute, generated designs | ✅ | `workcenter design --route`: DSN writer, FreeRouting, session merge; round-trip test makes DRC GREEN when FreeRouting is installed. |
| Autoroute, hand-drawn boards | 🚧 | Produces a session from a KiCad-exported DSN; import is manual. ROADMAP item 1. |
| `workcenter render` | ✅ | Schematic, board top and bottom, 3D top and isometric images; PNG through librsvg. |
| Skills | ✅ | 6 skills with frontmatter, checked by `make verify`. |
| Cloud environment | 🚧 | `environment/setup.sh` written; not yet set on an environment by a human. |
| Docker image | 🚧 | `Dockerfile` written; `release.yml` builds it on the first tag. |
| CI | ✅ | `ci.yml` green on PR #1; runs on every PR and push to `main`. |

States: ✅ done (gated) · 🚧 in progress · ❌ not started · 🧊 frozen/won't do.

## Current week

- **Shipping:** out-of-band — `kicadgen`, `design`, `render`, built while designing the first board.
- **Last release:** none
- **Known red:** none locally. The cloud setup script and the Docker build have not run yet.
