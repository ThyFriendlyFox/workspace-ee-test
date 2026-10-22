---
name: Autoroute
description: Routes the unrouted nets of a KiCad board with FreeRouting through a Specctra DSN export and returns a session file for import.
---

# Autoroute

FreeRouting routes a board from a Specctra DSN file and writes a Specctra
session (`.ses`). `workcenter autoroute` runs the router headless. The 2
ends of the round trip still need KiCad itself: `kicad-cli` 10 has no
Specctra export, so the DSN comes from KiCad, and the session goes back
in through KiCad. See steps 1 and 5.

## When

- `workcenter drc` reports unconnected items and the human wants an
  automatic first pass.
- A board has placement done and no routing.

## Inputs

1. The project directory with a `.kicad_pcb` that has footprints placed
   and nets assigned.
2. `workcenter doctor` shows `freerouting ok` and `java ok`. Absent means
   the JAR is missing; `install.sh` downloads it.

## Steps

1. Get the DSN. In KiCad: File, Export, Specctra DSN, saved as
   `<project>/<name>.dsn`. In a cloud session without a display, ask the
   human for that file and pass its path with `--dsn`. Tracking item:
   DSN export and session import through the IPC API on
   `agent-kit/ROADMAP.md`.
2. Run `workcenter drc <project>`. Fix every error that is not an
   unconnected item. The router cannot fix clearance or courtyard
   violations in placement.
3. Run `workcenter autoroute <project> --passes 20`. Output:
   `build/route/<name>.ses`. Add `--threads N` to bound CPU use and
   `--timeout S` for large boards.
4. Read the record. `pass` means a session file exists. `skip` with "no
   Specctra DSN" means step 1 did not happen. `fail` means FreeRouting
   exited non-zero; read `details.stderr`.
5. Import the session into the board. In KiCad: File, Import, Specctra
   Session, pick the `.ses`, save. Without a display, hand the `.ses`
   path to the human with that instruction.
6. Run `workcenter drc <project>` again. The routed board must pass
   before anything else happens.

## Checks

- The DSN and SES files stay in `build/`, never in the repository.
- A routed board goes through `board-gates` before it is called done.
- Power nets routed as planes in the design are excluded from the
  router by placing zones first; the router respects zones in the DSN.
