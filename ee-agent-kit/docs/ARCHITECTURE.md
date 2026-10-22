# Architecture

EE Workcenter is a toolchain installer, a Python command line, and a set
of skills that together run 4 gates on a KiCad 10 project. The code has
7 parts.

| Part | Folder | Task |
|---|---|---|
| Installer | `install.sh`, `requirements.txt` | Puts KiCad 10, ngspice, Java 21, FreeRouting, and a Python venv on an Ubuntu 24.04 machine. Idempotent. |
| CLI | `tools/workcenter` | Runs the engines against a project and reports 1 record per gate. Standard library only. |
| Skills | `.claude/skills/*/SKILL.md` | Tell the agent which gate comes next and how to read a report. Loaded by Claude Code from this repository or from a copy. |
| Fixture boards | `tests/boards/*`, `tests/test_gates.py` | The tests of the gates. 1 board passes everything; the others fail 1 named gate. |
| Manifest | `WORKCENTER.md` | The contract a project gets: tools, skills, gates, paths, requirements. |
| Environment | `environment/`, `Dockerfile` | The 2 ways the installer reaches a machine: a Claude Code cloud environment setup script, or a Docker image on the official KiCad base. |
| Kit | `ee-agent-kit/` | How work on this repository is run. Process, not product. |

## Data flow

1. A cloud environment (or a Dockerfile, or CI) runs `install.sh`. It
   writes the KiCad PPA source, installs the packages, downloads the
   FreeRouting JAR, creates the venv, links `workcenter` onto `PATH`,
   and copies `WORKCENTER.md` to `/opt/workcenters/ee/`.
2. An agent opens a board repository in that environment. With 2
   repositories attached, the `attached-repos` skill assigns roles:
   the board is the project, this repository is the workcenter.
3. The agent runs `workcenter gates <project>`.
4. The CLI finds `<name>.kicad_pro` and its siblings, then calls
   `kicad-cli sch erc`, `kicad-cli pcb drc`, `ngspice -b`, and
   `kicad-cli pcb export ...` in that order, each writing into
   `<project>/build/`.
5. The CLI parses each JSON report or log into a gate record and stops
   at the first red gate. All records land in `build/gates.json` and on
   stdout, as text or `--json`.
6. The agent reads the red gate's report, fixes the schematic or board,
   commits, and runs step 3 again.
7. GREEN: `build/fab/` holds gerbers, drill files, the BOM, and the
   schematic PDF. The board is done.

## CLI

| File | Task |
|---|---|
| `tools/workcenter` | `find_project`, 1 `gate_*` function per gate, `cmd_gates` for the ordered run, `cmd_doctor` for engine status, `emit` for output and exit codes. |

## Boundaries

| Boundary | Rule |
|---|---|
| CLI ↔ engines | Subprocess only. The CLI reads the engines' report files; it never imports KiCad or ngspice libraries. |
| Workcenter ↔ project | The workcenter reads the project and writes only `<project>/build/` or `--out`. Project source files are never modified by a gate run. |
| Kit ↔ code | The kit is read by agents and humans. Nothing executes it. `verify/verify.sh` checks its invariants (placeholders, skill parity). |
| Installer ↔ everything else | Every other part assumes the installer ran. Nothing else installs software. |
