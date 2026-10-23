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
### Changed
- `autoroute` skill: the generated-design path is headless end to end; the hand-drawn path still supplies the DSN.
- `doctor` reports `rsvg-convert` and the KiCad symbol libraries.
### Deprecated
### Removed
### Fixed
- FreeRouting session coordinates are read at the scale the session's placement block implies, not the declared resolution.
- FreeRouting pinned to 1.9.0: 2.1.0 hangs after routing in proxied environments because its GitHub version check fails.
### Security
