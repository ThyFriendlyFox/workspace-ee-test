# STATUS.md — where the project actually stands

The single source of truth for project state. Claims require evidence: a
passing gate, a linked run, a tag. Updated in the same commit as the
behavior change. The weekly cycle (WEEKLY.md step 5) refreshes it.

| Area | State | Evidence |
|---|---|---|
| `install.sh` on Ubuntu 24.04 | ✅ | Ran end to end in the authoring cloud session; `doctor` reported `ok`. See `DEVLOG.md` 2026-10-22. |
| Gates ERC, DRC, SIM, EXPORT | ✅ | `make verify` green locally at the install commit: fixture `pass-rc-divider` GREEN, `fail-drc-clearance` red at DRC, `fail-sim-spec` red at SIM. |
| Autoroute (DSN → FreeRouting → SES) | 🚧 | Produces a session file; import into the board is manual. ROADMAP item 1. |
| Skills | ✅ | 5 skills with frontmatter, checked by `make verify`. |
| Cloud environment | 🚧 | `environment/setup.sh` written; not yet run as an environment setup script by a human. |
| Docker image | 🚧 | `Dockerfile` written; not built (no daemon in the authoring session). `release.yml` builds it on the first tag. |
| CI | 🚧 | Workflows committed; first run happens on the first push to GitHub. |

States: ✅ done (gated) · 🚧 in progress · ❌ not started · 🧊 frozen/won't do.

## Current week

- **Shipping:** between cycles — kit installed, queue seeded.
- **Last release:** none
- **Known red:** none locally. CI, the Docker build, and the cloud setup script have not run yet.
