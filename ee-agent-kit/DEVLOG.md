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

## 2026-10-29 — The fab's own limits in the DRC

The user asked for a DRC that says whether a board can be made, and chose
Sierra Circuits as the fab. KiCad's DRC already ran on every board, but
against the workcenter's own rules, which nobody had compared with what a
fab publishes. Sierra's Web PCB order page gives the numbers: 4 mil trace and
gap, 6 mil holes and rings, 13 mil from a hole to inner-layer copper, 5 mil
legend lines. They now live in `rules/` as a KiCad rule file, each rule with
the words it came from, and a board can carry them for good (its design
file names the fab) or be checked against them once (`--fab`). Last Hit
v0.11, GREEN on the workcenter's rules, fails 47 of Sierra's: every via's
ring is 0.150 mm against 0.152, its labels are stroked 0.10 mm against
0.127, and inner copper comes within 0.25 mm of the receptacle's plastic
pegs. All three are cheap to fix in the next version; none would have shown
up before the fab's review.

Evidence: `make verify` green on the branch; `tests/test_fab.py`.

## 2026-10-29 — kistack joins the workcenter

The user asked for kistack in the workflow. It is a set of agent skills for
KiCad written by hand at American Embedded: how to wire a schematic, place
parts, lay out, choose parts, make footprints and symbols, export, look at
Gerbers and panelize. Every one was read before it went in, because agents
follow these files. Most of it applies here as written. Three things do not:
it tells an agent to find ways round a site's bot protection, which this
workcenter refuses; it edits the open board in KiCad, where our boards come
from a design file; and its placement checks need a KiCad server, which
KiCad 10's command line cannot run. So the skills sit unchanged under
`third_party/`, a workcenter skill says which to read when and where our
rules win, and a small reader answers the placement checks from the board
file instead of a server. On kistack's own test board they give the answers
its own tests expect.

Evidence: `make verify` green on the branch; `tests/test_placement.py`.

## 2026-10-28 — A cell that was never wired in

The user asked why the Last Hit's battery floated over the board, then
noticed that it had a contact at each end and nothing joined either one.
They were right twice over. When v0.6 traded a pouch cell for a 10440, the
pouch's protection circuit and its plug went with it: the notes still said
the cell protected itself, but the cell chosen is sold unprotected, and its
contacts were a pad for a spring nobody picked and a lead nobody drew. P20
only asked for the old part's ratings, so this became M56 and P20 now asks
what the old part did as well. The fix needs a dual switch whose drains are
joined inside the package, which KiCad's library draws only as two separate
symbols; projects can now bring their own symbol library, the way they
already bring their own footprints.

Evidence: `make verify` green on the branch; the project-symbol test runs
ERC on a schematic that uses one.

## 2026-10-27 — A parts list you can order from

The user asked for every prototype's parts sourced from Digi-Key with the
full cost, and for it to be a workcenter skill. `workcenter procure` now
reads a board's BOM from its schematic, matches each line to a row of a
parts file (the part, its supplier number, the price breaks and stock as the
supplier's page showed them, the date and the page), and writes the list
with the cheapest order per line and the totals per supplier. Buying ten of
a part is sometimes cheaper than buying seven; the command picks the
cheaper. Items off the board, like the cell and the bare boards, are rows
too. Two mistakes on the way became M54 and M55: a product page guessed
from memory came back as the wrong part, and a page that refused a script
was retried in disguise, which the session refused. P25 says how to read a
supplier: its API, or its pages with the fetch tool where it allows that,
the part number checked on the page. Many common capacitors and resistors
show no stock at Digi-Key this month; the list says so line by line.

Evidence: `make verify` green on the branch; the fixture priced to the cent;
the Last Hit parts lists.

## 2026-10-27 — Schematics with wires, and the parts the 3D views left out

The user looked at the Last Hit board and found two things the gates never
did. The schematic was a list of parts with a net name on every pin and no
wire between them; they put it beside a Commodore 64 service sheet. And the
board's underside had no microcontroller in the 3D pictures: KiCad's
footprints name 3D bodies its library does not ship, for three of the
packages we use, and the renders drew bare pads without a word.

The generator now draws wires. A small grid router joins the pins of each
net round the parts, puts a dot where wires tee, turns each power symbol
away from its pin, and writes the net's name once along its wire so the
schematic and the board agree on names. It is off unless a design asks, so
every older version's schematic comes out exactly as before. The first try
drew a power symbol's wire through a neighbouring pin and shorted 3.3 V to
ground; ERC caught it before anything was kept. `workcenter render` now
lists every part drawn without a body, and the model generator makes small
QFN, DFN and SOT bodies from the package drawing.

Evidence: `make verify` green on the branch; the Last Hit v0.10 schematics,
ERC 0/0 and no parity warning; M51, M52, P24.

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

**Mistakes became a file.** The human asked that every mistake be recorded with a process that prevents it. `MISTAKES.md` now holds the eighteen from these two days, each with its cost and root cause, and `PROCESSES.md` holds the fourteen checklists they produced, from pad geometry before a hand route to closing out a change. `make verify` refuses a mistake with no process and a process with no "Done when". The one that cost most, two hours of hand-routing to pad positions I had worked out in my head, is M11; its process is P1.

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
