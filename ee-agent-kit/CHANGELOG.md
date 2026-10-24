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
- `PROCESSES.md` P18 (firmware that drives power) with M32; `board-design` skill: ground corridors against split pours.
- `.claude/settings.json`: a PreToolUse hook (`tools/hooks/no_cd.py`) refuses a Bash command that runs `cd` (P8, M31).
- `tools/hooks/install_hooks.py`: puts the no-cd hook into a Claude Code settings file, user-wide by default, merged and idempotent; run by hand, never by `install.sh`. `workcenter doctor` reports whether the user-wide hook is there (M35).
- `kicadgen`: keep-out areas (`Design.keepout(polygon, layers, name)`, with `Design.circle(cx, cy, r)` for round ones): a KiCad rule area with no tracks or vias, a Specctra keepout for the router, and a refusal in the via check.
- `kicadgen`: `Design.corner_radius` rounds the board corners (Edge.Cuts arcs, polygon boundary in the DSN, rounded default pour, corner-aware via check); `Design.model()` attaches a 3D body to a part's footprint.
- `tools/wrlgen.py`: parametric VRML bodies in KiCad's 0.1 inch units: `usb-c-vertical`, `threaded-stud`.
- `workcenter render` adds `board-3d-bottom.png`.
- `kicadgen`: `Design.check_vias()` lists every via that hits a pad or track of another net on any layer, another via, a keep-out (by name) or the board edge; `workcenter design` prints the list before routing and exits 1 when it is not empty (M40, M41).
- `tools/hooks/no_script_test_edits.py`: a PreToolUse hook that refuses a Bash command writing under `tests/` by script (P9 step 6, M43).
- `PROCESSES.md` P21 (moving files in a project): self-relative paths listed before the move, every README command run after it, each folder diffed against its source commit (M44).
- `kicadgen`: four-layer (and any even count) boards: `Design.copper_layers` adds `In1.Cu`.. with a 1.6 mm stackup; `Design.plane_layers` gives an inner layer whole to a pour, which the router never sees; through pads and vias carry copper on every routing layer in the DSN; island stitching lands vias on any layer and keeps clear of other nets' copper on the layers a via passes.
- `docs/CONFIGURATION.md` names the FreeRouting pin that `install.sh` has carried since the 1.9.0 pin (M21).
- `ee-agent-kit/MISTAKES.md` (every mistake, its cost, its process) and `ee-agent-kit/PROCESSES.md` (binding checklists P1 to P21); `make verify` checks that each mistake names an existing process and each process has a "Done when" line.
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
- `kicadgen`'s via check treats a non-plated hole as board edge, as the DRC does; island stitching had put a via 0.2 mm from a receptacle's peg hole (M26).
- Island stitching after routing keeps its vias out of keepouts; one keepout check (`Design.in_keepout`) now serves both via placers (M30).
- The router sees a non-plated hole grown to the board-edge clearance the DRC applies to it, not the hole clearance (M33).
- Island stitching runs once per poured net, not once per zone: a net with two zones got two vias on one spot (M37).
- A custom pad on the bottom face is mirrored with its shapes, not only its position; its size is read from its shapes, not its anchor (M38).
- The generator's pad boxes leave out paste-only apertures, and measure a round pad as a circle, not as its box.
### Security
