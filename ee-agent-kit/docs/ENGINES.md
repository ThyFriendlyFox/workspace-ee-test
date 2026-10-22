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

Java autorouter. Powers the autoroute command: Specctra DSN in, Specctra
session out. Needs Java 21. `install.sh` downloads the pinned release
JAR and checks its SHA-256; a blocked download leaves the engine absent
and `doctor` reports `degraded`. `kicad-cli` 10 cannot export a DSN, so
the command takes one exported from KiCad (`<project>/<name>.dsn` or
`--dsn`) and skips loudly without it.

```sh
FREEROUTING_JAR=/opt/workcenters/ee/freerouting/freerouting.jar   # default
JAVA=java
```

Neither end of the round trip is headless yet: the DSN export and the
session import both happen in KiCad. ROADMAP item 1 adds both through
kipy.

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
