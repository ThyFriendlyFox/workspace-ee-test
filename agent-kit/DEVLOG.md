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
