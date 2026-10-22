# CI.md — what runs in `.github/` and why

The workflow files in `.github/workflows/` are the source of truth. This
file explains them and holds the repository settings that are not files.

| File | Trigger | Does |
|---|---|---|
| `ci.yml` | push to `main`, every PR, manual | `sudo ./install.sh` then `make verify`. The same install script as the cloud environment and the Dockerfile; the same verify as local. |
| `nightly.yml` | 06:17 UTC daily | Same as CI. Files 1 `ci-failure` issue on red when none is open. Catches a moved PPA, a new KiCad point release, a broken dependency. |
| `release.yml` | tag `v*.*.*` | Builds the Docker image, pushes `ghcr.io/<owner>/ee-workcenter:<tag>` and `:latest`, smoke-tests it with `workcenter doctor`, publishes the GitHub Release with generated notes. |
| `stale.yml` | Mondays | Marks issues stale after 60 days, closes after 14 more. `blocked`, `security`, `accepted` are exempt. |
| `../dependabot.yml` | weekly | pip (`requirements.txt`), GitHub Actions, Docker base image. Minor and patch updates grouped. |
| `../PULL_REQUEST_TEMPLATE.md` | every PR | What, Why, Evidence, checklist. |

## Toolchain step

CI installs with `sudo env REQUIRE_FREEROUTING=1 ./install.sh`. The
runner is `ubuntu-24.04`, so the PPA step, the Java package, and ngspice
match the cloud environment. `REQUIRE_FREEROUTING=1` makes a blocked JAR
download fail the run; a green CI proves the autoroute engine installs.

## Branch protection on `main` (repo Settings)

- Require the `verify` check; require PRs; require up-to-date branches;
  squash-merge only; auto-delete head branches.
