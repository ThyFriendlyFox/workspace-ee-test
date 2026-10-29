"""The pull-resistor check: `Design.undefined_inputs()` and `workcenter design` with `check_pulls`.

A control input (a gate, a logic input, a switch, an I2C line) that only an MCU pin drives floats in
reset and until firmware sets the pin. The check wants a resistor to a rail, or to a transistor's own
source for its gate, an output pin on the net, or the net named in `defined_nets` with the reason.
"""

from __future__ import annotations

import subprocess
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import kicadgen  # noqa: E402

CLI = ROOT / "tools" / "workcenter"
needs_libs = pytest.mark.skipif(
    not (kicadgen.SYMBOL_DIR / "Device.kicad_sym").is_file(),
    reason="KiCad symbol libraries are not installed",
)
MCU = "MCU_ST_STM32G0:STM32G031G8Ux"


def heater(pull: str | None = "GND") -> kicadgen.Design:
    """An MCU pin (PB4, bidirectional) on a MOSFET's gate (DMG1012T), with or without a pull-down."""
    d = kicadgen.Design(name="pulls", namespace=uuid.UUID(int=21))
    d.power_nets = {"GND": "GND", "+3V3": "+3V3"}
    d.add("U1", MCU, "MCU", None, sch_at=(50.8, 50.8), nets={"24": "GATE", "3": "+3V3", "4": "GND"})
    d.add(
        "Q1",
        "Transistor_FET:DMG1012T",
        "Q",
        None,
        sch_at=(101.6, 50.8),
        nets={"1": "GATE", "2": "GND", "3": "OUT"},
    )
    if pull:
        d.add("R1", "Device:R", "100k", None, sch_at=(88.9, 63.5), nets={"1": "GATE", "2": pull})
    return d


@needs_libs
def test_a_gate_only_an_mcu_pin_drives_is_reported():
    (line,) = heater(pull=None).undefined_inputs()
    assert line.startswith("GATE: Q1.1 (G, input), driven only by U1.24 (high-impedance in reset)")
    assert "defined_nets" in line


@needs_libs
def test_a_pull_to_a_rail_or_to_the_source_holds_the_gate():
    assert heater(pull="GND").undefined_inputs() == []
    assert heater(pull="+3V3").undefined_inputs() == []
    d = heater(pull=None)  # a P-style pull: gate to its own source on a net that is no rail
    d.parts[1].nets["2"] = "SRC"
    d.add("R2", "Device:R", "47k", None, sch_at=(88.9, 76.2), nets={"1": "GATE", "2": "SRC"})
    assert d.undefined_inputs() == []


@needs_libs
def test_a_series_resistor_is_not_a_pull():
    d = heater(pull="MCU_OUT")  # R1 from GATE to another net the MCU drives
    d.parts[0].nets["24"] = "MCU_OUT"
    d.add("U2", MCU, "MCU", None, sch_at=(50.8, 101.6), nets={"24": "GATE"})
    assert [ln.split(":")[0] for ln in d.undefined_inputs()] == ["GATE"]


@needs_libs
def test_an_output_pin_drives_the_net():
    d = heater(pull=None)
    d.add(
        "U2",
        "74xGxx:74LVC1G04",
        "inv",
        None,
        sch_at=(50.8, 101.6),
        nets={"4": "GATE", "3": "GND", "5": "+3V3"},
    )
    assert d.undefined_inputs() == []


@needs_libs
def test_switches_and_i2c_lines_need_a_level_and_a_declared_net_is_taken():
    d = heater()
    d.add("SW1", "Switch:SW_Push", "BTN", None, sch_at=(25.4, 76.2), nets={"1": "BTN", "2": "GND"})
    d.parts[0].nets["27"] = "BTN"
    d.parts[0].nets["18"] = "I2C_SDA"
    assert [ln.split(":")[0] for ln in d.undefined_inputs()] == ["BTN", "I2C_SDA"]
    d.defined_nets = {
        "BTN": "PB7's internal pull-up, set by the firmware",
        "I2C_SDA": "4.7k on the display board",
    }
    assert d.undefined_inputs() == []


@needs_libs
def test_design_lists_the_nets_and_fails_only_when_asked(tmp_path):
    src = tmp_path / "design.py"
    body = f"""
import sys, uuid
sys.path.insert(0, {str(ROOT / "tools")!r})
sys.path.insert(0, {str(Path(__file__).resolve().parent)!r})
from test_pulls import heater

def build():
    d = heater(pull=None)
    d.outline = (100.0, 100.0, 110.0, 110.0)
    d.check_pulls = CHECK
    return d
"""
    for check, want in ((False, 0), (True, 1)):
        src.write_text(body.replace("CHECK", str(check)), encoding="utf-8")
        r = subprocess.run(
            [sys.executable, str(CLI), "design", str(src), "--out", str(tmp_path / str(check))],
            capture_output=True,
            text=True,
        )
        assert r.returncode == want, r.stdout + r.stderr
        assert "  pull: GATE: Q1.1 (G, input)" in r.stdout
