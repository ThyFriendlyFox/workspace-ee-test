#!/usr/bin/env bash
# verify/verify.sh — one command answers "is this repo healthy".
# Runs the same steps locally and in CI, in this order:
#   1 lint  2 doctor (toolchain present)  3 tests on fixture boards
#   4 kit checks (no placeholders, every skill has frontmatter, manifest copied)
# A step that cannot run fails loudly; nothing passes silently.
set -euo pipefail
cd "$(dirname "$0")/.."

VENV_PY=/opt/workcenters/ee/venv/bin/python
PY=python3
[[ -x "$VENV_PY" ]] && PY="$VENV_PY"

step() { printf '\n== %s\n' "$*"; }

step "1/4 lint"
shellcheck install.sh verify/verify.sh environment/setup.sh
"$PY" -m ruff check tools tests
"$PY" -m ruff format --check tools tests

step "2/4 doctor"
python3 tools/workcenter doctor

step "3/4 tests"
"$PY" -m pytest -q tests

step "4/4 kit checks"
# Kit placeholders may remain only in SETUP.md, whose table documents them.
if grep -rnE '\{\{(PROJECT_NAME|REPO_SLUG|DEFAULT_BRANCH|BUILD_CMD|TEST_CMD|LINT_CMD|VERIFY_CMD|MIN_RUNTIME|SECURITY_EMAIL|PKG_ECOSYSTEM)\}\}' \
     ee-agent-kit docs 2>/dev/null | grep -v '^ee-agent-kit/SETUP.md:'; then
  echo "unfilled kit placeholders found"; exit 1
fi
for skill in .claude/skills/*/SKILL.md ee-agent-kit/skills/*/SKILL.md; do
  head -1 "$skill" | grep -q '^---$' || { echo "$skill: missing frontmatter"; exit 1; }
  grep -q '^name:' "$skill" || { echo "$skill: missing name"; exit 1; }
  grep -q '^description:' "$skill" || { echo "$skill: missing description"; exit 1; }
done
for kit_skill in ee-agent-kit/skills/*/; do
  name=$(basename "$kit_skill")
  diff -q "$kit_skill/SKILL.md" ".claude/skills/$name/SKILL.md" >/dev/null \
    || { echo "ee-agent-kit/skills/$name drifted from .claude/skills/$name"; exit 1; }
done
[[ -f WORKCENTER.md ]] || { echo "WORKCENTER.md missing at repo root"; exit 1; }
# Every mistake names a process that exists; every process says when it is done.
grep -oE '^Process: P[0-9]+' ee-agent-kit/MISTAKES.md | awk '{print $2}' | sort -u | while read -r p; do
  grep -qE "^## $p " ee-agent-kit/PROCESSES.md || { echo "MISTAKES.md names $p; PROCESSES.md has no '## $p'"; exit 1; }
done || exit 1
awk '/^## M[0-9]+ /{if (h != "" && !p) {print h ": no Process line"; bad = 1}; h = $0; p = 0}
     /^Process: P[0-9]+$/{p = 1}
     END{if (h != "" && !p) {print h ": no Process line"; bad = 1}; exit bad}' ee-agent-kit/MISTAKES.md || exit 1
awk '/^## P[0-9]+ /{if (h != "" && !d) {print h ": no Done when line"; bad = 1}; h = $0; d = 0}
     /^Done when:/{d = 1}
     END{if (h != "" && !d) {print h ": no Done when line"; bad = 1}; exit bad}' ee-agent-kit/PROCESSES.md || exit 1
echo "kit checks ok"

printf '\nVERIFY GREEN\n'
