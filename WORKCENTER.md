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
| FreeRouting | 1.9.0 | `workcenter design <design.py> --route` (generated boards, headless); `workcenter autoroute <project> [--dsn file]` (hand-drawn boards, DSN from KiCad) | `install.sh` (GitHub release, SHA-256 pinned; 2.1.0 hangs after routing when its GitHub version check cannot succeed) |
| kicad-python (kipy) | 0.8 | `/opt/workcenters/ee/venv/bin/python` | `install.sh` (PyPI) |
| librsvg | 2.58 | `rsvg-convert` (SVG to PNG for `workcenter render`) | `install.sh` (Ubuntu 24.04 archive) |
| FFmpeg | 6.1 | `ffmpeg` (the turning GIF of `workcenter render --views spin`) | `install.sh` (Ubuntu 24.04 archive) |
| kicadgen | this repo | `workcenter design <design.py> [--route]`; `python3 tools/kicadgen.py pins|footprint` | `install.sh` (part of the checkout) |
| workcenter CLI | this repo | `workcenter` | `install.sh` (symlink to `tools/workcenter`) |
| kistack | `641ade9` | `.claude/skills/kistack/SKILL.md` routes to `third_party/kistack/skills/`; `workcenter placement <check> <board> [args]` runs its placement checks | the checkout (vendored, `third_party/kistack/VENDORED.md`); shapely, numpy and pygerber by `install.sh` (PyPI) |

## Skills

| Skill | Use when |
|---|---|
| `attached-repos` | The session holds more than 1 repository. Run first. |
| `board-design` | A board is designed from a spec, as a Python design file built from the KiCad libraries. |
| `board-gates` | A board must pass ERC, DRC, simulation, and export. The fix loop. |
| `autoroute` | A board has unrouted nets and FreeRouting should route them. Headless for generated designs. |
| `simulate` | A circuit must meet a measurable spec before layout. |
| `blog-post` | A human asks for a public write-up of recent work. |
| `procurement` | A human asks what a board costs, for its parts list, or to order its parts. |
| `kistack` | Placing parts, reviewing a schematic, a layout or the Gerbers, choosing a part's derating, a footprint or symbol, or a panel: it names the kistack skill for the step, and where this workcenter's rules win. |

## Gates

| Gate | Command | Pass condition | Runs before |
|---|---|---|---|
| ERC | `workcenter erc <project>` | 0 errors in the ERC report | layout |
| DRC | `workcenter drc <project>` | 0 errors, 0 unconnected items, 0 parity errors | export |
| SIM | `workcenter sim <project>` | every `sim/*.cir` runs clean and every `*.expect.json` bound holds | export |
| EXPORT | `workcenter export <project>` | gerbers, drill, BOM, schematic PDF produced | hand-off to fabrication |
| ALL | `workcenter gates <project>` | the 4 gates above in order, none red | a board is called done |

Not a gate, but part of every hand-off: `workcenter render <project>` writes
the schematic, board top and bottom, and 3D images into `build/render/`, and
every layer that has something on it into `build/render/layers/` (one PNG per
layer with the outline, bottom layers seen from below) with an overview sheet,
`build/render/layers.png`. `--views spin` adds `build/render/board-spin.gif`,
the 3D board turning once round (`--spin-frames`, `--spin-tilt`, `--spin-zoom`,
`--spin-pivot`;
a minute or two of frames). `--views` takes any of schematic, 2d, 3d, layers,
spin, or all. Its summary names every part the 3D views draw without a body
(a footprint naming a model that is not on disk); `--strict` fails on one.
A finished board version shows its layer sheets and a turning
GIF of every board and its assembly in its README (`PROCESSES.md` P23), and
a wired schematic someone has read (`sch_wires`, P24).

Not a gate either: `workcenter procure <project> --parts parts.csv` prices the
schematic's BOM from a parts file (supplier, supplier number, price breaks,
stock, date and URL per part, items off the board too) and writes
`build/procure/bom.csv`, `parts.csv` and `parts.md`: the orderable list with
the cheapest order per line and totals per supplier for each `--boards`
count. It fails on a line with no part or no price; `--strict` also on a
line short of stock or a price older than 90 days (`PROCESSES.md` P25).

Not a gate: `workcenter placement <check> <board> [args]` runs one of
kistack's layout-placement checks on the board file (`pin_sides`,
`placement_audit`, `route_check`, `local_search`, `group_search`) with KiCad's
Python module reading the board, where kistack itself needs a KiCad server.
Run `placement_audit` and `route_check` on each IC whose parts moved, before
routing (the `kistack` skill). `move` is refused: a generated board changes in
its design file.

A project may add gates. It may not remove these.

## Paths

| Purpose | Path |
|---|---|
| Install root | `/opt/workcenters/ee` |
| Engine environment | `/opt/workcenters/ee/env.sh` |
| Tool cache | the session scratchpad; the engines write nothing outside the output directory |
| Project output | `<project>/build/` (reports, `fab/`, `sim/`, `route/`, `render/`) |

## Project requirements

- `.gitignore` entries: `build/`, `*.kicad_prl`
- Files: one `<name>.kicad_pro` with `<name>.kicad_sch` and `<name>.kicad_pcb` beside it
- Optional: `design.py` exposing `build() -> kicadgen.Design`, the source the KiCad files are generated from
- Optional: `sim/<deck>.cir` with `sim/<deck>.expect.json` for the SIM gate
