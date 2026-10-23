"""Tests for tools/kicadgen.py: the library-backed design generator.

Library-dependent tests skip loudly when the KiCad libraries are absent;
routing tests skip when FreeRouting is absent. The round trip test builds
a 2-resistor board, routes it, merges the session, and expects DRC clean.
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
sys.path.insert(0, str(ROOT / "tools"))
import kicadgen  # noqa: E402

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
