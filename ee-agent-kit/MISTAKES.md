# MISTAKES.md — every mistake, and the process that now prevents it

Append only. Each entry names what happened, what it cost, the root
cause, and the process in `PROCESSES.md` that prevents it. A mistake with
no process is not recorded yet: write the process first (`P13`).

Entry shape:

```
## M<n> — YYYY-MM-DD — <one line>
What happened: <plain words>
Cost: <time, a red run, a redo>
Root cause: <the real one, not the symptom>
Process: P<n>
```

## M1 — 2026-10-22 — The PPA step assumed the host's python
What happened: `install.sh` called `add-apt-repository`, which needs the system python's `apt_pkg`; the cloud image's default `python3` is another version and the step broke.
Cost: a failed install, a rewrite of the step to write the sources file and verify the key fingerprint itself.
Root cause: an install step assumed something about the host it had not checked.
Process: P2

## M2 — 2026-10-22 — Version regexes read proxy text
What happened: the doctor's Java and ngspice version patterns matched text the proxy injected into the tools' output.
Cost: a wrong doctor verdict until the patterns were anchored.
Root cause: patterns anchored on free text instead of a token the tool guarantees.
Process: P7

## M3 — 2026-10-22 — Files written into the wrong repository
What happened: simulation fixtures were created under the agent kit folder because the shell's working directory had drifted after a `cd` in an earlier command.
Cost: a move and a second look at every path written that hour.
Root cause: relative paths in a shell whose working directory does not persist the way it looks.
Process: P8

## M4 — 2026-10-23 — Trusted the session file's resolution token
What happened: FreeRouting's session declares `(resolution um 10)` but writes coordinates at 10 times that; every merged track was off the board.
Cost: one wrong board and the scale logic in `merge_ses`.
Root cause: a declared unit taken on faith instead of derived from the data.
Process: P7

## M5 — 2026-10-23 — FreeRouting 2.1.0 never returned
What happened: the latest release calls GitHub at start; in the proxied session the call fails and the program sleeps forever after routing without saving.
Cost: several routing runs that had to be killed; the pin to 1.9.0.
Root cause: an engine version adopted without a run in the environment it has to work in.
Process: P6

## M6 — 2026-10-23 — Routed a stale DSN
What happened: parts were moved in the design and the previous DSN was routed; the merged tracks shorted the moved parts.
Cost: a confusing DRC and a re-route.
Root cause: routing was not tied to regeneration.
Process: P4

## M7 — 2026-10-23 — Heavy tracks too wide for their pads
What happened: a 1.0 mm net class could not enter SOT-23 and TSSOP pads; the router left the pins open without an error.
Cost: a routing round and the pad-entry rule.
Root cause: track width chosen from current without checking pad pitch.
Process: P1

## M8 — 2026-10-23 — A single gate overwrote the whole gates report
What happened: `workcenter drc` wrote `gates.json` with one gate's result, replacing the report of the full run.
Cost: a misleading report in the project's docs.
Root cause: a command's written files were not listed when it was added.
Process: P10

## M9 — 2026-10-23 — Back-side pads swapped in the DSN
What happened: Specctra mirrors a back-side part about the Y axis and KiCad about the X axis; the router saw every bottom part half a turn off and connected the wrong pads.
Cost: a two-sided test board full of shorts and the +180 rule in the DSN writer.
Root cause: two tools' mirror conventions assumed equal.
Process: P7

## M10 — 2026-10-23 — Labels below the DRC's text minimum
What happened: 0.5 mm silkscreen labels were placed before the text rules were set; the DRC flagged all 13.
Cost: a rule override and a regeneration.
Root cause: geometry before rules.
Process: P3

## M11 — 2026-10-23 — Hand-routed to pads from memory
What happened: the heater corner was hand-routed with the SOT-23 gate and source swapped (a mirrored part at rotation 0 has gate bottom-left, source top-left), the 1206 shunt's pad 1 at the wrong end, two MCU pins at wrong y, and a via on the USB-C's D+/D− pads that had been forgotten.
Cost: four DRC rounds with shorts and clearance errors, about two hours.
Root cause: pad positions computed in my head instead of read from the DRC report.
Process: P1

## M12 — 2026-10-23 — The install looked hung and was cancelled
What happened: `install.sh` hid apt's output; on a GitHub runner the KiCad download from the PPA took long, the step printed nothing for 30 minutes, and the job hit its timeout.
Cost: the board repository's first CI run cancelled; a scheduled check-in to find out why; the visible, non-interactive apt step.
Root cause: a long network step with its output suppressed and no step timeout tuned to it.
Process: P2

## M13 — 2026-10-23 — A README promised a tag that could not be pushed
What happened: the v0.2 README said v0.1 is kept at tag `v0.1`; the session's git proxy refuses tag pushes with HTTP 403, so the tag never reached the remote.
Cost: a follow-up commit and a second CI run.
Root cause: a document named something before it existed on the remote.
Process: P5

## M14 — 2026-10-23 — A full artifact store turned green gates red
What happened: the board's CI passed every gate, then the artifact upload failed on the account's storage quota and the run was marked failed, twice.
Cost: two red runs that were green, a workflow commit.
Root cause: a convenience step was allowed to fail the job.
Process: P2

## M15 — 2026-10-23 — Scripted edits against a formatted file
What happened: three edit scripts failed because their anchors were copied from text the formatter had since reflowed; one script wrote nothing while reporting partial progress.
Cost: three retries and one careful re-read.
Root cause: anchors from memory, formatter run after the copy.
Process: P9

## M16 — 2026-10-23 — Pre-placed vias beside every ground pad
What happened: a via was reserved beside every ground pad before routing, to stop pour islands; it ate the row gaps and the router went from 4 open items to 15. Measured only after the fact.
Cost: a routing round and the experiment that should have come first.
Root cause: a change to the router's inputs adopted without a before-and-after measurement.
Process: P11

## M17 — 2026-10-23 — Tests that need pcbnew skipped in silence
What happened: the venv could not import KiCad's `pcbnew`, so the pour and stitching tests were skipped; nothing in the summary made the skip visible.
Cost: a run that looked green with its most important tests not run.
Root cause: an expected engine treated as optional by the test suite.
Process: P12

## M18 — 2026-10-23 — Wrong flag order on the CLI
What happened: `workcenter gates --json` instead of `workcenter --json gates`; the report parser read an empty string.
Cost: one wasted command.
Root cause: a flag used without reading `--help` this session.
Process: P8

## M19 — 2026-10-24 — Answered a question that was a change request
What happened: asked whether the USB-C was normal to the board, I explained the v0.2 orientation, noted that a vertical receptacle "would be a v0.3 change", and did nothing. The human had assumed the port was vertical and expected the board to change.
Cost: a turn of work lost; v0.3 started a day late, after the human asked where it was.
Root cause: a question that revealed the design differed from what the human assumed was treated as a question to answer, not as a decision to surface and act on.
Process: P15

## M20 — 2026-10-24 — Pushed behind a look at the log instead of the verify verdict
What happened: the verify run for M19 never ran (`cd` in a backgrounded command did not take, and `make` ran in the wrong directory), and the commit-and-push chain was gated on `tail` of the log, which succeeds whatever the log says. The branch reached the remote without a green verify.
Cost: a second verify run and this entry; no red CI, because the change was documentation and the kit checks passed afterwards.
Root cause: the push was chained behind reading a log instead of behind the verify's own verdict, and a relative working directory was trusted in a background shell.
Process: P14

## M21 — 2026-10-24 — The configuration table kept the old engine version
What happened: `docs/CONFIGURATION.md` still said `FREEROUTING_VERSION` defaults to 2.1.0 a day after `install.sh` pinned 1.9.0 (M5). Found while adding a table for a new tool.
Cost: a wrong number in a reference document for a day; one line to fix.
Root cause: the pin's process named the landmine map, the CHANGELOG and ENGINES.md, but not the configuration table that repeats the default.
Process: P6

## M22 — 2026-10-24 — A `cd && ...` chain ran in the wrong directory again
What happened: a documentation edit command started with `cd repo && ls ... && python3 ...`; a parallel tool call reset the shell's working directory between the `cd` and the `ls`, the `ls` failed, the chain stopped, and the edits silently did not happen. Same mechanism as M20.
Cost: one lost command and the diagnosis that explains M20: parallel tool calls share one shell, so `cd` is a race.
Root cause: `cd` used at all. P8 said absolute paths and still allowed a leading `cd`.
Process: P8

## M23 — 2026-10-24 — Two wake inputs on one interrupt line
What happened: the v0.2 to v0.4 pin plans put the service button on PB7 and the puff sensor on PA7. On an STM32 the EXTI line is chosen by pin number, one port at a time, so both share EXTI7 and only one can wake the MCU from Stop. Found while planning v0.5 from ST's open pin data.
Cost: three board revisions with a pin plan the firmware could not have used; no hardware built.
Root cause: pins chosen by name and function from memory, without checking the shared resources (EXTI lines, timers, ADC channels) against the vendor's data.
Process: P16

## M24 — 2026-10-24 — Circle courtyards read as two corners
What happened: `kicadgen footprint` printed a circle courtyard as the box between its centre and one point on the circle, e.g. (1.25, 0, 1.25, 0) for a 2.5 mm test pad. Nothing checked placement with it, but P1 tells the agent to read geometry from that command.
Cost: a wrong number in the tool the processes trust; found when the 510 footprint's courtyard read as a point.
Root cause: the parser treated every courtyard shape's `start`/`end` as corners; no test parsed a footprint with a circle courtyard.
Process: P7

## M25 — 2026-10-24 — An escape written for the wrong layer of quoting
What happened: a Python edit script inside a quoted shell heredoc wrote `"\\n"`, meaning a newline; the heredoc passes it through, Python reads a backslash and an `n`, and the test file ended in a stray line-continuation character.
Cost: one failed test collection and a repair edit.
Root cause: an escape written for the shell when the text was going straight to Python.
Process: P9

## M26 — 2026-10-24 — Island stitching put a via against a plastic peg's hole
What happened: routing Last Hit v0.5, `reserve_vias` placed a ground via 0.2 mm from the USB-C receptacle's non-plated peg hole. The DRC treats a non-plated hole as board edge and wants 0.3 mm; the via check only knew hole-to-hole spacing.
Cost: one red DRC after routing and a fix in the generator.
Root cause: the generator's own clearance model for copper it adds did not cover every DRC rule that applies to that copper.
Process: P17

## M27 — 2026-10-24 — M25 again, minutes after writing its rule
What happened: another edit script in a quoted heredoc ended a test file with a literal backslash and n; the same script added an assertion that could never fail (`in (True, False)`).
Cost: a repair with the Edit tool; caught before any commit.
Root cause: P9 step 5 was read as advice; a test appended by script was not read back before running.
Process: P9

## M28 — 2026-10-24 — Tracks written for where a part was going to be
What happened: moving Last Hit v0.5's regulator, its input and output tracks were written in the same edit as the move, with pad x computed for a position 0.4 mm right of where the part was placed. The DRC passed only because the endpoints still fell inside the 1.3 mm pads.
Cost: a regeneration to put the tracks on the pad centres; on smaller pads it would have been a short.
Root cause: pad positions of a moved part computed in my head instead of read after the move.
Process: P1

## M29 — 2026-10-24 — Hand-routed lanes walled off other nets
What happened: on Last Hit v0.5 a 3.3 V lane drawn 8 mm across the top face above the display pads, and a VBUS lane below them, left the display's SDA pad and a regulator ground pin with no way in; moving a pad onto the router's corridor made it worse. Each fix opened a new link somewhere else.
Cost: three routing runs and a re-placement of the regulator, which is what fixed it.
Root cause: a long hand route treated as a local fix; on two layers a track is a wall for every net on its layer that has to cross it.
Process: P11

## M30 — 2026-10-24 — Keepouts checked by one of the two via placers
What happened: PR #12 taught `_via_fits` (stitching and reserved vias before routing) to refuse a via in a keepout, but the island stitcher that runs after routing (`stitch_zones`, `_via_spot`) has its own placement and was not touched. On Last Hit v0.6's first route it put two ground vias under cartridge A's collar, and the DRC flagged both.
Cost: a red DRC on the first v0.6 route and a second workcenter PR.
Root cause: P17's rules were checked in the function being edited, not in every code path that places the same copper.
Process: P17

## M31 — 2026-10-24 — A `cd` in a command, a fourth time
What happened: a pytest command started with `cd /home/user/workspace-ee-test;`, against P8. Nothing ran in the wrong place this time, but the session's working directory moved.
Cost: none this time; the same slip cost lost edits in M20 and M22.
Root cause: P8 was a rule only the agent checked.
Process: P8

## M32 — 2026-10-24 — Firmware draft bugs, and tests that could not fail
What happened: the first draft of Last Hit's firmware let a shorted coil run for up to 2 ms before the overcurrent cut (the PWM period was not restarted when a channel turned on), retried a dead display forever (keeping the MCU awake), and would have lit the display again after about 25 days idle (a millisecond comparison across the counter's wrap). Three test checks could never fail. All were found before hand-off: the bugs in review, the checks by breaking the code on purpose (29 mutations, each caught by a named test).
Cost: rework inside the firmware task; none of it shipped.
Root cause: no checklist for the failures embedded code repeats (the exposure window of a safety cut, unbounded retries, counter wrap), and tests not proven able to fail.
Process: P18

## M33 — 2026-10-24 — The router's model of a non-plated hole used the wrong clearance
What happened: the DSN writer grew each non-plated hole by the 0.25 mm hole clearance, but the DRC treats such a hole as board edge and wants the 0.3 mm edge clearance. On Last Hit v0.6 FreeRouting ran a 3.3 V track 0.25 mm from the USB-C's plastic peg hole and the DRC flagged it. M26 had fixed the same rule for the generator's own vias only.
Cost: one red DRC after an otherwise complete route, and a fix in the DSN writer.
Root cause: P17 listed the copper the generator places, not the obstacles it hands the router, whose copper the DRC judges by the same rules.
Process: P17

## M34 — 2026-10-24 — Pushed with lint findings on the screen
What happened: the push of Last Hit's mutation script was chained behind the firmware tests only; `ruff check` ran in the same command, printed two line-length findings, and the push went ahead.
Cost: a follow-up formatting change; the board repository's CI has no lint step, so nothing turned red.
Root cause: a check that only printed its result, outside the push chain.
Process: P14

## M35 — 2026-10-24 — A `cd` again, an hour after the hook that refuses it
What happened: a board-repository command carried a no-op `(cd /tmp && true)`. The no-`cd` hook (M31) lives in the workcenter's `.claude/settings.json`, which only loads in a session opened inside the workcenter; this session was rooted above both repositories, so nothing refused it.
Cost: none this time; a check that looked installed was not running.
Root cause: a machine check scoped to one repository, trusted for every session. Installing it user-wide is the human's decision (writing their settings was refused, rightly, when tried unasked).
Process: P8

## M36 — 2026-10-24 — A test file edited by `sed`
What happened: an `import os` was inserted into `tests/test_kicadgen.py` with `sed`, against P9 step 6. The file was read back and the tests ran green.
Cost: none; recorded because the rule says every slip is.
Root cause: a one-line convenience taken past a rule that names test files.
Process: P9

## M37 — 2026-10-24 — Island stitching looped per zone, not per net
What happened: the island stitcher ran once for each zone, and each run read the pours of the zone's whole net. A net with two zones (a ground plane on `In1.Cu` and a pour on `F.Cu`) found the same island twice in one round and got two vias on the same spot. Every board so far had one zone per net, so nothing showed it until the four-layer test did.
Cost: one red test while adding four-layer boards; no board shipped with it.
Root cause: a loop over the containers of a thing (zones) where the work is per thing (net), and tests that only ever had one of each.
Process: P17

## M38 — 2026-10-24 — Custom pads kept their top-face shape on the bottom face
What happened: the generator mirrors a bottom-face footprint the way KiCad's Flip does, but it walked only the pad's position, not the shapes inside a custom pad. A QFN-28 on the bottom face got its corner pads' chamfers on the wrong side, 0.03 mm from the next pad round the corner; the DRC on the unrouted Last Hit board found four. The generator's pad boxes also read a custom pad as its 0.14 mm anchor, so its own via checks saw almost no copper there.
Cost: one DRC round; no board shipped with it. Every earlier board had only rectangles, rounded rectangles and circles.
Root cause: a footprint transform written for the pad shapes in use, never checked against the shapes the libraries also hold.
Process: P19

## M39 — 2026-10-24 — The charger kept a pouch cell's current for a 320 mAh cell
What happened: v0.6 swapped v0.5's 600 mAh pouch for a 10440 (about 320 mAh) and kept the charger's 2 kΩ program resistor: 500 mA, about 1.5 C, where 10440 makers give 0.5 C standard and 1 C at most. Found while re-reading the BOM for the 38 mm board.
Cost: v0.6 at 48.26 mm was published with it; no board was built. The 38 mm board sets 5.1 kΩ, 196 mA.
Root cause: a part swap that rechecked the part's size and drain rating, not the values other parts took from the old one's ratings.
Process: P20

## M40 — 2026-10-24 — Vias planned inside a collar keep-out
What happened: on the 38 mm Last Hit board the regulator and the charger went under cartridge B with vias beside them for their battery feeds; the keep-out under the collar forbids vias, and a via passes every layer, so the DRC refused all three. The keep-out had been read as a top-face rule for tracks.
Cost: one placement round; the regulator, the dividers and the charger moved.
Root cause: placement planned against pad clearances, with the area rules (what each keep-out forbids, on which layers) never listed.
Process: P3

## M41 — 2026-10-24 — Hand vias under the other face's pads, three times
What happened: escape vias for the MCU and a ground via, drawn for the bottom face, landed under pads on the top face (the cell's positive pad, two puff pads). The DRC reported shorts each time.
Cost: three DRC rounds and two moves of the puff pads.
Root cause: a hand-placed via checked against the face being drawn; the generator's own via check, which looks at every layer, never ran on hand vias.
Process: P1

## M42 — 2026-10-24 — The display body rotated the wrong way
What happened: the assembly render stood the OLED module on its long edge with its face toward the cylinders: KiCad's model rotation turns the other way from the sign assumed.
Cost: one render.
Root cause: another tool's sign convention assumed, not read from a render of an asymmetric body.
Process: P7

## M43 — 2026-10-24 — A test file edited by script again
What happened: a coordinate in `tests/test_kicadgen.py` was changed with a Python replace in PR #17's work, and a comparison in PR #16's; P9 step 6 and M36 say tests are written with the Edit tool.
Cost: none in behaviour; the tests ran green. Recorded because the rule had been broken before.
Root cause: a rule that only a reader enforces, broken under the habit of scripted edits for every other file.
Process: P9

## M44 — 2026-10-24 — A script's path to the workcenter broken by moving it one folder down
What happened: the Last Hit board moved into `v0.6/` so that each prototype is a folder, and `assembly.py` still looked for a workcenter checkout at `HERE.parent / "workspace-ee-test"`, which now named the board repository's own root. The grep for self-relative paths before the move printed the lines that used the found path, not the line that built it, and CI never runs the script, so the replay of CI passed.
Cost: one failed assembly run, caught before the push.
Root cause: the moved files were checked through the commands CI runs, not through every path they compute from their own location and every command their READMEs name.
Process: P21

## M45 — 2026-10-24 — A test point judged outside an arc by eye
What happened: the per-corner radius test asserted that (111.6, 100.4) lies outside a 1 mm corner arc centred at (111, 101); it is 0.85 mm from the centre, inside. The read-back before the run caught it.
Cost: none; the test never ran with the wrong point.
Root cause: a distance estimated from the numbers' look instead of computed.
Process: P9

## M46 — 2026-10-24 — Router vias below the board's minimum hole
What happened: the Last Hit v0.7 display board set its vias to 0.5 / 0.25 mm, small for a small board; the generator writes a 0.3 mm minimum hole into every board's rules. The DRC of the unrouted board (P3 step 3) had no via to check, the router placed nine 0.25 mm vias, and the DRC refused all nine (drill out of range) after the route.
Cost: one route and one gates run; the vias went to 0.6 / 0.3 and the board routed again.
Root cause: a via size set without reading the rules the generator writes, and the one check that compared them, the DRC, runs after the router has placed the vias.
Process: P3

## M47 — 2026-10-24 — A 3D model turned the wrong way again
What happened: in the Last Hit v0.7 assembly the display board's body was attached with a rotation worked out by the right-hand rule, (90, 0, 90); KiCad turns models the other way, and the board hung below the base instead of standing on it. M42 was the same mistake. P7 step 4 says to read a sign convention from the tool, but P7 is for parsing another tool's output, and attaching a model is not parsing, so the step was never read.
Cost: one assembly render; (-90, 0, -90) stood the board up.
Root cause: the convention learned in M42 was written down only as "read it from the tool", under a trigger that does not name the act that needs it, and the convention itself was written nowhere.
Process: P7

## M48 — 2026-10-24 — A new feature built inside a finished version
What happened: after Last Hit v0.7 was pushed (`6b27d37`), the user asked for a seventh joint pad to feed the panel's VBAT from the cell. The new joint footprints and the panel's VBAT switch went into `v0.7/`, read as "the version in work". The user stopped it: every new feature is a new version.
Cost: an interrupted round; the edits moved to `v0.8/` and `v0.7/` went back to its commit.
Root cause: the project's rules said how to start a new version, not when; "the highest version is the one in work" was read as "change it in place".
Process: P22

## M49 — 2026-10-24 — A process whose steps contradict each other
What happened: P22 (M48) said in step 2 that the previous version's README banner changes to "archived", and in step 4 that `git status` on the previous folder prints nothing. The case it was written for, v0.7 after v0.8 was made, fails step 4 by following step 2. Found while closing out v0.8, after PR #21 merged.
Cost: a second PR for one line of a process.
Root cause: the process was written from the rule, not walked through the case that caused it.
Process: P13

## M50 — 2026-10-24 — CLI flags without the configuration table, and the table split in two
What happened: PR #23 gave `workcenter render` `--views`, `--spin-frames`, `--spin-tilt`, `--spin-zoom` and `--spin-pivot` without the rows P10 step 4 asks for in `docs/CONFIGURATION.md`. Checking it found `--rounds`, from an earlier PR, missing too, and the `tools/workcenter` flag table cut in two by the `wrlgen` and `kicadgen` sections, four of its rows standing under `kicadgen`.
Cost: a configuration doc wrong for every flag added since the split; found while writing P23, after #23 merged.
Root cause: P10 was not read before the command line changed, and nothing compared the table with the code.
Process: P10

## M51 — 2026-10-27 — Nine versions of schematics nobody could read
What happened: every Last Hit schematic, v0.1 to v0.9, came out of the generator as symbols with a stub and a net label on each pin and no wire between parts. ERC and parity passed, so the gates were GREEN, and each README showed the sheet. The user put it beside a Commodore 64 service schematic: the pieces are listed, nothing is joined.
Cost: no version's schematic could be followed from a pin to the part it drives; the generator gained a schematic router and v0.10 redrew both boards.
Root cause: the schematic writer was built to the gates, which labels satisfy, and no step looked at the schematic as a drawing.
Process: P24

## M52 — 2026-10-27 — Bare pads where four parts should be
What happened: from v0.6 on, the MCU (QFN-28 4 x 4 mm), the charger (DFN-8 3 x 2 mm) and the SOT-523 gate drivers rendered as bare pads on the base board's underside. KiCad's footprints name 3D bodies its 3D library does not ship, and `workcenter render` drew without them and said nothing. The user saw it in the v0.9 pictures.
Cost: four versions of 3D pictures and turning GIFs with parts missing.
Root cause: nothing compared the bodies the footprints name with the files on disk, and the pictures were checked for framing, not for what was missing.
Process: P23

## M53 — 2026-10-27 — `cd` again, in a session with two repositories
What happened: two commands started with `cd` while the generator was being tested. The no-cd hook does not load in a session with two repositories, and P8 was not read again. Nothing ran in the wrong place.
Cost: none this time.
Root cause: habit, with the hook that refuses it absent in this kind of session; installing it user-wide is the user's decision.
Process: P8
