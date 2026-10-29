"""`workcenter sources` and the SIM gate's vendor models (library/sources.csv).

The library is built in each test's tmp_path: a datasheet as text, a SPICE model written the PSpice way
(a resistor that names a RES model, a LOT tolerance), and a STEP header. The project is the passing RC
divider fixture; its parts file names an MPN for each line. KiCad- and ngspice-dependent tests skip when
the engine is absent.
"""

from __future__ import annotations

import datetime
import hashlib
import http.server
import importlib.machinery
import json
import shutil
import subprocess
import sys
import threading
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "tools" / "workcenter"
BOARDS = ROOT / "tests" / "boards"

needs_kicad = pytest.mark.skipif(shutil.which("kicad-cli") is None, reason="kicad-cli is not installed")
needs_ngspice = pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice is not installed")


def load_cli():
    loader = importlib.machinery.SourceFileLoader("workcenter_cli_sources", str(CLI))
    module = types.ModuleType("workcenter_cli_sources")
    module.__file__ = str(CLI)
    sys.modules[module.__name__] = module
    loader.exec_module(module)
    return module


def run(*args: object) -> tuple[int, list[dict]]:
    proc = subprocess.run(
        [sys.executable, str(CLI), "--json", *map(str, args)], capture_output=True, text=True, check=False
    )
    return proc.returncode, (json.loads(proc.stdout) if proc.stdout.strip() else [])


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# A divider written the PSpice way: R1 names a RES model whose R is 99.5, so PSpice makes it 99.5 Ohm
# where ngspice, reading the value alone, makes it 1 Ohm. A tolerance spec ngspice does not know.
MODEL = """* Test divider model
* Model Version: 2.1, Date: 02/02/2007
.SUBCKT RDIV IN OUT GND
R1 IN OUT Rmod 1
R2 OUT GND 100
.MODEL Rmod RES (R=99.5 TC1=1E-3 LOT/1/UNIFORM=1% DEV/GAUSS=0.5%)
.ENDS
"""
DATASHEET = "RC0603 thick film chip resistors\nProduct specification - November 14, 2025 V.14\n"
STEP = "ISO-10303-21;\nHEADER;\nFILE_NAME('R_0603.step','2026-04-02T00:00:00',(''),(''),'','','');\nENDSEC;\n"
PARTS = "\n".join(
    [
        "Value,Footprint,Qty,Manufacturer,MPN,Supplier,SKU,Pack,Breaks,Stock,Checked,URL,Note",
        "100n,Capacitor_SMD:C_0603_1608Metric,,Samsung,CL10B104KB8NNNC,Digi-Key,1276-1000-1-ND,,1:0.10,0,{today},,",
        "Conn_01x03,Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical,,Sullins,PREC003SAAN-RC,"
        "Digi-Key,35-PREC003SAAN-RC-ND,,1:0.10,40331,{today},,",
        "10k,Resistor_SMD:R_0603_1608Metric,,Yageo,RC0603FR-0710KL,Digi-Key,311-10.0KHRCT-ND,,1:0.10,0,{today},,",
        "",
    ]
)
HEADER = "MPN,Kind,URL,File,Member,Revision,Dated,Subckt,Ngspice,SHA256,Checked,Note"


def library(tmp_path: Path, url: str = "https://example.com") -> tuple[Path, Path]:
    """A library with every row right, and the parts file: (sources.csv, parts.csv)."""
    lib = tmp_path / "library"
    (lib / "yageo").mkdir(parents=True)
    (lib / "yageo" / "rc_l.txt").write_text(DATASHEET, encoding="utf-8")
    (lib / "yageo" / "rdiv.lib").write_text(MODEL, encoding="utf-8")
    (lib / "yageo" / "r0603.step").write_text(STEP, encoding="utf-8")
    rows = [
        HEADER,
        f"RC0603FR-0710KL,datasheet,{url}/rc_l.txt,yageo/rc_l.txt,,V.14,2025-11,,,"
        f"{sha(lib / 'yageo' / 'rc_l.txt')},2026-10-29,",
        f"RC0603FR-0710KL,spice,{url}/rdiv.lib,yageo/rdiv.lib,,Model Version: 2.1,2007,RDIV,"
        f"res-model tolerance,{sha(lib / 'yageo' / 'rdiv.lib')},2026-10-29,",
        f"RC0603FR-0710KL,step,{url}/r0603.step,yageo/r0603.step,,,,,,"
        f"{sha(lib / 'yageo' / 'r0603.step')},2026-10-29,",
        "CL10B104KB8NNNC,datasheet,https://example.com/cl10,,,,,,,,2026-10-29,"
        "the page builds the PDF on request",
        "PREC003SAAN-RC,datasheet,https://example.com/prec,,,,,,,,2026-10-29,a mechanical header",
    ]
    (lib / "sources.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    parts = tmp_path / "parts.csv"
    parts.write_text(PARTS.format(today=datetime.date.today().isoformat()), encoding="utf-8")
    return lib / "sources.csv", parts


# ------------------------------------------------------------ pure logic


def test_spice_facts_reads_pins_models_includes_and_the_header():
    cli = load_cli()
    facts = cli.spice_facts(
        MODEL + '.include "sub/deep.lib"\n.SUBCKT X2 A B\n+ C PARAMS: K=1\nR1 A B 1\n.ENDS\n'
    )
    assert facts["subckts"] == {"RDIV": ["IN", "OUT", "GND"], "X2": ["A", "B", "C"]}
    assert facts["models"] == ["RMOD"]
    assert facts["includes"] == ["sub/deep.lib"]
    assert facts["header"] == ["Model Version: 2.1, Date: 02/02/2007"]


def test_translate_model_folds_res_models_and_drops_tolerances():
    cli = load_cli()
    out = cli.translate_model(MODEL, {"res-model", "tolerance"})
    assert "R1 IN OUT {99.5*1} tc1=1E-3 tc2" not in out  # only the model's own coefficients move
    assert "R1 IN OUT {99.5*1} tc1=1E-3" in out
    assert "LOT/" not in out and "DEV/" not in out
    assert "* .MODEL Rmod RES" in out  # kept as a comment, folded into R1
    assert "R2 OUT GND 100" in out  # a plain resistor is left alone
    assert cli.translate_model(MODEL, set()) == MODEL


def test_a_model_is_asked_for_by_the_whole_reference_prefix():
    cli = load_cli()
    refs = ("U1", "Q2", "D3", "DS1", "SW1", "R4", "J1", "TP1")
    # DS1 is a display, not a diode: its prefix is DS, not D (Last Hit v0.12's OLED panel)
    assert [r for r in refs if cli.needs_model(r)] == ["U1", "Q2", "D3"]


def test_read_sources_refuses_a_row_it_cannot_check(tmp_path):
    cli = load_cli()
    path = tmp_path / "sources.csv"
    for row, why in (
        ("X,datasheet,,,,,,,,,,", "needs a Note"),
        ("X,schematic,,a.pdf,,,,,,,,", "Kind 'schematic'"),
        ("X,spice,,a.lib,,,,,pspice,,,", "Ngspice 'pspice'"),
    ):
        path.write_text(HEADER + "\n" + row + "\n", encoding="utf-8")
        with pytest.raises(ValueError, match=why):
            cli.read_sources(path)


# ----------------------------------------------------------- the command


@needs_kicad
@needs_ngspice
def test_sources_passes_a_library_that_holds_what_its_rows_say(tmp_path):
    sources, parts = library(tmp_path)
    code, records = run(
        "sources", BOARDS / "pass-rc-divider", "--parts", parts, "--sources", sources, "--out", tmp_path / "o"
    )
    assert code == 0, records
    details = records[0]["details"]
    assert details["problems"] == []
    by = {e["mpn"]: e for e in details["parts"]}
    assert set(by) == {"RC0603FR-0710KL", "CL10B104KB8NNNC", "PREC003SAAN-RC"}
    spice = next(r for r in by["RC0603FR-0710KL"]["rows"] if r["kind"] == "spice")
    assert spice["ngspice"] == "loads" and spice["subckts"] == ["RDIV"]
    step = next(r for r in by["RC0603FR-0710KL"]["rows"] if r["kind"] == "step")
    assert step["step_name"] == "R_0603.step"
    # the model's 2007 against the datasheet's 2025, and the two datasheets kept as notes only
    assert any("dated 2007, the datasheet 2025" in w for w in details["warnings"])
    assert (tmp_path / "o" / "sources" / "sources.md").is_file()
    code, records = run(
        "sources",
        BOARDS / "pass-rc-divider",
        "--parts",
        parts,
        "--sources",
        sources,
        "--out",
        tmp_path / "o",
        "--strict",
    )
    assert code == 1  # a warning fails a strict run


@needs_kicad
@needs_ngspice
def test_sources_names_each_way_a_library_drifts_from_its_rows(tmp_path):
    sources, parts = library(tmp_path)
    lib = sources.parent
    (lib / "yageo" / "rc_l.txt").write_text(DATASHEET.replace("V.14", "V.15"), encoding="utf-8")
    (lib / "yageo" / "rdiv.lib").write_text(MODEL + '.include "missing.lib"\n', encoding="utf-8")
    text = sources.read_text(encoding="utf-8")
    sources.write_text("\n".join(ln for ln in text.splitlines() if "CL10B104KB8NNNC" not in ln) + "\n")
    code, records = run(
        "sources", BOARDS / "pass-rc-divider", "--parts", parts, "--sources", sources, "--out", tmp_path / "o"
    )
    assert code == 1
    problems = records[0]["details"]["problems"]
    assert any("rc_l.txt changed since its row" in p for p in problems), problems
    assert any("does not print the revision 'V.14'" in p for p in problems), problems
    assert any("sub-models not in the library: missing.lib" in p for p in problems), problems
    assert any("C1 CL10B104KB8NNNC: no datasheet row" in p for p in problems), problems


class Supplier(http.server.BaseHTTPRequestHandler):
    """Serves the test's files; /refused answers 403 the way a bot wall does."""

    root: Path = Path()
    agents: list[str] = []

    def do_GET(self):  # noqa: N802 (the handler's name is http.server's)
        Supplier.agents.append(self.headers.get("User-Agent", ""))
        path = Supplier.root / self.path.lstrip("/")
        if self.path.startswith("/refused"):
            self.send_response(403)
            self.end_headers()
        elif path.is_file():
            body = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass


@needs_kicad
def test_fetch_reads_each_url_again_and_says_what_changed(tmp_path):
    served = tmp_path / "served"
    served.mkdir()
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Supplier)
    Supplier.root, Supplier.agents = served, []
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        sources, parts = library(tmp_path, url)
        (served / "rc_l.txt").write_text(DATASHEET, encoding="utf-8")  # the same file
        (served / "rdiv.lib").write_text(MODEL.replace("2.1", "2.2"), encoding="utf-8")  # a new revision
        text = sources.read_text(encoding="utf-8").replace(f"{url}/r0603.step", f"{url}/refused/r0603.step")
        sources.write_text(text, encoding="utf-8")  # the CL10 and PREC datasheets 404
        code, records = run(
            "sources",
            BOARDS / "pass-rc-divider",
            "--parts",
            parts,
            "--sources",
            sources,
            "--out",
            tmp_path / "o",
            "--fetch",
        )
    finally:
        server.shutdown()
    fetched = {(f["mpn"], f["kind"]): f["status"] for f in records[0]["details"]["fetched"]}
    assert fetched[("RC0603FR-0710KL", "datasheet")] == "same"
    assert fetched[("RC0603FR-0710KL", "spice")] == "changed"
    assert fetched[("RC0603FR-0710KL", "step")] == "refused"
    assert fetched[("CL10B104KB8NNNC", "datasheet")] == "gone"
    assert set(Supplier.agents) == {load_cli().FETCH_AGENT}  # who asks, said plainly
    assert (tmp_path / "o" / "sources" / "fetched" / "yageo" / "rdiv.lib").is_file()
    assert sha(sources.parent / "yageo" / "rdiv.lib") == sha(tmp_path / "library" / "yageo" / "rdiv.lib")
    assert "2.1" in (sources.parent / "yageo" / "rdiv.lib").read_text()  # the library is never written


# ------------------------------------------------------------ the SIM gate


DECK = """* divider from the vendor model: 1 V in
.include "../library/yageo/rdiv.lib"
V1 in 0 DC 1
X1 in out 0 RDIV
.control
op
let vout = v(out)
print vout
.endc
.end
"""


def sim_project(tmp_path: Path, expect: dict) -> Path:
    sources, _ = library(tmp_path)
    proj = tmp_path / "proj"
    (proj / "sim").mkdir(parents=True)
    (proj / "sim" / "rdiv.cir").write_text(DECK.replace("../library", str(sources.parent)), encoding="utf-8")
    (proj / "sim" / "rdiv.expect.json").write_text(json.dumps(expect), encoding="utf-8")
    (proj / "library").symlink_to(sources.parent, target_is_directory=True)
    return proj


@needs_ngspice
def test_sim_runs_a_listed_model_translated_and_checks_its_row(tmp_path):
    # 99.5 Ohm over 100 Ohm: 0.501 V. Read the PSpice way it is right; read as ngspice reads the file
    # untranslated, R1 is 1 Ohm and vout 0.990 V.
    proj = sim_project(tmp_path, {"vout": {"min": 0.49, "max": 0.51, "source": "R2 / (R1 + R2)"}})
    code, records = run("sim", proj, "--out", tmp_path / "o")
    assert code == 0, records
    deck = records[0]["details"]["decks"]["rdiv"]
    assert deck["measures"]["vout"] == pytest.approx(100 / 199.5, abs=1e-3)
    assert deck["models"][0]["mpn"] == "RC0603FR-0710KL" and deck["models"][0]["fixes"] == [
        "res-model",
        "tolerance",
    ]
    assert deck["ran"].endswith("run/rdiv/rdiv.cir")
    # the model edited after its row was written fails the deck
    lib = tmp_path / "library" / "yageo" / "rdiv.lib"
    lib.write_text(MODEL.replace("R2 OUT GND 100", "R2 OUT GND 101"), encoding="utf-8")
    code, records = run("sim", proj, "--out", tmp_path / "o")
    assert code == 1
    assert any("changed since its sources row" in f for f in records[0]["details"]["failures"])


@needs_ngspice
def test_a_warn_bound_names_a_model_off_its_datasheet_and_fails_only_strict(tmp_path):
    proj = sim_project(
        tmp_path, {"vout": {"min": 0.45, "max": 0.5, "warn": "the model against its datasheet's 0.5 V max"}}
    )
    code, records = run("sim", proj, "--out", tmp_path / "o")
    assert code == 0, records
    assert any("against its datasheet" in w for w in records[0]["details"]["warnings"])
    code, records = run("sim", proj, "--out", tmp_path / "o", "--strict")
    assert code == 1
