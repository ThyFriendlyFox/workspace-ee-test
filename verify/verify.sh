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
     agent-kit docs 2>/dev/null | grep -v '^agent-kit/SETUP.md:'; then
  echo "unfilled kit placeholders found"; exit 1
fi
for skill in .claude/skills/*/SKILL.md agent-kit/skills/*/SKILL.md; do
  head -1 "$skill" | grep -q '^---$' || { echo "$skill: missing frontmatter"; exit 1; }
  grep -q '^name:' "$skill" || { echo "$skill: missing name"; exit 1; }
  grep -q '^description:' "$skill" || { echo "$skill: missing description"; exit 1; }
done
for kit_skill in agent-kit/skills/*/; do
  name=$(basename "$kit_skill")
  diff -q "$kit_skill/SKILL.md" ".claude/skills/$name/SKILL.md" >/dev/null \
    || { echo "agent-kit/skills/$name drifted from .claude/skills/$name"; exit 1; }
done
[[ -f WORKCENTER.md ]] || { echo "WORKCENTER.md missing at repo root"; exit 1; }
echo "kit checks ok"

printf '\nVERIFY GREEN\n'
