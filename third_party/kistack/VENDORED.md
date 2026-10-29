# kistack, vendored

KiStack by American Embedded: hand-written agent skills for KiCad (schematic
wiring and review, placement with checking scripts, layout, PCB review, BOM
decisions, footprints, symbols, kicad-cli exports, Gerber review, KiKit
panelizing, Blender product renders).

| | |
|---|---|
| Source | https://github.com/American-Embedded/kistack (GitHub also shows it as BackplaneWorks/kistack) |
| Commit | `641ade9041bb0844c4530dfff11010eef30919af`, 2026-10-26, "Merge pull request #13 … canonical-save-milestones" |
| Copied | 2026-10-29: `skills/`, `tests/`, `LICENSE`, `README.md`, `.gitignore`, byte for byte |
| Left out | `img/american-embedded-logo.png`: the licence says the logo may not be reproduced without written permission. The README's image link is therefore broken here. |
| Licence | `LICENSE`: the MIT grant and disclaimer, copyright 2026 American Embedded, LLC, plus the logo sentence |

Nothing under this folder is edited. The workcenter's changes live outside it:

- `tools/kistack_board.py` stands in for `skills/layout-placement/scripts/ipc_board.py`, reading the
  board file with KiCad's Python module instead of a KiCad server, and
  `workcenter placement <check> <board> [args]` runs the read-only checks with it.
- `.claude/skills/kistack/SKILL.md` says which kistack skill to read at which step here, what runs
  in this environment, and where the workcenter's own rules win.

## Updating

1. Clone the source at the new commit and read every changed `SKILL.md` and script before copying:
   agents follow these files.
2. Copy the same paths over this folder (still without the logo), remove `__pycache__`, and update
   the commit row above.
3. Run `make verify`. `tests/test_placement.py` runs the placement checks on kistack's own synthetic
   board through the stand-in; a change to what `ipc_board.load` returns shows up there.
4. Re-read `.claude/skills/kistack/SKILL.md` against the new skills and fix any override that no
   longer matches.
