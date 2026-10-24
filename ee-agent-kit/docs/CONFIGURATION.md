# Configuration

EE Workcenter reads environment variables and command-line flags. There
is no configuration file. Defaults apply when a variable is unset; an
unset variable never causes a failure.

| Platform | Path |
|---|---|
| Linux | `/opt/workcenters/ee` (install root), `/opt/workcenters/ee/env.sh` (generated, sourceable) |

## `install.sh`

| Field | Type | Default | Use |
|---|---|---|---|
| `WORKCENTER_ROOT` | path | `/opt/workcenters/ee` | Where the venv, the JAR, the manifest copy, and `env.sh` live. |
| `FREEROUTING_VERSION` | string | `1.9.0` | Release to download. 2.1.0 hangs after routing in a proxied session (landmine map). |
| `FREEROUTING_SHA256` | hex | pinned in the script | Expected JAR checksum. Empty skips the check with a warning. |
| `FREEROUTING_URL` | URL | GitHub release asset for the version | Alternate download location. |
| `REQUIRE_FREEROUTING` | `0`/`1` | `0` | `1` makes a failed JAR download fatal. CI sets `1`. |
| `SKIP_APT` | `0`/`1` | `0` | `1` skips the apt step entirely. |

## `tools/workcenter`

| Field | Type | Default | Use |
|---|---|---|---|
| `WORKCENTER_ROOT` | path | `/opt/workcenters/ee` | Locates the venv and the JAR. |
| `FREEROUTING_JAR` | path | `$WORKCENTER_ROOT/freerouting/freerouting.jar` | The autoroute engine. |
| `KICAD_CLI` | command | `kicad-cli` | The KiCad engine. |
| `NGSPICE` | command | `ngspice` | The simulation engine. |
| `JAVA` | command | `java` | Runs the JAR. |

| Flag | Commands | Default | Use |
|---|---|---|---|
| `--json` | all | off | Machine-readable output. |
| `--out DIR` | gates, erc, drc, sim, export, autoroute | `<project>/build` | Where reports and artifacts go. |
| `--strict` | gates, erc, drc, sim, export | off | Warnings fail the gate. |
| `--step` | gates, export | off | Also export a STEP model. |
| `--dsn FILE` | autoroute | `<project>/<name>.dsn`, then `build/route/<name>.dsn` | Specctra DSN exported from KiCad. Absent means the command skips. |
| `--passes N` | autoroute, design | `20` autoroute, `60` design | FreeRouting optimisation passes. |

## `tools/wrlgen.py`

| Preset | Flags | Default | Use |
|---|---|---|---|
| `usb-c-vertical OUT` | `--height H`, `--base W D H`, `--shell W D WALL` | 7.0; 9.9 6.2 1.6; 9.0 3.6 0.25 | Vertical USB-C receptacle body: plastic base, metal shell, tongue. |
| `connector-510 OUT` | `--collar D`, `--height H`, `--tab-radius R` | 9.5; 4.0; 4.0 | PCB-mount 510 battery connector: collar with an M7 x 0.5 internal thread, insulator, spring pin, four tabs. |
| `cartridge-510 OUT` | `--diameter D`, `--length L`, `--fill F` | 10.5; 52; 0.6 | 510 cartridge for assembly renders; z = 0 is the collar top, the thread reaches down into it. |
| `pouch-cell OUT` | `--size W D H` | 25 8 35 | Li-polymer pouch cell standing on its long edge. |
| `display-module OUT` | `--pcb W D T` | 38 12 1.2 | 0.91 in 128 x 32 OLED module lying face up. |
| `threaded-stud OUT` | `--major D`, `--pitch P`, `--height H`, `--tail D LEN`, `--shoulder D H` | 1.6; 0.35; 4.0; 0.7 1.6; 1.5 0.4 | Threaded contact stud in a through-hole pad; `--tail 0 0 --shoulder 0 0` for a bare threaded barrel. |

Every number is millimetres; the file is written in KiCad's VRML unit (0.1 inch).

## `tools/kicadgen.py`

| Command | Flags | Use |
|---|---|---|
| `pins LIB:SYMBOL...` | | Pin numbers, names, types and positions of library symbols. |
| `footprint LIB:FOOTPRINT...` | `--lib NAME=DIR` (repeatable) | Pads, layers, drills and courtyard; `--lib` reads a project `.pretty` folder. |
| `--threads N` | autoroute | engine default | FreeRouting thread count. |
| `--timeout S` | autoroute, design | `600` autoroute, `900` design | Kill the router after S seconds. |
| `--route` | design | off | Export the DSN, run FreeRouting, merge the session before writing. |
| `--width PX` | render | `1600` | Image width; the schematic PNG is twice that. |

## `tools/kicadgen.py`

| Field | Type | Default | Use |
|---|---|---|---|
| `KICAD_SYMBOL_DIR` | path | `/usr/share/kicad/symbols` | Symbol libraries to read. |
| `KICAD_FOOTPRINT_DIR` | path | `/usr/share/kicad/footprints` | Footprint libraries to read. |
| `FREEROUTING_JAR` | path | `/opt/workcenters/ee/freerouting/freerouting.jar` | Used by `route()`. |

## `environment/setup.sh`

| Field | Type | Default | Use |
|---|---|---|---|
| `WORKCENTER_REPO` | URL | this repository | Where the cloud environment clones from. |
| `WORKCENTER_REF` | branch or tag | `main` | What it checks out. |

<!-- Rules for these tables:
     · Every shipped option appears here — an undocumented option is a
       defect.
     · New options land in this table in the same PR that adds them.
     · Defaults shown here are the real defaults in code, not intended
       ones. -->
