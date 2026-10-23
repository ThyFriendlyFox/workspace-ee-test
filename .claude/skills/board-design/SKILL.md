---
name: Board Design
description: Writes a KiCad 10 schematic and board as a Python design file built from the installed libraries, routes it headless, and iterates until the gates are GREEN.
---

# Board Design

The agent designs a board as code. A design file exposes `build()` that
returns a `kicadgen.Design`: parts from the KiCad libraries, nets as
names, positions on the board. `workcenter design` turns it into a KiCad
project and routes it with FreeRouting. No GUI at any step.

## When

- A new board, from a spec to fabrication outputs.
- A board change that is easier to express in Python than by hand in
  KiCad: moving a block, swapping a part, adding a channel.

## Inputs

1. A spec: what the board must do, the body it must fit, the connectors.
2. `python3 tools/kicadgen.py pins Lib:Symbol` and
   `python3 tools/kicadgen.py footprint Lib:Footprint` to read pins, pad
   numbers, and courtyards before placing anything.
3. The `attached-repos` roles: the design file lives in the project
   repository, never in the workcenter.

## Steps

1. **Pick parts from the libraries.** Check each symbol and footprint
   exists first; several common modules are not in KiCad's libraries.
   Record the choice and the reason in the project README.
2. **Write `design.py`.** One `d.add(ref, "Lib:Symbol", value, "Lib:Footprint",
   sch_at=(x, y), pcb_at=(x, y), nets={pin: net})` per part. Rules:
   - Power nets go in `d.power_nets` and get power symbols. Nets with no
     power-output pin (GND, VBUS from a connector) go in `d.flagged_nets`
     for a PWR_FLAG. A net that already has a power-output pin must not be
     flagged: two drivers is an ERC error.
   - Stacked hidden connector pins (USB-C VBUS A4/A9/B4/B9, GND A1/B1/A12/
     B12) all need the net, or their pads stay open.
   - Every unused pin is left out of `nets`; the generator places a
     no-connect and names its pad net the way KiCad does, so parity passes.
   - Schematic positions on the 1.27 mm grid, as multiples of 2.54.
   - `d.net_classes` for heavy nets. The widest track that enters a pad is
     the pad pitch minus the pad width minus 2 x clearance: 0.6 mm for
     SOT-23 and 0603, 0.4 mm for TSSOP. Put the ADC sense pin behind a
     series resistor so it is not on the heavy net.
3. **Place.** Keep courtyards apart; read them with the `footprint`
   command. Group by current: heater copper short, connectors at edges,
   decoupling beside the IC. Rotate with `pcb_rot`, 90 degrees at a time.
4. **Generate and check.** `workcenter design design.py` then
   `workcenter erc .` and `workcenter drc .`. Fix every error except
   unconnected items before routing. Courtyard overlaps and pad clearance
   are placement mistakes the router cannot fix.
5. **Route.** `workcenter design design.py --route --passes 40`. The
   command prints unrouted nets. More than a few unrouted means a width
   that cannot enter a pad, a crowded region, or a board too small. Change
   the design, not the router settings.
6. **Gates.** `workcenter gates .` until GREEN. `workcenter render .` for
   the images. Commit `design.py` and the generated `.kicad_*` files
   together; the generated files are what KiCad opens.

## Checks

- `python3 tools/kicadgen.py pins` was run for every symbol with more than
  2 pins before nets were assigned.
- ERC: 0 errors and 0 warnings. Library-table warnings are suppressed in
  the generated project because every symbol and footprint is embedded.
- DRC: 0 errors. Silkscreen warnings near board edges are acceptable;
  clearance and courtyard warnings are not.
- The design file is the only hand-written source; nobody edits the
  generated KiCad files.
- The README names each part choice and the reason.
