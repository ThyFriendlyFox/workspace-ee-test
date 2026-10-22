#!/usr/bin/env bash
# install.sh — install the EE Workcenter toolchain on Ubuntu 24.04.
#
# Usage:
#   sudo ./install.sh            install or update every engine
#   ./install.sh --check         report engine status; install nothing
#
# Every step skips work that is already done, so the script is safe to
# run again. A required step that fails exits non-zero, so a cloud
# environment that runs this as its setup script fails to start instead
# of starting without tools.
#
# Environment overrides:
#   WORKCENTER_ROOT       install root            (default /opt/workcenters/ee)
#   FREEROUTING_VERSION   FreeRouting release     (default below)
#   FREEROUTING_SHA256    expected JAR checksum   (default below; empty skips the check)
#   FREEROUTING_URL       JAR download URL        (default: GitHub release asset)
#   REQUIRE_FREEROUTING   1 makes a failed JAR download fatal (default 0: warn)
#   SKIP_APT              1 skips the apt step (for images that ship KiCad 10)

set -euo pipefail

WC_NAME="ee"
WC_ROOT="${WORKCENTER_ROOT:-/opt/workcenters/${WC_NAME}}"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# KiCad 10 PPA, added by writing the sources file and key directly:
# add-apt-repository needs the system python's apt_pkg, which images with a
# different default python3 do not have.
KICAD_PPA_URL="https://ppa.launchpadcontent.net/kicad/kicad-10.0-releases/ubuntu/"
KICAD_PPA_FPR="FDA854F61C4D0D9572BB95E5245D5502FAD7A805"   # "PPA for KiCad: 10.0 releases"
KICAD_KEYRING="/etc/apt/keyrings/kicad-10.0-releases.gpg"
KICAD_SOURCES="/etc/apt/sources.list.d/kicad-10.0-releases.sources"
KICAD_PACKAGES=(kicad kicad-symbols kicad-footprints kicad-templates)
BASE_PACKAGES=(ngspice openjdk-21-jre-headless xvfb shellcheck
               python3 python3-venv python3-pip curl ca-certificates)

FREEROUTING_VERSION="${FREEROUTING_VERSION:-2.1.0}"
FREEROUTING_SHA256="${FREEROUTING_SHA256:-2c07d58f75dac03782664081e7a58b41c25400d871a9fcf166a2ea6fe60d5def}"
FREEROUTING_URL="${FREEROUTING_URL:-https://github.com/freerouting/freerouting/releases/download/v${FREEROUTING_VERSION}/freerouting-${FREEROUTING_VERSION}.jar}"
REQUIRE_FREEROUTING="${REQUIRE_FREEROUTING:-0}"
SKIP_APT="${SKIP_APT:-0}"

log() { printf '[install] %s\n' "$*"; }
warn() { printf '[install] WARN: %s\n' "$*" >&2; }
die() { printf '[install] ERROR: %s\n' "$*" >&2; exit 1; }

kicad10_present() {
  command -v kicad-cli >/dev/null 2>&1 && kicad-cli version 2>/dev/null | grep -q '^10\.'
}

add_kicad_ppa() {
  local codename
  # shellcheck source=/dev/null
  codename="$(. /etc/os-release && echo "${VERSION_CODENAME}")"
  install -d -m 0755 /etc/apt/keyrings
  if [[ ! -s "$KICAD_KEYRING" ]]; then
    log "apt: fetching PPA signing key ${KICAD_PPA_FPR}"
    curl -fsSL --retry 3 --connect-timeout 20 \
      "https://keyserver.ubuntu.com/pks/lookup?op=get&options=mr&search=0x${KICAD_PPA_FPR}" \
      | gpg --dearmor -o "${KICAD_KEYRING}.tmp"
    gpg --no-default-keyring --keyring "${KICAD_KEYRING}.tmp" --list-keys --with-colons 2>/dev/null \
      | grep -q "^fpr:::::::::${KICAD_PPA_FPR}:" \
      || die "apt: PPA key fingerprint mismatch; refusing to trust it"
    mv "${KICAD_KEYRING}.tmp" "$KICAD_KEYRING"
    chmod 0644 "$KICAD_KEYRING"
  fi
  cat > "$KICAD_SOURCES" <<EOF
Types: deb
URIs: ${KICAD_PPA_URL}
Suites: ${codename}
Components: main
Signed-By: ${KICAD_KEYRING}
EOF
  log "apt: ${KICAD_SOURCES} written for ${codename}"
}

step_apt() {
  if [[ "$SKIP_APT" == "1" ]]; then
    log "apt: skipped (SKIP_APT=1)"
    return
  fi
  export DEBIAN_FRONTEND=noninteractive
  local packages=("${BASE_PACKAGES[@]}")
  if kicad10_present; then
    log "apt: KiCad 10 present ($(kicad-cli version)); PPA step skipped"
  else
    add_kicad_ppa
    packages+=("${KICAD_PACKAGES[@]}")
  fi
  log "apt: update"
  apt-get update -qq
  log "apt: install ${packages[*]}"
  apt-get install -y -qq --no-install-recommends "${packages[@]}" >/dev/null
  kicad10_present || die "kicad-cli 10.x not found after install"
  log "apt: done; kicad-cli $(kicad-cli version)"
}

step_freerouting() {
  local dir="${WC_ROOT}/freerouting"
  local jar="${dir}/freerouting-${FREEROUTING_VERSION}.jar"
  mkdir -p "$dir"
  if [[ ! -s "$jar" ]]; then
    log "freerouting: downloading ${FREEROUTING_URL}"
    if curl -fsSL --retry 3 --connect-timeout 20 -o "${jar}.tmp" "$FREEROUTING_URL"; then
      mv "${jar}.tmp" "$jar"
    else
      rm -f "${jar}.tmp"
      if [[ "$REQUIRE_FREEROUTING" == "1" ]]; then
        die "freerouting: download failed and REQUIRE_FREEROUTING=1"
      fi
      warn "freerouting: download failed; the autoroute engine is unavailable until the JAR is placed at ${jar}"
      return
    fi
  fi
  if [[ -n "$FREEROUTING_SHA256" ]]; then
    echo "${FREEROUTING_SHA256}  ${jar}" | sha256sum -c - >/dev/null \
      || die "freerouting: checksum mismatch for ${jar}"
    log "freerouting: checksum ok"
  else
    warn "freerouting: no FREEROUTING_SHA256 set; checksum not verified ($(sha256sum "$jar" | cut -d' ' -f1))"
  fi
  ln -sfn "$jar" "${dir}/freerouting.jar"
  log "freerouting: ${jar}"
}

step_python() {
  local venv="${WC_ROOT}/venv"
  if [[ ! -x "${venv}/bin/python" ]]; then
    log "python: creating venv at ${venv}"
    python3 -m venv "$venv"
  fi
  log "python: installing requirements.txt into venv"
  "${venv}/bin/pip" install -q --upgrade pip
  "${venv}/bin/pip" install -q -r "${SRC_DIR}/requirements.txt"
  log "python: $("${venv}/bin/python" --version), $("${venv}/bin/pip" list --format=freeze 2>/dev/null | grep -Ei '^(kicad-python|pytest|ruff)=' | tr '\n' ' ')"
}

step_link() {
  mkdir -p "$WC_ROOT"
  ln -sfn "${SRC_DIR}/tools/workcenter" /usr/local/bin/workcenter
  install -m 0644 "${SRC_DIR}/WORKCENTER.md" "${WC_ROOT}/WORKCENTER.md"
  cat > "${WC_ROOT}/env.sh" <<EOF
# Generated by install.sh. Source this to address the workcenter from a shell.
export WORKCENTER_ROOT="${WC_ROOT}"
export WORKCENTER_SRC="${SRC_DIR}"
export FREEROUTING_JAR="${WC_ROOT}/freerouting/freerouting.jar"
EOF
  log "link: /usr/local/bin/workcenter -> ${SRC_DIR}/tools/workcenter"
  log "link: manifest at ${WC_ROOT}/WORKCENTER.md"
}

main() {
  if [[ "${1:-}" == "--check" ]]; then
    exec python3 "${SRC_DIR}/tools/workcenter" doctor
  fi
  [[ "$EUID" -eq 0 ]] || die "run as root (sudo ./install.sh)"
  local t0=$SECONDS
  step_apt
  step_freerouting
  step_python
  step_link
  log "done in $((SECONDS - t0))s"
  python3 "${SRC_DIR}/tools/workcenter" doctor
}

main "$@"
