---
name: Autoroute
description: Routes a board with FreeRouting headless; generated designs round-trip through Specctra DSN and SES automatically, hand-drawn boards supply the DSN.
---

# Autoroute

FreeRouting routes a board from a Specctra DSN file and writes a Specctra
session (`.ses`). There are 2 ways in:

- **A kicadgen design** (`design.py`, see the `board-design` skill):
  `workcenter design design.py --route` writes the DSN itself, runs the
  router, and merges the session into the generated board. Fully headless.
- **A hand-drawn board**: `kicad-cli` 10 has no Specctra export, so the
  DSN comes from KiCad (File, Export, Specctra DSN) and the session goes
  back in through KiCad (File, Import, Specctra Session).

## When

- `workcenter drc` reports unconnected items on a placed board.
- A generated design is ready for copper.

## Inputs

1. The project directory with a `.kicad_pcb` that has footprints placed
   and nets assigned, or the `design.py` that generates it.
2. `workcenter doctor` shows `freerouting ok` and `java ok`.

## Steps, generated design

1. `workcenter drc .` first. Fix courtyard overlaps and pad clearance in
   the placement; the router cannot.
2. `workcenter design design.py --route --passes 20`. The command prints
   the segment and via counts. Output: `build/route/<name>.dsn`, `.ses`,
   `freerouting.log`, and the routed `.kicad_pcb`. 20 passes on a
   40-part board take 1 to 5 minutes.
3. `workcenter drc .` reports what stayed unrouted. Unrouted nets mean a
   track width that cannot enter a pad, a crowded region, or a part
   placed where the net cannot reach it. Change the design, run again.
   Do not lower clearances.
4. `workcenter gates .` must be GREEN before the board is called routed.

## Steps, hand-drawn board

1. Export the DSN from KiCad to `<project>/<name>.dsn` or pass `--dsn`.
2. `workcenter autoroute . --passes 20` writes `build/route/<name>.ses`.
3. Import the session in KiCad and save. Without a display, hand the
   `.ses` path to the human with that instruction.
4. `workcenter drc .` again.

## Known behaviour

- FreeRouting writes session coordinates at 10 times the declared
  resolution. The merge takes the scale from the session's placement
  block, which echoes component positions it knows. Trust the DRC, not
  the resolution token.
- The engine is FreeRouting 1.9.0. Release 2.1.0 checks GitHub for
  updates and, when that fails, sleeps forever after routing without
  saving the session; `install.sh` pins 1.9.0 for that reason. Pass
  `--passes` to trade time for completion.
- Per-net widths and vias come from `d.net_classes`; FreeRouting honours
  them through DSN classes. The DRC checks them through the project's
  net class patterns.

## Checks

- DSN, SES, and the log stay in `build/`, never in the repository.
- A routed board goes through `board-gates` before it is called done.
- The `.kicad_pcb` is regenerated from the design, never patched by hand.
