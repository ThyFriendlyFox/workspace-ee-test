#!/usr/bin/env python3
"""PreToolUse hook: refuse a Bash command that runs `cd` (PROCESSES.md P8, MISTAKES.md M20, M22, M31).

Parallel tool calls share one shell, so a `cd` in one command is undone or raced by the next without
an error. Claude Code passes the tool call as JSON on stdin; exit 2 blocks the call and shows the
message on stderr to the agent, which retries with absolute paths (`make -C`, `git -C`).
"""

from __future__ import annotations

import json
import re
import sys

# `cd` as a command word: at the start, or after a separator, a subshell or a line break.
CD = re.compile(r"(?:^|[;&|(]|\n)\s*cd(?:\s|$)")


def main() -> int:
    try:
        call = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0  # not ours to judge
    if call.get("tool_name") != "Bash":
        return 0
    command = (call.get("tool_input") or {}).get("command", "")
    if CD.search(command):
        print(
            "P8: no `cd` in a command. Parallel tool calls share one shell; use absolute paths, "
            "`make -C DIR`, `git -C DIR`, `python3 /abs/script.py`.",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
