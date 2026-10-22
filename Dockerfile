# EE Workcenter image: KiCad 10 (official image) + ngspice + FreeRouting + this repo.
# Build:  docker build -t ee-workcenter .
# Run:    docker run --rm -v "$PWD/board:/work" ee-workcenter workcenter gates /work
#
# Not built in the cloud session that authored it (no Docker daemon there);
# release.yml builds and smoke-tests it on every tag. See ee-agent-kit/CI.md.
FROM kicad/kicad:10.0

USER root
ENV DEBIAN_FRONTEND=noninteractive
COPY . /opt/workcenters/ee/src
WORKDIR /opt/workcenters/ee/src
# The image ships kicad-cli 10, so install.sh skips the PPA and adds the rest.
RUN REQUIRE_FREEROUTING=1 ./install.sh \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

USER kicad
WORKDIR /work
ENTRYPOINT []
CMD ["workcenter", "doctor"]
