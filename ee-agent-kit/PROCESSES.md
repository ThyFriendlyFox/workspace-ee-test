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
   source for a coordinate; never a position computed in your head. A
   part moved in the same change is regenerated and its pads read after
   the move; its tracks are never written in the edit that moves it.
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
3. Keep a real sample of the output in `tests/` and parse it there, one
   for every shape the format allows (a courtyard can be a rectangle,
   lines, a polygon or a circle).

Done when: a test parses a real sample and the parser's assumptions are
written next to it.

## P8 — Shell discipline

When: every shell command.

1. Absolute paths, and no `cd`. Parallel tool calls share one shell, so a
   `cd` in one command is undone by the next without an error: a
   `cd X && ...` chain stops or runs in the wrong repository. Use
   `make -C`, `git -C`, `python3 /abs/script.py`, and absolute paths in
   every heredoc. In this repository a PreToolUse hook
   (`tools/hooks/no_cd.py`) refuses a Bash command that runs `cd`. A
   session opened outside this repository does not load it: check
   `workcenter doctor` for the "no-cd hook" line, and where it is absent,
   ask the human whether to install it user-wide
   (`python3 tools/hooks/install_hooks.py`); never write their settings
   unasked.
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
5. Inside a quoted heredoc (`<<'EOF'`) the shell passes text through as
   written. Write no backslash escapes in it at all: `chr(10)` for a line
   break, real line breaks inside a triple-quoted string.
6. Tests are written with the Write or Edit tool, not appended by a
   script, and read back before they run: every assertion must be able
   to fail.

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
5. A hand-routed track is a wall on its layer. Before drawing one longer
   than three pad pitches, list the pads on each side of it whose nets
   must cross it. If one of them cannot cross on the other layer, move a
   part instead of drawing the lane.

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
   `tail` succeeds whatever the log says. Every check you run before a
   push is in the chain (`ruff check ... && make test && git push`); a
   check whose result only prints is not a gate.
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

## P16 — A pin plan

When: choosing or changing which MCU pin carries which signal.

1. Read the alternate-function table from the vendor's data: ST's open
   pin data (`STM32_open_pin_data`, the MCU and GPIO-modes XML) or the
   datasheet. Never from memory.
2. Write the plan as a table: pin, port, and the exact function each
   signal uses (AF number and timer channel, ADC channel, EXTI line, I2C
   or UART instance).
3. Check the shared resources: no two interrupt or wake inputs on one EXTI
   line (same pin number, different port); PWM channels that must run
   together on one timer; analog inputs on ADC channels; no pin in analog
   mode at reset sees a voltage above VDD; multi-bonded pins (several
   ports on one package pin) keep the unused ones as inputs.
4. Write the firmware's pin set-up from the same table and build it.

Done when: the README's pin table names the function of every used pin,
the shared-resource checks are written next to it, and the firmware that
configures those pins compiles.

## P17 — Copper the tools add

When: changing code in the workcenter that places copper on its own
(stitching vias, reserved vias, generated tracks or pours).

1. List every code path that places that copper: grep the generator for
   every place a via or track is appended (stitching and reserved vias
   before routing, island stitching after it, generated tracks), and the
   obstacles the DSN gives the router, whose tracks are copper the tool
   chain adds too.
2. List every DRC rule that applies to that copper: copper to copper by
   net, hole to hole, copper to board edge, non-plated holes, which the
   DRC treats as board edge, and keepouts.
3. Each rule is one check, with the same numbers the board's design rules
   use, read from the `Design`, not typed again; every path from step 1
   calls it.
4. One test per rule and per path: place the copper just inside and just
   outside each kind of obstacle and expect refused and accepted.
5. Test with two of everything the code loops over: two zones of one net,
   more than two copper layers, a via that passes layers it does not join.
   A loop written against one of each double-counts or skips the second
   (M37).

Done when: every rule on the list has a test, and a routed board with the
change passes the DRC with no item placed by the tool.

## P18 — Firmware that drives power

When: writing or changing firmware that switches a heater, a motor, a
charger, or any other load from a battery.

1. For every safety cut-off, write down the worst-case time from the fault
   to the cut, and test it against a fake timer on the host.
2. Every retry has a limit and a give-up state; a dead peripheral must not
   keep the MCU awake or the load on.
3. Every elapsed-time comparison is wrap-safe (subtract, then compare),
   and a test runs the counter across its wrap.
4. Prove the tests can fail: break each safety behaviour once (a mutation
   script kept with the firmware) and see a named test fail.
5. Every output that drives a load is off at reset, in every fault
   handler, and when the loop that commands it stops (a deadman).

Done when: the host tests cover steps 1, 2, 3 and 5, the mutation run
catches every mutation, and the cut-off times are in the firmware README.

## P19 — Footprint geometry the generator transforms

When: changing how the generator copies, flips or rotates a footprint, or
placing a footprint with a pad shape no board here has used (custom pads,
chamfered rectangles, paste-only apertures).

1. List the footprint's pad shapes and, for a custom pad, its primitive
   kinds (polygon, line, rectangle, circle, arc).
2. Place it on the face and at the rotation the board uses, generate the
   unrouted board and run `workcenter drc .`. A clearance between two pads
   of one footprint is the generator's bug, never the board's.
3. Add a test that places the new shape on the bottom face and runs the
   DRC, and one that reads its pad size as the copper, not the anchor.

Done when: the unrouted board's DRC shows no clearance inside any
footprint, and the tests for the shape are in the suite.

## P20 — Swapping a part

When: replacing a part with another (a cell, a connector, a regulator, a
switch) or changing its rating.

1. List every value on the board chosen from the old part's ratings:
   charge current, current limits and sense ranges, cut-off voltages,
   fuse ratings, thermal budget, pull values that assume its thresholds.
2. Recompute each from the new part's datasheet and write the value and
   the rating it comes from in the project README's BOM or decisions.

Done when: every value on the list cites the new part's rating in the
README.
