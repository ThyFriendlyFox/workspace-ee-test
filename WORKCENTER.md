# WORKCENTER.md — EE Workcenter

<!-- This file at the root marks the repository as a workcenter to
     skills/attached-repos. install.sh copies it to
     /opt/workcenters/ee/WORKCENTER.md so an environment without the
     repository attached still finds it. -->

The EE Workcenter turns a KiCad 10 project into fabrication outputs that
passed every gate. "Done" means `workcenter gates <project>` prints GREEN.

## Tools

| Tool | Version | Command | Installed by |
|---|---|---|---|
| KiCad | 10.0 | `kicad-cli` | `install.sh` (PPA kicad/kicad-10.0-releases) |
| ngspice | 42 | `ngspice` | `install.sh` (Ubuntu 24.04 archive) |
| FreeRouting | 2.1 | `workcenter autoroute <project> [--dsn file]` (DSN exported from KiCad; `kicad-cli` 10 has no Specctra export) | `install.sh` (GitHub release, SHA-256 pinned) |
| kicad-python (kipy) | 0.8 | `/opt/workcenters/ee/venv/bin/python` | `install.sh` (PyPI) |
| workcenter CLI | this repo | `workcenter` | `install.sh` (symlink to `tools/workcenter`) |

## Skills

| Skill | Use when |
|---|---|
| `attached-repos` | The session holds more than 1 repository. Run first. |
| `board-gates` | A board must pass ERC, DRC, simulation, and export. The fix loop. |
| `autoroute` | A board has unrouted nets and FreeRouting should route them. |
| `simulate` | A circuit must meet a measurable spec before layout. |
| `blog-post` | A human asks for a public write-up of recent work. |

## Gates

| Gate | Command | Pass condition | Runs before |
|---|---|---|---|
| ERC | `workcenter erc <project>` | 0 errors in the ERC report | layout |
| DRC | `workcenter drc <project>` | 0 errors, 0 unconnected items, 0 parity errors | export |
| SIM | `workcenter sim <project>` | every `sim/*.cir` runs clean and every `*.expect.json` bound holds | export |
| EXPORT | `workcenter export <project>` | gerbers, drill, BOM, schematic PDF produced | hand-off to fabrication |
| ALL | `workcenter gates <project>` | the 4 gates above in order, none red | a board is called done |

A project may add gates. It may not remove these.

## Paths

| Purpose | Path |
|---|---|
| Install root | `/opt/workcenters/ee` |
| Engine environment | `/opt/workcenters/ee/env.sh` |
| Tool cache | the session scratchpad; the engines write nothing outside the output directory |
| Project output | `<project>/build/` (reports, `fab/`, `sim/`, `route/`) |

## Project requirements

- `.gitignore` entries: `build/`
- Files: one `<name>.kicad_pro` with `<name>.kicad_sch` and `<name>.kicad_pcb` beside it
- Optional: `sim/<deck>.cir` with `sim/<deck>.expect.json` for the SIM gate
