#!/usr/bin/env python3
"""Generate the fixture boards under tests/boards.

The fixtures are committed files; this script is how they are made and how
`tests/test_gates.py::test_fixtures_match_generator` proves they did not
drift. Every UUID is derived from a name, so a re-run writes identical
bytes. Symbols and footprints are embedded, copied from the KiCad 10
libraries (CC-BY-SA 4.0 with the design exception), so no library tables
are needed to run the gates.

Circuit: J1 (3-pin header) feeds VIN into R1; R2 to GND forms a divider;
C1 filters VOUT. 5 V in, 2.5 V out. The board is 25 x 20 mm, 2 layers,
routed on F.Cu.

    python3 tests/boards/generate.py            # write both fixtures
    python3 tests/boards/generate.py --check    # exit 1 if files differ
"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
NS = uuid.UUID("8d3e9c4a-5f1b-4f2e-9a7d-2c1b3e4f5a6b")
NAME = "rc_divider"
ROOT_UUID = str(uuid.uuid5(NS, "sheet/root"))


def uid(key: str) -> str:
    return str(uuid.uuid5(NS, key))


# ------------------------------------------------------------ schematic

SCH_VERSION = 20250114
PCB_VERSION = 20241229

FONT = "(effects (font (size 1.27 1.27)))"
FONT_HIDE = "(effects (font (size 1.27 1.27)) (hide yes))"
FONT_LEFT = "(effects (font (size 1.27 1.27)) (justify left))"


def lib_symbol_r() -> str:
    return f"""
		(symbol "Device:R"
			(pin_numbers (hide yes))
			(pin_names (offset 0))
			(exclude_from_sim no)
			(in_bom yes)
			(on_board yes)
			(property "Reference" "R" (at 2.032 0 90) {FONT})
			(property "Value" "R" (at 0 0 90) {FONT})
			(property "Footprint" "" (at -1.778 0 90) {FONT_HIDE})
			(property "Datasheet" "~" (at 0 0 0) {FONT_HIDE})
			(property "Description" "Resistor" (at 0 0 0) {FONT_HIDE})
			(property "ki_keywords" "R res resistor" (at 0 0 0) {FONT_HIDE})
			(property "ki_fp_filters" "R_*" (at 0 0 0) {FONT_HIDE})
			(symbol "R_0_1"
				(rectangle (start -1.016 -2.54) (end 1.016 2.54)
					(stroke (width 0.254) (type default)) (fill (type none)))
			)
			(symbol "R_1_1"
				(pin passive line (at 0 3.81 270) (length 1.27)
					(name "" {FONT}) (number "1" {FONT}))
				(pin passive line (at 0 -3.81 90) (length 1.27)
					(name "" {FONT}) (number "2" {FONT}))
			)
			(embedded_fonts no)
		)"""


def lib_symbol_c() -> str:
    return f"""
		(symbol "Device:C"
			(pin_numbers (hide yes))
			(pin_names (offset 0.254))
			(exclude_from_sim no)
			(in_bom yes)
			(on_board yes)
			(property "Reference" "C" (at 0.635 2.54 0) {FONT_LEFT})
			(property "Value" "C" (at 0.635 -2.54 0) {FONT_LEFT})
			(property "Footprint" "" (at 0.9652 -3.81 0) {FONT_HIDE})
			(property "Datasheet" "~" (at 0 0 0) {FONT_HIDE})
			(property "Description" "Unpolarized capacitor" (at 0 0 0) {FONT_HIDE})
			(property "ki_keywords" "cap capacitor" (at 0 0 0) {FONT_HIDE})
			(property "ki_fp_filters" "C_*" (at 0 0 0) {FONT_HIDE})
			(symbol "C_0_1"
				(polyline (pts (xy -2.032 0.762) (xy 2.032 0.762))
					(stroke (width 0.508) (type default)) (fill (type none)))
				(polyline (pts (xy -2.032 -0.762) (xy 2.032 -0.762))
					(stroke (width 0.508) (type default)) (fill (type none)))
			)
			(symbol "C_1_1"
				(pin passive line (at 0 3.81 270) (length 2.794)
					(name "" {FONT}) (number "1" {FONT}))
				(pin passive line (at 0 -3.81 90) (length 2.794)
					(name "" {FONT}) (number "2" {FONT}))
			)
			(embedded_fonts no)
		)"""


def lib_symbol_conn() -> str:
    pins = ""
    for n, y in ((1, 2.54), (2, 0), (3, -2.54)):
        pins += f"""
				(pin passive line (at -5.08 {y} 0) (length 3.81)
					(name "Pin_{n}" {FONT}) (number "{n}" {FONT}))"""
    return f"""
		(symbol "Connector_Generic:Conn_01x03"
			(pin_names (offset 1.016) (hide yes))
			(exclude_from_sim no)
			(in_bom yes)
			(on_board yes)
			(property "Reference" "J" (at 0 5.08 0) {FONT})
			(property "Value" "Conn_01x03" (at 0 -5.08 0) {FONT})
			(property "Footprint" "" (at 0 0 0) {FONT_HIDE})
			(property "Datasheet" "~" (at 0 0 0) {FONT_HIDE})
			(property "Description" "Generic connector, single row, 01x03" (at 0 0 0) {FONT_HIDE})
			(property "ki_keywords" "connector" (at 0 0 0) {FONT_HIDE})
			(property "ki_fp_filters" "Connector*:*_1x??_*" (at 0 0 0) {FONT_HIDE})
			(symbol "Conn_01x03_1_1"
				(rectangle (start -1.27 3.81) (end 1.27 -3.81)
					(stroke (width 0.254) (type default)) (fill (type background)))
				(rectangle (start -1.27 2.667) (end 0 2.413)
					(stroke (width 0.1524) (type default)) (fill (type none)))
				(rectangle (start -1.27 0.127) (end 0 -0.127)
					(stroke (width 0.1524) (type default)) (fill (type none)))
				(rectangle (start -1.27 -2.413) (end 0 -2.667)
					(stroke (width 0.1524) (type default)) (fill (type none))){pins}
			)
			(embedded_fonts no)
		)"""


# Parts: reference -> (lib_id, value, footprint, description, schematic position)
PARTS = {
    "J1": (
        "Connector_Generic:Conn_01x03",
        "Conn_01x03",
        "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical",
        "Generic connector, single row, 01x03",
        (60.96, 60.96),
    ),
    "R1": ("Device:R", "10k", "Resistor_SMD:R_0603_1608Metric", "Resistor", (72.39, 54.61)),
    "R2": ("Device:R", "10k", "Resistor_SMD:R_0603_1608Metric", "Resistor", (72.39, 66.04)),
    "C1": ("Device:C", "100n", "Capacitor_SMD:C_0603_1608Metric", "Unpolarized capacitor", (80.01, 66.04)),
}

# Pin connection points in schematic coordinates (y down).
PIN_AT = {
    ("J1", "1"): (55.88, 58.42),
    ("J1", "2"): (55.88, 60.96),
    ("J1", "3"): (55.88, 63.5),
    ("R1", "1"): (72.39, 50.8),
    ("R1", "2"): (72.39, 58.42),
    ("R2", "1"): (72.39, 62.23),
    ("R2", "2"): (72.39, 69.85),
    ("C1", "1"): (80.01, 62.23),
    ("C1", "2"): (80.01, 69.85),
}

WIRES = [
    # VIN
    ((55.88, 58.42), (55.88, 50.8)),
    ((55.88, 50.8), (72.39, 50.8)),
    # VOUT
    ((55.88, 60.96), (72.39, 60.96)),
    ((72.39, 60.96), (80.01, 60.96)),
    ((80.01, 60.96), (80.01, 62.23)),
    ((72.39, 58.42), (72.39, 60.96)),
    ((72.39, 60.96), (72.39, 62.23)),
    # GND
    ((55.88, 63.5), (55.88, 69.85)),
    ((55.88, 69.85), (72.39, 69.85)),
    ((72.39, 69.85), (80.01, 69.85)),
]
JUNCTIONS = [(72.39, 60.96), (72.39, 69.85)]
LABELS = [("VIN", (60.96, 50.8)), ("VOUT", (63.5, 60.96)), ("GND", (63.5, 69.85))]


def fmt(v: float) -> str:
    s = f"{v:.6f}".rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


def schematic() -> str:
    out = [
        f"""(kicad_sch
	(version {SCH_VERSION})
	(generator "eeschema")
	(generator_version "9.0")
	(uuid "{ROOT_UUID}")
	(paper "A4")
	(lib_symbols{lib_symbol_conn()}{lib_symbol_r()}{lib_symbol_c()}
	)"""
    ]
    for i, (x, y) in enumerate(JUNCTIONS):
        out.append(f"""
	(junction (at {fmt(x)} {fmt(y)}) (diameter 0) (color 0 0 0 0) (uuid "{uid(f"junction/{i}")}"))""")
    for i, (a, b) in enumerate(WIRES):
        out.append(f"""
	(wire (pts (xy {fmt(a[0])} {fmt(a[1])}) (xy {fmt(b[0])} {fmt(b[1])}))
		(stroke (width 0) (type default)) (uuid "{uid(f"wire/{i}")}"))""")
    for name, (x, y) in LABELS:
        out.append(f"""
	(label "{name}" (at {fmt(x)} {fmt(y)} 0)
		(effects (font (size 1.27 1.27)) (justify left bottom)) (uuid "{uid(f"label/{name}")}"))""")
    for ref, (lib_id, value, footprint, descr, (x, y)) in PARTS.items():
        pins = "".join(
            f"""
		(pin "{n}" (uuid "{uid(f"pin/{ref}/{n}")}"))"""
            for n in ("1", "2", "3")
            if (ref, n) in PIN_AT
        )
        out.append(f"""
	(symbol (lib_id "{lib_id}") (at {fmt(x)} {fmt(y)} 0) (unit 1)
		(exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)
		(uuid "{uid(f"symbol/{ref}")}")
		(property "Reference" "{ref}" (at {fmt(x + 2.54)} {fmt(y - 1.27)} 0) {FONT_LEFT})
		(property "Value" "{value}" (at {fmt(x + 2.54)} {fmt(y + 1.27)} 0) {FONT_LEFT})
		(property "Footprint" "{footprint}" (at {fmt(x)} {fmt(y)} 0) {FONT_HIDE})
		(property "Datasheet" "~" (at {fmt(x)} {fmt(y)} 0) {FONT_HIDE})
		(property "Description" "{descr}" (at {fmt(x)} {fmt(y)} 0) {FONT_HIDE}){pins}
		(instances (project "{NAME}" (path "/{ROOT_UUID}" (reference "{ref}") (unit 1))))
	)""")
    out.append("""
	(sheet_instances (path "/" (page "1")))
	(embedded_fonts no)
)
""")
    return "".join(out)


# ---------------------------------------------------------------- board

NETS = {"/VIN": 1, "/VOUT": 2, "/GND": 3}
PAD_NET = {
    ("J1", "1"): "/VIN",
    ("J1", "2"): "/VOUT",
    ("J1", "3"): "/GND",
    ("R1", "1"): "/VIN",
    ("R1", "2"): "/VOUT",
    ("R2", "1"): "/VOUT",
    ("R2", "2"): "/GND",
    ("C1", "1"): "/VOUT",
    ("C1", "2"): "/GND",
}
# Board placement (mm). Pads are at known offsets: 0603 at x = ±0.825 (R) / ±0.775 (C), header pins at y = 0, 2.54, 5.08.
PLACE = {"J1": (105.0, 105.0), "R1": (112.0, 103.0), "R2": (118.0, 107.54), "C1": (118.0, 112.0)}

TRACKS = {
    "/VIN": [
        ((105.0, 105.0), (109.0, 105.0)),
        ((109.0, 105.0), (109.0, 103.0)),
        ((109.0, 103.0), (111.175, 103.0)),
    ],
    "/VOUT": [
        ((112.825, 103.0), (115.0, 103.0)),
        ((115.0, 103.0), (115.0, 112.0)),
        ((105.0, 107.54), (115.0, 107.54)),
        ((115.0, 107.54), (117.175, 107.54)),
        ((115.0, 112.0), (117.225, 112.0)),
    ],
    "/GND": [
        ((105.0, 110.08), (110.0, 110.08)),
        ((110.0, 110.08), (110.0, 116.0)),
        ((110.0, 116.0), (121.0, 116.0)),
        ((121.0, 116.0), (121.0, 107.54)),
        ((118.825, 107.54), (121.0, 107.54)),
        ((118.775, 112.0), (121.0, 112.0)),
    ],
}
# The deliberate defect: a GND stub 0.05 mm from C1 pad 1 (VOUT). Default clearance is 0.2 mm.
CLEARANCE_DEFECT = [((119.0, 116.0), (119.0, 112.65)), ((119.0, 112.65), (116.5, 112.65))]

FP_FONT = "(effects (font (size 1 1) (thickness 0.15)))"


def fp_props(ref: str, value: str, descr: str, ref_at: str, val_at: str) -> str:
    return f"""
		(property "Reference" "{ref}" (at {ref_at} 0) (layer "F.SilkS") (uuid "{uid(f"fp/{ref}/ref")}") {FP_FONT})
		(property "Value" "{value}" (at {val_at} 0) (layer "F.Fab") (uuid "{uid(f"fp/{ref}/val")}") {FP_FONT})
		(property "Datasheet" "" (at 0 0 0) (layer "F.Fab") (hide yes) (uuid "{uid(f"fp/{ref}/ds")}") {FP_FONT})
		(property "Description" "{descr}" (at 0 0 0) (layer "F.Fab") (hide yes) (uuid "{uid(f"fp/{ref}/descr")}") {FP_FONT})
		(path "/{uid(f"symbol/{ref}")}")
		(sheetname "/")
		(sheetfile "{NAME}.kicad_sch")"""


def pad(ref: str, n: str, body: str) -> str:
    net = PAD_NET[(ref, n)]
    return f"""
		(pad "{n}" {body}
			(net {NETS[net]} "{net}") (pintype "passive") (uuid "{uid(f"pad/{ref}/{n}")}"))"""


def fp_shape(ref: str, key: str, body: str) -> str:
    return f"""
		({body} (uuid "{uid(f"shape/{ref}/{key}")}"))"""


def footprint_0603(ref: str, kind: str, value: str, descr: str) -> str:
    x, y = PLACE[ref]
    lib = "Resistor_SMD:R_0603_1608Metric" if kind == "R" else "Capacitor_SMD:C_0603_1608Metric"
    pad_x, pad_w = (0.825, 0.8) if kind == "R" else (0.775, 0.9)
    silk = 0.237258 if kind == "R" else 0.14058
    silk_y = 0.5225 if kind == "R" else 0.51
    fab_h = 0.4125 if kind == "R" else 0.4

    def smd(x: float) -> str:
        return (
            f"smd roundrect (at {fmt(x)} 0) (size {pad_w} 0.95) "
            '(layers "F.Cu" "F.Mask" "F.Paste") (roundrect_rratio 0.25)'
        )

    return f"""
	(footprint "{lib}" (layer "F.Cu") (uuid "{uid(f"fp/{ref}")}") (at {fmt(x)} {fmt(y)})
		(descr "{descr}, SMD 0603 (1608 Metric)")
		(tags "{descr.lower()}"){fp_props(ref, value, descr, "0 -1.43", "0 1.43")}
		(attr smd){fp_shape(ref, "silk1", f'fp_line (start {fmt(-silk)} {fmt(-silk_y)}) (end {fmt(silk)} {fmt(-silk_y)}) (stroke (width 0.12) (type solid)) (layer "F.SilkS")')}{fp_shape(ref, "silk2", f'fp_line (start {fmt(-silk)} {fmt(silk_y)}) (end {fmt(silk)} {fmt(silk_y)}) (stroke (width 0.12) (type solid)) (layer "F.SilkS")')}{fp_shape(ref, "crtyd", 'fp_rect (start -1.48 -0.73) (end 1.48 0.73) (stroke (width 0.05) (type solid)) (fill no) (layer "F.CrtYd")')}{fp_shape(ref, "fab", f'fp_rect (start -0.8 {fmt(-fab_h)}) (end 0.8 {fmt(fab_h)}) (stroke (width 0.1) (type solid)) (fill no) (layer "F.Fab")')}
		(fp_text user "${{REFERENCE}}" (at 0 0 0) (layer "F.Fab") (uuid "{uid(f"fp/{ref}/reftext")}")
			(effects (font (size 0.4 0.4) (thickness 0.06)))){pad(ref, "1", smd(-pad_x))}{pad(ref, "2", smd(pad_x))}
		(embedded_fonts no)
	)"""


def footprint_header(ref: str) -> str:
    x, y = PLACE[ref]
    lines = [
        ("s1", "(start -1.38 -1.38) (end 0 -1.38)", "F.SilkS", 0.12),
        ("s2", "(start -1.38 0) (end -1.38 -1.38)", "F.SilkS", 0.12),
        ("s3", "(start -1.38 1.27) (end -1.38 6.46)", "F.SilkS", 0.12),
        ("s4", "(start -1.38 1.27) (end 1.38 1.27)", "F.SilkS", 0.12),
        ("s5", "(start -1.38 6.46) (end 1.38 6.46)", "F.SilkS", 0.12),
        ("s6", "(start 1.38 1.27) (end 1.38 6.46)", "F.SilkS", 0.12),
        ("f1", "(start -1.27 -0.635) (end -0.635 -1.27)", "F.Fab", 0.1),
        ("f2", "(start -1.27 6.35) (end -1.27 -0.635)", "F.Fab", 0.1),
        ("f3", "(start -0.635 -1.27) (end 1.27 -1.27)", "F.Fab", 0.1),
        ("f4", "(start 1.27 -1.27) (end 1.27 6.35)", "F.Fab", 0.1),
        ("f5", "(start 1.27 6.35) (end -1.27 6.35)", "F.Fab", 0.1),
    ]
    shapes = "".join(
        fp_shape(ref, k, f'fp_line {geom} (stroke (width {w}) (type solid)) (layer "{layer}")')
        for k, geom, layer, w in lines
    )
    shapes += fp_shape(
        ref,
        "crtyd",
        'fp_rect (start -1.77 -1.77) (end 1.77 6.85) (stroke (width 0.05) (type solid)) (fill no) (layer "F.CrtYd")',
    )
    tht = '(size 1.7 1.7) (drill 1) (layers "*.Cu" "*.Mask") (remove_unused_layers no)'
    pads = (
        pad(ref, "1", f"thru_hole rect (at 0 0) {tht}")
        + pad(ref, "2", f"thru_hole circle (at 0 2.54) {tht}")
        + pad(ref, "3", f"thru_hole circle (at 0 5.08) {tht}")
    )
    return f"""
	(footprint "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical" (layer "F.Cu") (uuid "{uid(f"fp/{ref}")}") (at {fmt(x)} {fmt(y)})
		(descr "Through hole straight pin header, 1x03, 2.54mm pitch, single row")
		(tags "Through hole pin header THT 1x03 2.54mm single row"){fp_props(ref, "Conn_01x03", "Generic connector, single row, 01x03", "0 -2.38", "0 7.46")}
		(attr through_hole){shapes}
		(fp_text user "${{REFERENCE}}" (at 0 2.54 90) (layer "F.Fab") (uuid "{uid(f"fp/{ref}/reftext")}")
			(effects (font (size 1 1) (thickness 0.15)))){pads}
		(embedded_fonts no)
	)"""


def board(defect: bool) -> str:
    layers = """
		(0 "F.Cu" signal)
		(2 "B.Cu" signal)
		(9 "F.Adhes" user "F.Adhesive")
		(11 "B.Adhes" user "B.Adhesive")
		(13 "F.Paste" user)
		(15 "B.Paste" user)
		(5 "F.SilkS" user "F.Silkscreen")
		(7 "B.SilkS" user "B.Silkscreen")
		(1 "F.Mask" user)
		(3 "B.Mask" user)
		(17 "Dwgs.User" user "User.Drawings")
		(19 "Cmts.User" user "User.Comments")
		(21 "Eco1.User" user "User.Eco1")
		(23 "Eco2.User" user "User.Eco2")
		(25 "Edge.Cuts" user)
		(27 "Margin" user)
		(31 "F.CrtYd" user "F.Courtyard")
		(29 "B.CrtYd" user "B.Courtyard")
		(35 "F.Fab" user)
		(33 "B.Fab" user)"""
    out = [
        f"""(kicad_pcb
	(version {PCB_VERSION})
	(generator "pcbnew")
	(generator_version "9.0")
	(general (thickness 1.6) (legacy_teardrops no))
	(paper "A4")
	(layers{layers}
	)
	(setup
		(pad_to_mask_clearance 0)
		(allow_soldermask_bridges_in_footprints no)
		(tenting front back)
		(pcbplotparams
			(layerselection 0x00000000_00000000_55555555_5755f5ff)
			(plot_on_all_layers_selection 0x00000000_00000000_00000000_00000000)
			(disableapertmacros no)
			(usegerberextensions no)
			(usegerberattributes yes)
			(usegerberadvancedattributes yes)
			(creategerberjobfile yes)
			(dashed_line_dash_ratio 12.000000)
			(dashed_line_gap_ratio 3.000000)
			(svgprecision 4)
			(plotframeref no)
			(mode 1)
			(useauxorigin no)
			(hpglpennumber 1)
			(hpglpenspeed 20)
			(hpglpendiameter 15.000000)
			(pdf_front_fp_property_popups yes)
			(pdf_back_fp_property_popups yes)
			(pdf_metadata yes)
			(pdf_single_document no)
			(dxfpolygonmode yes)
			(dxfimperialunits yes)
			(dxfusepcbnewfont yes)
			(psnegative no)
			(psa4output no)
			(plot_black_and_white yes)
			(plotinvisibletext no)
			(sketchpadsonfab no)
			(plotpadnumbers no)
			(hidednponfab no)
			(sketchdnponfab yes)
			(crossoutdnponfab yes)
			(subtractmaskfromsilk no)
			(outputformat 1)
			(mirror no)
			(drillshape 1)
			(scaleselection 1)
			(outputdirectory "")
		)
	)
	(net 0 "")"""
    ]
    for name, n in NETS.items():
        out.append(f"""
	(net {n} "{name}")""")
    out.append(footprint_header("J1"))
    out.append(footprint_0603("R1", "R", "10k", "Resistor"))
    out.append(footprint_0603("R2", "R", "10k", "Resistor"))
    out.append(footprint_0603("C1", "C", "100n", "Unpolarized capacitor"))
    out.append(f"""
	(gr_rect (start 100 100) (end 125 120)
		(stroke (width 0.1) (type default)) (fill no) (layer "Edge.Cuts") (uuid "{uid("edge")}"))""")
    tracks = [(net, seg) for net, segs in TRACKS.items() for seg in segs]
    if defect:
        tracks += [("/GND", seg) for seg in CLEARANCE_DEFECT]
    for i, (net, (a, b)) in enumerate(tracks):
        out.append(f"""
	(segment (start {fmt(a[0])} {fmt(a[1])}) (end {fmt(b[0])} {fmt(b[1])}) (width 0.25) (layer "F.Cu") (net {NETS[net]}) (uuid "{uid(f"seg/{i}/{net}")}"))""")
    out.append("""
	(embedded_fonts no)
)
""")
    return "".join(out)


# -------------------------------------------------------------- project


def project() -> str:
    data = {
        "board": {
            "design_settings": {
                "defaults": {},
                "rule_severities": {"lib_footprint_issues": "ignore", "lib_footprint_mismatch": "ignore"},
                "rules": {
                    "min_clearance": 0.0,
                    "min_connection": 0.0,
                    "min_copper_edge_clearance": 0.5,
                    "min_hole_clearance": 0.25,
                    "min_hole_to_hole": 0.25,
                    "min_microvia_diameter": 0.2,
                    "min_microvia_drill": 0.1,
                    "min_resolved_spokes": 2,
                    "min_silk_clearance": 0.0,
                    "min_text_height": 0.8,
                    "min_text_thickness": 0.08,
                    "min_through_hole_diameter": 0.3,
                    "min_track_width": 0.0,
                    "min_via_annular_width": 0.1,
                    "min_via_diameter": 0.5,
                    "solder_mask_to_copper_clearance": 0.0,
                    "use_height_for_length_calcs": True,
                },
            },
            "ipc2581": {"dist": "", "distpn": "", "internal_id": "", "mfg": "", "mpn": ""},
            "layer_presets": [],
            "viewports": [],
        },
        "boards": [],
        "cvpcb": {"equivalence_files": []},
        # Symbols and footprints are embedded by design, so the "library not in the
        # configuration" checks are noise for these fixtures.
        "erc": {
            "erc_exclusions": [],
            "meta": {"version": 0},
            "rule_severities": {"footprint_link_issues": "ignore", "lib_symbol_issues": "ignore"},
        },
        "libraries": {"pinned_footprint_libs": [], "pinned_symbol_libs": []},
        "meta": {"filename": f"{NAME}.kicad_pro", "version": 3},
        "net_settings": {
            "classes": [
                {
                    "bus_width": 12,
                    "clearance": 0.2,
                    "diff_pair_gap": 0.25,
                    "diff_pair_via_gap": 0.25,
                    "diff_pair_width": 0.2,
                    "line_style": 0,
                    "microvia_diameter": 0.3,
                    "microvia_drill": 0.1,
                    "name": "Default",
                    "pcb_color": "rgba(0, 0, 0, 0.000)",
                    "priority": 2147483647,
                    "schematic_color": "rgba(0, 0, 0, 0.000)",
                    "track_width": 0.25,
                    "via_diameter": 0.6,
                    "via_drill": 0.3,
                    "wire_width": 6,
                }
            ],
            "meta": {"version": 4},
            "net_colors": None,
            "netclass_assignments": None,
            "netclass_patterns": [],
        },
        "pcbnew": {
            "last_paths": {
                "gencad": "",
                "idf": "",
                "netlist": "",
                "plot": "",
                "pos_files": "",
                "specctra_dsn": "",
                "step": "",
                "svg": "",
                "vrml": "",
            },
            "page_layout_descr_file": "",
        },
        "schematic": {"legacy_lib_dir": "", "legacy_lib_list": [], "meta": {"version": 1}},
        "sheets": [[ROOT_UUID, "Root"]],
        "text_variables": {},
    }
    return json.dumps(data, indent=2) + "\n"


# ------------------------------------------------------------------ main

FIXTURES = {
    "pass-rc-divider": {"defect": False},
    "fail-drc-clearance": {"defect": True},
}


def render() -> dict[Path, str]:
    files: dict[Path, str] = {}
    for folder, opts in FIXTURES.items():
        d = HERE / folder
        files[d / f"{NAME}.kicad_pro"] = project()
        files[d / f"{NAME}.kicad_sch"] = schematic()
        files[d / f"{NAME}.kicad_pcb"] = board(defect=opts["defect"])
    return files


def main(argv: list[str]) -> int:
    files = render()
    if "--check" in argv:
        stale = [p for p, text in files.items() if not p.is_file() or p.read_text(encoding="utf-8") != text]
        for p in stale:
            print(f"stale: {p.relative_to(HERE.parent.parent)}")
        return 1 if stale else 0
    for p, text in files.items():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        print(f"wrote {p.relative_to(HERE.parent.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
