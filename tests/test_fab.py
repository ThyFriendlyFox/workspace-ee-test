"""Fabrication house rule sets (rules/*.kicad_dru): `workcenter drc|gates --fab` and `Design.fab`.

The fixture fail-fab-sierra is the passing divider with a 0.6/0.3 mm via (a 0.15 mm ring) and a legend
label stroked 0.10 mm: GREEN on the gates, RED with Sierra Circuits' Web PCB limits (6 mil ring, 5 mil
legend). KiCad-dependent tests skip when kicad-cli is absent.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "tools" / "workcenter"
BOARDS = ROOT / "tests" / "boards"
sys.path.insert(0, str(ROOT / "tools"))
import kicadgen  # noqa: E402

SIERRA = "sierra-circuits-web"
needs_kicad = pytest.mark.skipif(shutil.which("kicad-cli") is None, reason="kicad-cli is not installed")


def run(*args: object) -> tuple[int, list[dict]]:
    proc = subprocess.run(
        [sys.executable, str(CLI), "--json", *map(str, args)], capture_output=True, text=True, check=False
    )
    return proc.returncode, (json.loads(proc.stdout) if proc.stdout.strip() else [])


def drc_types(out: Path) -> set[str]:
    data = json.loads((out / "drc.json").read_text(encoding="utf-8"))
    return {v["type"] for v in data["violations"]}


@needs_kicad
def test_fixture_is_green_without_the_fab_and_red_with_it(tmp_path):
    code, records = run("gates", BOARDS / "fail-fab-sierra", "--strict", "--out", tmp_path / "plain")
    assert code == 0, records
    code, records = run("gates", BOARDS / "fail-fab-sierra", "--fab", SIERRA, "--out", tmp_path / "fab")
    assert code == 1
    assert [r["gate"] for r in records] == ["erc", "drc"]
    drc = records[1]
    assert drc["status"] == "fail" and drc["details"]["fab"] == SIERRA
    assert {"annular_width", "text_thickness"} <= drc_types(tmp_path / "fab")
    rules = {v["description"] for v in drc["details"]["first"]}
    assert any("sierra-web: annular ring 6 mil" in r for r in rules), rules


@needs_kicad
def test_the_passing_divider_meets_the_fab_and_the_project_is_untouched(tmp_path):
    before = sorted(p.name for p in (BOARDS / "pass-rc-divider").iterdir())
    code, records = run("drc", BOARDS / "pass-rc-divider", "--fab", SIERRA, "--strict", "--out", tmp_path)
    assert code == 0, records
    assert not (BOARDS / "pass-rc-divider" / "rc_divider.kicad_dru").exists()
    assert sorted(p.name for p in (BOARDS / "pass-rc-divider").iterdir() if p.name != "build") == [
        n for n in before if n != "build"
    ]


def test_an_unknown_fab_is_refused_with_the_known_ones(tmp_path):
    code, records = run("drc", BOARDS / "pass-rc-divider", "--fab", "nofab", "--out", tmp_path)
    (record,) = records
    assert record["status"] == "error" and code != 0
    assert SIERRA in record["summary"]


def test_fab_minimums_are_the_board_wide_rules_only():
    mins = kicadgen.fab_minimums(kicadgen.fab_rules(SIERRA).read_text(encoding="utf-8"))
    assert mins == {
        "min_track_width": 0.1016,
        "min_clearance": 0.1016,
        "min_through_hole_diameter": 0.1524,
        "min_via_annular_width": 0.1524,
    }  # the inner-layer drill rule and the legend rule stay in the rule file


def test_design_fab_raises_the_board_rules_and_refuses_the_fabs_vias(tmp_path):
    d = kicadgen.Design(name="t", namespace=uuid.UUID(int=11), fab=SIERRA)
    rules = d.board_rules()
    assert rules["min_via_annular_width"] == 0.1524  # raised from the workcenter's 0.1
    assert rules["min_through_hole_diameter"] == 0.3  # the board's own is stricter and stays
    assert any("annular ring 0.15 is below the board's minimum 0.1524" in p for p in d.check_via_rules())
    d.via_size, d.via_drill = 0.65, 0.3  # a 0.175 mm ring
    assert d.check_via_rules() == []
    d.rules = {"min_via_annular_width": 0.2}  # a design's own rule still wins
    assert d.board_rules()["min_via_annular_width"] == 0.2


def test_design_fab_writes_the_rule_file_into_the_project(tmp_path):
    d = kicadgen.Design(name="t", namespace=uuid.UUID(int=12), fab=SIERRA)
    d.outline = (100.0, 100.0, 110.0, 110.0)
    written = d.write(tmp_path)
    dru = tmp_path / "t.kicad_dru"
    assert dru in written
    text = dru.read_text(encoding="utf-8")
    assert text.startswith("(version 1)") and "sierra-web: inner drill to copper 13 mil" in text
    assert "Copied by the workcenter from sierra-circuits-web.kicad_dru" in text
    plain = kicadgen.Design(name="p", namespace=uuid.UUID(int=13))
    plain.outline = (100.0, 100.0, 110.0, 110.0)
    plain.write(tmp_path)
    assert not (tmp_path / "p.kicad_dru").exists()


def test_an_unknown_design_fab_is_refused():
    with pytest.raises(ValueError, match="no fab rule set 'nofab'"):
        kicadgen.Design(name="t", namespace=uuid.UUID(int=14), fab="nofab").board_rules()
