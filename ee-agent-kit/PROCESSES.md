# PROCESSES.md — the checklists you follow

Every process here exists because a mistake in `MISTAKES.md` cost real
time. They are binding the way `AGENTS.md` is: before you do a thing a
process names, you follow its steps, in order, and you do not call the
thing done until its "Done when" line holds. A process you cannot follow
is a blocker to report, not a step to skip.

`make verify` checks that every mistake names a process that exists and
that every process says when it is done.

Numbering is permanent. A process is never deleted; one that no longer
applies is marked retired with the date and the reason.

## P1 — Pad geometry before a hand route

When: before `d.track`, `d.via`, `reserve_vias`, or any coordinate that
must clear or land on a pad.

1. Read the footprint with `python3 tools/kicadgen.py footprint Lib:Fp`.
   List every pad, including a connector's unused ones (USB-C D+/D−,
   shield, mounting holes).
2. Generate the unrouted board and run `workcenter drc .`. The report
   names each pad with its board position. Those positions are the only
   source for a coordinate; never a position computed in your head.
3. A part on `B.Cu` is mirrored about the X axis: at rotation 0 its pad 1
   is on the left and its pads' y are flipped. Confirm against the DRC
   report, every time.
4. Track widths come from the pad: the widest track into a pad is pitch
   minus pad width minus 2 x clearance. A sense tap on a heavy net is
   drawn thinner with `width=`.
5. End a track on the pad centre. Route one net, run `workcenter drc .`,
   read every clearance line it prints, fix, then the next net.

Done when: the pre-routed board's DRC shows only unconnected items.

## P2 — CI and install steps

When: writing or changing a workflow, `install.sh`, `environment/setup.sh`,
or any step that downloads, installs, or runs for more than a minute.

1. Output stays visible. Never `>/dev/null` a network or install step;
   print a line per fetched package, downloaded file, or finished stage.
2. Non-interactive: `DEBIAN_FRONTEND=noninteractive`, `-y`, explicit
   `Dpkg::Options` for config prompts. Nothing may wait on a terminal.
3. A timeout on every long step (`timeout-minutes`, `curl --max-time`,
   `--connect-timeout`, `--retry`).
4. Assume nothing about the host: not the default `python3`, not that
   `add-apt-repository` works, not that a keyserver answers quickly.
5. The verdict steps (gates, verify) come before convenience steps
   (artifact upload, render for humans). A convenience step is
   `continue-on-error: true` with a short retention; it must not turn a
   green verdict red.
6. After pushing a CI change, watch its run to the end. A run that
   looks stuck is read, not waited out: fetch the job log and find the
   last line printed.

Done when: the run is green, its log shows progress lines in every long
step, and no step depended on a terminal.

## P3 — Design rules before geometry

When: starting a board, or changing clearances, text sizes, or net
classes.

1. Set `d.rules`, `d.net_classes`, `track_width`, `clearance`,
   `edge_clearance`, via sizes first, with the fab's limits in the README.
2. Silkscreen text below 0.8 mm needs `min_text_height` and
   `min_text_thickness` in `d.rules` or the DRC flags every label.
3. Generate and run `workcenter erc .` and `workcenter drc .` on the
   unrouted board. Every error except unconnected items is a placement or
   rule mistake; fix it here, not after routing.

Done when: ERC 0/0 and DRC shows only unconnected items before the first
route.

## P4 — Before every route

When: about to run `workcenter design --route` or `workcenter autoroute`.

1. Regenerate from the design file in the same command. A DSN from an
   earlier generation routes against parts that have moved and ships
   shorts that look like the router's fault.
2. P3's "Done when" holds on this exact design.
3. One route per design change. Read the printed summary: segments,
   vias, rounds, islands. Then `workcenter drc .` for what stayed open.

Done when: the DRC after the route lists 0 errors, or every remaining
error is named in the next design change.

## P5 — Docs name what exists

When: writing a tag, commit, branch, URL, run link, or path into a
README, devlog, status line, or PR body.

1. Confirm it on the remote first: `git ls-remote --heads --tags origin`,
   the run's page, the file in the merged tree.
2. A push that is refused (tags are refused by the session's git proxy
   with HTTP 403) changes the document, not the claim: name the commit
   hash instead of the tag.
3. Numbers in a document (segments, vias, warnings) are copied from the
   gate report of the committed board, not from an earlier run.

Done when: every name in the document resolves on the remote at the time
of the push.

## P6 — Pinning or changing an engine version

When: changing the version of kicad-cli, ngspice, FreeRouting, Java, or a
Python package in `requirements.txt`.

1. Reproduce the fault or the gain with the exact version, in the
   environment that showed it (proxied cloud session, GitHub runner).
2. Pin with the reason in `install.sh` (a comment with the symptom), a
   row in the landmine map, a CHANGELOG line, `docs/ENGINES.md`, and
   every table that repeats the default (`docs/CONFIGURATION.md`):
   `grep -rn` the old version string across the kit before the commit.
3. Keep a check that fails when the pin is lost: a doctor line, a test,
   or a checksum.

Done when: `make verify` is green with the new version and the landmine
map says why it is that version.

## P7 — Parsing another tool's output

When: reading a version string, a report, a session file, a log, or any
file another program wrote.

1. Anchor the pattern on a token the tool guarantees (`version "`, a
   section header), never on free text that a proxy or a locale can
   change.
2. Derive scales and units from data the file contains (the placement
   block of a session), not from a declaration the writer may not honour.
3. Keep a real sample of the output in `tests/` and parse it there.

Done when: a test parses a real sample and the parser's assumptions are
written next to it.

## P8 — Shell discipline

When: every shell command.

1. Absolute paths, and no `cd`. Parallel tool calls share one shell, so a
   `cd` in one command is undone by the next without an error: a
   `cd X && ...` chain stops or runs in the wrong repository. Use
   `make -C`, `git -C`, `python3 /abs/script.py`, and absolute paths in
   every heredoc.
2. `--help` before a flag you have not used in this session. Global
   flags such as `--json` go before the subcommand.
3. `pkill -x name`, never `pkill -f` with a pattern that matches the
   shell running it.
4. Long jobs run in the background with a log file; foreground commands
   stay under the tool's timeout.

Done when: the command ran where and how you meant, and the paths it
printed are the ones you expected.

## P9 — Scripted edits

When: changing a file with a script (python replace, sed) instead of the
Edit tool.

1. Run the formatter first (`ruff format`), so the anchors you copy are
   the text that is on disk.
2. Copy every anchor from the current file, not from memory or from an
   earlier version of this conversation.
3. Check every anchor before writing anything; a script that writes the
   first half and fails on the second leaves a file nobody has read.
4. A change of a few lines goes through the Edit tool after a Read.

Done when: the script reported every anchor found, and the formatter and
linter pass on the result.

## P10 — Adding or changing a CLI command

When: touching `tools/workcenter` or `tools/kicadgen.py`'s command line.

1. Write down every file the command creates, overwrites, or deletes. A
   partial run (one gate) never rewrites a whole-run report
   (`gates.json`).
2. The `--help` text says what the command writes and where.
3. One test per exit code and one per written file.
4. `docs/CONFIGURATION.md` gets the new flag in the same PR.

Done when: `make verify` is green and the configuration table names the
flag.

## P11 — Changing what the router sees

When: changing the DSN writer, net classes, fixed wiring, planes, via
reservations, or part spacing in a design to help the router.

1. One change at a time.
2. Measure before and after on the same design: unconnected items from
   `workcenter drc .`, pour islands, segments, vias. The scratchpad
   variant script runs the alternatives side by side.
3. Adopt only what reduces the open items; revert the rest even when it
   looked right.
4. Record the numbers in the commit message.

Done when: the commit says what was measured and the number went down.

## P12 — Optional engines in tests

When: a test depends on FreeRouting, `pcbnew`, ngspice, or any engine
that may be absent.

1. The skip is explicit and named: a marker with a reason.
2. Where the engine is expected (CI, the cloud environment), the skip is
   a failure: a test asserts the engine is importable or on `PATH`.
3. `make verify` runs the tests with the same Python the CLI uses; the
   venv is created with `--system-site-packages` so it sees `pcbnew`.
4. Read the test summary for skips before calling a run green.

Done when: the summary shows no unexpected skips and the engine test is
green on the runner.

## P13 — Recording a mistake

When: you did something wrong, a step surprised you, a run was red for a
reason you caused, or you had to redo work.

1. Add an entry to `MISTAKES.md` in the same PR as the fix, in the entry
   shape: what happened, what it cost, the root cause, `Process: P<n>`.
2. Point at the process that prevents it. If none does, add one here or
   extend one, with a "Done when" line.
3. If a machine can check the process, add the check to
   `verify/verify.sh` or a test in the same PR.
4. If the cause is the environment (a tool, a proxy, a runner), add a row
   to the landmine map in `AGENTS.md` too.
5. Say it in the report to the human: the mistake, the cost, the process.

Done when: `make verify` is green with the entry, and the process it
names has a "Done when" line.

## P14 — Closing out a change

When: a change is about to be called done.

1. `make verify` green locally; for a board, `workcenter gates .` GREEN.
   Run it with an absolute path (`make -C /path verify`), never behind a
   `cd`, and in the background with a log.
2. Chain the commit and the push behind the verdict itself, never behind
   a look at the log: `grep -q 'VERIFY GREEN' log && git push ...`. A
   `tail` succeeds whatever the log says.
3. Push, then confirm the remote holds it: `git ls-remote`.
4. Watch CI to the end; red CI is work now, not later.
5. The report names the commit, the run link, and the numbers from the
   gate report; a skipped or blocked part is named as such.

Done when: the remote has the commit, its CI run is green, and the report
has been sent.

## P15 — A question that reveals a mismatch

When: a human asks whether the work is a certain way (an orientation, a
size, a part, a behaviour) and the honest answer is that it is not.

1. Answer the question in one sentence.
2. Name the mismatch as a decision: what the design does now, what the
   question assumed, what changing it costs and touches.
3. If the change is reversible and inside the task's scope (a board
   revision, a document, a tool default), do it in the same turn and say
   so. Ask first only when it widens the scope or spends real money.
4. Never close with "that would be a vN change" and no owner. The reply
   carries either the change or an explicit question.

Done when: the reply holds the answer and either the finished change or a
direct question, and nothing is left as a note for later.
