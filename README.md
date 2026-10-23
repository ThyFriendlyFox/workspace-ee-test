# EE Workcenter

A workcenter is a pre-packaged environment an agent steps into to do 1
kind of work well. This one does electronics: it turns a KiCad 10
project into fabrication outputs that passed every gate.

- **Engines:** KiCad 10 (`kicad-cli`), ngspice, FreeRouting.
- **Gates:** ERC, DRC, SIM, EXPORT, in that order. A board is done when
  `workcenter gates <project>` prints GREEN.
- **Design as code:** `workcenter design design.py --route` builds a
  schematic and a routed board from a Python file that names parts from
  the KiCad libraries. No GUI at any step.
- **Skills:** tell a Claude Code agent which gate comes next and how to
  read a report.
- **Fixture boards:** the tests. 1 passes everything, the others fail 1
  named gate.

## Quick start

```sh
sudo ./install.sh                 # Ubuntu 24.04; KiCad 10 PPA, ngspice, Java 21, FreeRouting, venv
workcenter doctor                 # every engine present?
workcenter gates tests/boards/pass-rc-divider        # GREEN
workcenter gates tests/boards/fail-drc-clearance     # red at DRC, on purpose
```

Output goes to `<project>/build/`: `erc.json`, `drc.json`, `sim/`,
`fab/` (gerbers, drill, BOM, schematic PDF), `gates.json`.

## As a Claude Code cloud environment

The environment carries the software; the board repository carries the
board. Create an environment whose setup script is the 3 lines in
`environment/setup.sh`, with the network hosts from
`environment/README.md`. Open any board repository in it. Attach this
repository as a second repository when its skills should load.

## As a Docker image

`docker build -t ee-workcenter .` on the official `kicad/kicad:10.0`
base. `release.yml` publishes it to GHCR on every tag.

## Repository map

| Path | What |
|---|---|
| `install.sh` | The single source of the toolchain. |
| `tools/workcenter` | The CLI: gates, `design`, `render`, `doctor`. Standard library only. |
| `tools/kicadgen.py` | Design a board in Python from the KiCad libraries; writes the KiCad project and routes it headless. |
| `WORKCENTER.md` | The contract a project gets from this workcenter. |
| `.claude/skills/` | `attached-repos`, `board-design`, `board-gates`, `autoroute`, `simulate`, `blog-post`. |
| `tests/boards/` | Fixture boards and what each proves. |
| `environment/` | Cloud environment setup script and hosts. |
| `ee-agent-kit/` | How work on this repository is run. Start at `ee-agent-kit/ROUTING.md`. |

## Working on this repository

`make verify` must be green before any push. `ee-agent-kit/AGENTS.md` is
binding; `ee-agent-kit/ROADMAP.md` decides what gets built.

MIT licensed. KiCad, ngspice, and FreeRouting keep their own licenses.
