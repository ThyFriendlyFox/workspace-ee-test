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
    # the ring is a board-wide limit, so the copy's own minimum carries it (M62); the legend rule has
    # a condition and stays a rule
    assert any("board setup constraints min annular width 0.1524 mm" in r for r in rules), rules
    assert any("sierra-web: legend text stroke 5 mil" in r for r in rules), rules


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


def test_the_project_rule_file_never_loosens_the_boards_own_rules():
    text = kicadgen.fab_rules(SIERRA).read_text(encoding="utf-8")
    kept = kicadgen.fab_project_rules(text, {"min_hole_clearance": 0.25, "min_text_thickness": 0.1})
    # a board-wide rule would override every net class's clearance with the fab's 4 mil (M62)
    assert "(constraint clearance" not in kept and "(constraint track_width" not in kept
    assert "(constraint annular_width" not in kept and "(constraint hole_size" not in kept
    assert "is board-wide: carried as the board's own minimum (min_clearance 0.1016 mm)" in kept
    assert "(constraint hole_clearance (min 0.3302mm))" in kept  # the fab's is the stricter
    assert "(constraint text_thickness (min 0.127mm))" in kept
    stricter = kicadgen.fab_project_rules(text, {"min_hole_clearance": 0.4, "min_text_thickness": 0.13})
    assert "(constraint hole_clearance (min 0.4mm))" in stricter  # the board's own is the stricter
    assert "(constraint text_thickness (min 0.13mm))" in stricter


def narrow_pair(name: str, n: int, fab: str = "") -> kicadgen.Design:
    """Net A in a class with 0.3 mm clearance, and net B's track 0.25 mm beside it: wide enough for the
    board's 0.2 mm and the fab's 4 mil, too narrow for the class."""
    d = kicadgen.Design(name=name, namespace=uuid.UUID(int=n), outline=(100.0, 100.0, 112.0, 110.0), fab=fab)
    d.add(
        "R1",
        "Device:R",
        "10k",
        "Resistor_SMD:R_0603_1608Metric",
        sch_at=(50.8, 50.8),
        pcb_at=(103.0, 103.0),
        nets={"1": "A", "2": "B"},
    )
    d.net_classes = {"Wide": {"width": 0.2, "clearance": 0.3, "via": 0.6, "via_drill": 0.3, "nets": ["A"]}}
    d.track("A", [(102.225, 103.0), (102.225, 108.0)], "F.Cu", width=0.2)
    d.track("B", [(103.775, 103.0), (103.775, 106.0), (102.675, 106.0), (102.675, 108.0)], "F.Cu", width=0.2)
    return d


def class_clearances(out: Path) -> list[str]:
    data = json.loads((out / "drc.json").read_text(encoding="utf-8"))
    return [v["description"] for v in data["violations"] if v["type"] == "clearance"]


@needs_kicad
def test_a_net_class_clearance_holds_under_the_fab(tmp_path):
    """A fab rule file must add the fab's floors, never replace the board's own rules: under the
    Sierra rules a 0.25 mm gap next to a 0.3 mm net class is still a clearance error (M62)."""
    plain = tmp_path / "plain"
    narrow_pair("nc", 62).write(plain)
    run("drc", plain, "--out", plain / "build")
    assert any("clearance 0.3000 mm" in d for d in class_clearances(plain / "build"))

    with_fab = tmp_path / "fab"
    narrow_pair("nc", 62, fab=SIERRA).write(with_fab)
    assert "(constraint clearance" not in (with_fab / "nc.kicad_dru").read_text(encoding="utf-8")
    run("drc", with_fab, "--out", with_fab / "build")
    assert any("clearance 0.3000 mm" in d for d in class_clearances(with_fab / "build"))

    code, records = run("drc", plain, "--fab", SIERRA, "--out", tmp_path / "once")
    assert code == 1 and records[0]["details"]["fab"] == SIERRA
    assert any("clearance 0.3000 mm" in d for d in class_clearances(tmp_path / "once"))


def test_an_unknown_design_fab_is_refused():
    with pytest.raises(ValueError, match="no fab rule set 'nofab'"):
        kicadgen.Design(name="t", namespace=uuid.UUID(int=14), fab="nofab").board_rules()
