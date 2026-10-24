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
     SOT-23 and 0603, 0.5 mm for 0402, 0.4 mm for TSSOP. Put the ADC sense
     pin behind a series resistor so it is not on the heavy net; a sense
     tap may be drawn thinner than its class with `width=` on `d.track`.
   - `pcb_layer="B.Cu"` puts a part on the bottom face. The generator
     mirrors it the way KiCad does. On the back face a part at rotation 0
     has its pad 1 on the left and its pads' y mirrored: a SOT-23 has gate
     bottom-left, source top-left, drain right. Read positions from a DRC
     report (`workcenter drc`) rather than from memory before hand-routing
     to a back-side pad.
   - `corner_radius=` on `Design` rounds the board corners; the outline becomes
     four lines and four arcs, the router's boundary and the default pour
     follow them, and the via check knows the corners. Pads near a corner
     need `edge_clearance` from the arc, not from the rectangle. Half the
     short side makes a stadium (round ends, two arcs meeting).
   - A part the library lacks gets a project footprint: a `.pretty` folder
     in the project, named in `d.footprint_dirs = {"Name": path}` and used
     as `"Name:Footprint"`. Read it with
     `python3 tools/kicadgen.py footprint --lib Name=path Name:Footprint`
     before placing; the generated project gets an `fp-lib-table` for it.
   - `d.keepout(d.circle(cx, cy, r), layers=("F.Cu",), name="collar")` keeps
     tracks and vias out of an area (under grounded metal, a mounting
     screw, an antenna). KiCad gets a rule area, the router a keepout, and
     the generator's own vias stay out of it.
   - `d.model(ref, "${KIPRJMOD}/models/x.wrl")` gives a part a 3D body for the
     renders and the STEP export when the library has none (vertical
     receptacles, wire pads with a stud). `python3 tools/wrlgen.py` writes
     parametric bodies (`usb-c-vertical`, `threaded-stud`) in KiCad's VRML
     units; keep them in the project under `models/` with the command that
     made them.
   - `d.text(label, x, y, "F.SilkS", size, thickness)` for contact labels.
     Below 0.8 mm text, set `d.rules = {"min_text_height": ..,
     "min_text_thickness": ..}` or the DRC flags every label.
   - `d.zone("GND", layers=("F.Cu", "B.Cu"), connect="solid")` for a
     ground pour on both faces. The router treats it as a plane and routes
     no ground track; KiCad fills it when the design is written. Prefer
     solid connections on a dense board: thermal spokes get starved
     between 0402 pads and the DRC reports each one.
3. **Place.** Keep courtyards apart; read them with the `footprint`
   command. Group by current: heater copper short, connectors at edges,
   decoupling beside the IC on the same face as its pins. Rotate with
   `pcb_rot`, 90 degrees at a time. Leave the router room: 0402 columns
   2.3 mm apart let one track pass, rows 1.7 mm apart let a via sit between
   them. A TSSOP's pads block its sides; signals reach them from under the
   body or from the row ends.
4. **Generate and check.** `workcenter design design.py` then
   `workcenter erc .` and `workcenter drc .`. Fix every error except
   unconnected items before routing. Courtyard overlaps and pad clearance
   are placement mistakes the router cannot fix.
5. **Route.** `workcenter design design.py --route --passes 60`. The
   command prints what the router did and which ground pads ended up on an
   island; `workcenter drc .` lists what stayed unrouted. FreeRouting
   stops early when it decides a connection cannot be made; more passes do
   not help. For each one left:
   - A width that cannot enter a pad, a crowded region, or a board too
     small: change the design, not the router settings.
   - A link the router could not find but a person can: draw it with
     `d.track(net, [(x, y), ...], layer)` and `d.via(net, x, y)` at the
     end of `build()`. The router keeps hand-routed copper and routes
     around it. Draw the heavy loop first (battery feed, heater return),
     then the taps and gate drives, one net at a time, with
     `workcenter drc .` between rounds: the DRC names the pad or track
     each slip touches. End tracks on pad centres. A part moved in the
     same change is regenerated and its pads read before its tracks are
     written. A long hand route is a wall on its layer: list the pads it
     cuts off from their nets first, and move a part rather than draw a
     lane that leaves one with no way in.
   - A ground pad cut off from the pour: the design command already
     routes again with a via reserved beside it (`--rounds`); if it still
     reports the island, move the walling track or the part.
6. **Gates.** `workcenter gates .` until GREEN. `workcenter render .` for
   the images: schematic, both faces, 3D top, bottom and isometric. Commit
   `design.py`, any `models/*.wrl`, and the generated `.kicad_*` files
   together; the generated files are what KiCad opens.

## Checks

- `python3 tools/kicadgen.py pins` was run for every symbol with more than
  2 pins before nets were assigned.
- ERC: 0 errors and 0 warnings. Library-table warnings are suppressed in
  the generated project because every symbol and footprint is embedded.
- DRC: 0 errors. Silkscreen warnings near board edges are acceptable;
  clearance and courtyard warnings are not.
- The design file is the only hand-written source; nobody edits the
  generated KiCad files. Hand-routed copper lives in `build()` too.
- The README names each part choice and the reason, and lists every
  external contact with its net, pad and position.
