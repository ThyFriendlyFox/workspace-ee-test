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
6. A via is on every copper layer. Before writing `d.via`, look at what
   sits on the other face and the inner layers at that spot; then
   `workcenter design` lists every hand via that hits a pad, a track, a
   via, a keep-out or the edge (and exits 1). Fix those before routing.
7. A slot's or an oval pad's long axis comes from the placed board as
   well: the footprint file draws it at rotation 0. Read the hole's size
   and the footprint's rotation from the generated `.kicad_pcb`, turn the
   slot by that rotation (and mirror it for `B.Cu`), and draw a keep-out
   round it from those ends, never from the footprint file (M57).

Done when: the pre-routed board's DRC shows only unconnected items and
`workcenter design` reports no via problem.

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
4. List the area rules before placing: each keep-out, what it forbids
   (tracks, vias, pours) and on which layers. A keep-out that forbids
   vias forbids them on every layer, since a via passes them all. Mark the
   via-free areas; a part placed in one is wired out on its own face to a
   via outside, so give it a path there.
5. Via sizes are rules too. The default via, each net class's and each
   hand via must meet the board's minimum hole (0.3 mm), minimum via
   (0.5 mm) and annular ring (0.1 mm), as `Design.board_rules()` gives
   them with `d.rules` laid over. The router places most vias, so the
   unrouted DRC of step 3 cannot see them; `workcenter design` checks the
   sizes (`Design.check_via_rules()`) and exits 1 before routing. A
   smaller via needs the fab's limit in the README and `d.rules` set to it
   (M46).

Done when: ERC 0/0 and DRC shows only unconnected items before the first
route, `workcenter design` reports no via problem, and the via-free areas
are named in a comment in the design file.

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
file another program wrote; or handing another tool a value whose sign or
axis it defines (a 3D model's rotation or offset, an export's origin).

1. Anchor the pattern on a token the tool guarantees (`version "`, a
   section header), never on free text that a proxy or a locale can
   change.
2. Derive scales and units from data the file contains (the placement
   block of a session), not from a declaration the writer may not honour.
3. Keep a real sample of the output in `tests/` and parse it there, one
   for every shape the format allows (a courtyard can be a rectangle,
   lines, a polygon or a circle).
4. A sign convention (which way a rotation turns, which axis is up) is
   read from the tool, never assumed: render or export once with an
   asymmetric body and look at the result before building on it. Write
   the convention down where its next use will read it (the skill for
   that tool), and use the written one instead of working it out again.
   KiCad 10's is in the `board-design` skill (M42, M47).

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
   to fail. The `no_script_test_edits.py` hook refuses a Bash command
   that writes under `tests/` (M43). The hook does not load in a session
   with two repositories; the step holds there all the same (M61).
7. A test's geometric expectation (inside or outside, how far, which
   side) is computed before it is written: one `python3 -c` with the
   distance printed, not a judgement by eye (M45). A timing expectation
   (the tick an event lands on) likewise, counted from the code's own
   start: a debounce's first sample, a timer's first period (M60).
8. Rows added to a data file (a CSV, a table) go in as text inside the
   file's own bytes, keeping its line ends and quoting; a round trip
   through a reader and a writer rewrites every line. After the edit,
   `git diff --stat` shows only the rows meant (M59).

Done when: the script reported every anchor found, and the formatter and
linter pass on the result.

## P10 — Adding or changing a CLI command

When: touching `tools/workcenter` or `tools/kicadgen.py`'s command line.

1. Write down every file the command creates, overwrites, or deletes. A
   partial run (one gate) never rewrites a whole-run report
   (`gates.json`).
2. The `--help` text says what the command writes and where.
3. One test per exit code and one per written file.
4. `docs/CONFIGURATION.md` gets the new flag in the same PR, in its
   command's table; `test_every_cli_flag_is_in_the_configuration_table`
   fails the PR when a flag has no row (M50).

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
   extend one, with a "Done when" line. Walk a new or changed process
   through the case that caused it, step by step, before the PR: each step
   must be one that case can follow and each check one it passes. Two
   steps that cannot both hold are a mistake in the process.
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
   gate report; a skipped or blocked part is named as such. A board
   version's report carries its pictures (P23).

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
5. Give every control input a level while the MCU is in reset: a gate, an
   enable, a switch, an I2C line that only an MCU pin drives floats until
   firmware sets that pin. Set `check_pulls = True` in the design file;
   `workcenter design` then fails on each net with no output driving it and
   no resistor to a rail (or, for a gate, to its own source). Add the pull,
   or name the net in `defined_nets` with the reason: the datasheet line
   for an internal pull and the firmware line that sets it, or the part on
   the other board of a joint.

Done when: the README's pin table names the function of every used pin,
the shared-resource checks are written next to it, the firmware that
configures those pins compiles, and `workcenter design` reports no
`pull:` line for a design with `check_pulls`.

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
3. List what the old part did besides its ratings: protection it carried
   (a cell's protection circuit, a fuse, a thermistor), how it was held,
   and how it was connected (a plug, tabs, a holder). For each, read the
   new part's datasheet or listing: either it does the same, or the job
   moves to the board or the assembly with a part chosen for it, in this
   change (M56). A pad for a part not yet chosen is an open item in the
   README, never a contact, and the README never claims a function no
   chosen part performs.

Done when: every value on the list cites the new part's rating in the
README, and every function on the step 3 list names the part that does
it now.

## P21 — Moving files in a project

When: moving or renaming files or folders in a project: a version into
its own folder, a script into a subfolder, a library to a new path.

1. Before the move, list every path a moved file computes from its own
   location and every reference to a moved file from elsewhere:
   `grep -rn -E '__file__|\.parent|parents\[|\.\./|KIPRJMOD'` over the
   moved files, and a grep for each moved name over READMEs, CI and
   library tables. Read every hit in full; a line that uses a path is not
   the line that builds it.
2. After the move, run every command the moved files' READMEs name from
   the new location, not only the ones CI runs. A script CI never runs
   breaks without a red check.
3. Diff each moved or restored folder against the commit it came from
   (`git archive <commit> | tar -x` into the scratchpad, then
   `diff -rq`). The only differences are the ones the commit message
   names.

Done when: every command the READMEs name ran from the new location, and
the diff against each source commit shows only the named edits.

## P22 — Versions of a project

When: changing a project kept as version folders (`v0.1/`, `v0.2/`, ...),
before the first edit of a request.

1. A new feature is a new version. A feature is anything the boards or the
   firmware do or carry that the latest version does not: a part, a pad, a
   net, a connection, a board, a dimension, a firmware behaviour. Copy the
   latest folder to the next number first (`cp -a`, then remove its
   `build/` folders) and make every edit in the copy. When unsure whether a
   change is a feature, it is one.
2. The latest version takes only what finishes the request it was made
   for: gate fixes, renders, documents, what its own CI asks for. Once it is
   pushed and a new feature is asked for, it is finished: its README banner
   says archived, with its last commit.
3. In the new folder, the README banner names the version it came from; the
   series index gets a row; the project's CLAUDE.md names the new version
   as the one in work.
4. `git diff --stat <its last commit> -- <previous version>/` shows one
   file, its README, with one line changed: the banner of step 2.

Done when: the request's edits sit only in the new folder, the previous
folder matches its commit but for the banner, and the index and CLAUDE.md
name the new version.

## P23 — Pictures of a finished board version

When: a board version's gates are GREEN and P14's close-out is next; again
after any change to what the boards look like in that version.

1. `workcenter render <board>` for every board of the version: the stills
   and every layer (`build/render/layers/`, `build/render/layers.png`). Its
   summary names each part the 3D views draw without a body (`--strict`
   fails on one): give each its body before any picture is kept (M52).
2. A turning GIF of every board, `workcenter render <board> --views spin`,
   seen from the face that carries the parts; a board with parts on both
   faces gets one from above and one from below (`--spin-tilt -125`, with
   its own `--out` so the first is kept). An assembly gets its own, made by
   the project's assembly script so it is redrawn with the stills, with
   `--spin-zoom` and `--spin-pivot` set so its tallest part stays in frame.
3. Check the framing before keeping a GIF. The frames at 0, 90, 180 and
   270 degrees decide it, the end-on ones crop first: try with
   `--spin-frames 4` (under half a minute) and lower `--spin-zoom` until
   all four are whole.
4. Copy the layer sheet, the layer images and the GIFs into the version's
   `docs/`. The README shows the GIFs beside the stills and the layer
   sheets, and names each command with its tilt, zoom and pivot, so the
   next version draws them the same way.
5. Send the GIFs and the layer sheets with the report.

Done when: the version's `docs/` holds a layer sheet and a turning GIF for
every board and for the assembly, all four test frames of each GIF whole,
no render names a part without a body, the README shows them and names
their commands, and the report carried them.

## P24 — A schematic someone reads

When: writing or changing a board's schematic, and before a board version's
close-out.

1. The design sets `sch_wires = True` and keeps its layout in one table of
   positions and angles (`SCHEMATIC`), in blocks the way the signal flows:
   power left to right along the top, each support part beside the pin it
   serves, connectors facing the circuit they feed.
2. Labels only for nets that cross the whole sheet (`sch_label_nets`), each
   named in a comment; every other net is a wire.
3. Check the drawing against the design: ERC 0 errors and 0 warnings, and
   the DRC shows no parity warning, so every wired net carries the board's
   name.
4. Plot the sheet (`workcenter render . --views schematic`) and read it:
   follow each signal in the README's pin table from its MCU pin to its part.
   Move a part when a wire wanders round the sheet or text lands on a part,
   and plot again.

Done when: ERC is 0/0, the DRC shows no parity warning, and the plot in the
README is the one that was read.

## P25 — Prices and part numbers from a distributor

When: looking up a part, its price or its stock at a distributor, or
writing a parts file (the `procurement` skill).

1. Reach the supplier the sanctioned way: its API with the user's own
   credentials, or its pages with the fetch tool where its robots.txt allows
   (Digi-Key's allows Claude-User). A script that gets a 403 has been
   refused; never retry it with a browser's user agent or any other disguise
   (M55).
2. Find the product page by search, never by a URL from memory, and confirm
   the manufacturer part number printed on the page before reading a price
   (M54).
3. One part per value and footprint, meeting the strictest use on every
   board that names it (voltage, dielectric, power), read from the design's
   notes.
4. Record what the page shows: the supplier number of the cut tape or bulk
   packaging, every price break, the stock (0 when out of stock, the expected
   date in the note), the date read and the URL. No price from memory or a
   search snippet.
5. A part the supplier does not carry gets the supplier that does, or no
   price and a note saying where it was looked for; never a part with
   another footprint without a design change.
6. `workcenter procure` prices the BOM; its "Not priced", "Short of stock"
   and "Prices to check again" lists go into the report.

Done when: every priced row in the parts file has the URL it was read from
and the date, and the report carries `procure`'s totals and its three lists.

## P26 — A feature the user reaches

When: adding or changing a way the user reaches a feature on the device:
a button gesture, a port, a mode, a firmware update.

1. Write the user's steps on the device as assembled, from the state it
   sits in: what powers it, whether it is ever off, when the MCU resets,
   and what is running at that moment (a watchdog, timers, a load, the
   display).
2. Every step must work in that state. A step that needs a reset, a
   removed cell, a debugger or a jumper is not a user's step; it may stay
   as a bench path, named as one in the README.
3. A hand-over to other code (a ROM bootloader, an updater, a second
   image) lists what the hand-over leaves running and what the other code
   expects at entry, each from its documentation, cited. What would not
   survive the hand-over is stopped or reset before it (M58).
4. Whatever the user keeps across it (a schedule, a calibration) is saved
   before the hand-over, and a host test drives the user's steps through
   the app: the hand-over happens only in the intended state, after the
   save.

Done when: the version's README gives the user's steps, each hand-over's
entry conditions cite their source, and a host test runs the steps.
