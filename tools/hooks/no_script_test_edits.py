#!/usr/bin/env python3
"""PreToolUse hook: refuse a Bash command that edits a test file by script (PROCESSES.md P9 step 6,
MISTAKES.md M36, M43).

Tests are written with the Write or Edit tool and read back, so every assertion is one somebody
read. A command that names a file under `tests/` and writes with `sed -i`, `perl -i`, a shell
redirect, `tee`, or Python's `write_text` / `open(..., "w")` is refused: exit 2 blocks the call
and the message on stderr tells the agent to use the Edit tool. Reading a test file, running the
tests and writing outside `tests/` pass.
"""

from __future__ import annotations

import json
import re
import sys

TEST_PATH = re.compile(r"(?:^|[\s'\"/=(])tests/[\w./-]*")
WRITES = [
    re.compile(r"\bsed\s+(?:-\w*\s+)*-i"),
    re.compile(r"\bperl\s+-\w*i"),
    re.compile(r">>?\s*['\"]?[\w./-]*tests/"),
    re.compile(r"\btee\b[^|;&]*tests/"),
    re.compile(r"\.write_text\("),
    re.compile(r"\bopen\([^)]*['\"][wa]\+?['\"]"),
]


def main() -> int:
    try:
        call = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0  # not ours to judge
    if call.get("tool_name") != "Bash":
        return 0
    command = (call.get("tool_input") or {}).get("command", "")
    if TEST_PATH.search(command) and any(w.search(command) for w in WRITES):
        print(
            "P9 step 6: a test file is written with the Edit or Write tool and read back, never by "
            "a script (sed -i, a redirect, write_text). Read the file, then Edit it.",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
