# Changelog

All notable changes to EE Workcenter are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/) · Versioning: [SemVer](https://semver.org/).

## [Unreleased]
### Added
- `tools/kicadgen.py`: design a KiCad 10 schematic and board in Python from the installed libraries; writes project, schematic, board, Specctra DSN; merges a routed session.
- `workcenter design <design.py> [--route]`: build a design file, optionally route it headless with FreeRouting.
- `workcenter render <project>`: schematic, board top and bottom, 3D top and isometric images.
- `board-design` skill.
- `install.sh` installs librsvg (`rsvg-convert`) for PNG output.
- `install.sh`, gates ERC, DRC, SIM, EXPORT, fixture boards, skills, kit, CI, cloud environment setup script, Dockerfile (2026-10-22).
- `kicadgen`: parts on the bottom face (`pcb_layer`), free silkscreen text (`d.text`), design-rule overrides (`d.rules`), per-part zone connection (`zone_connect`).
- `kicadgen`: copper pours (`d.zone`), filled headless on write; the router sees them as planes.
- `kicadgen`: hand-routed copper (`d.track`, `d.via`) passed to the router as fixed wiring; `stitch_pads` and `reserve_vias` for ground vias beside pads.
- `kicadgen`: after routing, pour islands are read with KiCad's `pcbnew` module and stitched with vias; `workcenter design --route --rounds N` reserves a via beside what is left and routes again.
- `install.sh` creates the venv with `--system-site-packages` so the workcenter's Python sees `pcbnew`.
- `kicadgen`: project footprint libraries (`Design.footprint_dirs`, an `fp-lib-table` in the generated project, `footprint --lib NAME=DIR`); stadium outlines (corner radius up to half the short side); circle courtyards read as centre and radius (M24).
- `tools/wrlgen.py`: `connector-510` (M7 x 0.5 internal thread), `cartridge-510`, `pouch-cell`, `display-module` presets; material transparency.
- `kicadgen`: `Design.corner_radius` rounds the board corners (Edge.Cuts arcs, polygon boundary in the DSN, rounded default pour, corner-aware via check); `Design.model()` attaches a 3D body to a part's footprint.
- `tools/wrlgen.py`: parametric VRML bodies in KiCad's 0.1 inch units: `usb-c-vertical`, `threaded-stud`.
- `workcenter render` adds `board-3d-bottom.png`.
- `docs/CONFIGURATION.md` names the FreeRouting pin that `install.sh` has carried since the 1.9.0 pin (M21).
- `ee-agent-kit/MISTAKES.md` (every mistake, its cost, its process) and `ee-agent-kit/PROCESSES.md` (binding checklists P1 to P14); `make verify` checks that each mistake names an existing process and each process has a "Done when" line.
### Changed
- `install.sh` prints apt progress and runs it non-interactively; the KiCad download from the PPA is slow on GitHub runners and a silent step was cancelled as hung.
- `workcenter render` leaves the fabrication layer out of the 2D top image.
- `merge_ses` drops the router's echoes of fixed wires and splits a track where the router joined onto it.
- `autoroute` skill: the generated-design path is headless end to end; the hand-drawn path still supplies the DSN.
- `doctor` reports `rsvg-convert` and the KiCad symbol libraries.
### Deprecated
### Removed
### Fixed
- FreeRouting session coordinates are read at the scale the session's placement block implies, not the declared resolution.
- FreeRouting pinned to 1.9.0: 2.1.0 hangs after routing in proxied environments because its GitHub version check fails.
### Security
