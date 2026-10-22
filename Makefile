# EE Workcenter — canonical commands. agent-kit/AGENTS.md names these.
VENV_PY := /opt/workcenters/ee/venv/bin/python
PY := $(shell test -x $(VENV_PY) && echo $(VENV_PY) || echo python3)

.PHONY: install doctor lint format test verify image

install:            ## install or update every engine (root)
	./install.sh

doctor:             ## report engine status; the "build" of this repo is a working toolchain
	python3 tools/workcenter doctor

lint:               ## shellcheck + ruff, read-only
	shellcheck install.sh verify/verify.sh environment/setup.sh
	$(PY) -m ruff check tools tests
	$(PY) -m ruff format --check tools tests

format:             ## apply ruff formatting
	$(PY) -m ruff format tools tests

test:               ## gate tests on the fixture boards
	$(PY) -m pytest -q tests

verify:             ## the full health gate: lint -> doctor -> test -> kit checks
	verify/verify.sh

image:              ## build the Docker image (needs a Docker daemon)
	docker build -t ee-workcenter:dev .
