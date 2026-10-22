---
name: Simulate
description: Runs ngspice on the project's sim decks and checks measured values against the bounds in the matching expect file.
---

# Simulate

The SIM gate runs every `sim/*.cir` deck in the project with ngspice in
batch mode and compares printed values against `sim/<deck>.expect.json`.
A circuit meets its spec when every bound holds.

## When

- A circuit has a measurable spec: a voltage, a gain, a cutoff, a
  settling time.
- Before layout, so the values on the schematic are right before they
  become copper.

## Inputs

1. `sim/<deck>.cir`: an ngspice batch deck. It ends with a `.control`
   block that prints the values under test, then `.endc` and `.end`.
2. `sim/<deck>.expect.json`: `{ "<name>": { "min": <n>, "max": <n> } }`.
   A name is a variable the `.control` block prints as `name = value`.

## Steps

1. Export the netlist from the schematic when the deck should follow the
   schematic: `kicad-cli sch export netlist --format spice --output
   sim/<name>.net <name>.kicad_sch`. Keep the exported netlist and the
   hand-written stimulus apart: the deck does `.include <name>.net` and
   adds sources, analysis, and the `.control` block.
2. Write the `.control` block so each value under test is 1 line:
   ```
   .control
   op
   let vout = v(out)
   print vout
   .endc
   .end
   ```
   `print` writes `vout = 2.500000e+00`, which the gate parses.
3. Write `sim/<deck>.expect.json` with the bounds from the spec, not from
   the first result.
4. Run `workcenter sim <project>`. The record has `decks.<deck>.measures`
   (every printed value), `decks.<deck>.checks` (bound by bound), and
   `failures`.
5. A failed bound means the circuit misses the spec. Change component
   values in the schematic, re-export the netlist, re-run. Do not widen
   the bound to pass.
6. An `errors` list that is not empty means ngspice rejected the deck.
   Read `build/sim/<deck>.log`; the line number in the message points at
   the deck.

## Checks

- Every bound in an expect file traces to a line in the spec or the
  schematic notes.
- A deck with no expect file still has to run clean; it proves nothing
  about the spec, and the report says so.
- `build/sim/` is not committed.
