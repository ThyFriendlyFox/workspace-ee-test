# VERIFICATION.md — one command answers "is this repo healthy"

`make verify` runs `verify/verify.sh`, in order:

1. Lint — `shellcheck` on every shell script, `ruff check` and
   `ruff format --check` on `tools/` and `tests/`.
2. Doctor — `python3 tools/workcenter doctor`. A missing required engine
   (kicad-cli 10, ngspice, python 3.12) fails here, before any test.
3. Tests — `pytest tests`. The fixture boards under `tests/boards` are
   the gate tests: `pass-rc-divider` must be GREEN, `fail-drc-clearance`
   must stop at DRC with a `clearance` violation, `fail-sim-spec` must
   fail its `vout` bound. KiCad-dependent tests skip loudly without
   `kicad-cli`; step 2 already failed in that case.
4. Kit checks — no unfilled placeholder outside `ee-agent-kit/SETUP.md`;
   every `SKILL.md` has frontmatter with `name` and `description`;
   `ee-agent-kit/skills/*` and `.claude/skills/*` are identical;
   `WORKCENTER.md` exists at the root.

## Rules

- CI runs **the same command** as local. No CI-only logic.
- A gate that can't run in some environment **skips loudly**, never
  passes silently.
- New behavior lands with its gate in the same PR whenever feasible.
- A feature's completion promise (ROADMAP.md) should be backed by a gate
  here whenever it can be — evidence that keeps proving itself beats
  evidence produced once.
- Fixing a flaky or broken gate is always in scope, for any task.
- A new engine or gate lands with a fixture board that turns it red and
  one that keeps it green.
