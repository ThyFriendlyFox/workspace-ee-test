# EE Workcenter

This repository is a workcenter: tools, skills, and gates for turning a
KiCad 10 project into fabrication outputs that passed every check.

Read in this order:

1. `ee-agent-kit/ROUTING.md` decides which file governs the situation.
2. `ee-agent-kit/AGENTS.md` is binding whenever code here is touched.
3. `WORKCENTER.md` is the contract projects get from this workcenter.
4. `ee-agent-kit/PROCESSES.md` is binding before any action it names;
   every mistake lands in `ee-agent-kit/MISTAKES.md` with its process, in
   the same PR.

Session with more than 1 repository: run the `attached-repos` skill before
the first edit. This repository is read-only during a board task unless the
task is about the workcenter itself.
