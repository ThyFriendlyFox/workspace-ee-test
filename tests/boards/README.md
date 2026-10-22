# Fixture boards

These projects are the tests of the gates. Each one exists to make 1 gate
behave in a known way.

| Project | Expected | Why |
|---|---|---|
| `pass-rc-divider` | GREEN on `workcenter gates` | A 2-resistor divider with an RC filter. Schematic, board, and a sim deck with bounds. |
| `fail-drc-clearance` | ERC pass, DRC fail with a `clearance` violation | The same board with 1 track moved inside the clearance of a pad. |
| `fail-sim-spec` | SIM fail on the `vout` bound | The divider deck with bounds that the circuit cannot meet. No board. |

Symbols and footprints are embedded in the files, so no library tables are
needed to run them. `build/` output is ignored by git.

`kicad-cli` writes a `<name>.kicad_prl` next to the project when it runs.
It is a KiCad side file with no design content and is ignored by git.
