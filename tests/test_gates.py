"""Gate tests on the fixture boards.

The fixture boards under tests/boards are the real tests of this
workcenter: one passes every gate, the others fail a named gate for a
known reason. KiCad-dependent tests skip loudly when kicad-cli is absent.
"""

from __future__ import annotations

import importlib.machinery
import json
import shutil
import subprocess
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "tools" / "workcenter"
BOARDS = ROOT / "tests" / "boards"

needs_kicad = pytest.mark.skipif(shutil.which("kicad-cli") is None, reason="kicad-cli is not installed")
needs_ngspice = pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice is not installed")


def load_cli_module():
    loader = importlib.machinery.SourceFileLoader("workcenter_cli", str(CLI))
    module = types.ModuleType("workcenter_cli")
    module.__file__ = str(CLI)
    sys.modules[module.__name__] = module  # dataclasses look the defining module up here
    loader.exec_module(module)
    return module


def run(*args: object) -> tuple[int, list[dict]]:
    proc = subprocess.run(
        [sys.executable, str(CLI), "--json", *map(str, args)],
        capture_output=True,
        text=True,
        check=False,
    )
    payload = json.loads(proc.stdout) if proc.stdout.strip() else []
    return proc.returncode, payload


def statuses(records: list[dict]) -> dict[str, str]:
    return {r["gate"]: r["status"] for r in records}


# ----------------------------------------------------------- pure logic


def test_find_project_resolves_siblings():
    wc = load_cli_module()
    project = wc.find_project(str(BOARDS / "pass-rc-divider"))
    assert project.name == "rc_divider"
    assert project.sch and project.sch.name == "rc_divider.kicad_sch"
    assert project.pcb and project.pcb.name == "rc_divider.kicad_pcb"


def test_find_project_rejects_empty_dir(tmp_path):
    wc = load_cli_module()
    with pytest.raises(SystemExit):
        wc.find_project(str(tmp_path))


def test_count_severity_buckets():
    wc = load_cli_module()
    counts = wc.count_severity([{"severity": "error"}, {"severity": "warning"}, {"severity": "error"}, {}])
    assert counts == {"error": 2, "warning": 1, "other": 1}


def test_exit_code_fail_beats_skip():
    wc = load_cli_module()
    results = [wc.Result("erc", "skip", ""), wc.Result("drc", "fail", "")]

    class Args:
        json = True

    import contextlib
    import io

    with contextlib.redirect_stdout(io.StringIO()):
        code = wc.emit(results, Args())
    assert code == wc.EXIT_FAIL


# ------------------------------------------------------------ doctor


def test_doctor_reports_every_engine():
    code, _ = run("doctor")
    proc = subprocess.run(
        [sys.executable, str(CLI), "--json", "doctor"], capture_output=True, text=True, check=False
    )
    payload = json.loads(proc.stdout)
    assert set(payload["checks"]) >= {"kicad-cli", "ngspice", "python", "java", "freerouting", "manifest"}
    assert payload["checks"]["manifest"]["ok"] is True
    assert code in (0, 1)


# -------------------------------------------------------------- SIM gate


@needs_ngspice
def test_sim_gate_fails_on_spec_miss(tmp_path):
    code, records = run("sim", BOARDS / "fail-sim-spec", "--out", tmp_path)
    assert code == 1
    (record,) = records
    assert record["status"] == "fail"
    checks = record["details"]["decks"]["rc_divider"]["checks"]
    assert checks["vout"]["ok"] is False
    assert checks["vout"]["value"] is not None, "ngspice printed no vout; deck or parser broke"


@needs_ngspice
def test_sim_gate_passes_within_bounds(tmp_path):
    code, records = run("sim", BOARDS / "pass-rc-divider", "--out", tmp_path)
    assert code == 0, records
    (record,) = records
    assert record["status"] == "pass"
    vout = record["details"]["decks"]["rc_divider"]["measures"]["vout"]
    assert 2.45 <= vout <= 2.55


# -------------------------------------------------------- KiCad gates


@needs_kicad
@needs_ngspice
def test_pass_board_is_green(tmp_path):
    code, records = run("gates", BOARDS / "pass-rc-divider", "--out", tmp_path)
    assert code == 0, records
    assert statuses(records) == {"erc": "pass", "drc": "pass", "sim": "pass", "export": "pass"}
    assert (tmp_path / "gates.json").is_file()
    assert (tmp_path / "fab" / "bom.csv").is_file()
    assert (tmp_path / "fab" / "schematic.pdf").is_file()
    gerbers = list((tmp_path / "fab" / "gerbers").iterdir())
    assert any(p.suffix.lower() in (".gbr", ".gtl", ".gbl") for p in gerbers), gerbers
    assert any(p.suffix.lower() == ".drl" for p in gerbers), gerbers


@needs_kicad
def test_fail_board_stops_at_drc(tmp_path):
    code, records = run("gates", BOARDS / "fail-drc-clearance", "--out", tmp_path)
    assert code == 1
    assert [r["gate"] for r in records] == ["erc", "drc"], "gates must stop at the first red gate"
    assert records[0]["status"] == "pass"
    assert records[1]["status"] == "fail"
    types = {v["type"] for v in records[1]["details"]["first"]}
    assert "clearance" in types, types
    assert not (tmp_path / "fab").exists(), "export must not run after a red DRC"


@needs_kicad
def test_pass_board_erc_and_drc_are_clean_even_in_strict_mode(tmp_path):
    code, records = run("erc", BOARDS / "pass-rc-divider", "--out", tmp_path, "--strict")
    assert code == 0, records
    assert records[0]["details"]["counts"] == {"error": 0, "warning": 0, "other": 0}
    code, records = run("drc", BOARDS / "pass-rc-divider", "--out", tmp_path, "--strict")
    assert code == 0, records


def test_autoroute_without_dsn_skips_loudly(tmp_path):
    code, records = run("autoroute", BOARDS / "pass-rc-divider", "--out", tmp_path)
    (record,) = records
    assert record["status"] == "skip"
    assert code == 2
    assert "DSN" in record["summary"] or "engine missing" in record["summary"]


def test_fixtures_match_generator():
    proc = subprocess.run(
        [sys.executable, str(BOARDS / "generate.py"), "--check"], capture_output=True, text=True, check=False
    )
    assert proc.returncode == 0, f"fixtures drifted from generate.py:\n{proc.stdout}"
