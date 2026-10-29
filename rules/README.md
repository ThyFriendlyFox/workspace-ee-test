# Fabrication house rule sets

Each file is one fab's published limits as KiCad design rules (`.kicad_dru`, KiCad's own format), with
the page and the words each rule comes from. A project uses one in two ways:

- **For good:** set `fab = "<name>"` in the design file (`kicadgen.Design.fab`). The board's own
  minimums (`board_rules()`) rise to the fab's board-wide limits where they were looser, so the via
  check before routing (M46) refuses a via the fab would. `workcenter design` copies the file's layer
  and condition rules into the project as `<name>.kicad_dru`, which KiCad's DRC, and so
  `workcenter gates`, reads with the project.
- **Once:** `workcenter drc --fab <name> <project>` or `workcenter gates --fab <name> <project>` does the
  same on a copy for that run: the copy's minimums raised, the layer and condition rules after the
  project's own. Nothing in the project changes.

A fab's limits only add floors. In KiCad's DRC a custom rule overrides the board's own constraints and
every net class's, so a board-wide rule here (no layer, no condition) would put a 0.2 mm net class
clearance down to the fab's 4 mil, and a stricter board minimum (a 0.25 mm hole) down to the fab's. The
workcenter therefore never copies a board-wide rule into a project: it carries it as the board's own
minimum, and raises each rule it keeps to the board's own setting where that is stricter
(`kicadgen.fab_project_rules`; M62).

`<name>` is a file name here without `.kicad_dru`, or a path to any `.kicad_dru`.

| File | Fab and service | Read |
|---|---|---|
| `sierra-circuits-web.kicad_dru` | Sierra Circuits (Protoexpress), Web PCB: the online order, "Standard PCBs", IPC-6012 Class 2 | 2026-10-29 |

## Sierra Circuits, Web PCB

Checked: trace width and air gap 4 mil (0.1016 mm), finished hole 6 mil (0.1524 mm), annular ring 6 mil
(0.1524 mm), inner-layer drill to copper 13 mil (0.3302 mm) for plated and non-plated holes, legend
text stroke 5 mil (0.127 mm).

Sierra publishes these too, and KiCad's rule language cannot check them here: the legend's 5 mil applies
to silkscreen lines and arcs as well (KiCad's own footprints draw silkscreen at 0.12 mm, under it); a
3 to 4 mil solder mask dam for green (5 mil for black and blue); at most 100 holes a square inch; a 20 mil
inside radius and 40 mil width for notches, cutouts and slots; 0.8 mm boards held to ±10 %.

Not found on Sierra's pages, so not checked by this file and left to the board's own rules: copper to a
routed edge, copper to a non-plated hole on the outer layers, hole to hole, silkscreen text height and
clearance to pads, solder mask expansion. Their rigid-PCB "Standard" tier is looser (4 mil hole, 4 mil
ring) and is a different order; the pages also disagree in places (a "2 mil trace/space" card, a 5 mil
"preferred" ring). Ask Sierra before relying on anything looser than this file.
