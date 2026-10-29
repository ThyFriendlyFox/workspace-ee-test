# Engines

An engine is the external program a gate runs. EE Workcenter has 3
engines and 1 planned. Select an engine's binary with its environment
variable (`docs/CONFIGURATION.md`); the gate that uses it is fixed.

## kicad-cli

KiCad 10's command line. Powers the ERC, DRC, and EXPORT gates and the
DSN export step of autoroute. Headless; needs no display. Installed from
the KiCad PPA by `install.sh`, or present in the official
`kicad/kicad:10.0` image.

```sh
KICAD_CLI=kicad-cli   # default
```

Reports are JSON (`--format json`). Exit code 5 with
`--exit-code-violations` means "ran, found violations"; the CLI parses
the report rather than trusting the code.

## ngspice

Batch SPICE simulator. Powers the SIM gate. Runs `sim/*.cir` decks with
`ngspice -b -o <log>`; the gate parses `name = value` lines that the
deck's `.control` block prints. Installed from the Ubuntu archive.

```sh
NGSPICE=ngspice       # default
```

## FreeRouting

Java autorouter, release 1.9.0. Powers `workcenter design --route` and the
autoroute command: Specctra DSN in, Specctra session out. Needs Java 21.
`install.sh` downloads the pinned release JAR and checks its SHA-256; a
blocked download leaves the engine absent and `doctor` reports
`degraded`. Release 2.1.0 is not used: it checks GitHub for updates at
start and never finishes a job when that call fails, which it does in
every proxied environment. For a hand-drawn board `kicad-cli` 10 cannot
export a DSN, so the autoroute command takes one exported from KiCad
(`<project>/<name>.dsn` or `--dsn`) and skips loudly without it.

```sh
FREEROUTING_JAR=/opt/workcenters/ee/freerouting/freerouting.jar   # default
JAVA=java
```

For a kicadgen design the whole round trip is headless: `tools/kicadgen.py`
writes the DSN from the design model (0.1 um units, y up, pads as rect or
circle padstacks, non-plated holes as unconnected pins, net classes with
their own widths and vias) and merges the session back into the board.
FreeRouting writes session coordinates at 10 times its declared
resolution; the merge takes the scale from the session's placement block.
For a hand-drawn `.kicad_pcb` both ends still happen in KiCad; reading an
arbitrary board file into the DSN writer is ROADMAP item 1.

## kicadgen

`tools/kicadgen.py` is not an engine but the way designs reach the
engines without a GUI. It parses the KiCad symbol and footprint libraries
(`KICAD_SYMBOL_DIR`, `KICAD_FOOTPRINT_DIR`), flattens derived symbols,
strips the KiCad 10 library tokens the 9.0 file formats do not know, and
writes the schematic (stub wires and labels, power symbols, PWR_FLAG
pairs, no-connects with KiCad's `unconnected-(...)` pad nets), the board
(footprint instances with rotation, nets, outline, segments, vias), and
the project file (net classes, severities for the embedded-library
warnings). `workcenter design <design.py> [--route]` drives it.

## librsvg

`rsvg-convert` turns the SVGs that `kicad-cli` exports into PNGs for
`workcenter render`. Absent, the render command keeps the SVGs and says
which PNGs it skipped. It also flattens the layer overview sheet, an SVG
that places the per-layer PNGs in a grid.

## FFmpeg

`ffmpeg` joins the 3D frames that `kicad-cli pcb render` draws into the
turning GIF of `workcenter render --views spin`, with a palette made from
the frames themselves. Absent, the GIF is skipped with the reason; nothing
else needs it, and the CLI stays standard-library Python.

## kistack placement checks

Not an engine of its own: kistack's layout-placement scripts
(`third_party/kistack/skills/layout-placement/scripts`), run by
`workcenter placement` in the venv with shapely and numpy. kistack reads the
board through the IPC API, which needs a KiCad server with the board open;
KiCad 10.0's `kicad-cli` has no API server, so `tools/kistack_board.py`
answers the same `ipc_board.load()` from the board file with pcbnew: pads as
KiCad's own polygons, courtyards, the outline, netted copper shapes, and the
net classes and clearance overrides kistack's rules module asks for. The
scripts themselves are unchanged. Absent shapely or pcbnew, the command
skips (exit 2) and says which.

```sh
KISTACK_DIR=<checkout>/third_party/kistack   # default
```

## pygerber

`pygerber raster-2d <layer> -o <png> -d 1000 -s copper_alpha` draws one
Gerber layer as an image, for kistack's Gerber review. Release 2.4.3, from
PyPI into the venv. kistack's skill names the 3.x command
(`pygerber gerber convert png`); 2.4.3 is the newest stable release and has
`raster-2d` instead. No gate runs it yet.

## kipy (planned)

`kicad-python`, the official IPC API client, is installed in the venv
but no gate uses it yet. It needs a running KiCad, which under Xvfb is
possible in the cloud environment (`xvfb` is installed). First use:
session import (ROADMAP item 1).

## Writing a new engine

A new engine PR includes all of these:

1. The install step in `install.sh`, idempotent, with a pinned version
   and a checksum where the source allows one.
2. A `doctor` check in `tools/workcenter` with `required` set honestly.
3. A `gate_<name>` function returning a `Result`, with `skip` when the
   engine is absent and `error` when it crashes.
4. 2 fixture boards under `tests/boards`: 1 that the gate passes, 1 that
   it fails for a named reason, and the tests that assert both.
5. Its row here, its variables in `docs/CONFIGURATION.md`, its gate in
   `WORKCENTER.md`, and the skill that tells the agent when to run it.
