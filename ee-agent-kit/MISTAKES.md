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
