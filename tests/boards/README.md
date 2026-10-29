# Fixture boards

These projects are the tests of the gates. Each one exists to make 1 gate
behave in a known way.

| Project | Expected | Why |
|---|---|---|
| `pass-rc-divider` | GREEN on `workcenter gates` | A 2-resistor divider with an RC filter. Schematic, board, and a sim deck with bounds. |
| `fail-drc-clearance` | ERC pass, DRC fail with a `clearance` violation | The same board with 1 track moved inside the clearance of a pad. |
| `fail-sim-spec` | SIM fail on the `vout` bound | The divider deck with bounds that the circuit cannot meet. No board. |
| `fail-fab-sierra` | GREEN on `workcenter gates --strict`, DRC fail with `--fab sierra-circuits-web` (`annular_width`, `text_thickness`) | The divider with a 0.6/0.3 mm via (0.15 mm ring, under Sierra's 6 mil) on a bottom-face return of VOUT, and a legend label stroked 0.10 mm (under 5 mil). |

Symbols and footprints are embedded in the files, so no library tables are
needed to run them. `build/` output is ignored by git.

`kicad-cli` writes a `<name>.kicad_prl` next to the project when it runs.
It is a KiCad side file with no design content and is ignored by git.
