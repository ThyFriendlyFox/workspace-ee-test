"""Tests for tools/kicadgen.py: the library-backed design generator.

Library-dependent tests skip loudly when the KiCad libraries are absent;
routing tests skip when FreeRouting is absent. The round trip test builds
a 2-resistor board, routes it, merges the session, and expects DRC clean.
"""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import kicadgen  # noqa: E402
import wrlgen  # noqa: E402

CLI = ROOT / "tools" / "workcenter"
LIBS = kicadgen.SYMBOL_DIR / "Device.kicad_sym"
JAR = Path("/opt/workcenters/ee/freerouting/freerouting.jar")

needs_libs = pytest.mark.skipif(not LIBS.is_file(), reason="KiCad symbol libraries are not installed")
needs_kicad = pytest.mark.skipif(shutil.which("kicad-cli") is None, reason="kicad-cli is not installed")
needs_router = pytest.mark.skipif(
    not JAR.is_file() or shutil.which("java") is None, reason="FreeRouting is not installed"
)


# ----------------------------------------------------------- S-expressions


def test_parse_and_dump_round_trip_keeps_quoting():
    text = '(a "quoted \\"x\\"" bare 1.5 (b (c "d")))'
    node = kicadgen.parse(text)
    assert node[0] == "a"
    assert isinstance(node[1], kicadgen.Q) and node[1] == 'quoted "x"'
    assert not isinstance(node[2], kicadgen.Q)
    out = kicadgen.dumps(node)
    assert kicadgen.parse(out) == node
    assert '"quoted \\"x\\""' in out


def test_children_and_atoms_helpers():
    node = kicadgen.parse('(pad "1" smd rect (at 1 2 90) (size 3 4))')
    assert kicadgen.atoms(node) == ["1", "smd", "rect"]
    assert kicadgen.atoms(kicadgen.child(node, "at")) == ["1", "2", "90"]
    assert kicadgen.child(node, "missing") is None


# ---------------------------------------------------------------- library


@needs_libs
def test_load_symbol_flattens_extends_and_keeps_child_properties():
    sym = kicadgen.load_symbol("Regulator_Linear:TLV75533PDBV")
    assert sym.lib_id == "Regulator_Linear:TLV75533PDBV"
    assert kicadgen.child(sym.node, "extends") is None
    names = {p.number: p.name for p in sym.pins}
    assert names["1"] == "IN" and names["5"] == "OUT"
    assert sym.pin("4").hidden
    units = [str(kicadgen.atoms(u)[0]) for u in kicadgen.children(sym.node, "symbol")]
    assert all(u.startswith("TLV75533PDBV_") for u in units), units
    values = {
        str(kicadgen.atoms(p)[0]): str(kicadgen.atoms(p)[1]) for p in kicadgen.children(sym.node, "property")
    }
    assert values["Value"] == "TLV75533PDBV"


@needs_libs
def test_load_symbol_strips_kicad10_only_tokens():
    sym = kicadgen.load_symbol("Device:R")
    text = kicadgen.dumps(sym.node)
    for token in kicadgen.DROP_SYMBOL_TOKENS:
        assert f"({token}" not in text


@needs_libs
def test_load_footprint_reads_pads_and_courtyard():
    fp = kicadgen.load_footprint("Package_TO_SOT_SMD:SOT-23")
    assert [p.number for p in fp.pads] == ["1", "2", "3"]
    assert fp.pads[0].kind == "smd"
    assert fp.courtyard is not None and fp.courtyard[0] < 0 < fp.courtyard[2]
    assert kicadgen.child(fp.node, "version") is None


# ----------------------------------------------------------------- design


def divider() -> kicadgen.Design:
    d = kicadgen.Design(
        name="gen_divider",
        namespace=uuid.UUID("1b2c3d4e-0000-4000-8000-000000000001"),
        outline=(100.0, 100.0, 112.0, 110.0),
        title="GEN",
    )
    d.power_nets = {"GND": "GND", "VIN": "VBUS"}
    d.flagged_nets = ["GND", "VIN"]
    r = "Resistor_SMD:R_0603_1608Metric"
    d.add(
        "J1",
        "Connector_Generic:Conn_01x03",
        "IN",
        "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical",
        sch_at=(50.8, 50.8),
        pcb_at=(103.0, 102.5),
        nets={"1": "VIN", "2": "OUT", "3": "GND"},
    )
    d.add(
        "R1",
        "Device:R",
        "10k",
        r,
        sch_at=(71.12, 45.72),
        pcb_at=(108.5, 102.5),
        nets={"1": "VIN", "2": "OUT"},
    )
    d.add(
        "R2",
        "Device:R",
        "10k",
        r,
        sch_at=(71.12, 58.42),
        pcb_at=(108.5, 106.5),
        nets={"1": "OUT", "2": "GND"},
    )
    return d


@needs_libs
def test_design_names_open_pins_the_kicad_way():
    d = kicadgen.Design(name="t", namespace=uuid.UUID(int=7))
    d.add(
        "U1",
        "Regulator_Linear:TLV75533PDBV",
        "x",
        "Package_TO_SOT_SMD:SOT-23-5",
        sch_at=(0, 0),
        pcb_at=(105, 105),
        nets={"1": "A", "2": "B", "5": "C"},
    )
    opened = d.unconnected_nets()
    assert opened[("U1", "3")] == "unconnected-(U1-EN-Pad3)"
    assert opened[("U1", "4")] == "unconnected-(U1-NC-Pad4)"
    ids = d.net_ids()
    assert ids["/A"] == 1 and "unconnected-(U1-EN-Pad3)" in ids


@needs_libs
def test_design_dsn_lists_routable_nets_and_classes():
    d = divider()
    d.net_classes = {"Power": {"width": 0.5, "clearance": 0.2, "via": 0.8, "via_drill": 0.4, "nets": ["VIN"]}}
    dsn = d.dsn()
    assert "(resolution um 10)" in dsn
    # A power symbol's Value is the net name; the symbol (VBUS arrow) is only how it is drawn.
    assert '(net "VIN"' in dsn and '(net "/OUT"' in dsn and '(net "GND"' in dsn
    assert "(class Power" in dsn and "(width 5000)" in dsn
    assert "Via[0-1]_800:400_um" in dsn
    # boundary shrunk by edge clearance minus clearance, in 0.1 um
    assert "1001000 -1001000" in dsn


@needs_libs
def test_merge_ses_uses_placement_scale_not_resolution():
    d = divider()
    # FreeRouting-style session: resolution says 10 per um but coordinates are 100 per um.
    ses = """(session gen_divider (placement (resolution um 10)
      (component "Resistor_SMD:R_0603_1608Metric" (place R1 10850000 -10250000 front 0)))
      (routes (resolution um 10) (network_out
        (net "/OUT" (wire (path F.Cu 25000 10932500 -10250000 10767500 -10650000))
                    (via "Via[0-1]_600:300_um" 10800000 -10400000)))))"""
    segs, vias = d.merge_ses(ses)
    assert (segs, vias) == (1, 1)
    net, start, end, width, layer = d.segments[0]
    assert net == "/OUT" and layer == "F.Cu" and abs(width - 0.25) < 1e-9
    assert start == pytest.approx((109.325, 102.5)) and end == pytest.approx((107.675, 106.5))
    assert d.vias[0][1] == pytest.approx((108.0, 104.0)) and d.vias[0][2:] == (0.6, 0.3)


# ------------------------------------------------------------- end to end


def run_cli(*args: object) -> tuple[int, list[dict]]:
    proc = subprocess.run(
        [sys.executable, str(CLI), "--json", *map(str, args)], capture_output=True, text=True, check=False
    )
    return proc.returncode, (json.loads(proc.stdout) if proc.stdout.strip() else [])


@needs_libs
@needs_kicad
def test_generated_divider_passes_erc_and_only_lacks_routing(tmp_path):
    d = divider()
    d.write(tmp_path)
    code, records = run_cli("erc", tmp_path, "--out", tmp_path / "build", "--strict")
    assert code == 0, records
    code, records = run_cli("drc", tmp_path, "--out", tmp_path / "build")
    assert code == 1
    counts = records[0]["details"]["counts"]
    assert counts["violations"]["error"] == 0 and counts["schematic_parity"]["error"] == 0
    assert counts["unconnected_items"]["error"] > 0


@needs_libs
@needs_kicad
@needs_router
def test_route_round_trip_makes_drc_green(tmp_path):
    d = divider()
    summary = kicadgen.route(d, tmp_path / "build" / "route", passes=10, timeout=600)
    assert summary["unrouted"] in (0, None), summary  # 1.9.0 logs no count; the DRC below is the proof
    assert summary["segments"] > 0
    d.write(tmp_path)
    code, records = run_cli("gates", tmp_path, "--out", tmp_path / "build")
    assert code == 0, records
    assert {r["gate"]: r["status"] for r in records} == {
        "erc": "pass",
        "drc": "pass",
        "sim": "skip",
        "export": "pass",
    }


# ------------------------------------------------------- pours and hand routes


@needs_kicad
def test_pcbnew_imports_where_kicad_is_installed():
    """Pour filling and island stitching read the board with KiCad's Python module. install.sh makes the
    venv with --system-site-packages so this interpreter sees it; without that the pour tests skip in
    silence (MISTAKES.md M17), which this test turns into a red run."""
    import pcbnew  # noqa: F401


def poured_divider() -> kicadgen.Design:
    d = divider()
    d.zone("GND", layers=("F.Cu", "B.Cu"), connect="solid")
    return d


@needs_libs
def test_zone_is_written_to_the_board_and_as_planes_to_the_dsn():
    d = poured_divider()
    board = d.board()
    assert '(net_name "GND")' in board and '(layers "F.Cu" "B.Cu")' in board
    assert "(connect_pads yes" in board  # solid
    dsn = d.dsn()
    assert '(plane "GND" (polygon F.Cu 0 ' in dsn and '(plane "GND" (polygon B.Cu 0 ' in dsn
    d2 = divider()
    d2.zone("NOPE")
    with pytest.raises(KeyError):
        d2.board()


@needs_libs
def test_hand_routed_track_and_via_are_fixed_wiring_for_the_router():
    d = divider()
    d.track("OUT", [(103.0, 105.0), (108.0, 105.0)], "F.Cu")
    d.via("OUT", 105.0, 106.0)
    dsn = d.dsn()
    assert '(wire (path F.Cu 2500 1030000 -1050000 1080000 -1050000) (net "/OUT") (type fix))' in dsn
    assert '(via "Via[0-1]_600:300_um" 1050000 -1060000 (net "/OUT") (type fix))' in dsn
    with pytest.raises(ValueError):
        d.track("OUT", [(0, 0), (1, 1)], "In1.Cu")


@needs_libs
def test_merge_skips_router_echoes_and_splits_t_junctions():
    d = divider()
    d.track("OUT", [(103.0, 105.0), (108.0, 105.0)], "F.Cu")
    d.via("OUT", 105.0, 106.0)
    ses = """(session gen_divider (placement (resolution um 10)
      (component "Resistor_SMD:R_0603_1608Metric" (place R1 10850000 -10250000 front 0)))
      (routes (resolution um 10) (network_out
        (net "/OUT"
          (wire (path F.Cu 25000 10400000 -10500000 10700000 -10500000))
          (wire (path F.Cu 25000 10800000 -10500000 10800500 -10500000))
          (wire (path F.Cu 25000 10500000 -10500000 10500000 -10700000))
          (via "Via[0-1]_600:300_um" 10500000 -10600000)))))"""
    segs, vias = d.merge_ses(ses)
    assert (segs, vias) == (1, 0)  # the echo and the hair are dropped, the fixed via is not doubled
    ends = sorted((s, e) for _, s, e, _, _ in d.segments)
    assert ends == [
        ((103.0, 105.0), (105.0, 105.0)),
        ((105.0, 105.0), (105.0, 107.0)),
        ((105.0, 105.0), (108.0, 105.0)),
    ]


@needs_libs
def test_stitch_and_reserve_put_a_via_beside_a_surface_ground_pad():
    d = poured_divider()
    assert d.stitch_pads("GND") == 1  # R2 pad 2; J1 pin 3 is through-hole and needs none
    net, (x, y), size, drill = d.vias[0]
    assert net == "GND" and (size, drill) == (0.6, 0.3)
    assert abs(x - 109.325) < 1.0 and abs(y - 106.5) < 1.5
    d = poured_divider()
    assert d.reserve_vias(["R2.2"]) == 1 and d.reserve_vias(["R2.9", "ZZ.1"]) == 0


@needs_libs
@needs_kicad
def test_write_fills_the_pour_and_stitches_a_walled_off_pad(tmp_path):
    pytest.importorskip("pcbnew")
    d = poured_divider()
    # Hand routes for every net; the OUT net rings R2's ground pad on the top face, cutting it off
    # from the pour there. The bottom pour is whole, so one via should bring it back.
    d.track("VIN", [(103.0, 102.5), (107.675, 102.5)], "F.Cu")
    d.track("OUT", [(103.0, 105.04), (106.5, 105.04), (107.675, 106.5)], "F.Cu")
    d.track("OUT", [(109.325, 102.5), (109.325, 103.8), (110.3, 104.6), (110.3, 105.5)], "F.Cu")
    d.track(
        "OUT",
        [
            (107.675, 106.5),
            (108.4, 106.5),
            (108.4, 105.5),
            (110.3, 105.5),
            (110.3, 107.5),
            (108.4, 107.5),
            (108.4, 106.5),
        ],
        "F.Cu",
    )
    d.write(tmp_path)
    assert d.islands == []
    gnd_vias = [v for v in d.vias if v[0] == "GND"]
    assert len(gnd_vias) == 1
    pcb = (tmp_path / "gen_divider.kicad_pcb").read_text()
    assert "filled_polygon" in pcb
    code, records = run_cli("gates", tmp_path, "--out", tmp_path / "build")
    assert code == 0, records
    assert {r["gate"]: r["status"] for r in records} == {
        "erc": "pass",
        "drc": "pass",
        "sim": "skip",
        "export": "pass",
    }


@pytest.mark.parametrize(
    ("command", "blocked"),
    [
        ("cd /home/user/repo && ls", True),
        ("ls; cd build", True),
        ("(cd tools && make)", True),
        ("echo start\ncd /tmp", True),
        ("make -C /home/user/repo verify", False),
        ("git -C /home/user/repo status", False),
        ("ls /tmp/abcd /tmp/cd-rom", False),
    ],
)
def test_hook_refuses_a_bash_command_that_runs_cd(command, blocked):
    """P8 as a machine check (M31): the PreToolUse hook exits 2, which blocks the call."""
    hook = ROOT / "tools" / "hooks" / "no_cd.py"
    call = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    proc = subprocess.run(
        [sys.executable, str(hook)], input=call, capture_output=True, text=True, check=False
    )
    assert proc.returncode == (2 if blocked else 0), (command, proc.stderr)
    other = json.dumps({"tool_name": "Read", "tool_input": {"file_path": "/x"}})
    assert subprocess.run([sys.executable, str(hook)], input=other, text=True, check=False).returncode == 0


@pytest.mark.parametrize(
    ("command", "blocked"),
    [
        ("sed -i 's/a/b/' /home/user/repo/tests/test_x.py", True),
        ("python3 - <<'EOF'\np = Path('/r/tests/test_x.py')\np.write_text(s)\nEOF", True),
        ("cat >> /r/tests/test_x.py <<'EOF'\ndef test_y(): pass\nEOF", True),
        ("echo x | tee /r/tests/conftest.py", True),
        ("perl -pi -e 's/a/b/' tests/test_x.py", True),
        ("python3 -m pytest -q /r/tests/test_x.py -k four", False),
        ("grep -n def /r/tests/test_x.py", False),
        ("sed -n 1,40p /r/tests/test_x.py", False),
        ("python3 - <<'EOF'\nPath('/r/tools/x.py').write_text(s)\nEOF", False),
    ],
)
def test_hook_refuses_a_scripted_edit_to_a_test_file(command, blocked):
    """P9 step 6 as a machine check (M43): writing under tests/ by script is refused, reading and
    running tests are not, and scripted edits elsewhere pass."""
    hook = ROOT / "tools" / "hooks" / "no_script_test_edits.py"
    call = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
    proc = subprocess.run(
        [sys.executable, str(hook)], input=call, capture_output=True, text=True, check=False
    )
    assert proc.returncode == (2 if blocked else 0), (command, proc.stderr)


def test_hook_installer_merges_once_into_user_settings(tmp_path):
    """install.sh puts the no-cd hook in the user settings (M35): kept settings, added once, then a no-op."""
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir()
    keep = {"model": "x", "hooks": {"SessionStart": [{"matcher": "startup", "hooks": []}]}}
    settings.write_text(json.dumps(keep))
    hook_installer = ROOT / "tools" / "hooks" / "install_hooks.py"
    run = [sys.executable, str(hook_installer), "--settings", str(settings)]
    first = subprocess.run(run, capture_output=True, text=True, check=True).stdout
    second = subprocess.run(run, capture_output=True, text=True, check=True).stdout
    data = json.loads(settings.read_text())
    assert "added to" in first and "already in" in second, (first, second)
    assert data["model"] == "x" and data["hooks"]["SessionStart"] == keep["hooks"]["SessionStart"]
    hooks = [h["command"] for e in data["hooks"]["PreToolUse"] for h in e["hooks"]]
    assert len(hooks) == 1 and "no_cd.py" in hooks[0], hooks

    # The doctor reports it from the user settings ($HOME), and a settings file without it as absent.
    def doctor_sees_hook() -> bool:
        env = {**os.environ, "HOME": str(tmp_path)}
        cmd = [sys.executable, str(ROOT / "tools" / "workcenter"), "--json", "doctor"]
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env, check=False)
        return json.loads(proc.stdout)["checks"]["no-cd hook"]["ok"]

    assert doctor_sees_hook() is True
    settings.write_text(json.dumps(keep))
    assert doctor_sees_hook() is False


@needs_libs
@needs_kicad
def test_island_stitching_keeps_its_vias_out_of_keepouts(tmp_path):
    """The walled-off pad above with a keepout over its whole island: the only spots for a stitching
    via are forbidden, so the island is left to the DRC instead of a via under a grounded shell (M30)."""
    pytest.importorskip("pcbnew")
    d = poured_divider()
    d.track("VIN", [(103.0, 102.5), (107.675, 102.5)], "F.Cu")
    d.track("OUT", [(103.0, 105.04), (106.5, 105.04), (107.675, 106.5)], "F.Cu")
    d.track("OUT", [(109.325, 102.5), (109.325, 103.8), (110.3, 104.6), (110.3, 105.5)], "F.Cu")
    d.track(
        "OUT",
        [
            (107.675, 106.5),
            (108.4, 106.5),
            (108.4, 105.5),
            (110.3, 105.5),
            (110.3, 107.5),
            (108.4, 107.5),
            (108.4, 106.5),
        ],
        "F.Cu",
    )
    d.keepout(kicadgen.Design.circle(109.35, 106.5, 1.6), layers=("F.Cu",), name="shell")
    d.write(tmp_path)
    gnd_vias = [v for v in d.vias if v[0] == "GND"]
    assert not any(d.in_keepout(x, y, size / 2) for _, (x, y), size, _ in gnd_vias), gnd_vias
    assert d.islands, "the walled-off pad must be reported when no via may land in its island"


@needs_libs
@needs_kicad
@needs_router
def test_design_command_routes_a_poured_board_green(tmp_path):
    pytest.importorskip("pcbnew")
    design = tmp_path / "design.py"
    design.write_text(
        "import sys, uuid\n"
        f"sys.path.insert(0, {str(ROOT / 'tools')!r})\n"
        "import kicadgen\n"
        "def build():\n"
        "    d = kicadgen.Design(name='gen_divider', namespace=uuid.UUID(int=9),\n"
        "                        outline=(100.0, 100.0, 112.0, 110.0))\n"
        "    d.power_nets = {'GND': 'GND', 'VIN': 'VBUS'}\n"
        "    d.flagged_nets = ['GND', 'VIN']\n"
        "    r = 'Resistor_SMD:R_0603_1608Metric'\n"
        "    hdr = 'Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical'\n"
        "    d.add('J1', 'Connector_Generic:Conn_01x03', 'IN', hdr, sch_at=(50.8, 50.8),\n"
        "          pcb_at=(103.0, 102.5), nets={'1': 'VIN', '2': 'OUT', '3': 'GND'})\n"
        "    d.add('R1', 'Device:R', '10k', r, sch_at=(71.12, 45.72), pcb_at=(108.5, 102.5),\n"
        "          nets={'1': 'VIN', '2': 'OUT'})\n"
        "    d.add('R2', 'Device:R', '10k', r, sch_at=(71.12, 58.42), pcb_at=(108.5, 106.5),\n"
        "          nets={'1': 'OUT', '2': 'GND'})\n"
        "    d.zone('GND', layers=('F.Cu', 'B.Cu'), connect='solid')\n"
        "    return d\n",
        encoding="utf-8",
    )
    code, records = run_cli("design", design, "--route", "--passes", "10", "--rounds", "2")
    assert code == 0, records
    assert records["islands"] == []
    code, records = run_cli("gates", tmp_path, "--out", tmp_path / "build")
    assert code == 0, records


# ------------------------------------------------ rounded corners and 3D bodies


@needs_libs
def test_rounded_corners_write_arcs_and_a_polygon_boundary():
    d = divider()
    d.corner_radius = 2.0
    board = d.board()
    assert board.count("(gr_arc") == 4 and board.count("(gr_line") == 4 and "(gr_rect" not in board
    x1, y1, x2, y2 = d.outline
    k = 2.0 - 2.0 / math.sqrt(2.0)
    assert f"(mid {kicadgen.fmt(x2 - k)} {kicadgen.fmt(y1 + k)})" in board  # the top-right arc's midpoint
    boundary = d.dsn().split("(boundary")[1].split(")")[0].split()[3:]
    assert len(boundary) == 2 * (4 * 9 + 1)  # four corners of eight segments, closed, as x y pairs
    assert len(d.outline_polygon(d.edge_clearance)) == 36
    e = d.edge_clearance + 0.3
    assert d.inside_outline(x1 + e, (y1 + y2) / 2, e)  # beside a straight edge
    assert not d.inside_outline(x1 + e, y1 + e, e)  # in a corner the arc has cut away
    d.zone("GND", layers=("B.Cu",))
    assert len(d.zones[-1]["polygon"]) == 36  # the default pour follows the corners


@needs_libs
def test_model_is_written_into_the_footprint_instance():
    d = divider()
    d.model("R1", "${KIPRJMOD}/models/stud.wrl", offset=(0, 0, 1.5), rotate=(0, 0, 90))
    d.model("R2", "${KIPRJMOD}/models/other.wrl", replace=True)
    with pytest.raises(KeyError):
        d.model("R9", "x.wrl")
    ids = d.net_ids()
    r1 = kicadgen.dumps(d._footprint_instance(next(p for p in d.parts if p.ref == "R1"), ids))
    r2 = kicadgen.dumps(d._footprint_instance(next(p for p in d.parts if p.ref == "R2"), ids))
    assert r1.count("(model ") == 2  # the library body stays, ours is added
    assert '(model "${KIPRJMOD}/models/stud.wrl"' in r1
    flat = " ".join(r1.split())
    assert (
        "(offset (xyz 0 0 1.5) )" in flat
        and "(rotate (xyz 0 0 90) )" in flat
        and "(scale (xyz 1 1 1) )" in flat
    )
    assert r2.count("(model ") == 1 and "other.wrl" in r2  # replace drops the library body


def test_wrlgen_bodies_are_valid_vrml_in_kicad_units(tmp_path):
    out = tmp_path / "usb.wrl"
    nv, nf = wrlgen.write_wrl(out, wrlgen.usb_c_vertical(height=7.0), "test")
    text = out.read_text()
    assert text.startswith("#VRML V2.0 utf8") and text.count("IndexedFaceSet") == 3 and nv > 100 and nf > 100
    tops = []
    for shape in text.split("Shape {")[1:]:
        pts = shape.split("point [")[1].split("]")[0].split(",")
        idx = [
            int(i)
            for i in shape.split("coordIndex [")[1].split("]")[0].replace(",", " ").split()
            if i != "-1"
        ]
        assert max(idx) < len(pts)  # every index names a vertex
        tops.append(max(float(pt.split()[2]) for pt in pts))
    assert abs(max(tops) - 7.0 / 2.54) < 1e-3  # millimetres went in, KiCad's 0.1 inch units came out
    stud = wrlgen.threaded_stud(major=1.6, pitch=0.35, height=4.0)[0]
    radii = [math.hypot(x, y) for x, y, z in stud.vertices if 0.5 < z < 3.5]
    assert 0.60 < min(radii) < 0.62 and 0.79 < max(radii) < 0.801  # minor and major radius of M1.6 x 0.35
    assert wrlgen.main(["threaded-stud", str(tmp_path / "s.wrl")]) == 0 and (tmp_path / "s.wrl").is_file()


@needs_libs
@needs_kicad
# rounded corners, a stadium (half the 10 mm side), and a half circle at one end with one square corner
@pytest.mark.parametrize("radius", [2.0, 5.0, (5.0, 1.0, 0.0, 5.0)])
def test_rounded_board_passes_drc_except_for_routing(tmp_path, radius):
    d = divider()
    d.corner_radius = radius
    d.write(tmp_path)
    code, gates = run_cli("drc", tmp_path)
    drc = next(g for g in gates if g["gate"] == "drc")
    assert drc["details"]["counts"]["violations"]["error"] == 0, drc  # the arcs close the outline
    assert "invalid_outline" not in json.dumps(drc)


# --------------------------------------------- project footprints and stadiums


@needs_libs
def test_project_footprint_library_is_loaded_and_tabled(tmp_path):
    lib = tmp_path / "fp" / "Mine.pretty"
    lib.mkdir(parents=True)
    src = kicadgen.FOOTPRINT_DIR / "TestPoint.pretty" / "TestPoint_THTPad_D1.5mm_Drill0.7mm.kicad_mod"
    name = "TestPoint_THTPad_D1.5mm_Drill0.7mm"
    (lib / "Wire_Pad.kicad_mod").write_text(src.read_text().replace(f'"{name}"', '"Wire_Pad"', 1))
    d = divider()
    d.footprint_dirs = {"Mine": lib}
    d.add(
        "TP1",
        "Connector:TestPoint",
        "W",
        "Mine:Wire_Pad",
        sch_at=(50.8, 76.2),
        pcb_at=(110.5, 108.5),
        nets={"1": "GND"},
    )
    assert d.fp("Mine:Wire_Pad").courtyard == (-1.25, -1.25, 1.25, 1.25)  # a circle: centre and radius
    out = tmp_path / "proj"
    d.write(out)
    table = (out / "fp-lib-table").read_text()
    assert '(name "Mine")' in table and "Mine.pretty" in table
    assert '(footprint "Mine:Wire_Pad"' in (out / "gen_divider.kicad_pcb").read_text()
    assert kicadgen.main(["footprint", "--lib", f"Mine={lib}", "Mine:Wire_Pad"]) == 0


@needs_libs
@needs_kicad
def test_project_symbol_library_is_loaded_embedded_and_tabled(tmp_path):
    """A part the KiCad library lacks, or draws only in several units, comes from the project's own
    `.kicad_sym` file. Here KiCad's resistor, renamed, stands in for it: the schematic embeds it under
    the project's library name, the project gets a sym-lib-table, and ERC reads it like any other."""
    device = kicadgen.parse(LIBS.read_text(encoding="utf-8"))
    res = next(s for s in kicadgen.children(device, "symbol") if kicadgen.atoms(s)[0] == "R")
    for unit in kicadgen.children(res, "symbol"):
        unit[1] = kicadgen.Q("Res" + kicadgen.atoms(unit)[0][1:])  # R_0_1 -> Res_0_1
    res[1] = kicadgen.Q("Res")
    lib = tmp_path / "sym" / "Mine.kicad_sym"
    lib.parent.mkdir()
    lib.write_text(kicadgen.dumps(["kicad_symbol_lib", ["version", "20241209"], ["generator", "test"], res]))
    d = divider()
    d.symbol_dirs = {"Mine": lib}
    assert sorted(p.number for p in d.symbol("Mine:Res").pins) == ["1", "2"]
    d.add(
        "R3",
        "Mine:Res",
        "22k",
        "Resistor_SMD:R_0603_1608Metric",
        sch_at=(86.36, 58.42),
        pcb_at=(106.0, 108.8),
        nets={"1": "OUT", "2": "GND"},
    )
    out = tmp_path / "proj"
    d.write(out)
    table = (out / "sym-lib-table").read_text()
    assert table.startswith("(sym_lib_table") and '(name "Mine")' in table and "Mine.kicad_sym" in table
    sch = (out / "gen_divider.kicad_sch").read_text()
    assert '(symbol "Mine:Res"' in sch and '(lib_id "Mine:Res")' in sch
    assert kicadgen.main(["pins", "--lib", f"Mine={lib}", "Mine:Res"]) == 0
    code, records = run_cli("erc", out, "--out", out / "build", "--strict")
    assert code == 0, records


@needs_libs
def test_stadium_outline_drops_the_end_lines_and_shared_points():
    d = divider()  # 12 x 10 mm
    d.corner_radius = 5.0
    board = d.board()
    assert board.count("(gr_arc") == 4 and board.count("(gr_line") == 2  # no zero-length ends
    poly = d.outline_polygon()
    assert len(poly) == len(set(poly)) == 4 * 9 - 2  # the arcs meet at both ends; each point once
    assert d.inside_outline(106.0, 105.0, 0.5) and not d.inside_outline(100.6, 100.6, 0.3)
    d.corner_radius = 5.1
    with pytest.raises(ValueError):
        d.outline_polygon()


@needs_libs
def test_corner_radii_round_one_end_and_square_the_other():
    d = divider()  # 12 x 10 mm
    d.corner_radius = (5.0, 1.0, 1.0, 5.0)  # top-left, top-right, bottom-right, bottom-left
    board = d.board()
    assert board.count("(gr_arc") == 4 and board.count("(gr_line") == 3  # the left end is all arc
    poly = d.outline_polygon()
    assert len(poly) == len(set(poly)) == 4 * 9 - 1  # the two left arcs share one point
    assert d.inside_outline(111.4, 100.6, 0.3)  # inside the small top-right arc
    assert not d.inside_outline(111.8, 100.2, 0.0)  # outside it, though inside the rectangle
    assert not d.inside_outline(100.6, 100.6, 0.3)  # the left end's arc has cut this away
    d.corner_radius = (5.0, 0.0, 0.0, 5.0)  # square on the right
    board = d.board()
    assert board.count("(gr_arc") == 2 and board.count("(gr_line") == 3
    poly = d.outline_polygon()
    assert (112.0, 100.0) in poly and (112.0, 110.0) in poly  # a square corner is one point
    assert len(poly) == len(set(poly)) == 2 + 2 * 9 - 1
    assert d.inside_outline(111.7, 109.7, 0.3) and not d.inside_outline(100.6, 109.4, 0.3)
    for bad in ((6.0, 6.5, 0.0, 0.0), (-1.0, 0.0, 0.0, 0.0), (1.0, 1.0, 1.0)):
        d.corner_radius = bad  # the top side too short for both; a negative radius; three radii
        with pytest.raises(ValueError):
            d.outline_polygon()


@needs_libs
def test_thickness_writes_a_two_layer_stackup_and_the_default_does_not():
    d = divider()
    tree = kicadgen.parse(d.board())
    assert kicadgen.atoms(kicadgen.child(kicadgen.child(tree, "general"), "thickness")) == ["1.6"]
    assert kicadgen.child(kicadgen.child(tree, "setup"), "stackup") is None  # as every board before
    d.thickness = 0.8
    tree = kicadgen.parse(d.board())
    assert kicadgen.atoms(kicadgen.child(kicadgen.child(tree, "general"), "thickness")) == ["0.8"]
    stack = kicadgen.child(kicadgen.child(tree, "setup"), "stackup")
    kinds = [kicadgen.atoms(kicadgen.child(ly, "type"))[0] for ly in kicadgen.children(stack, "layer")]
    assert kinds.count("copper") == 2 and kinds.count("core") == 1 and "prepreg" not in kinds
    thick = [
        float(kicadgen.atoms(kicadgen.child(ly, "thickness"))[0])
        for ly in kicadgen.children(stack, "layer")
        if kicadgen.child(ly, "thickness") is not None
    ]
    assert sum(thick) == pytest.approx(0.8 + 0.02, abs=0.005)  # 0.8 mm board plus both masks
    d.thickness = 0.06
    with pytest.raises(ValueError):
        d.board()  # thinner than its own copper


def test_wrlgen_510_presets_have_an_internal_thread_and_glass(tmp_path):
    collar = wrlgen.connector_510()[0]
    bore = [math.hypot(x, y) for x, y, z in collar.vertices if 0.7 < z < 3.9 and math.hypot(x, y) < 4.0]
    assert 3.22 < min(bore) < 3.24 and 3.49 < max(bore) < 3.51  # M7 x 0.5: crests at the minor radius
    out = tmp_path / "cart.wrl"
    wrlgen.write_wrl(out, wrlgen.cartridge_510(), "test")
    assert "transparency 0.60" in out.read_text()  # the glass tank shows the oil
    for preset in ("connector-510", "cartridge-510", "pouch-cell", "display-module"):
        assert wrlgen.main([preset, str(tmp_path / f"{preset}.wrl")]) == 0


@needs_libs
def test_via_check_treats_a_non_plated_hole_as_board_edge():
    """A stitching via beside a USB-C receptacle's plastic peg: the DRC wants edge clearance from the
    peg's hole (M26), not just hole-to-hole spacing."""
    d = divider()
    d.add(
        "J5",
        "Connector:USB_C_Receptacle_USB2.0_16P",
        "USB-C",
        "Connector_USB:USB_C_Receptacle_G-Switch_GT-USB-7051x",
        sch_at=(50.8, 76.2),
        pcb_at=(105.0, 105.0),
        pcb_rot=90,
        pcb_layer="B.Cu",
        nets={"A1": "GND", "B1": "GND", "A12": "GND", "B12": "GND", "SH": "GND"},
    )
    boxes = d.pad_boxes()
    peg = next(b for b in boxes if b.ref == "J5" and b.kind == "np_thru_hole" and b.y2 < 105.0)
    cy = (peg.y1 + peg.y2) / 2
    near = peg.x2 + 0.3 + 0.2  # the via's copper 0.2 mm from the hole: inside the 0.3 mm edge clearance
    clear = peg.x2 + 0.3 + 0.35
    assert not d._via_fits(near, cy, 0.3, 0.3, "GND", boxes, tracks=False)
    assert d._via_fits(clear, cy, 0.3, 0.3, "GND", boxes, tracks=False)


@needs_libs
def test_router_keeps_edge_clearance_from_a_non_plated_hole():
    """The router sees a non-plated hole grown to the board-edge clearance the DRC applies to it (M33):
    the receptacle's 0.66 mm peg hole becomes a 0.66 + 2 x (0.3 - 0.2) mm obstacle, not 0.76."""
    d = divider()
    d.add(
        "J5",
        "Connector:USB_C_Receptacle_USB2.0_16P",
        "USB-C",
        "Connector_USB:USB_C_Receptacle_G-Switch_GT-USB-7051x",
        sch_at=(50.8, 76.2),
        pcb_at=(105.0, 105.0),
        pcb_rot=90,
        pcb_layer="B.Cu",
        nets={"A1": "GND", "B1": "GND", "A12": "GND", "B12": "GND", "SH": "GND"},
    )
    assert d.edge_clearance == 0.3 and d.clearance == 0.2
    dsn = d.dsn()
    assert 'Pad_circle_0.86x0.86_TH "NPTH0"' in dsn, [ln for ln in dsn.splitlines() if "NPTH" in ln]
    assert "Pad_circle_0.76x0.76_TH" not in dsn


@needs_libs
@needs_kicad
def test_keepout_reaches_kicad_the_router_and_the_via_check(tmp_path):
    d = divider()
    area = kicadgen.Design.circle(106.0, 108.5, 1.2)
    d.keepout(area, layers=("F.Cu",), name="shell")
    board = d.board()
    assert '(name "shell")' in board and "(tracks not_allowed)" in board and "(copperpour allowed)" in board
    assert '(keepout "shell" (polygon F.Cu 0 ' in d.dsn()
    boxes = d.pad_boxes()
    assert not d._via_fits(106.0, 108.5, 0.3, 0.3, "GND", boxes, tracks=False)  # inside
    assert not d._via_fits(
        106.0, 108.5 - 1.2 - 0.2, 0.3, 0.3, "GND", boxes, tracks=False
    )  # copper over the edge
    assert d._via_fits(106.0, 108.5 - 1.2 - 0.4, 0.3, 0.3, "GND", boxes, tracks=False)  # clear of it
    with pytest.raises(ValueError):
        d.keepout(area, layers=("F.SilkS",))
    d.track("OUT", [(104.0, 108.5), (108.0, 108.5)], "F.Cu")  # straight through the area
    d.write(tmp_path)
    code, gates = run_cli("drc", tmp_path)
    drc = next(g for g in gates if g["gate"] == "drc")
    report = json.loads((tmp_path / "build" / "drc.json").read_text())
    kinds = {v["type"] for v in report["violations"]}
    assert "items_not_allowed" in kinds, (drc, kinds)  # KiCad read the zone as a keepout


# ------------------------------------------------------------- four layers


def four_layer_divider() -> kicadgen.Design:
    """The divider on four layers: a ground plane on In1.Cu, In2.Cu free for routing."""
    d = divider()
    d.copper_layers = 4
    d.plane_layers = ("In1.Cu",)
    d.zone("GND", layers=("In1.Cu",), connect="solid")
    return d


def walled_off_ground_pad(d: kicadgen.Design) -> None:
    """Hand routes for every net; OUT rings R2's ground pad on the top face, an island there."""
    d.track("VIN", [(103.0, 102.5), (107.675, 102.5)], "F.Cu")
    d.track("OUT", [(103.0, 105.04), (106.5, 105.04), (107.675, 106.5)], "F.Cu")
    d.track("OUT", [(109.325, 102.5), (109.325, 103.8), (110.3, 104.6), (110.3, 105.5)], "F.Cu")
    ring = [(107.675, 106.5), (108.4, 106.5), (108.4, 105.5), (110.3, 105.5), (110.3, 107.5)]
    d.track("OUT", [*ring, (108.4, 107.5), (108.4, 106.5)], "F.Cu")


@needs_libs
def test_four_layer_board_writes_inner_layers_and_hides_the_plane_from_the_router():
    d = four_layer_divider()
    board = d.board()
    assert '(4 "In1.Cu" signal)' in board and '(6 "In2.Cu" signal)' in board
    assert '(layers "In1.Cu")' in board  # the plane's zone
    stack = kicadgen.child(kicadgen.child(kicadgen.parse(board), "setup"), "stackup")
    thick = [
        float(kicadgen.atoms(kicadgen.child(ly, "thickness"))[0])
        for ly in kicadgen.children(stack, "layer")
        if kicadgen.child(ly, "thickness") is not None
    ]
    assert sum(thick) == pytest.approx(1.6 + 0.02, abs=0.005)  # 1.6 mm board plus both masks
    dsn = d.dsn()
    assert "In1.Cu" not in dsn  # the router never sees the plane
    assert "(layer In2.Cu (type signal) (property (index 1)))" in dsn
    assert "(layer B.Cu (type signal) (property (index 2)))" in dsn
    assert '(padstack "Via[0-2]_600:300_um"' in dsn
    via = dsn.split('(padstack "Via[0-2]_600:300_um"')[1].split("(attach")[0]
    assert via.count("(shape (circle") == 3  # copper on every layer the router routes
    through = [ps for ps in dsn.split("(padstack ")[1:] if ps.split()[0].endswith('_TH"')]
    assert through and all(" In2.Cu " in ps.split("(attach")[0] for ps in through)  # pads too
    d.track("OUT", [(104.0, 108.5), (108.0, 108.5)], "In2.Cu")
    assert any(s[4] == "In2.Cu" for s in d.segments)
    with pytest.raises(ValueError, match="In1.Cu"):
        d.track("OUT", [(104.0, 108.5), (108.0, 108.5)], "In1.Cu")  # a plane takes no track
    d.plane_layers = ("F.Cu",)
    with pytest.raises(ValueError, match="inner layer"):
        d.board()
    d.plane_layers = ()
    d.copper_layers = 3
    with pytest.raises(ValueError, match="even"):
        d.board()


@needs_libs
@needs_kicad
@needs_router
def test_four_layer_board_routes_green_around_its_plane(tmp_path):
    """FreeRouting on the three routing layers; KiCad fills the plane round the router's vias."""
    pytest.importorskip("pcbnew")
    d = four_layer_divider()
    summary = kicadgen.route(d, tmp_path / "build" / "route", passes=10, timeout=600)
    assert summary["segments"] > 0, summary
    assert all(s[4] != "In1.Cu" for s in d.segments)
    d.write(tmp_path)
    code, records = run_cli("gates", tmp_path, "--out", tmp_path / "build")
    assert code == 0, records


@needs_libs
@needs_kicad
def test_island_stitching_drops_a_via_to_an_inner_plane_and_passes_the_gates(tmp_path):
    """The walled-off top pad with only the inner plane under it: the via lands on In1.Cu, and the
    four-layer board passes every gate with gerbers for both inner layers."""
    pytest.importorskip("pcbnew")
    d = four_layer_divider()
    d.zone("GND", layers=("F.Cu",), connect="solid")
    walled_off_ground_pad(d)
    d.write(tmp_path)
    assert d.islands == []
    assert len([v for v in d.vias if v[0] == "GND"]) == 1
    code, records = run_cli("gates", tmp_path, "--out", tmp_path / "build")
    assert code == 0, records
    assert {r["gate"]: r["status"] for r in records}["drc"] == "pass"
    gerbers = " ".join(next(r for r in records if r["gate"] == "export")["details"]["gerber_files"])
    assert "In1_Cu" in gerbers and "In2_Cu" in gerbers, gerbers


@needs_libs
@needs_kicad
def test_island_stitching_keeps_clear_of_tracks_on_the_layers_a_via_passes(tmp_path):
    """The same island with an In2.Cu track of another net under all of it: a via there would short
    to the track, so none is placed and the island is reported (P17)."""
    pytest.importorskip("pcbnew")
    d = four_layer_divider()
    d.zone("GND", layers=("F.Cu",), connect="solid")
    walled_off_ground_pad(d)
    d.track("OUT", [(108.6, 106.5), (110.1, 106.5)], "In2.Cu")
    d.write(tmp_path)
    near = [
        (x, y)
        for net, (x, y), size, _ in d.vias
        if net == "GND"
        and kicadgen._seg_dist((x, y), (108.6, 106.5), (110.1, 106.5)) < size / 2 + 0.125 + 0.2
    ]
    assert near == [] and d.islands, (near, d.islands)


# ------------------------------------------------------------- custom pads

QFN28 = "Package_DFN_QFN:QFN-28_4x4mm_P0.5mm"  # corner pads are chamfered custom shapes


@needs_libs
def test_custom_pad_is_sized_from_its_primitives():
    """A custom pad's `size` is its anchor only; the via checks need the copper (M38)."""
    pads = {p.number: p for p in kicadgen.load_footprint(QFN28).pads}
    corner, side = pads["1"], pads["2"]
    assert corner.shape == "custom" and side.shape == "roundrect"
    # A 0.665 x 0.16 polygon drawn with a 0.09 stroke: 0.755 x 0.25, the side pads' width.
    assert (corner.w, corner.h) == pytest.approx((0.755, 0.25), abs=1e-6)


@needs_libs
@needs_kicad
def test_back_face_custom_pads_mirror_their_shapes_and_keep_clearance(tmp_path):
    """A QFN on the bottom face: each corner pad's chamfer must face its neighbour round the corner,
    as on the top face; unmirrored shapes left 0.03 mm between corner pads (M38)."""
    d = kicadgen.Design(name="qfn_back", namespace=uuid.UUID(int=38), outline=(100.0, 100.0, 110.0, 110.0))
    d.add(
        "U1",
        "MCU_ST_STM32G0:STM32G031G8Ux",
        "STM32G031G8U6",
        QFN28,
        sch_at=(50.8, 50.8),
        pcb_at=(105.0, 105.0),
        pcb_layer="B.Cu",
        nets={"3": "VDD", "4": "GND"},
    )
    board = kicadgen.parse(d.board())
    fp = kicadgen.child(board, "footprint")
    pad1 = next(p for p in kicadgen.children(fp, "pad") if p[1] == "1")
    poly = kicadgen.child(kicadgen.child(pad1, "primitives"), "gr_poly")
    ys = [float(kicadgen.atoms(xy)[1]) for xy in kicadgen.children(kicadgen.child(poly, "pts"), "xy")]
    lib = kicadgen.load_footprint(QFN28).node
    lib_pad1 = next(p for p in kicadgen.children(lib, "pad") if p[1] == "1")
    lib_poly = kicadgen.child(kicadgen.child(lib_pad1, "primitives"), "gr_poly")
    lib_ys = [float(kicadgen.atoms(xy)[1]) for xy in kicadgen.children(kicadgen.child(lib_poly, "pts"), "xy")]
    assert ys == [-y for y in lib_ys]
    d.write(tmp_path)
    run_cli("drc", tmp_path)
    report = json.loads((tmp_path / "build" / "drc.json").read_text())
    clearance = [v for v in report["violations"] if v["type"] == "clearance"]
    assert clearance == [], clearance


# ------------------------------------------------------------- hand vias


@needs_libs
def test_check_vias_names_what_a_hand_via_hits():
    """A via passes every layer: one in a keepout or on another net's pad on either face is
    reported with what it hits, before any routing (M40, M41)."""
    d = divider()
    d.keepout(kicadgen.Design.circle(110.0, 108.5, 1.0), layers=("F.Cu",), name="shell")
    d.via("OUT", 110.0, 108.5)  # in the keepout
    d.via("VIN", 109.325, 106.5)  # on R2's ground pad, a top-face pad
    d.via("VIN", 104.0, 108.58)  # diagonal to J1's round ground pad: clear as a circle, not as its box
    d.via("GND", 101.2, 101.2)  # clear
    problems = d.check_vias()
    assert any("(110, 108.5): in keepout 'shell'" in p for p in problems), problems
    assert any("(109.325, 106.5): on R2.2 (GND, F.Cu)" in p for p in problems), problems
    assert not any("(104, 108.58)" in p for p in problems), problems
    assert not any("(101.2, 101.2)" in p for p in problems), problems
    # Two vias of one net may sit closer than two copper clearances; only their holes are held apart.
    d2 = divider()
    d2.via("GND", 106.0, 109.0, 0.8, 0.4)
    d2.via("GND", 106.8, 109.0, 0.8, 0.4)
    assert d2.check_vias() == []
    d2.via("GND", 106.4, 109.0, 0.8, 0.4)  # holes 0.0 mm apart
    assert any("on the GND via" in p for p in d2.check_vias())


@needs_libs
def test_design_command_reports_a_hand_via_problem_and_fails(tmp_path):
    design = tmp_path / "design.py"
    design.write_text(
        "import sys, uuid\n"
        f"sys.path.insert(0, {str(ROOT / 'tools')!r})\n"
        "import kicadgen\n"
        "def build():\n"
        "    d = kicadgen.Design(name='gen_divider', namespace=uuid.UUID(int=9),\n"
        "                        outline=(100.0, 100.0, 112.0, 110.0))\n"
        "    d.power_nets = {'GND': 'GND', 'VIN': 'VBUS'}\n"
        "    d.flagged_nets = ['GND', 'VIN']\n"
        "    r = 'Resistor_SMD:R_0603_1608Metric'\n"
        "    hdr = 'Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical'\n"
        "    d.add('J1', 'Connector_Generic:Conn_01x03', 'IN', hdr, sch_at=(50.8, 50.8),\n"
        "          pcb_at=(103.0, 102.5), nets={'1': 'VIN', '2': 'OUT', '3': 'GND'})\n"
        "    d.add('R1', 'Device:R', '10k', r, sch_at=(71.12, 45.72), pcb_at=(108.5, 102.5),\n"
        "          nets={'1': 'VIN', '2': 'OUT'})\n"
        "    d.add('R2', 'Device:R', '10k', r, sch_at=(71.12, 58.42), pcb_at=(108.5, 106.5),\n"
        "          nets={'1': 'OUT', '2': 'GND'})\n"
        "    d.via('VIN', 109.325, 106.5)\n"
        "    return d\n",
        encoding="utf-8",
    )
    code, records = run_cli("design", design, "--out", tmp_path / "out")
    assert code == 1, records
    assert records["via_problems"] == ["VIN via at (109.325, 106.5): on R2.2 (GND, F.Cu)"], records
    assert (tmp_path / "out" / "gen_divider.kicad_pcb").is_file()  # still written, for the DRC


# ------------------------------------------------------------- via sizes against the rules


@needs_libs
def test_check_via_rules_names_every_via_size_the_board_refuses():
    """The router places the default and net class vias, so the DRC of an unrouted board never
    sees them: their sizes are checked against the board's own rules before routing (M46)."""
    d = divider()
    assert d.check_via_rules() == []  # 0.6 / 0.3, the defaults
    d.via_size, d.via_drill = 0.5, 0.25  # the hole only: 0.25 < 0.3; 0.5 is the minimum via; ring 0.125
    d.net_classes = {
        "Power": {"width": 0.4, "clearance": 0.2, "via": 0.45, "via_drill": 0.3, "nets": ["VIN"]}
    }
    d.via("GND", 101.2, 101.2, 0.6, 0.2)  # the hole only: ring 0.2
    assert d.check_via_rules() == [
        "default via: drill 0.25 is below the board's minimum hole 0.3",
        "net class Power via: diameter 0.45 is below the board's minimum via 0.5",
        "net class Power via: annular ring 0.075 is below the board's minimum 0.1",
        "GND via at (101.2, 101.2): drill 0.2 is below the board's minimum hole 0.3",
    ]
    # A fab that drills 0.2 mm: the rule is lowered in `rules`, and the project file carries it.
    d.rules = {"min_through_hole_diameter": 0.2}
    assert d.check_via_rules() == [
        "net class Power via: diameter 0.45 is below the board's minimum via 0.5",
        "net class Power via: annular ring 0.075 is below the board's minimum 0.1",
    ]
    rules = json.loads(d.project())["board"]["design_settings"]["rules"]
    assert rules["min_through_hole_diameter"] == 0.2
    assert rules["min_via_diameter"] == 0.5


@needs_libs
def test_design_command_refuses_a_router_via_below_the_minimum_hole(tmp_path):
    design = tmp_path / "design.py"
    design.write_text(
        "import sys, uuid\n"
        f"sys.path.insert(0, {str(ROOT / 'tools')!r})\n"
        "import kicadgen\n"
        "def build():\n"
        "    d = kicadgen.Design(name='gen_divider', namespace=uuid.UUID(int=9),\n"
        "                        outline=(100.0, 100.0, 112.0, 110.0), via_size=0.5, via_drill=0.25)\n"
        "    d.power_nets = {'GND': 'GND', 'VIN': 'VBUS'}\n"
        "    d.flagged_nets = ['GND', 'VIN']\n"
        "    r = 'Resistor_SMD:R_0603_1608Metric'\n"
        "    hdr = 'Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical'\n"
        "    d.add('J1', 'Connector_Generic:Conn_01x03', 'IN', hdr, sch_at=(50.8, 50.8),\n"
        "          pcb_at=(103.0, 102.5), nets={'1': 'VIN', '2': 'OUT', '3': 'GND'})\n"
        "    d.add('R1', 'Device:R', '10k', r, sch_at=(71.12, 45.72), pcb_at=(108.5, 102.5),\n"
        "          nets={'1': 'VIN', '2': 'OUT'})\n"
        "    d.add('R2', 'Device:R', '10k', r, sch_at=(71.12, 58.42), pcb_at=(108.5, 106.5),\n"
        "          nets={'1': 'OUT', '2': 'GND'})\n"
        "    return d\n",
        encoding="utf-8",
    )
    code, records = run_cli("design", design, "--out", tmp_path / "out")
    assert code == 1, records
    assert records["via_problems"] == ["default via: drill 0.25 is below the board's minimum hole 0.3"], (
        records
    )


# ------------------------------------------------------- wired schematics


@needs_libs
@pytest.mark.parametrize(
    "rot, pin1, pin2",
    [
        (0, (50.8, 46.99), (50.8, 54.61)),
        (90, (46.99, 50.8), (54.61, 50.8)),
        (180, (50.8, 54.61), (50.8, 46.99)),
        (270, (54.61, 50.8), (46.99, 50.8)),
    ],
)
def test_turned_symbol_pins_are_where_kicad_puts_them(rot, pin1, pin2):
    """The pin positions KiCad's ERC reported for a Device:R at (50.8, 50.8) at each angle."""
    d = kicadgen.Design(name="r", namespace=uuid.UUID(int=11))
    part = d.add("R1", "Device:R", "1k", None, sch_at=(50.8, 50.8), nets={}, sch_rot=rot)
    pins = {p.number: p for p in part.symbol.pins}
    assert d._pin_point(part, pins["1"])[:2] == pytest.approx(pin1)
    assert d._pin_point(part, pins["2"])[:2] == pytest.approx(pin2)


@needs_libs
def test_sch_rot_takes_quarter_turns_only():
    d = kicadgen.Design(name="r", namespace=uuid.UUID(int=12))
    with pytest.raises(ValueError, match="sch_rot"):
        d.add("R1", "Device:R", "1k", None, sch_at=(50.8, 50.8), nets={}, sch_rot=45)


def test_router_crosses_another_net_straight_through():
    r = kicadgen.SchRouter(40, 40, 0)
    r.add_path("A", [(x, 10) for x in range(2, 30)])
    path = r.route("B", {(15, 2): None}, (20, 20), None)
    assert path[0] == (15, 2) and path[-1] == (20, 20)
    r.add_path("B", path)
    (i,) = [k for k, c in enumerate(path) if c[1] == 10]
    assert path[i - 1][0] == path[i][0] == path[i + 1][0]  # vertical through A's row, no bend there
    assert r.node.get(path[i]) is None  # neither net has an end or a bend at the crossing


def test_router_keeps_off_another_nets_end_and_out_of_its_line():
    r = kicadgen.SchRouter(30, 30, 0)
    r.add_path("A", [(5, y) for y in range(5, 21)])  # A ends at (5, 5) and (5, 20)
    across = r.route("B", {(2, 5): None}, (8, 5), None)  # the straight line runs into A's end
    assert across is not None and (5, 5) not in across
    along = r.route("C", {(5, 0): None}, (5, 25), None)  # the straight line runs down A's wire
    assert along is not None and not [c for c in along if c[0] == 5 and 5 <= c[1] <= 20]


def netlist_groups(sch: Path, out: Path) -> set[tuple[tuple[str, str], ...]]:
    """The pin groups of every net of two or more pins in KiCad's netlist of a schematic."""
    net = out / "net.net"
    subprocess.run(["kicad-cli", "sch", "export", "netlist", "-o", str(net), str(sch)], check=True)
    root = kicadgen.parse(net.read_text(encoding="utf-8"))
    groups = set()
    for n in kicadgen.children(kicadgen.child(root, "nets"), "net"):
        nodes = kicadgen.children(n, "node")
        pins = sorted(
            (kicadgen.atoms(kicadgen.child(x, "ref"))[0], kicadgen.atoms(kicadgen.child(x, "pin"))[0])
            for x in nodes
        )
        if len(pins) > 1:
            groups.add(tuple(pins))
    return groups


def wired_divider() -> kicadgen.Design:
    """The divider with a turned resistor into a capacitor beside it, wired."""
    d = divider()
    d.sch_wires = True
    d.add("R3", "Device:R", "1k", None, sch_at=(88.9, 52.07), nets={"1": "OUT", "2": "TAP"}, sch_rot=90)
    d.add("C1", "Device:C", "1n", None, sch_at=(99.06, 58.42), nets={"1": "TAP", "2": "GND"})
    return d


@needs_libs
@needs_kicad
def test_wired_divider_passes_erc_with_the_netlist_it_declares(tmp_path):
    d = wired_divider()
    d.write(tmp_path)
    code, records = run_cli("erc", tmp_path, "--out", tmp_path / "build", "--strict")
    assert code == 0, records
    sch = tmp_path / "gen_divider.kicad_sch"
    assert netlist_groups(sch, tmp_path) == {
        (("J1", "1"), ("R1", "1")),
        (("J1", "2"), ("R1", "2"), ("R2", "1"), ("R3", "1")),
        (("C1", "2"), ("J1", "3"), ("R2", "2")),
        (("C1", "1"), ("R3", "2")),
    }
    text = sch.read_text(encoding="utf-8")
    assert sorted(re.findall(r'\(label "([^"]+)"', text)) == ["OUT", "TAP"]  # each wired net named once
    assert len(re.findall(r"\(junction\b", text)) >= 1  # OUT tees off to R3
    assert "(at 88.9 52.07 90)" in text  # R3 stands turned


@needs_libs
@needs_kicad
def test_wired_schematic_keeps_the_boards_net_names(tmp_path):
    """A wired net is named by its label, not after a pin, so the board and the schematic agree."""
    d = divider()
    d.sch_wires = True
    d.write(tmp_path)
    code, records = run_cli("drc", tmp_path, "--out", tmp_path / "build")
    parity = records[0]["details"]["counts"]["schematic_parity"]
    assert parity["error"] == 0 and parity["warning"] == 0, records[0]["details"].get("first")


@needs_libs
def test_wired_schematic_labels_the_nets_it_is_told_to():
    d = divider()
    d.sch_wires = True
    d.sch_label_nets = ("OUT",)
    labels = re.findall(r'\(label "([^"]+)"', d.schematic())
    assert labels == ["OUT", "OUT", "OUT"]  # one on each of J1 pin 2, R1 pin 2, R2 pin 1


@needs_libs
def test_wiring_refuses_a_pin_off_the_grid():
    d = divider()
    d.sch_wires = True
    d.parts[1].sch_at = (71.0, 45.72)
    with pytest.raises(ValueError, match="off the 1.27 mm grid"):
        d.schematic()


@needs_libs
def test_unwired_schematic_is_still_stubs_and_labels():
    text = divider().schematic()
    assert re.findall(r'\(label "([^"]+)"', text) == ["OUT", "OUT", "OUT"] and not re.search(
        r"\(junction\b", text
    )


def test_wrlgen_package_bodies_put_pin_one_top_left(tmp_path):
    mould, metal, dot = wrlgen.leadless((4.0, 4.0, 0.55), (7, 7), 0.5, (0.4, 0.25))
    assert len(metal.vertices) == 28 * 8  # a box per terminal
    assert max(x for x, _, _ in dot.vertices) < 0 < min(y for _, y, _ in dot.vertices)  # by pin 1
    assert max(z for _, _, z in mould.vertices) == pytest.approx(0.55)
    mould, metal, dot = wrlgen.gullwing()  # Diodes' SOT523: body 0.8 x 1.6 x 0.75 on 0.05, tips 1.6 apart
    assert len(metal.vertices) == 3 * 3 * 8  # three leads of three pieces
    assert min(x for x, _, _ in metal.vertices) == pytest.approx(-0.8)
    assert max(x for x, _, _ in metal.vertices) == pytest.approx(0.8)
    assert max(z for _, _, z in mould.vertices) == pytest.approx(0.8)
    assert max(x for x, _, _ in dot.vertices) < 0 < min(y for _, y, _ in dot.vertices)
    for preset in ("leadless", "gullwing"):
        assert wrlgen.main([preset, str(tmp_path / f"{preset}.wrl")]) == 0
        assert (tmp_path / f"{preset}.wrl").read_text().startswith("#VRML V2.0 utf8")
