# ROADMAP.md — the source of all work

**This file is not optional.** Every feature the agent builds flows down
from here. If it isn't on this roadmap, it doesn't get built; if it needs
building, it gets added here first. One item ships per weekly cycle
(see `WEEKLY.md`).

`provisional: true` — the queue below was seeded at setup by the agent.
The human re-orders it.

## North star

EE Workcenter is the environment an agent steps into to take a KiCad
project from schematic to fabrication outputs with every gate green,
without a human running a tool by hand. Everything here serves that:
the toolchain installs itself, the gates are the definition of done, and
the skills tell the agent which gate comes next.

## Feature Queue — ordered; top unblocked item ships next

### 1. Headless autoroute for hand-drawn boards
- **Promise:** `workcenter autoroute --apply <project>` reads any `.kicad_pcb` (footprints, pads, outline, nets, existing tracks) into the DSN writer that `kicadgen` already has, runs FreeRouting, merges the session into the board file, and the new fixture `route-me` passes DRC with 0 unconnected items afterwards, with no KiCad GUI step.
- **Evidence:** `tests/test_gates.py::test_autoroute_apply_routes_fixture` green in `make verify`; the fixture's DRC report attached to the PR.
- **Use case:** Route a board (`docs/USE-CASES.md`).
- **Scope guard:** No routing heuristics of our own. No GUI automation. The generated-design path already works (`workcenter design --route`); this item is the board-file parser in front of it. Zones and arcs may be out of scope for the first cut and must be reported, not silently dropped.
- **Status:** ready

### 2. Board gates as a reusable GitHub workflow for board repositories
- **Promise:** A board repository that adds 1 workflow calling `ThyFriendlyFox/workspace-ee-test/.github/workflows/board-gates.yml@main` gets `workcenter gates` run on every PR, with the gates table in the job summary and a red check on a red gate.
- **Evidence:** A run link from a board repository, plus `tests/boards/pass-rc-divider` run through the workflow in this repository's CI.
- **Use case:** Review a board PR.
- **Scope guard:** No comments posted to the PR; the check and the summary are the output.
- **Status:** ready

### 3. Fabrication house rule sets
- **Promise:** `workcenter drc --fab jlcpcb <project>` applies `rules/jlcpcb.kicad_dru` on top of the project's rules, and the new fixture `fail-fab-jlcpcb` is GREEN without the flag and red with it.
- **Evidence:** `tests/test_gates.py::test_fab_rules_turn_fixture_red` green in `make verify`.
- **Use case:** Export for a fab.
- **Scope guard:** 1 fab in this item. The rule file format is KiCad's own `.kicad_dru`; no translation layer.
- **Status:** ready

### 4. MCP server for hosts that are not Claude Code
- **Promise:** `workcenter mcp` serves `doctor`, `gates`, `erc`, `drc`, `sim`, `export`, and `autoroute` as MCP tools over stdio, and the MCP inspector lists all 7 with their schemas.
- **Evidence:** An inspector screenshot and a test that drives the server with a scripted JSON-RPC session.
- **Use case:** Build another workcenter from this one.
- **Scope guard:** stdio only; no HTTP transport, no auth.
- **Status:** ready

## Later — candidates, not yet specced

- Copper pours in `kicadgen` — a zone per power net with `kicad-cli pcb drc --refill-zones`, so heater returns stop depending on 0.4 mm tracks.
- Pad-entry width check before routing — warn in `workcenter design` when a net class is wider than its narrowest pad allows.
- SIM gate from the schematic — export the SPICE netlist automatically and apply a stimulus template, so a project without a hand-written deck still gets a simulation.
- `workcenter new <name>` — scaffold a board project with the `.gitignore`, `sim/`, and a passing starter board.
- Publish the workcenter as an account-level Claude Code plugin — skills and the MCP server arrive in every cloud session without touching board repositories.
- BOM availability gate — `workcenter procure --strict` already fails on a line short of stock; a gate would run it before export. Needs a project-wide parts file first.
- Digi-Key API refresh for `procure` — re-read every Digi-Key row's breaks and stock through Product Information v4 with the user's own credentials, instead of page by page.
- STEP export in the EXPORT gate by default once the fixture proves it runs headless in CI within the time budget.

## Shipped

| Week | Feature | Release | Evidence |
|---|---|---|---|
| 2026-10-29 | kistack vendored with the `kistack` skill; `workcenter placement` runs its placement checks headless | unreleased | `tests/test_placement.py`; `third_party/kistack/VENDORED.md`; `DEVLOG.md` 2026-10-29 |
| 2026-10-27 | `workcenter procure` and the `procurement` skill: a schematic's BOM priced from a parts file, cheapest order per line, totals per supplier | unreleased | `tests/test_gates.py` (the fixture priced to the cent at 1 and 10 units; unmatched, unpriced and short-of-stock lines; the skip); the Last Hit parts lists; `DEVLOG.md` 2026-10-27 |
| 2026-10-27 | Wired schematics in `kicadgen` (`sch_wires`, `sch_rot`); `render` names parts drawn without a 3D body; `wrlgen` `leadless` and `gullwing` bodies | unreleased | `tests/test_kicadgen.py` and `tests/test_gates.py` (wired divider ERC-clean with its declared netlist and no parity warning; pin positions at each angle as KiCad's ERC reports them; the bare-part report); Last Hit v0.10's two schematics; `DEVLOG.md` 2026-10-27 |
| 2026-10-23 | `kicadgen` design-as-code generator; `workcenter design --route` headless autoroute for generated boards; `workcenter render`; `board-design` skill | unreleased | `tests/test_kicadgen.py` incl. the routed round trip; the first real board, GREEN in its own repository; `DEVLOG.md` 2026-10-23 |
| 2026-10-22 | Install the kit; `install.sh`; gates ERC, DRC, SIM, EXPORT; fixture boards; skills | unreleased | `make verify` green at the install commit; `DEVLOG.md` 2026-10-22 |

## Explicitly not doing

- Reverse engineering KiCad with REA or similar — KiCad is open source with an official IPC API and CLI. REA belongs to workcenters built on closed tools.
- GUI or screen automation of KiCad — every operation goes through `kicad-cli` or the IPC API.
- Bundling a patched KiCad — the workcenter installs the upstream PPA build or uses the upstream image.
- Installing `kicad-packages3d` by default — 3.3 GB for 3D models no gate reads.

## Queue changes

- 2026-10-22 — queue seeded at setup, 4 items, provisional.
- 2026-10-27 — `workcenter procure` shipped out of band: the user asked for every prototype's parts sourced from Digi-Key with the full cost, as a workcenter skill.
- 2026-10-27 — the Later item "`kicadgen` schematic layout" shipped out of band: the user found the Last Hit schematics unreadable (M51).
- 2026-10-23 — item 1 re-scoped: the generated-design half shipped out of band while building the first board; the remaining half is a `.kicad_pcb` reader in front of the same DSN writer.
- 2026-10-29 — kistack shipped out of band: the user asked for it in the workflow.
