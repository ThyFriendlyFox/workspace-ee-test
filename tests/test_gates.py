"""Gate tests on the fixture boards.

The fixture boards under tests/boards are the real tests of this
workcenter: one passes every gate, the others fail a named gate for a
known reason. KiCad-dependent tests skip loudly when kicad-cli is absent.
"""

from __future__ import annotations

import importlib.machinery
import json
import re
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


def test_every_cli_flag_is_in_the_configuration_table():
    """P10 step 4: each flag a command line takes has its row in docs/CONFIGURATION.md (M50).
    argparse flags, and kicadgen's, which it compares by hand (`a == "--lib"`)."""
    doc = (ROOT / "ee-agent-kit" / "docs" / "CONFIGURATION.md").read_text(encoding="utf-8")
    flag = re.compile(r'(?:add_argument\(\s*|\ba == )"(--[a-z0-9-]+)"')
    for tool in ("tools/workcenter", "tools/kicadgen.py", "tools/wrlgen.py", "tools/hooks/install_hooks.py"):
        flags = set(flag.findall((ROOT / tool).read_text(encoding="utf-8")))
        assert flags, f"{tool}: no flags found; the pattern no longer matches its parser"
        assert sorted(f for f in flags if f"`{f}" not in doc) == [], tool


# ------------------------------------------------------------- render


def test_copper_layers_and_render_views():
    cli = load_cli_module()
    assert cli.copper_layers(BOARDS / "pass-rc-divider" / "rc_divider.kicad_pcb") == ["F.Cu", "B.Cu"]
    assert cli.render_views("layers,spin") == ("layers", "spin")
    assert cli.render_views("all") == cli.RENDER_VIEWS
    assert "spin" not in cli.DEFAULT_VIEWS  # a minute or two of frames: only on request
    with pytest.raises(Exception, match="views are"):
        cli.render_views("layers,photo")


def test_render_refuses_an_unknown_view(tmp_path):
    code, records = run("render", BOARDS / "pass-rc-divider", "--out", tmp_path, "--views", "photo")
    assert code == 2 and records == []


@needs_kicad
def test_render_draws_each_layer_that_has_something_on_it(tmp_path):
    code, records = run("render", BOARDS / "pass-rc-divider", "--out", tmp_path, "--views", "layers")
    assert code == 0, records
    layers = tmp_path / "render" / "layers"
    names = sorted(p.name for p in layers.iterdir())
    # Two copper layers; the fixture has nothing on its back silkscreen, paste, fab or courtyard.
    drawn = ["F-Cu", "B-Cu", "F-Silkscreen", "F-Mask", "B-Mask", "F-Paste", "F-Fab", "F-Courtyard"]
    assert names == sorted(f"{n}.png" for n in [*drawn, "Edge-Cuts"]), names
    sheet = tmp_path / "render" / "layers.png"
    assert sheet.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert not list((tmp_path / "render").glob("*.svg")), "the sheet's SVG is not left behind"


@needs_kicad
@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg is not installed")
def test_render_spin_writes_a_looping_gif(tmp_path):
    args = ("--views", "spin", "--spin-frames", "3", "--width", "160")
    code, records = run("render", BOARDS / "pass-rc-divider", "--out", tmp_path, *args)
    assert code == 0, records
    gif = (tmp_path / "render" / "board-spin.gif").read_bytes()
    assert gif[:6] == b"GIF89a"
    assert b"NETSCAPE2.0" in gif  # loops
    assert gif.count(b"\x21\xf9\x04") == 3  # one graphic control block per frame
    assert not (tmp_path / "render" / "spin-frames").exists()


def test_render_spin_without_ffmpeg_skips_with_the_reason(tmp_path, monkeypatch):
    cli = load_cli_module()
    which = shutil.which
    monkeypatch.setattr(cli.shutil, "which", lambda name: None if name == "ffmpeg" else which(name))
    project = cli.find_project(str(BOARDS / "pass-rc-divider"))
    result = cli.gate_render(project, tmp_path, views=("spin",))
    assert result.status == "skip"
    assert result.details["skipped"] == ["board-spin.gif: ffmpeg missing"]


def test_footprint_blocks_skip_brackets_inside_quotes():
    cli = load_cli_module()
    text = '(kicad_pcb (version 1) (footprint "A:B" (property "Value" "a)b(") (at 1 2)) (footprint "C:D"))'
    blocks = cli.footprint_blocks(text)
    assert blocks == ['(footprint "A:B" (property "Value" "a)b(") (at 1 2))', '(footprint "C:D")']


def with_models(tmp_path: Path, monkeypatch) -> Path:
    """A copy of the passing fixture whose footprints name 3D models: R1 a library body that exists,
    R2 one that does not, C1 a missing library body and a project body that exists, J1 none."""
    project = tmp_path / "board"
    shutil.copytree(BOARDS / "pass-rc-divider", project)
    lib = tmp_path / "3dmodels"
    (lib / "Resistor_SMD.3dshapes").mkdir(parents=True)
    (lib / "Resistor_SMD.3dshapes" / "R_0603_1608Metric.step").write_text("x", encoding="utf-8")
    (project / "models").mkdir()
    (project / "models" / "c.wrl").write_text("#VRML V2.0 utf8\n", encoding="utf-8")
    for var in ("KICAD10_3DMODEL_DIR", "KICAD9_3DMODEL_DIR", "KICAD8_3DMODEL_DIR"):
        monkeypatch.setenv(var, str(lib))
    models = {
        "R1": ["${KICAD10_3DMODEL_DIR}/Resistor_SMD.3dshapes/R_0603_1608Metric.step"],
        "R2": ["${KICAD10_3DMODEL_DIR}/Resistor_SMD.3dshapes/R_0603_gone.step"],
        "C1": [
            "${KICAD10_3DMODEL_DIR}/Capacitor_SMD.3dshapes/C_0603_1608Metric.step",
            "${KIPRJMOD}/models/c.wrl",
        ],
    }
    pcb = project / "rc_divider.kicad_pcb"
    text = pcb.read_text(encoding="utf-8")
    cli = load_cli_module()
    for block in cli.footprint_blocks(text):
        ref = re.search(r'\(property "Reference" "([^"]+)"', block).group(1)
        if ref in models:
            lines = "".join(f'\n\t\t(model "{m}")' for m in models[ref])
            text = text.replace(block, block[:-1] + lines + "\n\t)")
    pcb.write_text(text, encoding="utf-8")
    return project


def test_parts_without_body_names_only_the_parts_drawn_bare(tmp_path, monkeypatch):
    cli = load_cli_module()
    project = cli.find_project(str(with_models(tmp_path, monkeypatch)))
    bare = cli.parts_without_body(project)
    assert [(b["ref"], b["footprint"]) for b in bare] == [("R2", "Resistor_SMD:R_0603_1608Metric")]
    assert bare[0]["models"] == ["${KICAD10_3DMODEL_DIR}/Resistor_SMD.3dshapes/R_0603_gone.step"]


@needs_kicad
def test_render_names_a_bare_part_and_strict_fails_on_it(tmp_path, monkeypatch):
    project = with_models(tmp_path, monkeypatch)
    code, records = run("render", project, "--out", tmp_path / "out", "--views", "3d", "--width", "320")
    assert code == 0, records
    assert records[0]["summary"].endswith("1 parts drawn without a 3D body: R2")
    assert [b["ref"] for b in records[0]["details"]["no_body"]] == ["R2"]
    code, records = run(
        "render", project, "--out", tmp_path / "out", "--views", "3d", "--width", "320", "--strict"
    )
    assert code == 1 and records[0]["status"] == "fail"
    code, records = run("render", project, "--out", tmp_path / "out", "--views", "2d")
    assert code == 0 and records[0]["details"]["no_body"] == []  # 2D views draw no bodies


def test_fixtures_match_generator():
    proc = subprocess.run(
        [sys.executable, str(BOARDS / "generate.py"), "--check"], capture_output=True, text=True, check=False
    )
    assert proc.returncode == 0, f"fixtures drifted from generate.py:\n{proc.stdout}"
