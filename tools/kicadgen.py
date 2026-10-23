#!/usr/bin/env python3
"""kicadgen — build KiCad 10 projects from the installed libraries.

A design is Python: parts placed from the KiCad symbol and footprint
libraries, nets as names. This module turns that into a schematic, a
board, a project file, a Specctra DSN for the autorouter, and merges the
router's session file back into the board. Standard library only.

    python3 tools/kicadgen.py pins Device:R MCU_ST_STM32G0:STM32G031F8Px
    python3 tools/kicadgen.py footprint Package_SO:TSSOP-20_4.4x6.5mm_P0.65mm

Coordinates are millimetres. Schematic y grows downward (KiCad); symbol
library y grows upward and is flipped on placement. Board rotation keeps
footprint-local pad coordinates and adds the rotation to each pad's own
angle, which is how KiCad stores rotated footprints.
"""

from __future__ import annotations

import copy
import importlib.util
import math
import os
import re
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path

SYMBOL_DIR = Path(os.environ.get("KICAD_SYMBOL_DIR", "/usr/share/kicad/symbols"))
FOOTPRINT_DIR = Path(os.environ.get("KICAD_FOOTPRINT_DIR", "/usr/share/kicad/footprints"))

SCH_VERSION = 20250114
PCB_VERSION = 20241229

# Tokens the KiCad 10 library format carries that the 9.0 file formats
# written here do not know. They are editor metadata, not design content.
DROP_SYMBOL_TOKENS = {"in_pos_files", "duplicate_pin_numbers_are_jumpers", "show_name", "do_not_autoplace"}
DROP_FOOTPRINT_TOKENS = {"version", "generator", "generator_version", "duplicate_pad_numbers_are_jumpers"}


# ------------------------------------------------------------ S-expressions


class Q(str):
    """A token that was quoted in the source and must stay quoted."""

    __slots__ = ()


Node = list  # [head: str, *children: str | Q | Node]

_TOKEN = re.compile(r'\s*(?:(\()|(\))|"((?:[^"\\]|\\.)*)"|([^\s()"]+))', re.S)


def parse(text: str) -> Node:
    """Parse one top-level S-expression."""
    stack: list[Node] = []
    root: Node | None = None
    pos, n = 0, len(text)
    while pos < n:
        m = _TOKEN.match(text, pos)
        if not m:
            raise ValueError(f"bad token at {pos}: {text[pos : pos + 40]!r}")
        pos = m.end()
        if m.group(1):
            node: Node = []
            if stack:
                stack[-1].append(node)
            stack.append(node)
        elif m.group(2):
            node = stack.pop()
            if not stack:
                root = node
                break
        elif m.group(3) is not None:
            stack[-1].append(Q(m.group(3).replace('\\"', '"').replace("\\\\", "\\")))
        elif m.group(4):
            if not stack:
                raise ValueError(f"atom outside list at {pos}")
            stack[-1].append(m.group(4))
        else:
            break
    if root is None:
        raise ValueError("unterminated S-expression")
    return root


def parse_all(text: str) -> list[Node]:
    """Parse every top-level S-expression in a file (a .kicad_sym has one)."""
    return [parse(text)]


def quote(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def dumps(node: Node | str, indent: int = 0) -> str:
    """Serialize with KiCad's tab layout: one child list per line."""
    if isinstance(node, Q):
        return quote(node)
    if isinstance(node, str):
        return node
    tab = "\t" * indent
    head = node[0] if node and isinstance(node[0], str) and not isinstance(node[0], Q) else None
    parts = [dumps(node[0], indent) if node else ""]
    inline = True
    out = "(" + parts[0]
    for child in node[1:]:
        if isinstance(child, list):
            inline = False
            out += "\n" + tab + "\t" + dumps(child, indent + 1)
        else:
            out += " " + dumps(child, indent)
    if head is not None and not inline:
        out += "\n" + tab + ")"
    else:
        out += ")"
    return out


def children(node: Node, head: str) -> list[Node]:
    return [c for c in node[1:] if isinstance(c, list) and c and c[0] == head]


def child(node: Node, head: str) -> Node | None:
    found = children(node, head)
    return found[0] if found else None


def atoms(node: Node) -> list[str]:
    return [c for c in node[1:] if not isinstance(c, list)]


def set_child(node: Node, head: str, new: Node) -> None:
    for i, c in enumerate(node):
        if isinstance(c, list) and c and c[0] == head:
            node[i] = new
            return
    node.append(new)


def remove_children(node: Node, heads: set[str]) -> None:
    node[:] = [c for c in node if not (isinstance(c, list) and c and c[0] in heads)]


def num(s: str) -> float:
    return float(s)


def fmt(v: float) -> str:
    s = f"{v:.6f}".rstrip("0").rstrip(".")
    return "0" if s in ("", "-0") else s


def uid(ns: uuid.UUID, key: str) -> Q:
    return Q(str(uuid.uuid5(ns, key)))


# ------------------------------------------------------------- libraries

_LIB_CACHE: dict[Path, Node] = {}


def _load_lib(path: Path) -> Node:
    if path not in _LIB_CACHE:
        _LIB_CACHE[path] = parse(path.read_text(encoding="utf-8"))
    return _LIB_CACHE[path]


@dataclass
class Pin:
    number: str
    name: str
    etype: str  # input, output, bidirectional, power_in, power_out, passive, ...
    x: float  # symbol coordinates, y up
    y: float
    angle: float  # direction the pin points from its connection point toward the body
    length: float
    hidden: bool = False


@dataclass
class Symbol:
    lib: str
    name: str
    node: Node  # flattened, renamed "Lib:Name", 9.0-compatible
    pins: list[Pin]

    @property
    def lib_id(self) -> str:
        return f"{self.lib}:{self.name}"

    def pin(self, number: str) -> Pin:
        for p in self.pins:
            if p.number == number:
                return p
        raise KeyError(f"{self.lib_id}: no pin {number}")


def _strip_tokens(node: Node, drop: set[str]) -> None:
    node[:] = [c for c in node if not (isinstance(c, list) and c and c[0] in drop)]
    for c in node:
        if isinstance(c, list):
            _strip_tokens(c, drop)


def _find_symbol(lib_node: Node, name: str) -> Node:
    for c in children(lib_node, "symbol"):
        if atoms(c) and atoms(c)[0] == name:
            return c
    raise KeyError(f"symbol {name!r} not in library")


def _flatten(lib_node: Node, name: str) -> Node:
    node = copy.deepcopy(_find_symbol(lib_node, name))
    ext = child(node, "extends")
    if ext is None:
        return node
    parent = _flatten(lib_node, atoms(ext)[0])
    parent_name = atoms(parent)[0]
    merged = copy.deepcopy(parent)
    merged[1] = Q(name)
    # Child properties override parent properties of the same key.
    own = {atoms(p)[0]: p for p in children(node, "property")}
    merged[:] = [
        c for c in merged if not (isinstance(c, list) and c and c[0] == "property" and atoms(c)[0] in own)
    ]
    insert_at = 2
    for c in merged[2:]:
        if (
            isinstance(c, list)
            and c
            and c[0] in ("pin_numbers", "pin_names", "exclude_from_sim", "in_bom", "on_board")
        ):
            insert_at = merged.index(c) + 1
    for p in own.values():
        merged.insert(insert_at, p)
        insert_at += 1
    # Child-level flags (in_bom etc.) override parent ones.
    for head in ("exclude_from_sim", "in_bom", "on_board", "pin_numbers", "pin_names"):
        c = child(node, head)
        if c is not None:
            set_child(merged, head, copy.deepcopy(c))
    # Units are named after the symbol: Parent_0_1 -> Child_0_1.
    for unit in children(merged, "symbol"):
        unit_name = atoms(unit)[0]
        if unit_name.startswith(parent_name + "_"):
            unit[1] = Q(name + unit_name[len(parent_name) :])
    return merged


def load_symbol(lib_id: str) -> Symbol:
    lib, name = lib_id.split(":", 1)
    lib_node = _load_lib(SYMBOL_DIR / f"{lib}.kicad_sym")
    node = _flatten(lib_node, name)
    _strip_tokens(node, DROP_SYMBOL_TOKENS)
    node[1] = Q(lib_id)
    pins: list[Pin] = []
    for unit in children(node, "symbol"):
        for p in children(unit, "pin"):
            at = child(p, "at")
            at_vals = atoms(at) if at else ["0", "0", "0"]
            length = child(p, "length")
            name_node = child(p, "name")
            number_node = child(p, "number")
            hide = child(p, "hide")
            pins.append(
                Pin(
                    number=str(atoms(number_node)[0]) if number_node else "",
                    name=str(atoms(name_node)[0]) if name_node else "",
                    etype=str(p[1]),
                    x=num(at_vals[0]),
                    y=num(at_vals[1]),
                    angle=num(at_vals[2]) if len(at_vals) > 2 else 0.0,
                    length=num(atoms(length)[0]) if length else 0.0,
                    hidden=bool(hide and atoms(hide) and atoms(hide)[0] == "yes"),
                )
            )
    return Symbol(lib, name, node, pins)


@dataclass
class Pad:
    number: str
    kind: str  # smd | thru_hole | np_thru_hole
    shape: str  # rect | roundrect | circle | oval | custom
    x: float
    y: float
    angle: float
    w: float
    h: float
    layers: list[str]
    drill: float = 0.0


@dataclass
class Footprint:
    lib: str
    name: str
    node: Node  # library footprint, 9.0-compatible, renamed "Lib:Name"
    pads: list[Pad]
    courtyard: tuple[float, float, float, float] | None  # x1 y1 x2 y2 local

    @property
    def lib_id(self) -> str:
        return f"{self.lib}:{self.name}"


def load_footprint(lib_id: str) -> Footprint:
    lib, name = lib_id.split(":", 1)
    node = parse((FOOTPRINT_DIR / f"{lib}.pretty" / f"{name}.kicad_mod").read_text(encoding="utf-8"))
    _strip_tokens(node, DROP_FOOTPRINT_TOKENS)
    node[1] = Q(lib_id)
    pads: list[Pad] = []
    for p in children(node, "pad"):
        at = atoms(child(p, "at"))
        size = atoms(child(p, "size"))
        layers = [str(a) for a in atoms(child(p, "layers"))]
        drill = child(p, "drill")
        drill_d = 0.0
        if drill:
            vals = [a for a in atoms(drill) if a not in ("oval",)]
            drill_d = num(vals[0]) if vals else 0.0
        pads.append(
            Pad(
                number=str(p[1]),
                kind=str(p[2]),
                shape=str(p[3]),
                x=num(at[0]),
                y=num(at[1]),
                angle=num(at[2]) if len(at) > 2 else 0.0,
                w=num(size[0]),
                h=num(size[1]),
                layers=layers,
                drill=drill_d,
            )
        )
    court = None
    xs: list[float] = []
    ys: list[float] = []
    for shape in node[1:]:
        if not isinstance(shape, list) or shape[0] not in ("fp_rect", "fp_line", "fp_poly", "fp_circle"):
            continue
        layer = child(shape, "layer")
        if not layer or atoms(layer)[0] not in ("F.CrtYd", "B.CrtYd"):
            continue
        for head in ("start", "end"):
            pt = child(shape, head)
            if pt:
                xs.append(num(atoms(pt)[0]))
                ys.append(num(atoms(pt)[1]))
        pts = child(shape, "pts")
        if pts:
            for xy in children(pts, "xy"):
                xs.append(num(atoms(xy)[0]))
                ys.append(num(atoms(xy)[1]))
    if xs:
        court = (min(xs), min(ys), max(xs), max(ys))
    return Footprint(lib, name, node, pads, court)


# ---------------------------------------------------------------- design

POWER_LIB = "power"


@dataclass
class Part:
    ref: str
    symbol: Symbol
    value: str
    footprint: Footprint | None
    sch_at: tuple[float, float]
    pcb_at: tuple[float, float] | None = None
    pcb_rot: float = 0.0
    pcb_layer: str = "F.Cu"
    nets: dict[str, str] = field(default_factory=dict)  # pin number -> net name
    descr: str = ""
    datasheet: str = ""
    stub: float = 2.54  # schematic stub wire length
    hide_ref: bool = False  # hide the reference designator on the board silkscreen

    @property
    def on_board(self) -> bool:
        return self.footprint is not None

    @property
    def in_bom(self) -> bool:
        """Follow the footprint: a test point or fiducial is excluded from the BOM in its library footprint."""
        if self.footprint is None:
            return False
        attr = child(self.footprint.node, "attr")
        return not (attr and "exclude_from_bom" in atoms(attr))

    def unconnected_net(self, pin: Pin) -> str:
        """KiCad's name for the net of a pin with no connection: unconnected-(REF-PINNAME-PadN)."""
        return f"unconnected-({self.ref}-{pin.name.replace('/', '{slash}')}-Pad{pin.number})"


@dataclass
class Design:
    name: str
    namespace: uuid.UUID
    parts: list[Part] = field(default_factory=list)
    power_nets: dict[str, str] = field(
        default_factory=dict
    )  # net name -> power symbol name (e.g. GND -> GND)
    flagged_nets: list[str] = field(default_factory=list)  # nets that get a PWR_FLAG
    outline: tuple[float, float, float, float] = (100.0, 100.0, 125.0, 120.0)
    track_width: float = 0.25
    clearance: float = 0.2
    edge_clearance: float = 0.3
    via_size: float = 0.6
    via_drill: float = 0.3
    # name -> {"width", "clearance", "via", "via_drill", "nets": [...]} for nets that need more copper
    net_classes: dict[str, dict] = field(default_factory=dict)
    title: str = ""
    segments: list[tuple[str, tuple[float, float], tuple[float, float], float, str]] = field(
        default_factory=list
    )
    vias: list[tuple[str, tuple[float, float], float, float]] = field(
        default_factory=list
    )  # net, at, size, drill
    _symcache: dict[str, Symbol] = field(default_factory=dict, repr=False)
    _fpcache: dict[str, Footprint] = field(default_factory=dict, repr=False)

    # ---- construction

    def uid(self, key: str) -> Q:
        return uid(self.namespace, key)

    def symbol(self, lib_id: str) -> Symbol:
        if lib_id not in self._symcache:
            self._symcache[lib_id] = load_symbol(lib_id)
        return self._symcache[lib_id]

    def fp(self, lib_id: str) -> Footprint:
        if lib_id not in self._fpcache:
            self._fpcache[lib_id] = load_footprint(lib_id)
        return self._fpcache[lib_id]

    def add(
        self,
        ref: str,
        lib_id: str,
        value: str,
        footprint: str | None,
        sch_at: tuple[float, float],
        nets: dict[str, str],
        pcb_at: tuple[float, float] | None = None,
        pcb_rot: float = 0.0,
        descr: str = "",
        datasheet: str = "~",
        stub: float = 2.54,
    ) -> Part:
        sym = self.symbol(lib_id)
        fpo = self.fp(footprint) if footprint else None
        for pin_no in nets:
            sym.pin(pin_no)  # raises on a typo
        if fpo is not None:
            pad_numbers = {p.number for p in fpo.pads}
            for pin_no in nets:
                if pin_no not in pad_numbers:
                    raise KeyError(f"{ref}: pin {pin_no} has no pad in {footprint}")
        part = Part(ref, sym, value, fpo, sch_at, pcb_at, pcb_rot, "F.Cu", dict(nets), descr, datasheet, stub)
        self.parts.append(part)
        return part

    # ---- nets

    def net_names(self) -> list[str]:
        names: list[str] = []
        for p in self.parts:
            for n in p.nets.values():
                if n not in names:
                    names.append(n)
        return names

    def pcb_net_name(self, name: str) -> str:
        """Power nets are global; signal nets are local labels on the root sheet."""
        return name if name in self.power_nets else f"/{name}"

    def unconnected_nets(self) -> dict[tuple[str, str], str]:
        """(ref, pad number) -> unconnected-(...) net for every board pin the schematic leaves open."""
        out: dict[tuple[str, str], str] = {}
        for part in self.parts:
            if not part.on_board or part.footprint is None:
                continue
            pad_numbers = {p.number for p in part.footprint.pads}
            for pin in part.symbol.pins:
                if pin.number and pin.number not in part.nets and pin.number in pad_numbers:
                    out[(part.ref, pin.number)] = part.unconnected_net(pin)
        return out

    def net_ids(self) -> dict[str, int]:
        ids = {self.pcb_net_name(n): i + 1 for i, n in enumerate(self.net_names())}
        for name in self.unconnected_nets().values():
            ids.setdefault(name, len(ids) + 1)
        return ids

    def class_of(self, pcb_net: str) -> dict:
        for name, spec in self.net_classes.items():
            if pcb_net in [self.pcb_net_name(n) for n in spec["nets"]]:
                return {"name": name, **spec}
        return {
            "name": "Default",
            "width": self.track_width,
            "clearance": self.clearance,
            "via": self.via_size,
            "via_drill": self.via_drill,
            "nets": [],
        }

    # ---- schematic

    def _pin_point(self, part: Part, pin: Pin) -> tuple[float, float, float, float]:
        """Connection point in schematic coordinates plus the outward unit vector."""
        x = part.sch_at[0] + pin.x
        y = part.sch_at[1] - pin.y
        a = math.radians(pin.angle)
        dx, dy = -math.cos(a), math.sin(a)  # outward, schematic y down
        return x, y, round(dx), round(dy)

    def schematic(self) -> str:
        ns = self.namespace
        root = uid(ns, "sheet/root")
        lib_symbols: dict[str, Node] = {}
        body: list[Node] = []
        power_counter = 0
        symbols_used: list[tuple[str, Symbol]] = []

        for part in self.parts:
            lib_symbols.setdefault(part.symbol.lib_id, part.symbol.node)
            symbols_used.append((part.ref, part.symbol))

        def power_symbol(net: str, x: float, y: float, key: str) -> None:
            nonlocal power_counter
            power_counter += 1
            sym = self.symbol(f"{POWER_LIB}:{self.power_nets[net]}")
            lib_symbols.setdefault(sym.lib_id, sym.node)
            ref = f"#PWR{power_counter:02d}"
            body.append(
                self._symbol_instance(ref, sym, net, "", (x, y), root, key, hidden_fields=True, in_bom=False)
            )

        for part in self.parts:
            body.append(
                self._symbol_instance(
                    part.ref,
                    part.symbol,
                    part.value,
                    part.footprint.lib_id if part.footprint else "",
                    part.sch_at,
                    root,
                    f"symbol/{part.ref}",
                    part.descr,
                    part.datasheet,
                    in_bom=part.in_bom,
                )
            )
            for pin in part.symbol.pins:
                if pin.hidden or not pin.number:
                    continue
                x, y, dx, dy = self._pin_point(part, pin)
                net = part.nets.get(pin.number)
                if net is None:
                    body.append(
                        [
                            "no_connect",
                            ["at", fmt(x), fmt(y)],
                            ["uuid", uid(ns, f"nc/{part.ref}/{pin.number}")],
                        ]
                    )
                    continue
                ex, ey = x + dx * part.stub, y + dy * part.stub
                body.append(
                    [
                        "wire",
                        ["pts", ["xy", fmt(x), fmt(y)], ["xy", fmt(ex), fmt(ey)]],
                        ["stroke", ["width", "0"], ["type", "default"]],
                        ["uuid", uid(ns, f"stub/{part.ref}/{pin.number}")],
                    ]
                )
                if net in self.power_nets:
                    power_symbol(net, ex, ey, f"pwr/{part.ref}/{pin.number}")
                else:
                    body.append(self._label(net, ex, ey, dx, dy, uid(ns, f"label/{part.ref}/{pin.number}")))

        # PWR_FLAG pairs: a flag wired to a power symbol drives the net for ERC.
        flag_sym = self.symbol(f"{POWER_LIB}:PWR_FLAG")
        lib_symbols.setdefault(flag_sym.lib_id, flag_sym.node)
        fx, fy = 20.32, 20.32
        for i, net in enumerate(self.flagged_nets):
            x = fx + i * 12.7
            body.append(
                self._symbol_instance(
                    f"#FLG{i + 1:02d}",
                    flag_sym,
                    "PWR_FLAG",
                    "",
                    (x, fy),
                    root,
                    f"flag/{net}",
                    hidden_fields=True,
                    in_bom=False,
                )
            )
            body.append(
                [
                    "wire",
                    ["pts", ["xy", fmt(x), fmt(fy)], ["xy", fmt(x), fmt(fy + 2.54)]],
                    ["stroke", ["width", "0"], ["type", "default"]],
                    ["uuid", uid(ns, f"flagwire/{net}")],
                ]
            )
            power_symbol(net, x, fy + 2.54, f"flagpwr/{net}")

        sch: Node = [
            "kicad_sch",
            ["version", str(SCH_VERSION)],
            ["generator", Q("eeschema")],
            ["generator_version", Q("9.0")],
            ["uuid", root],
            ["paper", Q("A3")],
        ]
        if self.title:
            sch.append(["title_block", ["title", Q(self.title)], ["company", Q("EE Workcenter")]])
        sch.append(["lib_symbols", *lib_symbols.values()])
        sch.extend(body)
        sch.append(["sheet_instances", ["path", Q("/"), ["page", Q("1")]]])
        sch.append(["embedded_fonts", "no"])
        return dumps(sch) + "\n"

    def _label(self, net: str, x: float, y: float, dx: int, dy: int, u: Q) -> Node:
        if dx > 0:
            rot, justify = "0", ["justify", "left", "bottom"]
        elif dx < 0:
            rot, justify = "180", ["justify", "right", "bottom"]
        elif dy < 0:
            rot, justify = "90", ["justify", "left", "bottom"]
        else:
            rot, justify = "270", ["justify", "right", "bottom"]
        return [
            "label",
            Q(net),
            ["at", fmt(x), fmt(y), rot],
            ["effects", ["font", ["size", "1.27", "1.27"]], justify],
            ["uuid", u],
        ]

    def _symbol_instance(
        self,
        ref: str,
        sym: Symbol,
        value: str,
        footprint: str,
        at: tuple[float, float],
        root: Q,
        key: str,
        descr: str = "",
        datasheet: str = "~",
        hidden_fields: bool = False,
        in_bom: bool = True,
    ) -> Node:
        ns = self.namespace
        x, y = at
        hide = ["effects", ["font", ["size", "1.27", "1.27"]], ["hide", "yes"]]
        node: Node = [
            "symbol",
            ["lib_id", Q(sym.lib_id)],
            ["at", fmt(x), fmt(y), "0"],
            ["unit", "1"],
            ["exclude_from_sim", "no"],
            ["in_bom", "yes" if in_bom else "no"],
            ["on_board", "no" if ref.startswith("#") else "yes"],
            ["dnp", "no"],
            ["uuid", uid(ns, key)],
        ]
        # Field positions: reference above-right, value below-right of the anchor.
        node.append(
            [
                "property",
                Q("Reference"),
                Q(ref),
                ["at", fmt(x + 1.27), fmt(y - 1.27), "0"],
                hide
                if hidden_fields
                else ["effects", ["font", ["size", "1.27", "1.27"]], ["justify", "left"]],
            ]
        )
        node.append(
            [
                "property",
                Q("Value"),
                Q(value),
                ["at", fmt(x + 1.27), fmt(y + 1.27), "0"],
                hide
                if hidden_fields
                else ["effects", ["font", ["size", "1.27", "1.27"]], ["justify", "left"]],
            ]
        )
        node.append(["property", Q("Footprint"), Q(footprint), ["at", fmt(x), fmt(y), "0"], hide])
        node.append(["property", Q("Datasheet"), Q(datasheet), ["at", fmt(x), fmt(y), "0"], hide])
        node.append(["property", Q("Description"), Q(descr), ["at", fmt(x), fmt(y), "0"], hide])
        for pin in sym.pins:
            if pin.number:
                node.append(["pin", Q(pin.number), ["uuid", uid(ns, f"{key}/pin/{pin.number}")]])
        node.append(
            [
                "instances",
                ["project", Q(self.name), ["path", Q(f"/{root}"), ["reference", Q(ref)], ["unit", "1"]]],
            ]
        )
        return node

    # ---- board

    def _footprint_instance(self, part: Part, net_ids: dict[str, int]) -> Node:
        assert part.footprint and part.pcb_at
        ns = self.namespace
        fpn = copy.deepcopy(part.footprint.node)
        rot = part.pcb_rot
        x, y = part.pcb_at
        out: Node = [
            "footprint",
            Q(part.footprint.lib_id),
            ["layer", Q("F.Cu")],
            ["uuid", uid(ns, f"fp/{part.ref}")],
            ["at", fmt(x), fmt(y)] + ([fmt(rot)] if rot else []),
        ]
        for head in ("descr", "tags"):
            c = child(fpn, head)
            if c:
                out.append(c)
        # Properties: Reference and Value from the design, the rest from the library, each with a uuid.
        props = {atoms(p)[0]: p for p in children(fpn, "property")}
        for key_name, val in (("Reference", part.ref), ("Value", part.value)):
            p = copy.deepcopy(
                props.get(key_name)
                or ["property", Q(key_name), Q(val), ["at", "0", "0", "0"], ["layer", Q("F.Fab")]]
            )
            p[2] = Q(val)
            self._rotate_at(p, rot)
            if key_name == "Reference" and part.hide_ref and child(p, "hide") is None:
                p.insert(4, ["hide", "yes"])
            p.insert(3, ["uuid", uid(ns, f"fp/{part.ref}/{key_name}")])
            out.append(p)
        fab_hidden = ["effects", ["font", ["size", "1", "1"], ["thickness", "0.15"]]]
        out.append(
            [
                "property",
                Q("Datasheet"),
                Q(part.datasheet if part.datasheet != "~" else ""),
                ["at", "0", "0", fmt(rot)],
                ["layer", Q("F.Fab")],
                ["hide", "yes"],
                ["uuid", uid(ns, f"fp/{part.ref}/Datasheet")],
                fab_hidden,
            ]
        )
        out.append(
            [
                "property",
                Q("Description"),
                Q(part.descr),
                ["at", "0", "0", fmt(rot)],
                ["layer", Q("F.Fab")],
                ["hide", "yes"],
                ["uuid", uid(ns, f"fp/{part.ref}/Description")],
                fab_hidden,
            ]
        )
        out.append(["path", Q(f"/{uid(ns, f'symbol/{part.ref}')}")])
        out.append(["sheetname", Q("/")])
        out.append(["sheetfile", Q(f"{self.name}.kicad_sch")])
        attr = child(fpn, "attr")
        out.append(attr if attr else ["attr", "smd"])
        shape_i = 0
        for item in fpn[1:]:
            if not isinstance(item, list):
                continue
            head = item[0]
            if head in ("fp_line", "fp_rect", "fp_circle", "fp_arc", "fp_poly"):
                item = copy.deepcopy(item)
                item.append(["uuid", uid(ns, f"fp/{part.ref}/shape/{shape_i}")])
                shape_i += 1
                out.append(item)
            elif head == "fp_text":
                item = copy.deepcopy(item)
                self._rotate_at(item, rot)
                item.insert(3, ["uuid", uid(ns, f"fp/{part.ref}/text/{shape_i}")])
                shape_i += 1
                out.append(item)
        open_nets = self.unconnected_nets()
        for p in children(fpn, "pad"):
            p = copy.deepcopy(p)
            self._rotate_at(p, rot)
            number = str(p[1])
            net = part.nets.get(number)
            tail: Node = []
            pin = next((pp for pp in part.symbol.pins if pp.number == number), None)
            if net is not None:
                pcb_net = self.pcb_net_name(net)
                tail.append(["net", str(net_ids[pcb_net]), Q(pcb_net)])
            elif (part.ref, number) in open_nets:
                pcb_net = open_nets[(part.ref, number)]
                tail.append(["net", str(net_ids[pcb_net]), Q(pcb_net)])
            if pin and tail:
                tail.append(["pintype", Q(pin.etype)])
            tail.append(["uuid", uid(ns, f"fp/{part.ref}/pad/{number}/{len(tail)}")])
            # KiCad writes net/pintype/uuid after the geometry tokens.
            p.extend(tail)
            out.append(p)
        out.append(["embedded_fonts", "no"])
        model = child(fpn, "model")
        if model:
            out.append(model)
        return out

    @staticmethod
    def _rotate_at(item: Node, rot: float) -> None:
        if not rot:
            return
        at = child(item, "at")
        if at is None:
            return
        vals = atoms(at)
        a = num(vals[2]) if len(vals) > 2 else 0.0
        at[:] = ["at", vals[0], vals[1], fmt((a + rot) % 360)]

    def board(self) -> str:
        ns = self.namespace
        net_ids = self.net_ids()
        x1, y1, x2, y2 = self.outline
        layers = [
            ["0", Q("F.Cu"), "signal"],
            ["2", Q("B.Cu"), "signal"],
            ["9", Q("F.Adhes"), "user", Q("F.Adhesive")],
            ["11", Q("B.Adhes"), "user", Q("B.Adhesive")],
            ["13", Q("F.Paste"), "user"],
            ["15", Q("B.Paste"), "user"],
            ["5", Q("F.SilkS"), "user", Q("F.Silkscreen")],
            ["7", Q("B.SilkS"), "user", Q("B.Silkscreen")],
            ["1", Q("F.Mask"), "user"],
            ["3", Q("B.Mask"), "user"],
            ["17", Q("Dwgs.User"), "user", Q("User.Drawings")],
            ["19", Q("Cmts.User"), "user", Q("User.Comments")],
            ["21", Q("Eco1.User"), "user", Q("User.Eco1")],
            ["23", Q("Eco2.User"), "user", Q("User.Eco2")],
            ["25", Q("Edge.Cuts"), "user"],
            ["27", Q("Margin"), "user"],
            ["31", Q("F.CrtYd"), "user", Q("F.Courtyard")],
            ["29", Q("B.CrtYd"), "user", Q("B.Courtyard")],
            ["35", Q("F.Fab"), "user"],
            ["33", Q("B.Fab"), "user"],
        ]
        plot = [
            "pcbplotparams",
            ["layerselection", "0x00000000_00000000_55555555_5755f5ff"],
            ["plot_on_all_layers_selection", "0x00000000_00000000_00000000_00000000"],
            ["disableapertmacros", "no"],
            ["usegerberextensions", "no"],
            ["usegerberattributes", "yes"],
            ["usegerberadvancedattributes", "yes"],
            ["creategerberjobfile", "yes"],
            ["dashed_line_dash_ratio", "12.000000"],
            ["dashed_line_gap_ratio", "3.000000"],
            ["svgprecision", "4"],
            ["plotframeref", "no"],
            ["mode", "1"],
            ["useauxorigin", "no"],
            ["hpglpennumber", "1"],
            ["hpglpenspeed", "20"],
            ["hpglpendiameter", "15.000000"],
            ["pdf_front_fp_property_popups", "yes"],
            ["pdf_back_fp_property_popups", "yes"],
            ["pdf_metadata", "yes"],
            ["pdf_single_document", "no"],
            ["dxfpolygonmode", "yes"],
            ["dxfimperialunits", "yes"],
            ["dxfusepcbnewfont", "yes"],
            ["psnegative", "no"],
            ["psa4output", "no"],
            ["plot_black_and_white", "yes"],
            ["plotinvisibletext", "no"],
            ["sketchpadsonfab", "no"],
            ["plotpadnumbers", "no"],
            ["hidednponfab", "no"],
            ["sketchdnponfab", "yes"],
            ["crossoutdnponfab", "yes"],
            ["subtractmaskfromsilk", "no"],
            ["outputformat", "1"],
            ["mirror", "no"],
            ["drillshape", "1"],
            ["scaleselection", "1"],
            ["outputdirectory", Q("")],
        ]
        pcb: Node = [
            "kicad_pcb",
            ["version", str(PCB_VERSION)],
            ["generator", Q("pcbnew")],
            ["generator_version", Q("9.0")],
            ["general", ["thickness", "1.6"], ["legacy_teardrops", "no"]],
            ["paper", Q("A4")],
            ["layers", *layers],
            [
                "setup",
                ["pad_to_mask_clearance", "0"],
                ["allow_soldermask_bridges_in_footprints", "no"],
                ["tenting", "front", "back"],
                plot,
            ],
            ["net", "0", Q("")],
        ]
        for name, i in sorted(net_ids.items(), key=lambda kv: kv[1]):
            pcb.append(["net", str(i), Q(name)])
        for part in self.parts:
            if part.on_board and part.pcb_at:
                pcb.append(self._footprint_instance(part, net_ids))
        pcb.append(
            [
                "gr_rect",
                ["start", fmt(x1), fmt(y1)],
                ["end", fmt(x2), fmt(y2)],
                ["stroke", ["width", "0.1"], ["type", "default"]],
                ["fill", "no"],
                ["layer", Q("Edge.Cuts")],
                ["uuid", uid(ns, "edge")],
            ]
        )
        if self.title:
            pcb.append(
                [
                    "gr_text",
                    Q(self.title),
                    ["at", fmt(x1 + 1.5), fmt(y2 - 1.2), "0"],
                    ["layer", Q("F.SilkS")],
                    ["uuid", uid(ns, "title")],
                    ["effects", ["font", ["size", "0.8", "0.8"], ["thickness", "0.12"]], ["justify", "left"]],
                ]
            )
        for i, (net, (sx, sy), (ex, ey), w, layer) in enumerate(self.segments):
            pcb.append(
                [
                    "segment",
                    ["start", fmt(sx), fmt(sy)],
                    ["end", fmt(ex), fmt(ey)],
                    ["width", fmt(w)],
                    ["layer", Q(layer)],
                    ["net", str(net_ids[net])],
                    ["uuid", uid(ns, f"seg/{i}")],
                ]
            )
        for i, (net, (vx, vy), size, drill) in enumerate(self.vias):
            pcb.append(
                [
                    "via",
                    ["at", fmt(vx), fmt(vy)],
                    ["size", fmt(size)],
                    ["drill", fmt(drill)],
                    ["layers", Q("F.Cu"), Q("B.Cu")],
                    ["net", str(net_ids[net])],
                    ["uuid", uid(ns, f"via/{i}")],
                ]
            )
        pcb.append(["embedded_fonts", "no"])
        return dumps(pcb) + "\n"

    # ---- project

    def project(self) -> str:
        import json

        def netclass(
            name: str, width: float, clearance: float, via: float, via_drill: float, priority: int
        ) -> dict:
            return {
                "bus_width": 12,
                "clearance": clearance,
                "diff_pair_gap": 0.25,
                "diff_pair_via_gap": 0.25,
                "diff_pair_width": 0.2,
                "line_style": 0,
                "microvia_diameter": 0.3,
                "microvia_drill": 0.1,
                "name": name,
                "pcb_color": "rgba(0, 0, 0, 0.000)",
                "priority": priority,
                "schematic_color": "rgba(0, 0, 0, 0.000)",
                "track_width": width,
                "via_diameter": via,
                "via_drill": via_drill,
                "wire_width": 6,
            }

        root = str(uid(self.namespace, "sheet/root"))
        data = {
            "board": {
                "design_settings": {
                    "defaults": {},
                    "rule_severities": {"lib_footprint_issues": "ignore", "lib_footprint_mismatch": "ignore"},
                    "rules": {
                        "min_clearance": 0.0,
                        "min_connection": 0.0,
                        "min_copper_edge_clearance": self.edge_clearance,
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
            "erc": {
                "erc_exclusions": [],
                "meta": {"version": 0},
                "rule_severities": {"footprint_link_issues": "ignore", "lib_symbol_issues": "ignore"},
            },
            "libraries": {"pinned_footprint_libs": [], "pinned_symbol_libs": []},
            "meta": {"filename": f"{self.name}.kicad_pro", "version": 3},
            "net_settings": {
                "classes": [
                    netclass(
                        "Default", self.track_width, self.clearance, self.via_size, self.via_drill, 2147483647
                    )
                ]
                + [
                    netclass(name, s["width"], s["clearance"], s["via"], s["via_drill"], i)
                    for i, (name, s) in enumerate(self.net_classes.items())
                ],
                "meta": {"version": 4},
                "net_colors": None,
                "netclass_assignments": None,
                "netclass_patterns": [
                    {"netclass": name, "pattern": self.pcb_net_name(n)}
                    for name, s in self.net_classes.items()
                    for n in s["nets"]
                ],
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
            "sheets": [[root, "Root"]],
            "text_variables": {},
        }
        return json.dumps(data, indent=2) + "\n"

    # ---- Specctra

    def dsn(self) -> str:
        """Specctra DSN of the placed board, in 0.1 um units with y up (KiCad's own convention)."""
        U = 10000.0  # mm -> 0.1 um

        def c(v: float) -> str:
            return str(int(round(v * U)))

        x1, y1, x2, y2 = self.outline
        net_ids = self.net_ids()
        images: dict[str, str] = {}
        padstacks: dict[str, str] = {}
        placement: list[str] = []
        pins_by_net: dict[str, list[str]] = {n: [] for n in net_ids}

        def padstack_for(pad: Pad, part_rot: float) -> str:
            w, h = pad.w, pad.h
            # Pad angle relative to the image: the image is rotated by the placement.
            if round((pad.angle) % 180) == 90:
                w, h = h, w
            layers = ["F.Cu", "B.Cu"] if pad.kind in ("thru_hole", "np_thru_hole") else ["F.Cu"]
            shape = (
                "circle" if pad.shape == "circle" or (pad.shape == "oval" and abs(w - h) < 1e-6) else "rect"
            )
            key = f"{shape}_{fmt(w)}x{fmt(h)}_{'TH' if len(layers) == 2 else 'SMD'}"
            name = f"Pad_{key}"
            if name not in padstacks:
                shapes = []
                for layer in layers:
                    if shape == "circle":
                        shapes.append(f"(shape (circle {layer} {c(max(w, h))}))")
                    else:
                        shapes.append(f"(shape (rect {layer} {c(-w / 2)} {c(-h / 2)} {c(w / 2)} {c(h / 2)}))")
                padstacks[name] = (
                    f'    (padstack "{name}"\n      '
                    + "\n      ".join(shapes)
                    + "\n      (attach off)\n    )"
                )
            return name

        for part in self.parts:
            if not (part.on_board and part.pcb_at and part.footprint):
                continue
            fp = part.footprint
            if fp.lib_id not in images:
                pins = []
                for i, pad in enumerate(fp.pads):
                    if pad.kind == "np_thru_hole":
                        # A hole with no copper: an unconnected pin the router must avoid. KiCad's hole
                        # clearance (0.25 mm) exceeds the track clearance (0.2 mm); the obstacle is grown
                        # by the difference so the router keeps the larger distance.
                        margin = 2 * max(0.0, 0.25 - self.clearance)
                        hole = Pad(
                            f"NPTH{i}",
                            "thru_hole",
                            "circle",
                            pad.x,
                            pad.y,
                            0.0,
                            pad.drill + margin,
                            pad.drill + margin,
                            ["*.Cu"],
                        )
                        pins.append(
                            f'      (pin {padstack_for(hole, part.pcb_rot)} "{hole.number}" {c(pad.x)} {c(-pad.y)})'
                        )
                        continue
                    ps = padstack_for(pad, part.pcb_rot)
                    pins.append(f'      (pin {ps} "{pad.number}" {c(pad.x)} {c(-pad.y)})')
                images[fp.lib_id] = f'    (image "{fp.lib_id}"\n' + "\n".join(pins) + "\n    )"
            px, py = part.pcb_at
            placement.append(
                f'    (component "{fp.lib_id}"\n      (place "{part.ref}" {c(px)} {c(-py)} front {fmt(part.pcb_rot)})\n    )'
            )
            for pin_no, net in part.nets.items():
                pins_by_net[self.pcb_net_name(net)].append(f"{part.ref}-{pin_no}")

        def via_name(size: float, drill: float) -> str:
            return f"Via[0-1]_{int(round(size * 1000))}:{int(round(drill * 1000))}_um"

        vias = {via_name(self.via_size, self.via_drill): (self.via_size, self.via_drill)}
        for s in self.net_classes.values():
            vias.setdefault(via_name(s["via"], s["via_drill"]), (s["via"], s["via_drill"]))
        via_ps = [
            f'    (padstack "{n}"\n      (shape (circle F.Cu {c(d)}))\n      (shape (circle B.Cu {c(d)}))\n      (attach off)\n    )'
            for n, (d, _) in vias.items()
        ]
        nets_out = []
        routable = []
        for name in sorted(net_ids, key=net_ids.get):
            pins = pins_by_net.get(name, [])
            if len(pins) >= 2:
                nets_out.append(f'    (net "{name}"\n      (pins {" ".join(pins)})\n    )')
                routable.append(name)
        classed = {self.pcb_net_name(n) for s in self.net_classes.values() for n in s["nets"]}
        classes = []
        default_nets = " ".join(f'"{n}"' for n in routable if n not in classed)
        classes.append(
            f'    (class kicad_default "" {default_nets}\n'
            f'      (circuit (use_via "{via_name(self.via_size, self.via_drill)}"))\n'
            f"      (rule (width {c(self.track_width)}) (clearance {c(self.clearance)}))\n    )"
        )
        for cname, s in self.net_classes.items():
            cnets = " ".join(f'"{self.pcb_net_name(n)}"' for n in s["nets"])
            classes.append(
                f"    (class {cname} {cnets}\n"
                f'      (circuit (use_via "{via_name(s["via"], s["via_drill"])}"))\n'
                f"      (rule (width {c(s['width'])}) (clearance {c(s['clearance'])}))\n    )"
            )
        # The router keeps `clearance` from the boundary; the DRC wants edge_clearance. Shrink the boundary.
        e = max(0.0, self.edge_clearance - self.clearance)
        bx1, by1, bx2, by2 = x1 + e, y1 + e, x2 - e, y2 - e
        boundary = f"      (path pcb 0 {c(bx1)} {c(-by1)} {c(bx2)} {c(-by1)} {c(bx2)} {c(-by2)} {c(bx1)} {c(-by2)} {c(bx1)} {c(-by1)})"
        return "\n".join(
            [
                f'(pcb "{self.name}.dsn"',
                '  (parser (string_quote ") (space_in_quoted_tokens on) (host_cad "KiCad\'s Pcbnew") (host_version "9.0"))',
                "  (resolution um 10)",
                "  (unit um)",
                "  (structure",
                "    (layer F.Cu (type signal) (property (index 0)))",
                "    (layer B.Cu (type signal) (property (index 1)))",
                "    (boundary",
                boundary,
                "    )",
                *[f'    (via "{n}")' for n in vias],
                f"    (rule (width {c(self.track_width)}) (clearance {c(self.clearance)}) "
                f"(clearance {c(self.clearance)} (type default_smd)) (clearance {c(self.clearance / 2)} (type smd_smd)))",
                "  )",
                "  (placement",
                *placement,
                "  )",
                "  (library",
                *images.values(),
                *padstacks.values(),
                *via_ps,
                "  )",
                "  (network",
                *nets_out,
                *classes,
                "  )",
                "  (wiring)",
                ")",
                "",
            ]
        )

    def merge_ses(self, text: str) -> tuple[int, int]:
        """Read a Specctra session and append its wires and vias to the board. Returns (segments, vias) added."""
        ses = parse(text)
        routes = child(ses, "routes")
        if routes is None:
            raise ValueError("session has no (routes)")
        res = child(routes, "resolution")
        unit_per_mm = 1000.0
        if res is not None:
            unit, count = atoms(res)[0], float(atoms(res)[1])
            unit_per_mm = {"um": 1000.0, "mm": 1.0, "mil": 39.37007874, "inch": 0.03937007874}[unit] * count
        # FreeRouting declares one resolution and writes coordinates at another. The placement block
        # echoes component positions we know, so the real scale comes from there when it is present.
        placement = child(ses, "placement")
        for comp in children(placement, "component") if placement else []:
            for pl in children(comp, "place"):
                vals = atoms(pl)
                part = next((p for p in self.parts if p.ref == str(vals[0]) and p.pcb_at), None)
                if part and abs(part.pcb_at[0]) > 1e-9 and abs(part.pcb_at[1]) > 1e-9:
                    sx, sy = float(vals[1]) / part.pcb_at[0], -float(vals[2]) / part.pcb_at[1]
                    if abs(sx - sy) / sx > 0.01:
                        raise ValueError(
                            f"session placement of {part.ref} is not a uniform scale of the design"
                        )
                    unit_per_mm = sx
                    break
            else:
                continue
            break

        def mm(v: str) -> float:
            return float(v) / unit_per_mm

        net_ids = self.net_ids()
        added_s = added_v = 0
        network = child(routes, "network_out")
        for net in children(network, "net") if network else []:
            name = str(atoms(net)[0])
            if name not in net_ids:
                raise KeyError(f"session net {name!r} is not in the design")
            for wire in children(net, "wire"):
                path = child(wire, "path")
                if path is None:
                    continue
                vals = atoms(path)
                layer, width = str(vals[0]), mm(vals[1])
                pts = [(mm(vals[i]), -mm(vals[i + 1])) for i in range(2, len(vals) - 1, 2)]
                for a, b in zip(pts, pts[1:], strict=False):
                    if a != b:
                        self.segments.append((name, a, b, width, layer))
                        added_s += 1
            for via in children(net, "via"):
                vals = atoms(via)
                m = re.match(r"Via\[\d+-\d+\]_(\d+):(\d+)_um", str(vals[0]))
                size, drill = (
                    (int(m.group(1)) / 1000, int(m.group(2)) / 1000) if m else (self.via_size, self.via_drill)
                )
                self.vias.append((name, (mm(vals[1]), -mm(vals[2])), size, drill))
                added_v += 1
        return added_s, added_v

    # ---- files

    def write(self, out_dir: Path) -> list[Path]:
        out_dir.mkdir(parents=True, exist_ok=True)
        files = {
            out_dir / f"{self.name}.kicad_pro": self.project(),
            out_dir / f"{self.name}.kicad_sch": self.schematic(),
            out_dir / f"{self.name}.kicad_pcb": self.board(),
        }
        for p, text in files.items():
            p.write_text(text, encoding="utf-8")
        return list(files)


# ------------------------------------------------------- design files, routing


def load_design(path: Path) -> Design:
    """Import a design file and call its build() -> Design."""
    path = Path(path).resolve()
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[path.stem] = module
    spec.loader.exec_module(module)
    build = getattr(module, "build", None)
    if build is None:
        raise AttributeError(f"{path} has no build() -> Design")
    design = build()
    if not isinstance(design, Design):
        raise TypeError(f"{path}: build() returned {type(design).__name__}, not Design")
    return design


UNROUTED_RE = re.compile(r"Auto-routing was completed in .*?\((\d+) unrouted\)")


def route(
    design: Design,
    build_dir: Path,
    jar: Path | None = None,
    passes: int = 60,
    timeout: int = 900,
    java: str = "java",
) -> dict:
    """Export the DSN, run FreeRouting, merge the session into the design. Returns a summary."""
    jar = jar or Path(os.environ.get("FREEROUTING_JAR", "/opt/workcenters/ee/freerouting/freerouting.jar"))
    if not jar.is_file():
        raise FileNotFoundError(str(jar))
    build_dir = Path(build_dir)
    build_dir.mkdir(parents=True, exist_ok=True)
    dsn, ses, log = (
        build_dir / f"{design.name}.dsn",
        build_dir / f"{design.name}.ses",
        build_dir / "freerouting.log",
    )
    dsn.write_text(design.dsn(), encoding="utf-8")
    ses.unlink(missing_ok=True)
    # FreeRouting 1.9.0: -de/-do/-mp only. It needs a display; xvfb-run provides one headless.
    cmd = [java, "-jar", str(jar), "-de", str(dsn), "-do", str(ses), "-mp", str(passes)]
    if not os.environ.get("DISPLAY") and shutil.which("xvfb-run"):
        cmd = ["xvfb-run", "-a", *cmd]
    proc = subprocess.run(cmd, cwd=build_dir, capture_output=True, text=True, timeout=timeout, check=False)
    text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    log.write_text(text, encoding="utf-8")
    if proc.returncode != 0 or not ses.is_file():
        raise RuntimeError(f"FreeRouting exited {proc.returncode}; see {log}")
    segments, vias = design.merge_ses(ses.read_text(encoding="utf-8"))
    m = UNROUTED_RE.search(text)
    return {
        "dsn": str(dsn),
        "ses": str(ses),
        "log": str(log),
        "segments": segments,
        "vias": vias,
        "unrouted": int(m.group(1)) if m else None,
    }


# ------------------------------------------------------------------- cli


def main(argv: list[str]) -> int:
    if len(argv) >= 2 and argv[0] == "pins":
        for lib_id in argv[1:]:
            sym = load_symbol(lib_id)
            print(f"== {sym.lib_id}  ({len(sym.pins)} pins)")
            for p in sorted(sym.pins, key=lambda p: (len(p.number), p.number)):
                print(
                    f"  {p.number:>4}  {p.name:<14} {p.etype:<14} at=({fmt(p.x)}, {fmt(p.y)}) ang={fmt(p.angle)} len={fmt(p.length)}{'  hidden' if p.hidden else ''}"
                )
        return 0
    if len(argv) >= 2 and argv[0] == "footprint":
        for lib_id in argv[1:]:
            fp = load_footprint(lib_id)
            print(f"== {fp.lib_id}  courtyard={fp.courtyard}")
            for pad in fp.pads:
                print(
                    f"  {pad.number:>4} {pad.kind:<10} {pad.shape:<9} at=({fmt(pad.x)}, {fmt(pad.y)}) ang={fmt(pad.angle)} size={fmt(pad.w)}x{fmt(pad.h)} {pad.layers}{' drill=' + fmt(pad.drill) if pad.drill else ''}"
                )
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
