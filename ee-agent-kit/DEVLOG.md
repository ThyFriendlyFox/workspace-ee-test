# DEVLOG.md — the live devlog

The plain history of this project. A person who knows nothing about the
code reads this file and knows what happened, in order, with no jargon.
Append only. Never rewrite an old entry — a wrong entry gets a
correction entry, not an edit.

Write every entry in the voice of `TONE.md`.

## Entry shape

Every entry has the same shape:

```
## YYYY-MM-DD — <one line: what happened>

<What we did. What worked. What broke. What we learned.
3–10 short sentences. Plain words. Past tense for what happened,
present tense for how things now stand.>

Evidence: <commit / tag / gate run / screenshot>
```

## When to write

- Every WEEKLY.md cycle writes one entry at step 5 (before merge).
- A failed or abandoned attempt gets an entry too. The devlog records
  what happened, not what succeeded. A week with no shipped feature
  still gets its entry.
- Out-of-band work (security patch, gate repair, big triage) gets one.
- SETUP.md writes the first entry: "Installed the agent kit."

## What does not go here

- Code detail that belongs in commit messages.
- Promises about the future — that is ROADMAP.md.
- State claims — that is STATUS.md. The devlog is the story; STATUS is
  the snapshot.

---

<!-- Entries below, newest first. -->

## 2026-10-23 — The board shrank to an inch and the tools had to grow up

The first board was 22 by 46 millimetres, parts on one face, headers for
the wires. The product is an inch by half an inch, so the second version
had to be that: both faces populated, 0402 parts, through-hole pads for the
battery, the coils and the puff sensor, and a USB-C port on the short edge.
The autorouter could not route it. Routed ground alone used up the board,
so the generator learned copper pours and KiCad fills them without a
window. Then the router, which treats a pour as a plane, let signal tracks
wall ground pads off from it; the generator now reads the filled board
with KiCad's own Python module, drops a via into every island it can, and
routes again with a via reserved beside the rest. The router also gives up
on links a person can see; the design file can now draw those by hand and
the router keeps them. Thirty-odd hand-drawn tracks later the board is
GREEN: no errors, no open connections, every ground pad on the pour. Two
mistakes cost hours: assuming where a mirrored part's pads land, and
hiding apt's output in the install script, which made a slow download look
like a hang in CI. Both are on the landmine map now.

Evidence: ThyFriendlyFox/vape-prototype v0.2 commit on main with `docs/gates.md` GREEN; this repository's PR with the generator changes and 6 new tests.

## 2026-10-23 — First real board, and the tools it forced into existence

We designed the first real board with the workcenter: a 39-part,
2-layer controller with a battery charger, an LDO, an MCU, and two
switched power channels. The board lives in its own repository, as the
attached-repos rule says; this repository keeps only the tools.

Hand-writing KiCad files does not scale past a few parts, so we built
`kicadgen`: a design is Python, parts come from the installed KiCad
libraries, and the generator writes the schematic, the board, and the
project. The first schematic passed ERC with 0 errors and 0 warnings on
the first run.

Routing broke three times. `kicad-cli` 10 cannot export a Specctra DSN, so
we wrote the exporter. FreeRouting wrote the session at 10 times its
declared resolution, so every track landed off the board; the merge now
reads the scale from the session's placement block. Then 1.0 mm heater
tracks could not enter SOT-23 and TSSOP pads, which the router reports as
unrouted pins, not as an error; 0.6 mm and a sense resistor in front of
the ADC fixed it. FreeRouting 2.1.0 then never finished a job: it checks
GitHub for updates at start, the call fails behind a proxy, and its main
thread sleeps forever after routing. The engine is pinned to 1.9.0, which
has no network code and finishes in under a minute.

We added `workcenter design` and `workcenter render`, a `board-design`
skill, and tests that include a routed round trip.

Evidence: `tests/test_kicadgen.py` green with FreeRouting installed, 22
tests in `make verify`; the first board's gates report lives with that
board.

## 2026-10-22 — Installed the agent kit; the workcenter exists

This repository started empty. We made it the EE Workcenter: a
toolchain installer, a command line that runs 4 gates on a KiCad
project, 5 skills, 3 fixture boards, and the agent kit that governs
work here. The gates are ERC, DRC, SIM, and EXPORT. A board is done
when all 4 are green.

The first install run broke at once: `add-apt-repository` imports a
module that only the system Python has, and the cloud image sets
Python 3.13 as default. We replaced it with a sources file and a
pinned key fingerprint. The second run installed KiCad 10.0.7, ngspice,
Java 21, and the FreeRouting 2.1.0 JAR.

The queue holds 4 items: session import through the IPC API, a reusable
GitHub workflow for board repositories, fabrication rule sets, and an
MCP server. The human has not ranked them yet.

Evidence: `make verify` green at the install commit; the install log in
the session scratchpad; `tests/boards/README.md` for what each fixture
proves.
