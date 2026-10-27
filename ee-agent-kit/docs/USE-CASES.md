# Use cases

Each case has the same shape.
**Open** is what the agent or human starts with. **Run** is the command
or skill. **Done** is the observable result that ends the case.

## Design a board from a spec

**Open.** A spec: what the board does, the body it fits, the connectors. An empty project repository.
**Run.** The `board-design` skill: pick parts from the libraries, write `design.py`, `workcenter design design.py --route`, then `workcenter gates .`.
**Done.** GREEN, `design.py` and the generated `.kicad_*` files committed together, images in `docs/`, the README naming each part choice.

## Validate a board

**Open.** A board repository with `<name>.kicad_pro`, `.kicad_sch`, and `.kicad_pcb`.
**Run.** `workcenter gates <project>`.
**Done.** GREEN, and `build/gates.json` holds 4 records with status `pass`.

## Fix a red board

**Open.** `workcenter gates` stopped at a red gate.
**Run.** The `board-gates` skill: read the report, fix the design, commit, run again.
**Done.** The same command prints GREEN. Each fix is 1 commit that names the violation type.

## Export for a fab

**Open.** A board that is GREEN.
**Run.** `workcenter export <project>`.
**Done.** `build/fab/` holds gerbers, drill files, `bom.csv`, and `schematic.pdf`. The folder is what the fab receives.

## Price a board's parts

**Open.** A board with a schematic, and a question: what does it cost, and where are its parts?
**Run.** The `procurement` skill: fill `parts.csv` from the suppliers' pages (P25), then `workcenter procure <project> --parts parts.csv --boards 1,10`.
**Done.** `build/procure/parts.md` lists an orderable part for every line with its supplier number, price and stock, the totals per supplier for each unit count, and nothing under "Not in the parts files".

## Simulate before layout

**Open.** A schematic with a measurable spec and a `sim/<deck>.cir` with `sim/<deck>.expect.json`.
**Run.** `workcenter sim <project>`, guided by the `simulate` skill.
**Done.** Every bound holds. A missed bound changes component values, never the bound.

## Route a board

**Open.** A board with footprints placed and nets unrouted.
**Run.** `workcenter autoroute <project>`, then the session import, then `workcenter drc`.
**Done.** DRC reports 0 unconnected items. Today the import step is manual in KiCad; ROADMAP item 1 makes it part of the command.

## Review a board PR

**Open.** A pull request that changes a `.kicad_sch` or `.kicad_pcb`.
**Run.** `workcenter gates` on the PR head, in CI or in a session.
**Done.** The gates table is in the review. A red gate blocks the merge.

## Work in a two-repository session

**Open.** A Claude Code cloud session with a board repository and this repository attached.
**Run.** The `attached-repos` skill before the first edit.
**Done.** The roles report names the board as project and this repository as workcenter. Every commit lands in the board repository.

## Stand up the cloud environment

**Open.** A claude.ai account with no EE environment.
**Run.** Create an environment with the 3 lines from `environment/setup.sh` and the hosts from `environment/README.md`.
**Done.** A new session in that environment prints `workcenter ee: ok` from `workcenter doctor` at start.

## Build another workcenter from this one

**Open.** A different kind of work with its own tools, such as firmware or mechanical CAD.
**Run.** Copy the shape: `install.sh`, a `tools/<name>` CLI with gates, fixture projects, `WORKCENTER.md`, the kit with `attached-repos`.
**Done.** `workcenter doctor` for the new workcenter reports `ok`, and its fixtures pass and fail as documented.
