#!/usr/bin/env bash
# environment/setup.sh — the setup script for a Claude Code cloud environment.
#
# Paste the 3 lines under "Setup script" into the environment's settings in
# claude.ai (cloud environment menu in the session title bar, then Edit), or
# paste this whole file. It runs as root before Claude Code launches, once per
# environment snapshot. See environment/README.md for the network hosts.
#
# Setup script:
#   git clone --depth 1 https://github.com/ThyFriendlyFox/workspace-ee-test /opt/workcenters/ee/src
#   bash /opt/workcenters/ee/src/install.sh
#   bash /opt/workcenters/ee/src/install.sh --check
set -euo pipefail

SRC=/opt/workcenters/ee/src
REPO="${WORKCENTER_REPO:-https://github.com/ThyFriendlyFox/workspace-ee-test}"
REF="${WORKCENTER_REF:-main}"

if [[ -d "$SRC/.git" ]]; then
  git -C "$SRC" fetch --depth 1 origin "$REF"
  git -C "$SRC" checkout -q FETCH_HEAD
else
  git clone --depth 1 --branch "$REF" "$REPO" "$SRC"
fi
bash "$SRC/install.sh"
bash "$SRC/install.sh" --check
