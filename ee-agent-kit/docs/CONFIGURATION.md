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
| `FREEROUTING_VERSION` | string | `2.1.0` | Release to download. |
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
