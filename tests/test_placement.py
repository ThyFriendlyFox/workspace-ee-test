"""kistack's layout-placement checks, run headless through `workcenter placement`.

The board is kistack's own synthetic fixture (third_party/kistack/tests/layout-placement/
make_fixture.py): a 16-pin QFN with three capacitors and a resistor. kistack's tests run the same
checks over KiCad's IPC API, which KiCad 10.0 cannot serve headless; here tools/kistack_board.py
reads the board file instead, and the answers below are the ones kistack's tests expect.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / "tools" / "workcenter"
FIXTURE = ROOT / "third_party" / "kistack" / "tests" / "layout-placement" / "make_fixture.py"


def _needs_geometry():
    pytest.importorskip("pcbnew")
    pytest.importorskip("shapely")


@pytest.fixture(scope="module")
def board(tmp_path_factory) -> Path:
    _needs_geometry()
    out = tmp_path_factory.mktemp("kistack")
    subprocess.run([sys.executable, "-I", str(FIXTURE), str(out)], check=True)
    return out / "fixture.kicad_pcb"


def placement(*args: object) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI), "placement", *map(str, args)], capture_output=True, text=True, timeout=600
    )


def test_pin_sides_reads_the_board_file(board):
    r = placement("pin_sides", board, "U1")
    assert r.returncode == 0, r.stderr
    assert "pin   1 VDD" in r.stdout
    assert "centre: 1 pads, nets ['GND']" in r.stdout  # the exposed pad


def test_unknown_part_is_refused(board):
    r = placement("pin_sides", board, "U9")
    assert r.returncode == 1
    assert "no footprint U9" in r.stderr


def test_audit_finds_a_decoupler_turned_the_wrong_way(board):
    r = placement("placement_audit", board, "--ic", "U1")
    assert r.returncode == 0, r.stderr
    # C1 sits 1.7 mm from pin 1 with its ground pad toward the pin, which the audit flags.
    assert "1.700 mm to C1.1  GROUND PAD FACES PIN" in r.stdout
    # the rules come from the fixture's .kicad_pro through the stand-in's board object
    assert "track width 0.150 mm (board minimum min_track_width)" in r.stderr


def test_route_check_routes_the_local_links(board):
    r = placement("route_check", board, "--ic", "U1")
    assert r.returncode == 0, r.stderr
    assert "all local links together: yes" in r.stdout
    assert "escapes to the edge routed in both orders: 11/11" in r.stdout


def test_move_is_refused_for_a_generated_board(board):
    r = placement("move", board, "C1=105,95,90")
    assert r.returncode == 2
    assert "design.py" in r.stderr


def test_unknown_check_is_refused(board):
    r = placement("reroute_everything", board)
    assert r.returncode != 0
    assert "not one of" in r.stderr
