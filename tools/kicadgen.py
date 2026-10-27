#!/usr/bin/env python3
"""kicadgen — build KiCad 10 projects from the installed libraries.

A design is Python: parts placed from the KiCad symbol and footprint
libraries, nets as names. This module turns that into a schematic, a
board, a project file, a Specctra DSN for the autorouter, and merges the
router's session file back into the board. Standard library only.

    python3 tools/kicadgen.py pins Device:R MCU_ST_STM32G0:STM32G031F8Px
    python3 tools/kicadgen.py footprint Package_SO:TSSOP-20_4.4x6.5mm_P0.65mm
    python3 tools/kicadgen.py footprint --lib LastHit=footprints/LastHit.pretty LastHit:Connector_510

A project keeps its own footprints in a `.pretty` folder and names it in
`Design.footprint_dirs`; the generated project gets an `fp-lib-table` for it.

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
import tempfile
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


def _custom_pad_extent(pad: Node, w: float, h: float) -> tuple[float, float]:
    """Width and height of a custom pad's copper: the anchor and every primitive, stroke included,
    as a box centred on the pad (the larger side of each axis, so the box covers it all)."""
    ex, ey = w / 2, h / 2
    prims = child(pad, "primitives")
    for prim in prims[1:] if prims else []:
        if not isinstance(prim, list) or not prim:
            continue
        width = child(prim, "width")
        half = num(atoms(width)[0]) / 2 if width else 0.0
        pts = [atoms(xy) for xy in children(child(prim, "pts"), "xy")] if child(prim, "pts") else []
        pts += [atoms(child(prim, head)) for head in ("start", "end", "mid") if child(prim, head)]
        if prim[0] == "gr_circle" and child(prim, "center") and child(prim, "end"):
            c, e = atoms(child(prim, "center")), atoms(child(prim, "end"))
            r = math.hypot(num(e[0]) - num(c[0]), num(e[1]) - num(c[1]))
            pts = [(num(c[0]) + sx * r, num(c[1]) + sy * r) for sx in (-1, 1) for sy in (-1, 1)]
        for x, y in ((num(pt[0]), num(pt[1])) for pt in pts):
            ex, ey = max(ex, abs(x) + half), max(ey, abs(y) + half)
    return 2 * ex, 2 * ey


def load_footprint(lib_id: str, dirs: dict[str, Path] | None = None) -> Footprint:
    """A footprint by `Lib:Name`, from `dirs[Lib]` when the project names that library, else KiCad's."""
    lib, name = lib_id.split(":", 1)
    base = Path(dirs[lib]) if dirs and lib in dirs else FOOTPRINT_DIR / f"{lib}.pretty"
    node = parse((base / f"{name}.kicad_mod").read_text(encoding="utf-8"))
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
        w, h = num(size[0]), num(size[1])
        if str(p[3]) == "custom":  # the copper is the primitives; `size` is only the anchor
            w, h = _custom_pad_extent(p, w, h)
        pads.append(
            Pad(
                number=str(p[1]),
                kind=str(p[2]),
                shape=str(p[3]),
                x=num(at[0]),
                y=num(at[1]),
                angle=num(at[2]) if len(at) > 2 else 0.0,
                w=w,
                h=h,
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
        if shape[0] == "fp_circle":  # (center) and a point on the circle, not two corners
            c, e = child(shape, "center"), child(shape, "end")
            if c and e:
                cx, cy = num(atoms(c)[0]), num(atoms(c)[1])
                r = math.hypot(num(atoms(e)[0]) - cx, num(atoms(e)[1]) - cy)
                xs.extend((cx - r, cx + r))
                ys.extend((cy - r, cy + r))
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


# ------------------------------------------------------------ schematic wiring

SCH_GRID = 1.27  # KiCad's connection grid: every pin end of a library symbol sits on it
TEXT_ADVANCE = 1.34  # mm a character of 1.27 mm text takes in KiCad's font, read off a plotted "R1"
SHEETS = {"A4": (297.0, 210.0), "A3": (420.0, 297.0), "A2": (594.0, 420.0), "A1": (841.0, 594.0)}
STEPS = ((1, 0), (0, 1), (-1, 0), (0, -1))  # east, south, west, north on the sheet (y down)
Cell = tuple[int, int]


def rot_vec(x: float, y: float, rot: int) -> tuple[float, float]:
    """A sheet vector (y down) turned counter-clockwise on screen by `rot` degrees, the way KiCad turns
    a symbol placed at that angle. Read from KiCad's ERC report: at 90 a resistor's pin 1 moves from
    the top to the left, at 270 to the right."""
    r = rot % 360
    if r == 0:
        return x, y
    if r == 90:
        return y, -x
    if r == 180:
        return -x, -y
    return -y, x


def symbol_box(sym: Symbol) -> tuple[float, float, float, float]:
    """The symbol's drawn body in library coordinates (y up): the rectangles, lines, circles, arcs and
    curves of every unit, without pins or text. A symbol that draws none is its pins' inner ends."""
    xs: list[float] = []
    ys: list[float] = []
    for unit in children(sym.node, "symbol"):
        for g in unit[2:]:
            if not isinstance(g, list) or not g:
                continue
            if g[0] == "circle":
                c, r = child(g, "center"), child(g, "radius")
                cx, cy, rr = num(atoms(c)[0]), num(atoms(c)[1]), num(atoms(r)[0])
                xs += [cx - rr, cx + rr]
                ys += [cy - rr, cy + rr]
            elif g[0] in ("rectangle", "polyline", "arc", "bezier"):
                for head in ("start", "mid", "end"):
                    p = child(g, head)
                    if p is not None:
                        xs.append(num(atoms(p)[0]))
                        ys.append(num(atoms(p)[1]))
                pts = child(g, "pts")
                for xy in children(pts, "xy") if pts is not None else []:
                    xs.append(num(atoms(xy)[0]))
                    ys.append(num(atoms(xy)[1]))
    if not xs:
        for p in sym.pins:
            a = math.radians(p.angle)
            xs.append(p.x + p.length * math.cos(a))
            ys.append(p.y + p.length * math.sin(a))
    return min(xs), min(ys), max(xs), max(ys)


class SchRouter:
    """Orthogonal schematic wires on the 1.27 mm grid, one net at a time.

    KiCad joins a wire to anything one of its ends touches, and to a wire it overlaps along its length;
    two wires that cross at right angles stay apart. So an edge between two cells carries one net, the
    ends and bends of a wire ("nodes") belong to one net, and a wire crosses another only straight
    through a cell where neither has a node.
    """

    BEND = 2.0  # a bend costs as much as two cells of wire
    CROSS = 3.0
    TEXT = 12.0  # over a part's name or value, or a label
    NEAR = 0.4  # beside a part's body
    BESIDE = 0.8  # one cell from another net's wire running the same way
    LIMIT = 400_000  # states expanded before a connection is given up

    def __init__(self, cols: int, rows: int, margin: int):
        self.lo = (margin, margin)
        self.hi = (cols - margin, rows - margin)
        self.blocked: set[Cell] = set()
        self.ends: set[Cell] = set()  # pin ends: a wire enters one only as the connection it routes
        self.soft: dict[Cell, float] = {}
        self.node: dict[Cell, str] = {}
        self.edge: dict[tuple[Cell, int], str] = {}  # (cell, 0): the edge east of it; (cell, 1): south

    @staticmethod
    def edge_key(a: Cell, b: Cell) -> tuple[Cell, int]:
        if a[1] == b[1]:
            return (min(a, b), 0)
        return ((a[0], min(a[1], b[1])), 1)

    def along(self, c: Cell, axis: int) -> set[str]:
        """Nets with a wire into cell c along an axis, 0 horizontal and 1 vertical."""
        if axis == 0:
            keys = (((c[0] - 1, c[1]), 0), (c, 0))
        else:
            keys = (((c[0], c[1] - 1), 1), (c, 1))
        return {self.edge[k] for k in keys if k in self.edge}

    def inside(self, c: Cell) -> bool:
        return self.lo[0] <= c[0] <= self.hi[0] and self.lo[1] <= c[1] <= self.hi[1]

    def free(self, c: Cell, net: str) -> bool:
        """Whether a wire of `net` may end or bend at c."""
        if c in self.blocked or not self.inside(c):
            return False
        if self.node.get(c, net) != net:
            return False
        return all(n == net for axis in (0, 1) for n in self.along(c, axis))

    def add_path(self, net: str, cells: list[Cell]) -> None:
        for a, b in zip(cells, cells[1:], strict=False):
            self.edge[self.edge_key(a, b)] = net
        for i, c in enumerate(cells):
            inner = 0 < i < len(cells) - 1
            if not inner or (cells[i - 1][0] != cells[i + 1][0] and cells[i - 1][1] != cells[i + 1][1]):
                self.node[c] = net

    def route(
        self, net: str, sources: dict[Cell, Cell | None], target: Cell, approach: Cell | None
    ) -> list[Cell] | None:
        """The cheapest path from any source to target, or None. `sources` maps a cell to the one cell
        a path may leave it by (a pin's exit), or None for any; the path enters target from `approach`
        when one is given."""
        import heapq

        tx, ty = target
        heap: list[tuple[float, int, float, Cell, int]] = []
        best: dict[tuple[Cell, int], float] = {}
        prev: dict[tuple[Cell, int], tuple[Cell, int] | None] = {}
        count = 0
        for s in sorted(sources):
            best[(s, 4)] = 0.0
            prev[(s, 4)] = None
            heapq.heappush(heap, (abs(s[0] - tx) + abs(s[1] - ty), count, 0.0, s, 4))
            count += 1
        expanded = 0
        while heap:
            _, _, g, c, d = heapq.heappop(heap)
            if c == target:
                path, state = [], (c, d)
                while state is not None:
                    path.append(state[0])
                    state = prev[state]
                return path[::-1]
            if g > best.get((c, d), math.inf):
                continue
            expanded += 1
            if expanded > self.LIMIT:
                return None
            # straight through another net's wire: no bend here
            crossing = d != 4 and any(n != net for axis in (0, 1) for n in self.along(c, axis))
            for nd, (sx, sy) in enumerate(STEPS):
                if d != 4 and nd == (d + 2) % 4:
                    continue
                if crossing and nd != d:
                    continue
                nb = (c[0] + sx, c[1] + sy)
                if d == 4 and sources.get(c) is not None and nb != sources[c]:
                    continue
                if not self.inside(nb):
                    continue
                if nb == target:
                    if approach is not None and c != approach:
                        continue
                elif nb in self.blocked or nb in self.ends:
                    continue
                if self.edge.get(self.edge_key(c, nb), net) != net:
                    continue
                if self.node.get(nb, net) != net:
                    continue
                axis = nd % 2
                if any(n != net for n in self.along(nb, axis)):
                    continue
                cross = any(n != net for n in self.along(nb, 1 - axis))
                if cross and nb == target:
                    continue
                step = 1.0 + self.soft.get(nb, 0.0)
                if d not in (4, nd):
                    step += self.BEND
                if cross:
                    step += self.CROSS
                for side in (-1, 1):  # another net's wire running alongside, one cell over
                    o = (nb[0] + side * (1 - axis), nb[1] + side * axis)
                    if any(n != net for n in self.along(o, axis)):
                        step += self.BESIDE
                ng = g + step
                if ng < best.get((nb, nd), math.inf):
                    best[(nb, nd)] = ng
                    prev[(nb, nd)] = (c, d)
                    heapq.heappush(heap, (ng + abs(nb[0] - tx) + abs(nb[1] - ty), count, ng, nb, nd))
                    count += 1
        return None

    def segments(
        self, net: str, keep: set[Cell], pins: set[Cell]
    ) -> tuple[list[tuple[Cell, Cell]], list[Cell]]:
        """The net's wires as straight segments that end at every bend, tee and cell in `keep` (pin ends,
        labels, power symbols), and the cells where three or more connections meet, a pin end counting
        as one."""
        adj: dict[Cell, set[Cell]] = {}
        for (c, axis), n in self.edge.items():
            if n != net:
                continue
            o = (c[0] + 1, c[1]) if axis == 0 else (c[0], c[1] + 1)
            adj.setdefault(c, set()).add(o)
            adj.setdefault(o, set()).add(c)

        def breaks(c: Cell) -> bool:
            nb = adj[c]
            if c in keep or len(nb) != 2:
                return True
            a, b = sorted(nb)
            return a[0] != b[0] and a[1] != b[1]

        segs: set[tuple[Cell, Cell]] = set()
        for c in adj:
            if not breaks(c):
                continue
            for o in adj[c]:
                dx, dy = o[0] - c[0], o[1] - c[1]
                e = o
                while not breaks(e):
                    e = (e[0] + dx, e[1] + dy)
                segs.add((min(c, e), max(c, e)))
        dots = sorted(c for c, nb in adj.items() if len(nb) + (1 if c in pins else 0) >= 3)
        return sorted(segs), dots


# ---------------------------------------------------------------- design

POWER_LIB = "power"


def _inside_polygon(x: float, y: float, poly: list[tuple[float, float]]) -> bool:
    """Even-odd point-in-polygon test."""
    inside = False
    for (x1, y1), (x2, y2) in zip(poly, poly[1:] + poly[:1], strict=True):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def _seg_dist(p: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    """Distance from point p to segment ab."""
    (px, py), (ax, ay), (bx, by) = p, a, b
    dx, dy = bx - ax, by - ay
    if dx == dy == 0:
        return math.hypot(px - ax, py - ay)
    u = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + u * dx), py - (ay + u * dy))


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
    zone_connect: int | None = (
        None  # how zones meet this part's pads: None inherit, 0 none, 1 thermal, 2 solid
    )
    models: list[dict] = field(default_factory=list)  # extra 3D bodies, see Design.model()
    sch_rot: int = (
        0  # the symbol's angle on the sheet, 0, 90, 180 or 270, counter-clockwise as KiCad shows it
    )

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
class PadBox:
    """A placed pad's copper on one layer, in board coordinates."""

    ref: str
    net: str  # pcb net name, "" for a pad with no net
    x1: float
    y1: float
    x2: float
    y2: float
    layer: str
    kind: str  # smd | thru_hole | np_thru_hole
    drill: float
    number: str = ""
    shape: str = ""  # the footprint's pad shape; a circle is measured as one, not as its box


@dataclass
class Design:
    name: str
    namespace: uuid.UUID
    parts: list[Part] = field(default_factory=list)
    power_nets: dict[str, str] = field(
        default_factory=dict
    )  # net name -> power symbol name (e.g. GND -> GND)
    flagged_nets: list[str] = field(default_factory=list)  # nets that get a PWR_FLAG
    # The schematic: False writes a stub and a net label on every pin; True draws wires between the
    # pins of each net round the parts (SchRouter) and keeps labels for the nets in sch_label_nets,
    # one-pin nets, and a pin no wire can reach. Wiring needs every pin on the 1.27 mm grid.
    sch_wires: bool = False
    sch_label_nets: tuple[str, ...] = ()
    sheet: str = "A3"  # paper: A4, A3, A2 or A1
    outline: tuple[float, float, float, float] = (100.0, 100.0, 125.0, 120.0)
    track_width: float = 0.25
    clearance: float = 0.2
    edge_clearance: float = 0.3
    # Rounded board corners: one radius for all four (0 a rectangle, half the short side a stadium),
    # or four, (top-left, top-right, bottom-right, bottom-left), to round one end and square the other.
    corner_radius: float | tuple[float, float, float, float] = 0.0
    thickness: float = 1.6  # the finished board, mm; any other value writes a stackup on two layers too
    footprint_dirs: dict[str, Path] = field(
        default_factory=dict
    )  # project footprint libraries: name -> .pretty
    via_size: float = 0.6
    via_drill: float = 0.3
    # Copper layers, an even count: F.Cu, In1.Cu .. In(n-2).Cu, B.Cu. Set it first: track, zone and
    # keepout check their layer against it.
    copper_layers: int = 2
    # Inner layers given whole to pours (a ground plane): no track goes there and the router never sees
    # them; its through vias still pass, and KiCad clears each other-net via when it fills the plane.
    plane_layers: tuple[str, ...] = ()
    # name -> {"width", "clearance", "via", "via_drill", "nets": [...]} for nets that need more copper
    net_classes: dict[str, dict] = field(default_factory=dict)
    title: str = ""
    segments: list[tuple[str, tuple[float, float], tuple[float, float], float, str]] = field(
        default_factory=list
    )
    vias: list[tuple[str, tuple[float, float], float, float]] = field(
        default_factory=list
    )  # net, at, size, drill
    texts: list[tuple[str, float, float, str, float, float]] = field(
        default_factory=list
    )  # text, x, y, layer, size, thickness
    rules: dict[str, float] = field(default_factory=dict)  # overrides for board.design_settings.rules
    zones: list[dict] = field(default_factory=list)  # copper pours, see zone()
    keepouts: list[dict] = field(default_factory=list)  # areas no track or via enters, see keepout()
    islands: list[list[str]] = field(default_factory=list)  # pads cut off from their pour, set by write()
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
            self._fpcache[lib_id] = load_footprint(lib_id, self.footprint_dirs)
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
        pcb_layer: str = "F.Cu",
        zone_connect: int | None = None,
        sch_rot: int = 0,
    ) -> Part:
        if sch_rot not in (0, 90, 180, 270):
            raise ValueError(f"{ref}: sch_rot must be 0, 90, 180 or 270, not {sch_rot!r}")
        sym = self.symbol(lib_id)
        fpo = self.fp(footprint) if footprint else None
        for pin_no in nets:
            sym.pin(pin_no)  # raises on a typo
        if fpo is not None:
            pad_numbers = {p.number for p in fpo.pads}
            for pin_no in nets:
                if pin_no not in pad_numbers:
                    raise KeyError(f"{ref}: pin {pin_no} has no pad in {footprint}")
        if pcb_layer not in ("F.Cu", "B.Cu"):
            raise ValueError(f"{ref}: pcb_layer must be F.Cu or B.Cu, not {pcb_layer!r}")
        if zone_connect not in (None, 0, 1, 2):
            raise ValueError(f"{ref}: zone_connect must be None, 0, 1 or 2, not {zone_connect!r}")
        part = Part(
            ref, sym, value, fpo, sch_at, pcb_at, pcb_rot, pcb_layer, dict(nets), descr, datasheet, stub
        )
        part.zone_connect = zone_connect
        part.sch_rot = sch_rot
        self.parts.append(part)
        return part

    def model(
        self,
        ref: str,
        path: str,
        offset: tuple[float, float, float] = (0.0, 0.0, 0.0),
        scale: tuple[float, float, float] = (1.0, 1.0, 1.0),
        rotate: tuple[float, float, float] = (0.0, 0.0, 0.0),
        replace: bool = False,
    ) -> None:
        """Attach a 3D body to a part's footprint, for the renders and the STEP export.

        `path` is what KiCad resolves: `${KIPRJMOD}/models/x.wrl` for a file kept with the project,
        `${KICAD10_3DMODEL_DIR}/...` for a library body. `replace` drops the library's own model.
        A `.wrl` body is in 0.1 inch units (KiCad scales VRML by 2.54); `tools/wrlgen.py` writes them.
        """
        part = next((p for p in self.parts if p.ref == ref), None)
        if part is None:
            raise KeyError(f"{ref}: no such part")
        part.models.append(
            {
                "path": path,
                "offset": tuple(offset),
                "scale": tuple(scale),
                "rotate": tuple(rotate),
                "replace": replace,
            }
        )

    # ---- outline

    def _corner_radii(self) -> tuple[float, float, float, float]:
        """The four corner radii (top-left, top-right, bottom-right, bottom-left), checked.

        One number rounds every corner alike: at most half the short side (a stadium). Four give
        each corner its own: none negative, and the two on any side together no longer than it.
        """
        x1, y1, x2, y2 = self.outline
        w, h = x2 - x1, y2 - y1
        r = self.corner_radius
        if isinstance(r, (int, float)):
            if r < 0 or r > min(w, h) / 2 + 1e-9:
                raise ValueError(f"corner_radius {r} must be between 0 and half the board's short side")
            return (float(r),) * 4
        radii = tuple(float(v) for v in r)
        if len(radii) != 4:
            raise ValueError(
                f"corner_radius takes one radius or four (top-left, top-right, bottom-right, bottom-left), not {r!r}"
            )
        tl, tr, br, bl = radii
        sides = (("top", tl + tr, w), ("right", tr + br, h), ("bottom", br + bl, w), ("left", bl + tl, h))
        if min(radii) < 0 or any(both > side + 1e-9 for _, both, side in sides):
            long = [name for name, both, side in sides if both > side + 1e-9]
            raise ValueError(
                f"corner_radius {r!r}: radii must not be negative, and the two on a side must fit along it"
                + (f" (too long: {', '.join(long)})" if long else "")
            )
        return radii  # type: ignore[return-value]

    def copper_names(self) -> list[str]:
        """The copper layers, top to bottom."""
        n = self.copper_layers
        if n < 2 or n > 32 or n % 2:
            raise ValueError(f"copper_layers must be an even count from 2 to 32, not {n!r}")
        return ["F.Cu", *[f"In{i}.Cu" for i in range(1, n - 1)], "B.Cu"]

    def routing_layers(self) -> list[str]:
        """The copper layers tracks may use, top to bottom: every layer but the plane layers."""
        names = self.copper_names()
        for layer in self.plane_layers:
            if layer not in names[1:-1]:
                raise ValueError(f"plane layer {layer!r} must be an inner layer of this board: {names[1:-1]}")
        return [layer for layer in names if layer not in self.plane_layers]

    def _check_layer(self, what: str, layer: str, routing: bool = False) -> None:
        names = self.routing_layers() if routing else self.copper_names()
        if layer not in names:
            raise ValueError(f"{what} layer must be one of {', '.join(names)}, not {layer!r}")

    def outline_polygon(self, inset: float = 0.0, n: int = 8) -> list[tuple[float, float]]:
        """The board outline shrunk by `inset`, clockwise; a rounded corner becomes `n` segments.

        A stadium (radius half the short side) has no straight ends: the arcs meet, and the point
        they share is listed once. A square corner is one point.
        """
        x1, y1, x2, y2 = self.outline
        x1, y1, x2, y2 = x1 + inset, y1 + inset, x2 - inset, y2 - inset
        tl, tr, br, bl = (max(0.0, r - inset) for r in self._corner_radii())
        corners = [  # clockwise from the top right, as (centre, start angle, radius)
            ((x2 - tr, y1 + tr), -90.0, tr),
            ((x2 - br, y2 - br), 0.0, br),
            ((x1 + bl, y2 - bl), 90.0, bl),
            ((x1 + tl, y1 + tl), 180.0, tl),
        ]
        pts: list[tuple[float, float]] = []
        for (cx, cy), a0, r in corners:
            for i in range(n + 1 if r > 0 else 1):
                a = math.radians(a0 + 90.0 * i / n)
                pt = (round(cx + r * math.cos(a), 4), round(cy + r * math.sin(a), 4)) if r > 0 else (cx, cy)
                if not pts or math.hypot(pt[0] - pts[-1][0], pt[1] - pts[-1][1]) > 1e-6:
                    pts.append(pt)
        if len(pts) > 1 and math.hypot(pts[0][0] - pts[-1][0], pts[0][1] - pts[-1][1]) <= 1e-6:
            pts.pop()
        return pts

    def inside_outline(self, x: float, y: float, margin: float = 0.0) -> bool:
        """Is (x, y) at least `margin` inside the board edge, rounded corners included?"""
        x1, y1, x2, y2 = self.outline
        if not (x1 + margin <= x <= x2 - margin and y1 + margin <= y <= y2 - margin):
            return False
        tl, tr, br, bl = self._corner_radii()
        for r, left, top in ((tl, True, True), (tr, False, True), (br, False, False), (bl, True, False)):
            if r - margin <= 0:
                continue  # a square corner: the inset rectangle above already decided
            cx = x1 + r if left else x2 - r
            cy = y1 + r if top else y2 - r
            in_corner = (x < cx if left else x > cx) and (y < cy if top else y > cy)
            if in_corner and math.hypot(x - cx, y - cy) > r - margin:
                return False
        return True

    def _edge_cuts(self, ns: uuid.UUID) -> list[Node]:
        """The Edge.Cuts graphics: one rectangle, or lines and an arc per round corner.

        A stadium drops the two lines that would have no length; a square corner has no arc.
        """
        x1, y1, x2, y2 = self.outline
        tl, tr, br, bl = self._corner_radii()

        def stroke() -> Node:
            return ["stroke", ["width", "0.1"], ["type", "default"]]

        if max(tl, tr, br, bl) <= 0:
            return [
                [
                    "gr_rect",
                    ["start", fmt(x1), fmt(y1)],
                    ["end", fmt(x2), fmt(y2)],
                    stroke(),
                    ["fill", "no"],
                    ["layer", Q("Edge.Cuts")],
                    ["uuid", uid(ns, "edge")],
                ]
            ]

        def k(r: float) -> float:  # an arc's midpoint sits this far in from both edges
            return r - r / math.sqrt(2.0)

        lines = [
            ((x1 + tl, y1), (x2 - tr, y1)),
            ((x2, y1 + tr), (x2, y2 - br)),
            ((x2 - br, y2), (x1 + bl, y2)),
            ((x1, y2 - bl), (x1, y1 + tl)),
        ]
        arcs = [  # numbered as before per-corner radii, so a uniform radius keeps its uuids
            (tr, (x2 - tr, y1), (x2 - k(tr), y1 + k(tr)), (x2, y1 + tr)),
            (br, (x2, y2 - br), (x2 - k(br), y2 - k(br)), (x2 - br, y2)),
            (bl, (x1 + bl, y2), (x1 + k(bl), y2 - k(bl)), (x1, y2 - bl)),
            (tl, (x1, y1 + tl), (x1 + k(tl), y1 + k(tl)), (x1 + tl, y1)),
        ]
        out: list[Node] = []
        for i, ((sx, sy), (ex, ey)) in enumerate(lines):
            if math.hypot(ex - sx, ey - sy) < 1e-6:
                continue  # a stadium's end: the two arcs meet here
            out.append(
                [
                    "gr_line",
                    ["start", fmt(sx), fmt(sy)],
                    ["end", fmt(ex), fmt(ey)],
                    stroke(),
                    ["layer", Q("Edge.Cuts")],
                    ["uuid", uid(ns, f"edge/line/{i}")],
                ]
            )
        for i, (r, (sx, sy), (mx, my), (ex, ey)) in enumerate(arcs):
            if r <= 0:
                continue  # a square corner: the two lines meet here
            out.append(
                [
                    "gr_arc",
                    ["start", fmt(sx), fmt(sy)],
                    ["mid", fmt(mx), fmt(my)],
                    ["end", fmt(ex), fmt(ey)],
                    stroke(),
                    ["layer", Q("Edge.Cuts")],
                    ["uuid", uid(ns, f"edge/arc/{i}")],
                ]
            )
        return out

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

    def text(
        self,
        text: str,
        x: float,
        y: float,
        layer: str = "F.SilkS",
        size: float = 0.8,
        thickness: float = 0.12,
    ) -> None:
        """Free text on the board, e.g. a contact label on the silkscreen. Centered on (x, y)."""
        self.texts.append((text, x, y, layer, size, thickness))

    def track(
        self, net: str, points: list[tuple[float, float]], layer: str = "F.Cu", width: float | None = None
    ) -> None:
        """Pre-route a net by hand: a polyline on one layer. The router keeps it and routes around it."""
        self._check_layer("track", layer, routing=True)
        pcb_net = self.pcb_net_name(net)
        w = self.class_of(pcb_net)["width"] if width is None else width
        for a, b in zip(points, points[1:], strict=False):
            self.segments.append((pcb_net, (float(a[0]), float(a[1])), (float(b[0]), float(b[1])), w, layer))

    def via(
        self, net: str, x: float, y: float, size: float | None = None, drill: float | None = None
    ) -> None:
        """Place a via by hand, e.g. a ground stitch; the router keeps it."""
        pcb_net = self.pcb_net_name(net)
        spec = self.class_of(pcb_net)
        self.vias.append(
            (
                pcb_net,
                (float(x), float(y)),
                spec["via"] if size is None else size,
                spec["via_drill"] if drill is None else drill,
            )
        )

    def pad_boxes(self) -> list[PadBox]:
        """Every pad as placed on the board; a through-hole pad appears once per copper layer."""
        boxes: list[PadBox] = []
        open_nets = self.unconnected_nets()
        for part in self.parts:
            if not (part.on_board and part.footprint and part.pcb_at):
                continue
            px, py = part.pcb_at
            back = part.pcb_layer == "B.Cu"
            th = math.radians(part.pcb_rot)
            for pad in part.footprint.pads:
                if not any(layer.endswith(".Cu") for layer in pad.layers):
                    continue  # a paste-only aperture (an exposed pad's paste windows): no copper
                fx, fy = pad.x, -pad.y if back else pad.y
                x = px + fx * math.cos(th) + fy * math.sin(th)
                y = py - fx * math.sin(th) + fy * math.cos(th)
                w, h = (pad.h, pad.w) if round((pad.angle + part.pcb_rot) % 180) == 90 else (pad.w, pad.h)
                net = part.nets.get(pad.number)
                name = self.pcb_net_name(net) if net else open_nets.get((part.ref, pad.number), "")
                layers = (
                    self.copper_names() if pad.kind in ("thru_hole", "np_thru_hole") else [part.pcb_layer]
                )
                for layer in layers:
                    boxes.append(
                        PadBox(
                            part.ref,
                            name,
                            x - w / 2,
                            y - h / 2,
                            x + w / 2,
                            y + h / 2,
                            layer,
                            pad.kind,
                            pad.drill,
                            pad.number,
                            "circle"
                            if pad.shape == "circle" or (pad.shape == "oval" and abs(pad.w - pad.h) < 1e-6)
                            else pad.shape,
                        )
                    )
        return boxes

    def stitch_pads(self, net: str, gap: float = 0.1) -> int:
        """A via of `net` beside every surface pad of `net` on a poured layer, where one fits.

        The router leaves a poured net's pads alone and other nets' tracks can wall a pad off from the
        pour; a via of its own, placed before routing, keeps each pad on the pour. Tries the four sides
        of the pad, `gap` from its edge, and keeps the design clearance from everything else.
        Returns the number of vias placed.
        """
        pcb_net = self.pcb_net_name(net)
        poured = {layer for z in self.zones if z["net"] == net for layer in z["layers"]}
        spec = self.class_of(pcb_net)
        r, drill = spec["via"] / 2, spec["via_drill"]
        boxes = self.pad_boxes()
        placed = 0
        for pad in boxes:
            if pad.net != pcb_net or pad.layer not in poured or pad.kind != "smd":
                continue
            cx, cy = (pad.x1 + pad.x2) / 2, (pad.y1 + pad.y2) / 2
            candidates = [
                (cx, pad.y2 + gap + r),
                (cx, pad.y1 - gap - r),
                (pad.x2 + gap + r, cy),
                (pad.x1 - gap - r, cy),
            ]
            for vx, vy in candidates:
                if self._via_fits(vx, vy, r, drill, pcb_net, boxes):
                    self.via(net, round(vx, 3), round(vy, 3))
                    placed += 1
                    break
        return placed

    def reserve_vias(self, pads: list[str], gaps: tuple[float, ...] = (0.1, 0.3, 0.5, 0.8)) -> int:
        """A fixed via beside each named pad ("REF.N") of a poured net, for the next routing pass.

        Call it with only the hand-routed copper on the design: the routed tracks are about to be
        redone around the new vias. Returns how many vias were placed.
        """
        boxes = self.pad_boxes()
        placed = 0
        for name in pads:
            ref, _, number = name.partition(".")
            pad = next((b for b in boxes if b.ref == ref and b.number == number and b.kind == "smd"), None)
            if pad is None or pad.net == "":
                continue
            spec = self.class_of(pad.net)
            r, drill = spec["via"] / 2, spec["via_drill"]
            cx, cy = (pad.x1 + pad.x2) / 2, (pad.y1 + pad.y2) / 2
            spots = [
                (vx, vy)
                for gap in gaps
                for vx, vy in (
                    (cx, pad.y2 + gap + r),
                    (cx, pad.y1 - gap - r),
                    (pad.x2 + gap + r, cy),
                    (pad.x1 - gap - r, cy),
                )
            ]
            for vx, vy in spots:
                if self._via_fits(
                    vx, vy, r, drill, pad.net, boxes
                ):  # the fixed tracks count, the routed ones are gone
                    self.vias.append((pad.net, (round(vx, 3), round(vy, 3)), spec["via"], drill))
                    placed += 1
                    break
        return placed

    def _via_fits(
        self,
        vx: float,
        vy: float,
        r: float,
        drill: float,
        pcb_net: str,
        boxes: list[PadBox],
        tracks: bool = True,
    ) -> bool:
        """Clearance check for a via at (vx, vy): board edge, other nets' pads, holes, vias and tracks.

        A non-plated hole is board edge to the DRC: the via's copper keeps `edge_clearance` from the
        hole's outline (its box, which covers an oval peg), whatever the net.
        """
        return not self._via_problems(vx, vy, r, drill, pcb_net, boxes, tracks, first=True)

    def _via_problems(
        self,
        vx: float,
        vy: float,
        r: float,
        drill: float,
        pcb_net: str,
        boxes: list[PadBox],
        tracks: bool = True,
        first: bool = False,
        skip_via: int | None = None,
        same_net_vias: bool = True,
    ) -> list[str]:
        """What stops a via at (vx, vy), one line each; empty when it fits. A via passes every copper
        layer, so a pad or track of another net on any layer blocks it (M41). `first` stops at the
        first problem; `skip_via` leaves out the design's own via of that index; `same_net_vias=False`
        holds a via of the same net only to the hole-to-hole rule, as the DRC does (the placers keep
        their vias apart)."""
        out: list[str] = []
        if not self.inside_outline(vx, vy, self.edge_clearance + r):
            out.append(f"closer than {fmt(self.edge_clearance)} mm to the board edge")
            if first:
                return out
        name = self.keepout_at(vx, vy, r)
        if name:
            out.append(f"in keepout {name!r}")
            if first:
                return out
        c = self.clearance
        for pad in boxes:
            dx = max(pad.x1 - vx, 0.0, vx - pad.x2)
            dy = max(pad.y1 - vy, 0.0, vy - pad.y2)
            gap = math.hypot(dx, dy)
            if pad.shape == "circle":
                gap = max(
                    0.0,
                    math.hypot(vx - (pad.x1 + pad.x2) / 2, vy - (pad.y1 + pad.y2) / 2)
                    - (pad.x2 - pad.x1) / 2,
                )
            if pad.kind == "np_thru_hole":
                if gap < max(r + self.edge_clearance, drill / 2 + 0.25):
                    out.append(f"too near {pad.ref}'s non-plated hole")
            elif (
                pad.drill
                and math.hypot(vx - (pad.x1 + pad.x2) / 2, vy - (pad.y1 + pad.y2) / 2)
                < drill / 2 + pad.drill / 2 + 0.25
            ):
                out.append(f"hole to hole with {pad.ref}.{pad.number}")
            elif pad.net != pcb_net and gap < r + c:
                out.append(f"on {pad.ref}.{pad.number} ({pad.net or 'no net'}, {pad.layer})")
            if first and out:
                return out
        for i, (net, (ox, oy), size, odrill) in enumerate(self.vias):
            if i == skip_via:
                continue
            copper = r + size / 2 + c if (net != pcb_net or same_net_vias) else 0.0
            if math.hypot(ox - vx, oy - vy) < max(copper, drill / 2 + odrill / 2 + 0.25):
                out.append(f"on the {net} via at ({fmt(ox)}, {fmt(oy)})")
                if first:
                    return out
        for n, (sx, sy), (ex, ey), w, layer in self.segments:
            if tracks and n != pcb_net and _seg_dist((vx, vy), (sx, sy), (ex, ey)) < r + w / 2 + c:
                out.append(f"on a {n} track ({layer})")
                if first:
                    return out
        return list(dict.fromkeys(out))  # a through pad appears once per layer; say it once

    def check_vias(self) -> list[str]:
        """Every via on the design that breaks a clearance, a keepout or the board edge, with what it
        hits: the hand-placed ones are checked before routing, where the DRC would find them only
        after (M40, M41)."""
        boxes = self.pad_boxes()
        out = []
        for i, (net, (x, y), size, drill) in enumerate(self.vias):
            for problem in self._via_problems(
                x, y, size / 2, drill, net, boxes, skip_via=i, same_net_vias=False
            ):
                out.append(f"{net} via at ({fmt(x)}, {fmt(y)}): {problem}")
        return out

    def keepout(
        self, polygon: list[tuple[float, float]], layers: tuple[str, ...] = ("F.Cu",), name: str = ""
    ) -> None:
        """An area no track or via may enter on `layers` (a metal shell sitting on the board).

        Pads and pours may: a ground pour under a grounded shell is what the area is for. KiCad gets a
        rule area, the router a Specctra keepout, and the generator's own via checks honour it.
        """
        for layer in layers:
            self._check_layer("keepout", layer)
        if len(polygon) < 3:
            raise ValueError("keepout needs a polygon of at least 3 points")
        self.keepouts.append(
            {
                "polygon": [(float(x), float(y)) for x, y in polygon],
                "layers": tuple(layers),
                "name": name or f"keepout{len(self.keepouts) + 1}",
            }
        )

    def in_keepout(self, x: float, y: float, r: float) -> bool:
        """True when a via of radius `r` at (x, y) would touch any keepout. A via spans every layer,
        so a keepout on either face refuses it. Every path that places a via asks this (P17)."""
        return self.keepout_at(x, y, r) is not None

    def keepout_at(self, x: float, y: float, r: float) -> str | None:
        """The name of the first keepout a via of radius `r` at (x, y) would touch, or None."""
        for k in self.keepouts:
            poly = k["polygon"]
            edges = zip(poly, poly[1:] + poly[:1], strict=True)
            if _inside_polygon(x, y, poly) or min(_seg_dist((x, y), a, b) for a, b in edges) < r:
                return k["name"]
        return None

    @staticmethod
    def circle(cx: float, cy: float, r: float, n: int = 24) -> list[tuple[float, float]]:
        """A circle as an `n`-sided polygon, for keepouts and zones."""
        return [
            (
                round(cx + r * math.cos(2 * math.pi * i / n), 4),
                round(cy + r * math.sin(2 * math.pi * i / n), 4),
            )
            for i in range(n)
        ]

    def zone(
        self,
        net: str,
        layers: tuple[str, ...] = ("B.Cu",),
        polygon: list[tuple[float, float]] | None = None,
        clearance: float | None = None,
        min_thickness: float = 0.25,
        connect: str = "thermal",
        thermal_gap: float = 0.25,
        thermal_bridge: float = 0.4,
    ) -> None:
        """A copper pour of `net` on `layers`, the whole board unless a polygon is given.

        KiCad fills it when the design is written (`write`); the router sees it as a plane, so the
        net's pads need no tracks on those layers. `connect` is "thermal" (reliefs) or "solid".
        """
        for layer in layers:
            self._check_layer("zone", layer)
        if connect not in ("thermal", "solid"):
            raise ValueError(f"zone connect must be thermal or solid, not {connect!r}")
        if polygon is None:
            polygon = self.outline_polygon(self.edge_clearance)
        self.zones.append(
            {
                "net": net,
                "layers": tuple(layers),
                "polygon": [tuple(p) for p in polygon],
                "clearance": self.clearance if clearance is None else clearance,
                "min_thickness": min_thickness,
                "connect": connect,
                "thermal_gap": thermal_gap,
                "thermal_bridge": thermal_bridge,
            }
        )

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
        vx, vy = rot_vec(pin.x, -pin.y, part.sch_rot)
        x = part.sch_at[0] + vx
        y = part.sch_at[1] + vy
        a = math.radians(pin.angle)
        dx, dy = rot_vec(-math.cos(a), math.sin(a), part.sch_rot)  # outward, schematic y down
        return x, y, round(dx), round(dy)

    @staticmethod
    def _sheet_box(sym: Symbol, at: tuple[float, float], rot: int) -> tuple[float, float, float, float]:
        """A symbol's body on the sheet (y down) at a position and angle."""
        x0, y0, x1, y1 = symbol_box(sym)
        pts = [rot_vec(x, -y, rot) for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
        xs = [at[0] + p[0] for p in pts]
        ys = [at[1] + p[1] for p in pts]
        return min(xs), min(ys), max(xs), max(ys)

    def _field_spots(
        self,
        sym: Symbol,
        at: tuple[float, float],
        rot: int,
        texts: list[str],
        sides: set[tuple[int, int]],
        fields: tuple[str, ...] = ("Reference", "Value"),
    ) -> list[tuple[float, float]]:
        """Where each of `fields` (showing `texts`) starts, its left end at mid-height, so it reads level
        beside the body: the library's own spot for a symbol at 0 whose field is level, otherwise a side
        no pin leaves from, right, left, above, below in that order. `sides` holds the pins' outward
        directions."""
        x0, y0, x1, y1 = self._sheet_box(sym, at, rot)
        widths = [len(t) * TEXT_ADVANCE for t in texts]
        lib = {atoms(p)[0]: p for p in children(sym.node, "property")}
        spots: list[tuple[float, float]] = []
        names = fields
        if rot == 0 and all(n in lib and len(atoms(child(lib[n], "at"))) > 2 for n in names):
            for name, w in zip(names, widths, strict=True):
                fx, fy, fa = (num(v) for v in atoms(child(lib[name], "at"))[:3])
                if fa != 0:
                    break
                eff = child(lib[name], "effects")
                just = atoms(child(eff, "justify")) if eff is not None and child(eff, "justify") else []
                sx = at[0] + fx - (0 if "left" in just else w if "right" in just else w / 2)
                spots.append((round(sx, 3), round(at[1] - fy, 3)))
            if len(spots) == len(texts):
                return spots
            spots = []
        cy, cx = (y0 + y1) / 2, (x0 + x1) / 2
        rows = [cy - 1.27 * (len(texts) - 1) + 2.54 * i for i in range(len(texts))]
        if (1, 0) not in sides:
            return [(round(x1 + 0.635, 3), round(r, 3)) for r in rows]
        if (-1, 0) not in sides:
            return [(round(x0 - 0.635 - w, 3), round(r, 3)) for r, w in zip(rows, widths, strict=True)]
        if (0, -1) not in sides:
            top = y0 - 1.27 - 2.54 * (len(texts) - 1)
            return [(round(cx - w / 2, 3), round(top + 2.54 * i, 3)) for i, w in enumerate(widths)]
        if (0, 1) not in sides:
            return [(round(cx - w / 2, 3), round(y1 + 1.905 + 2.54 * i, 3)) for i, w in enumerate(widths)]
        return [(round(x0, 3), round(y0 - 1.27, 3)), (round(x0, 3), round(y1 + 1.905, 3))][: len(texts)]

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

        for part in self.parts if not self.sch_wires else ():
            places = None
            if part.sch_rot:
                sides = {self._pin_point(part, p)[2:] for p in part.symbol.pins if not p.hidden and p.number}
                spots = self._field_spots(
                    part.symbol, part.sch_at, part.sch_rot, [part.ref, part.value], sides
                )
                places = dict(zip(("Reference", "Value"), spots, strict=True))
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
                    rot=part.sch_rot,
                    places=places,
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
        if self.sch_wires:
            self._wired(root, lib_symbols, body)
        for i, net in enumerate(self.flagged_nets if not self.sch_wires else ()):
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
            ["paper", Q(self.sheet)],
        ]
        if self.title:
            sch.append(["title_block", ["title", Q(self.title)], ["company", Q("EE Workcenter")]])
        sch.append(["lib_symbols", *lib_symbols.values()])
        sch.extend(body)
        sch.append(["sheet_instances", ["path", Q("/"), ["page", Q("1")]]])
        sch.append(["embedded_fonts", "no"])
        return dumps(sch) + "\n"

    def _wired(self, root: Q, lib_symbols: dict[str, Node], body: list[Node]) -> None:
        """The parts, power symbols, labels and wires of a wired schematic (`sch_wires`).

        Every pin gets one cell of wire out of its end (its exit). A power pin's exit takes a power
        symbol pointing away from the part, and the exits of neighbouring pins of one power net on one
        side of a part share a wire and a symbol. A net in `sch_label_nets` or with one pin gets a label
        on each exit. Every other net is wired, shortest first, by growing a tree from one pin to the
        nearest pin left; a pin no path reaches gets a label, and so does the tree it was cut from.
        """
        ns = self.namespace
        g = SCH_GRID
        if self.sheet not in SHEETS:
            raise ValueError(f"sheet must be one of {', '.join(SHEETS)}, not {self.sheet!r}")
        w, h = SHEETS[self.sheet]
        r = SchRouter(int(w / g), int(h / g), round(12.7 / g))
        for i in range(int((w - 122) / g), int(w / g) + 1):  # the title block, bottom right
            for j in range(int((h - 46) / g), int(h / g) + 1):
                r.blocked.add((i, j))

        def cell(x: float, y: float, what: str) -> Cell:
            i, j = round(x / g), round(y / g)
            if abs(i * g - x) > 1e-3 or abs(j * g - y) > 1e-3:
                raise ValueError(f"{what} at {x:.3f}, {y:.3f} is off the {g} mm grid; move the part")
            return (i, j)

        def cells_in(box: tuple[float, float, float, float]) -> list[Cell]:
            x0, y0, x1, y1 = box
            return [
                (i, j)
                for i in range(math.ceil(x0 / g - 1e-6), math.floor(x1 / g + 1e-6) + 1)
                for j in range(math.ceil(y0 / g - 1e-6), math.floor(y1 / g + 1e-6) + 1)
            ]

        def area(box: tuple[float, float, float, float], soft: float | None = None) -> None:
            for c in cells_in(box):
                if soft is None:
                    r.blocked.add(c)
                else:
                    r.soft[c] = max(r.soft.get(c, 0.0), soft)

        def text_area(x: float, y: float, text: str) -> None:
            area((x, y - 0.635, x + len(text) * TEXT_ADVANCE, y + 0.635), SchRouter.TEXT)

        anchors: set[Cell] = set()  # power symbols and labels: wire ends that are not pins
        names: set[Cell] = set()  # the labels that name a wired net, on a run of its wire
        labelled: dict[str, list[Cell]] = {}

        def label(net: str, p: Cell, e: Cell, key: str) -> None:
            r.add_path(net, [p, e])
            dx, dy = e[0] - p[0], e[1] - p[1]
            body.append(self._label(net, e[0] * g, e[1] * g, dx, dy, uid(ns, key)))
            anchors.add(e)
            labelled.setdefault(net, []).append(e)
            length = len(net) * TEXT_ADVANCE
            x, y = e[0] * g, e[1] * g
            if dx:  # level text above the wire's line
                area((min(x, x + dx * length), y - 1.27, max(x, x + dx * length), y), SchRouter.TEXT)
            else:
                area((x - 1.27, min(y, y + dy * length), x, max(y, y + dy * length)), SchRouter.TEXT)

        power_count = 0

        def power(net: str, e: Cell, d: tuple[int, int], key: str) -> None:
            """A power symbol on the wire end e, pointing along d; moved out along d, the wire with it,
            while its drawing would land on something already on the sheet."""
            nonlocal power_count
            power_count += 1
            sym = self.symbol(f"{POWER_LIB}:{self.power_nets[net]}")
            lib_symbols.setdefault(sym.lib_id, sym.node)
            y0, y1 = symbol_box(sym)[1::2]
            natural = (0, 1) if y0 + y1 < 0 else (0, -1)  # where the symbol's drawing hangs from its pin
            rot = next(t for t in (0, 90, 180, 270) if tuple(round(v) for v in rot_vec(*natural, t)) == d)
            a = e
            a, run = e, [e]
            for k in range(5):
                cand = [(e[0] + d[0] * i, e[1] + d[1] * i) for i in range(k + 1)]
                if not all(r.free(c, net) and (c == e or c not in r.ends) for c in cand):
                    break  # the wire out would touch something: no further
                drawn = cells_in(self._sheet_box(sym, (cand[-1][0] * g, cand[-1][1] * g), rot))
                if all(
                    c not in r.blocked and c not in r.node and not r.along(c, 0) and not r.along(c, 1)
                    for c in drawn
                    if c != cand[-1]
                ):
                    a, run = cand[-1], cand
                    break
            # with no clear spot the symbol stays on e and only its drawing overlaps: a symbol joins
            # the sheet at its pin, so the overlap is untidy but never a connection
            if len(run) > 1:
                r.add_path(net, run)
            at = (a[0] * g, a[1] * g)
            area(self._sheet_box(sym, at, rot))
            r.blocked.discard(a)
            (spot,) = self._field_spots(sym, at, rot, [net], {(-d[0], -d[1])}, ("Value",))
            text_area(*spot, net)
            anchors.add(a)
            labelled.setdefault(net, []).append(a)  # power symbols of one name join, as labels do
            body.append(
                self._symbol_instance(
                    f"#PWR{power_count:02d}",
                    sym,
                    net,
                    "",
                    at,
                    root,
                    key,
                    in_bom=False,
                    rot=rot,
                    places={"Value": spot},
                    hidden=("Reference",),
                )
            )

        # parts and their pins
        terminals: dict[str, list[tuple[Cell, Cell, str, str]]] = {}  # net -> (end, exit, ref, "REF pin N")
        pin_ends: set[Cell] = set()
        for part in self.parts:
            sym = part.symbol
            box = self._sheet_box(sym, part.sch_at, part.sch_rot)
            area((box[0] - g, box[1] - g, box[2] + g, box[3] + g), SchRouter.NEAR)
            area(box)
            sides: set[tuple[int, int]] = set()
            for pin in sym.pins:
                if pin.hidden or not pin.number:
                    continue
                x, y, dx, dy = self._pin_point(part, pin)
                sides.add((dx, dy))
                what = f"{part.ref} pin {pin.number}"
                p = cell(x, y, what)
                for k in range(1, round(pin.length / g)):  # the pin's own line, from its end to the body
                    r.blocked.add((p[0] - dx * k, p[1] - dy * k))
                net = part.nets.get(pin.number, f"~nc/{part.ref}/{pin.number}")
                if r.node.get(p, net) != net:
                    raise ValueError(f"{what}: its end touches another net's pin; move the part")
                r.node[p] = net
                r.ends.add(p)
                if pin.number not in part.nets:
                    body.append(
                        [
                            "no_connect",
                            ["at", fmt(x), fmt(y)],
                            ["uuid", uid(ns, f"nc/{part.ref}/{pin.number}")],
                        ]
                    )
                    continue
                pin_ends.add(p)
                t = terminals.setdefault(net, [])
                if all(o[0] != p for o in t):  # stacked pins of one net are one connection
                    t.append((p, (p[0] + dx, p[1] + dy), part.ref, what))
            texts = [part.ref, part.value]
            spots = self._field_spots(sym, part.sch_at, part.sch_rot, texts, sides)
            for (sx, sy), text in zip(spots, texts, strict=True):
                text_area(sx, sy, text)
            body.append(
                self._symbol_instance(
                    part.ref,
                    sym,
                    part.value,
                    part.footprint.lib_id if part.footprint else "",
                    part.sch_at,
                    root,
                    f"symbol/{part.ref}",
                    part.descr,
                    part.datasheet,
                    in_bom=part.in_bom,
                    rot=part.sch_rot,
                    places=dict(zip(("Reference", "Value"), spots, strict=True)),
                )
            )
        for net, terms in sorted(terminals.items()):
            for _, e, _, what in terms:
                if not r.free(e, net) or e in r.ends:
                    raise ValueError(f"{what}: the cell beside its end is taken; move the part")
                r.node[e] = net

        # power flags, top left, as the stub-and-label schematic has them
        flag_sym = self.symbol(f"{POWER_LIB}:PWR_FLAG")
        for i, net in enumerate(self.flagged_nets):
            fx, fy = 20.32 + i * 12.7, 20.32
            f, a = cell(fx, fy, f"PWR_FLAG of {net}"), cell(fx, fy + 2.54, f"PWR_FLAG of {net}")
            area(self._sheet_box(flag_sym, (fx, fy), 0))
            r.blocked.discard(f)
            body.append(
                self._symbol_instance(
                    f"#FLG{i + 1:02d}",
                    flag_sym,
                    "PWR_FLAG",
                    "",
                    (fx, fy),
                    root,
                    f"flag/{net}",
                    hidden_fields=True,
                    in_bom=False,
                )
            )
            r.add_path(net, [f, (f[0], f[1] + 1), a])
            power(net, a, (0, 1), f"flagpwr/{net}")

        # power pins: a symbol on each run of neighbouring exits
        for net in sorted(n for n in terminals if n in self.power_nets):
            sides_of: dict[tuple[str, tuple[int, int]], list[tuple[Cell, Cell]]] = {}
            for p, e, ref, _ in terminals.pop(net):
                sides_of.setdefault((ref, (e[0] - p[0], e[1] - p[1])), []).append((p, e))
            for (ref, d), items in sorted(sides_of.items()):
                along = 1 if d[0] else 0  # the coordinate that runs along the side
                items.sort(key=lambda t: (t[1][along], t[1][1 - along]))
                runs = [[items[0]]]
                for p, e in items[1:]:
                    q = runs[-1][-1][1]
                    gap = e[along] - q[along]
                    between = [
                        (q[0] + (k if along == 0 else 0), q[1] + (k if along == 1 else 0))
                        for k in range(1, gap)
                    ]
                    if e[1 - along] == q[1 - along] and gap <= 2 and all(r.free(c, net) for c in between):
                        runs[-1].append((p, e))
                    else:
                        runs.append([(p, e)])
                for run in runs:
                    for p, e in run:
                        r.add_path(net, [p, e])
                    first, last = run[0][1], run[-1][1]
                    if first != last:
                        r.add_path(
                            net,
                            [
                                (first[0] + (k if along == 0 else 0), first[1] + (k if along == 1 else 0))
                                for k in range(last[along] - first[along] + 1)
                            ],
                        )
                    power(net, first, d, f"pwr/{ref}/{first[0]}/{first[1]}")

        # labels where asked, and on one-pin nets
        for net in sorted(terminals):
            terms = terminals[net]
            if net in self.sch_label_nets or len(terms) == 1:
                for p, e, _, what in terminals.pop(net):
                    label(net, p, e, f"label/{what}")

        # wires, the shortest nets first
        def spread(terms: list) -> tuple[int, str]:
            xs = [t[1][0] for t in terms]
            ys = [t[1][1] for t in terms]
            return max(xs) - min(xs) + max(ys) - min(ys)

        for net in sorted(terminals, key=lambda n: (spread(terminals[n]), n)):
            terms = sorted(terminals[net], key=lambda t: (t[1][0], t[1][1]))
            p0, e0, _, what0 = terms[0]
            r.add_path(net, [p0, e0])
            tree = {e0}
            left, failed = terms[1:], []
            while left:
                t = min(
                    left, key=lambda t: (min(abs(t[1][0] - c[0]) + abs(t[1][1] - c[1]) for c in tree), t[1])
                )
                left.remove(t)
                p, e = t[0], t[1]
                sources = {
                    c: None for c in tree if not any(n != net for axis in (0, 1) for n in r.along(c, axis))
                }
                path = r.route(net, sources, p, e)
                if path is None:
                    failed.append(t)
                    continue
                r.add_path(net, path)
                tree.update(path[:-1])
            if failed:
                for p, e, _, what in failed:
                    label(net, p, e, f"label/{what}")
                d0 = (e0[0] - p0[0], e0[1] - p0[1])
                body.append(self._label(net, e0[0] * g, e0[1] * g, d0[0], d0[1], uid(ns, f"label/{what0}")))
                anchors.add(e0)
                labelled.setdefault(net, []).append(e0)

        # Each wired net carries its name once, so KiCad's net is the board's and a reader sees it: a
        # label on a level run of its wire, never on a bend, a tee or a crossing (a label joins every
        # wire through its point), where its text covers the least.
        def covered(c: Cell) -> bool:
            return (
                c in r.blocked or r.soft.get(c, 0.0) >= SchRouter.TEXT or bool(r.along(c, 0) | r.along(c, 1))
            )

        for net in sorted(n for n in terminals if n not in labelled):
            reach = math.ceil(len(net) * TEXT_ADVANCE / g)
            best = None
            for (c, axis), n in sorted(r.edge.items()):
                # c inside a straight run: wire of this net on both sides, no end, bend or crossing at c
                before = ((c[0] - 1, c[1]), 0) if axis == 0 else ((c[0], c[1] - 1), 1)
                if n != net or r.edge.get(before) != net:
                    continue
                if c in r.node or any(o != net for o in r.along(c, 1 - axis)):
                    continue
                if axis == 0:  # level text above the wire, reading right
                    over = sum(covered((c[0] + k, c[1] - 1)) for k in range(reach + 1))
                else:  # text left of the wire, reading up
                    over = sum(covered((c[0] - 1, c[1] - k)) for k in range(reach + 1))
                key = (over, axis, c[1], c[0])
                if best is None or key < best[0]:
                    best = (key, c, (1, 0) if axis == 0 else (0, -1))
            if best is None:  # no level run: the name goes on the first pin's exit
                p0, e0 = sorted(terminals[net], key=lambda t: (t[1][0], t[1][1]))[0][:2]
                best = (None, e0, (e0[0] - p0[0], e0[1] - p0[1]))
            _, at, (dx, dy) = best
            body.append(self._label(net, at[0] * g, at[1] * g, dx, dy, uid(ns, f"name/{net}")))
            r.node[at] = net
            anchors.add(at)
            labelled.setdefault(net, []).append(at)
            names.add(at)

        # every net's wires in one piece, or each piece labelled
        for net in sorted(set(r.edge.values())):
            parent: dict[Cell, Cell] = {}

            def find(c: Cell, parent: dict[Cell, Cell] = parent) -> Cell:
                while parent.setdefault(c, c) != c:
                    parent[c] = parent[parent[c]]
                    c = parent[c]
                return c

            for (c, axis), n in r.edge.items():
                if n == net:
                    o = (c[0] + 1, c[1]) if axis == 0 else (c[0], c[1] + 1)
                    parent[find(c)] = find(o)
            pieces = {find(c) for c in parent}
            if len(pieces) > 1 and {find(c) for c in labelled.get(net, [])} != pieces:
                raise RuntimeError(f"schematic wiring: {net} came out in {len(pieces)} unlabelled pieces")
            segs, dots = r.segments(net, pin_ends | anchors, pin_ends | (anchors - names))
            for a, b in segs:
                body.append(
                    [
                        "wire",
                        ["pts", ["xy", fmt(a[0] * g), fmt(a[1] * g)], ["xy", fmt(b[0] * g), fmt(b[1] * g)]],
                        ["stroke", ["width", "0"], ["type", "default"]],
                        ["uuid", uid(ns, f"wire/{net}/{a}/{b}")],
                    ]
                )
            for c in dots:
                body.append(
                    [
                        "junction",
                        ["at", fmt(c[0] * g), fmt(c[1] * g)],
                        ["diameter", "0"],
                        ["color", "0", "0", "0", "0"],
                        ["uuid", uid(ns, f"junction/{net}/{c}")],
                    ]
                )

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
        rot: int = 0,
        places: dict[str, tuple[float, float]] | None = None,
        hidden: tuple[str, ...] = (),
    ) -> Node:
        """`places` puts a field's text start (left end, mid-height, from `_field_spots`) where given and
        level: KiCad adds the field's angle to the symbol's and flips its justification at 90 and 180,
        read from its plots. `hidden` hides those fields."""
        ns = self.namespace
        x, y = at
        hide = ["effects", ["font", ["size", "1.27", "1.27"]], ["hide", "yes"]]
        shown = [
            "effects",
            ["font", ["size", "1.27", "1.27"]],
            ["justify", "left" if rot in (0, 270) else "right"],
        ]
        # Default field positions: reference above-right, value below-right of the anchor.
        spots = {"Reference": (x + 1.27, y - 1.27), "Value": (x + 1.27, y + 1.27), **(places or {})}
        texts = {"Reference": ref, "Value": value}
        fields = [
            [
                "property",
                Q(name),
                Q(texts[name]),
                ["at", fmt(spots[name][0]), fmt(spots[name][1]), str(rot % 180)],
                hide if hidden_fields or name in hidden else shown,
            ]
            for name in ("Reference", "Value")
        ]
        node: Node = [
            "symbol",
            ["lib_id", Q(sym.lib_id)],
            ["at", fmt(x), fmt(y), str(rot)],
            ["unit", "1"],
            ["exclude_from_sim", "no"],
            ["in_bom", "yes" if in_bom else "no"],
            ["on_board", "no" if ref.startswith("#") else "yes"],
            ["dnp", "no"],
            ["uuid", uid(ns, key)],
            *fields,
        ]
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

    _FLIP_LAYERS = {
        "F.Cu": "B.Cu",
        "F.SilkS": "B.SilkS",
        "F.Mask": "B.Mask",
        "F.Paste": "B.Paste",
        "F.CrtYd": "B.CrtYd",
        "F.Fab": "B.Fab",
        "F.Adhes": "B.Adhes",
    }

    @classmethod
    def _flip(cls, node: Node) -> None:
        """Mirror a library footprint about the X axis onto the back side, the way KiCad's Flip does:
        y negated, angles negated, front layers swapped for back layers, text mirrored."""
        for item in node:
            if not isinstance(item, list) or not item:
                continue
            head = item[0]
            if head in ("layer", "layers"):
                item[1:] = [Q(cls._FLIP_LAYERS.get(str(a), str(a))) for a in item[1:]]
            elif head == "at":
                vals = atoms(item)
                item[:] = ["at", vals[0], fmt(-num(vals[1]))] + (
                    [fmt(-num(vals[2]))] if len(vals) > 2 else []
                )
            elif head in ("start", "end", "center", "mid", "xy"):
                vals = atoms(item)
                item[:] = [head, vals[0], fmt(-num(vals[1]))]
            elif head == "effects":
                just = child(item, "justify")
                if just is None:
                    item.append(["justify", "mirror"])
                elif "mirror" not in atoms(just):
                    just.append("mirror")
            if head in (
                "pad",
                "fp_text",
                "property",
                "fp_line",
                "fp_rect",
                "fp_circle",
                "fp_arc",
                "fp_poly",
                "pts",
                # A custom pad's copper: its shapes are in the pad's frame and mirror with it (M38).
                "primitives",
                "gr_poly",
                "gr_line",
                "gr_rect",
                "gr_circle",
                "gr_arc",
                "gr_curve",
            ):
                cls._flip(item)

    def _footprint_instance(self, part: Part, net_ids: dict[str, int]) -> Node:
        assert part.footprint and part.pcb_at
        ns = self.namespace
        fpn = copy.deepcopy(part.footprint.node)
        back = part.pcb_layer == "B.Cu"
        if back:
            self._flip(fpn)
        rot = part.pcb_rot
        x, y = part.pcb_at
        out: Node = [
            "footprint",
            Q(part.footprint.lib_id),
            ["layer", Q("B.Cu" if back else "F.Cu")],
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
        if part.zone_connect is not None:
            out.append(["zone_connect", str(part.zone_connect)])
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
        if model and not any(m["replace"] for m in part.models):
            out.append(model)
        for m in part.models:
            out.append(
                [
                    "model",
                    Q(m["path"]),
                    ["offset", ["xyz", *(fmt(v) for v in m["offset"])]],
                    ["scale", ["xyz", *(fmt(v) for v in m["scale"])]],
                    ["rotate", ["xyz", *(fmt(v) for v in m["rotate"])]],
                ]
            )
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

    @staticmethod
    def _stackup(copper: list[str], thickness: float = 1.6) -> Node:
        """An FR4 stackup, 1.6 mm unless told otherwise: 35 um outer and 15 um inner copper; on a
        multilayer board 7628 prepreg (0.21 mm) under each outer layer and between core pairs, the
        cores sharing the rest; on two layers one core between the faces."""
        outer, inner_cu, prepreg = 0.035, 0.0152, 0.2104
        n = len(copper)
        if n == 2:
            prepreg = 0.0  # no prepreg: the one core is the board
        cores = max(n // 2 - 1, 1)
        rest = thickness - 2 * outer - (n - 2) * inner_cu - (n // 2) * prepreg
        core = round(rest / cores, 4)
        if core <= 0:
            raise ValueError(f"a {thickness} mm board is too thin for {n} copper layers")
        out: Node = [
            "stackup",
            ["layer", Q("F.SilkS"), ["type", Q("Top Silk Screen")]],
            ["layer", Q("F.Paste"), ["type", Q("Top Solder Paste")]],
            ["layer", Q("F.Mask"), ["type", Q("Top Solder Mask")], ["thickness", "0.01"]],
        ]
        for i, name in enumerate(copper):
            cu = outer if i in (0, n - 1) else inner_cu
            out.append(["layer", Q(name), ["type", Q("copper")], ["thickness", fmt(cu)]])
            if i < n - 1:
                kind, t = ("prepreg", prepreg) if i % 2 == 0 and n > 2 else ("core", core)
                out.append(
                    [
                        "layer",
                        Q(f"dielectric {i + 1}"),
                        ["type", Q(kind)],
                        ["thickness", fmt(t)],
                        ["material", Q("FR4")],
                        ["epsilon_r", "4.5"],
                        ["loss_tangent", "0.02"],
                    ]
                )
        out += [
            ["layer", Q("B.Mask"), ["type", Q("Bottom Solder Mask")], ["thickness", "0.01"]],
            ["layer", Q("B.Paste"), ["type", Q("Bottom Solder Paste")]],
            ["layer", Q("B.SilkS"), ["type", Q("Bottom Silk Screen")]],
            ["copper_finish", Q("None")],
            ["dielectric_constraints", "no"],
        ]
        return out

    def board(self) -> str:
        ns = self.namespace
        net_ids = self.net_ids()
        x1, y1, x2, y2 = self.outline
        copper = self.copper_names()
        self.routing_layers()  # refuses a plane layer that is not an inner layer
        inner = [[str(2 + 2 * i), Q(name), "signal"] for i, name in enumerate(copper[1:-1], start=1)]
        layers = [
            ["0", Q("F.Cu"), "signal"],
            *inner,
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
            ["general", ["thickness", fmt(self.thickness)], ["legacy_teardrops", "no"]],
            ["paper", Q("A4")],
            ["layers", *layers],
            [
                "setup",
                # A two-layer board at the default thickness keeps KiCad's own stackup, as it always has.
                *(
                    [self._stackup(copper, self.thickness)]
                    if len(copper) > 2 or abs(self.thickness - 1.6) > 1e-9
                    else []
                ),
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
        pcb.extend(self._edge_cuts(ns))
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
        for i, (text, tx, ty, layer, size, thickness) in enumerate(self.texts):
            effects: Node = [
                "effects",
                ["font", ["size", fmt(size), fmt(size)], ["thickness", fmt(thickness)]],
            ]
            if layer.startswith("B."):
                effects.append(["justify", "mirror"])
            pcb.append(
                [
                    "gr_text",
                    Q(text),
                    ["at", fmt(tx), fmt(ty), "0"],
                    ["layer", Q(layer)],
                    ["uuid", uid(ns, f"text/{i}")],
                    effects,
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
        for i, z in enumerate(self.zones):
            pcb_net = self.pcb_net_name(z["net"])
            if pcb_net not in net_ids:
                raise KeyError(f"zone net {z['net']!r} is on no part")
            connect: Node = ["connect_pads", ["clearance", fmt(z["clearance"])]]
            if z["connect"] == "solid":
                connect.insert(1, "yes")
            pcb.append(
                [
                    "zone",
                    ["net", str(net_ids[pcb_net])],
                    ["net_name", Q(pcb_net)],
                    ["layers", *[Q(layer) for layer in z["layers"]]],
                    ["uuid", uid(ns, f"zone/{i}")],
                    ["hatch", "edge", "0.5"],
                    ["priority", "0"],
                    connect,
                    ["min_thickness", fmt(z["min_thickness"])],
                    ["filled_areas_thickness", "no"],
                    [
                        "fill",
                        "yes",
                        ["thermal_gap", fmt(z["thermal_gap"])],
                        ["thermal_bridge_width", fmt(z["thermal_bridge"])],
                    ],
                    ["polygon", ["pts", *[["xy", fmt(px), fmt(py)] for px, py in z["polygon"]]]],
                ]
            )
        for i, k in enumerate(self.keepouts):
            pcb.append(
                [
                    "zone",
                    ["net", "0"],
                    ["net_name", Q("")],
                    ["layers", *[Q(layer) for layer in k["layers"]]],
                    ["uuid", uid(ns, f"keepout/{i}")],
                    ["name", Q(k["name"])],
                    ["hatch", "edge", "0.5"],
                    ["connect_pads", ["clearance", "0"]],
                    ["min_thickness", "0.25"],
                    ["filled_areas_thickness", "no"],
                    [
                        "keepout",
                        ["tracks", "not_allowed"],
                        ["vias", "not_allowed"],
                        ["pads", "allowed"],
                        ["copperpour", "allowed"],
                        ["footprints", "allowed"],
                    ],
                    ["fill", ["thermal_gap", "0.5"], ["thermal_bridge_width", "0.5"]],
                    ["polygon", ["pts", *[["xy", fmt(px), fmt(py)] for px, py in k["polygon"]]]],
                ]
            )
        pcb.append(["embedded_fonts", "no"])
        return dumps(pcb) + "\n"

    # ---- project

    def board_rules(self) -> dict:
        """The board's design rules as the project file carries them: the workcenter's defaults with
        `rules` laid over them. The key order is the file's; changing it changes every project."""
        return {
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
            **self.rules,
        }

    def check_via_rules(self) -> list[str]:
        """Every via size the board's own rules refuse: the default via, each net class's and each
        hand via's, against the minimum hole, via diameter and annular ring. The router places the
        default and net class vias, so the DRC of an unrouted board never sees one (M46)."""
        rules = self.board_rules()
        hole, dia, ring = (
            rules["min_through_hole_diameter"],
            rules["min_via_diameter"],
            rules["min_via_annular_width"],
        )
        sizes = [("default via", self.via_size, self.via_drill)]
        sizes += [(f"net class {name} via", s["via"], s["via_drill"]) for name, s in self.net_classes.items()]
        sizes += [
            (f"{net} via at ({fmt(x)}, {fmt(y)})", size, drill) for net, (x, y), size, drill in self.vias
        ]
        out = []
        for what, size, drill in sizes:
            if drill < hole - 1e-9:
                out.append(f"{what}: drill {fmt(drill)} is below the board's minimum hole {fmt(hole)}")
            if size < dia - 1e-9:
                out.append(f"{what}: diameter {fmt(size)} is below the board's minimum via {fmt(dia)}")
            if (size - drill) / 2 < ring - 1e-9:
                out.append(
                    f"{what}: annular ring {fmt((size - drill) / 2)} is below the board's minimum {fmt(ring)}"
                )
        return out

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
                    "rules": self.board_rules(),
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
        # The router sees the routing layers only; a plane layer is KiCad's to fill. A through pad or
        # via has copper on every layer it sees, or the router would run an inner track through it.
        routing = self.routing_layers()

        def padstack_for(pad: Pad, part_rot: float) -> str:
            w, h = pad.w, pad.h
            # Pad angle relative to the image: the image is rotated by the placement.
            if round((pad.angle) % 180) == 90:
                w, h = h, w
            through = pad.kind in ("thru_hole", "np_thru_hole")
            layers = routing if through else ["F.Cu"]
            shape = (
                "circle" if pad.shape == "circle" or (pad.shape == "oval" and abs(w - h) < 1e-6) else "rect"
            )
            key = f"{shape}_{fmt(w)}x{fmt(h)}_{'TH' if through else 'SMD'}"
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
                        # A hole with no copper: an unconnected pin the router must avoid. The DRC treats
                        # a non-plated hole as board edge (copper keeps `edge_clearance` from it) and
                        # wants at least the 0.25 mm hole clearance; the obstacle is grown by the
                        # difference to the track clearance so the router keeps the larger one (M33).
                        margin = 2 * max(0.0, max(0.25, self.edge_clearance) - self.clearance)
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
            back = part.pcb_layer == "B.Cu"
            side = "back" if back else "front"
            # Specctra mirrors a back-side image about the Y axis; KiCad flips about the X axis.
            # The two differ by a half turn, so the router gets the rotation plus 180 degrees.
            rot = (part.pcb_rot + 180) % 360 if back else part.pcb_rot
            placement.append(
                f'    (component "{fp.lib_id}"\n      (place "{part.ref}" {c(px)} {c(-py)} {side} {fmt(rot)})\n    )'
            )
            for pin_no, net in part.nets.items():
                pins_by_net[self.pcb_net_name(net)].append(f"{part.ref}-{pin_no}")

        def via_name(size: float, drill: float) -> str:
            return f"Via[0-{len(routing) - 1}]_{int(round(size * 1000))}:{int(round(drill * 1000))}_um"

        vias = {via_name(self.via_size, self.via_drill): (self.via_size, self.via_drill)}
        for s in self.net_classes.values():
            vias.setdefault(via_name(s["via"], s["via_drill"]), (s["via"], s["via_drill"]))
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
        # Tracks and vias already on the board (pre-routed by hand or stitched) are fixed for the router.
        wiring = [
            f'    (wire (path {layer} {c(w)} {c(sx)} {c(-sy)} {c(ex)} {c(-ey)}) (net "{net}") (type fix))'
            for net, (sx, sy), (ex, ey), w, layer in self.segments
        ] + [
            f'    (via "{via_name(size, drill)}" {c(vx)} {c(-vy)} (net "{net}") (type fix))'
            for net, (vx, vy), size, drill in self.vias
        ]
        for _net, _at, size, drill in self.vias:
            vias.setdefault(via_name(size, drill), (size, drill))
        # The router keeps `clearance` from the boundary; the DRC wants edge_clearance. Shrink the boundary.
        e = max(0.0, self.edge_clearance - self.clearance)
        via_ps = [
            f'    (padstack "{n}"\n'
            + "".join(f"      (shape (circle {layer} {c(d)}))\n" for layer in routing)
            + "      (attach off)\n    )"
            for n, (d, _) in vias.items()
        ]
        ring = self.outline_polygon(e)
        boundary = "      (path pcb 0 " + " ".join(f"{c(px)} {c(-py)}" for px, py in [*ring, ring[0]]) + ")"
        # A zone is a plane to the router: pads of its net on that layer count as connected, other
        # nets route across it, and KiCad fills around their tracks.
        planes = [
            f'    (plane "{self.pcb_net_name(z["net"])}" (polygon {layer} 0 '
            + " ".join(f"{c(px)} {c(-py)}" for px, py in z["polygon"])
            + "))"
            for z in self.zones
            for layer in z["layers"]
            if layer in routing
        ]
        # A keepout on a plane layer still refuses vias, which pass through every layer: the router
        # gets it as a via keepout on the top layer.
        keepouts = [
            f'    ({"keepout" if layer in routing else "via_keepout"} "{k["name"]}" '
            f"(polygon {layer if layer in routing else routing[0]} 0 "
            + " ".join(f"{c(px)} {c(-py)}" for px, py in k["polygon"])
            + "))"
            for k in self.keepouts
            for layer in k["layers"]
        ]
        layer_defs = [
            f"    (layer {layer} (type signal) (property (index {i})))" for i, layer in enumerate(routing)
        ]
        return "\n".join(
            [
                f'(pcb "{self.name}.dsn"',
                '  (parser (string_quote ") (space_in_quoted_tokens on) (host_cad "KiCad\'s Pcbnew") (host_version "9.0"))',
                "  (resolution um 10)",
                "  (unit um)",
                "  (structure",
                *layer_defs,
                "    (boundary",
                boundary,
                "    )",
                *planes,
                *keepouts,
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
                "  (wiring",
                *wiring,
                "  )",
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
                    if math.hypot(a[0] - b[0], a[1] - b[1]) < 0.02:
                        continue  # the router echoes fixed wires with a hair of a stub
                    if not self._has_segment(name, a, b, layer) and not self._covered(name, a, b, layer):
                        self.segments.append((name, a, b, width, layer))
                        added_s += 1
            for via in children(net, "via"):
                vals = atoms(via)
                m = re.match(r"Via\[\d+-\d+\]_(\d+):(\d+)_um", str(vals[0]))
                size, drill = (
                    (int(m.group(1)) / 1000, int(m.group(2)) / 1000) if m else (self.via_size, self.via_drill)
                )
                at = (mm(vals[1]), -mm(vals[2]))
                if not self._has_via(name, at):  # fixed vias come back in the session
                    self.vias.append((name, at, size, drill))
                    added_v += 1
        self._split_junctions()
        return added_s, added_v

    def _split_junctions(self) -> None:
        """Split a segment wherever another segment of its net ends on it, so a T-junction the
        router made onto a hand-routed track is two proper segment ends, not a dangling end."""
        ends = [(n, p, ly) for n, a, b, _, ly in self.segments for p in (a, b)]
        out = []
        for n, a, b, w, ly in self.segments:
            cuts = sorted(
                {
                    round(
                        ((p[0] - a[0]) * (b[0] - a[0]) + (p[1] - a[1]) * (b[1] - a[1]))
                        / max((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2, 1e-12),
                        6,
                    )
                    for m, p, lay in ends
                    if m == n
                    and lay == ly
                    and _seg_dist(p, a, b) < 0.005
                    and math.hypot(p[0] - a[0], p[1] - a[1]) > 0.02
                    and math.hypot(p[0] - b[0], p[1] - b[1]) > 0.02
                }
            )
            pts = [a] + [(a[0] + u * (b[0] - a[0]), a[1] + u * (b[1] - a[1])) for u in cuts] + [b]
            out.extend((n, p, q, w, ly) for p, q in zip(pts, pts[1:], strict=False))
        self.segments = out

    def _has_via(self, net: str, at: tuple[float, float]) -> bool:
        return any(n == net and math.hypot(vx - at[0], vy - at[1]) < 0.01 for n, (vx, vy), _, _ in self.vias)

    def _covered(self, net: str, a: tuple[float, float], b: tuple[float, float], layer: str) -> bool:
        """True when a and b both lie on one existing segment of the net: the router's echo of a
        fixed wire, cut at a different point."""
        return any(
            n == net and ly == layer and _seg_dist(a, s, e) < 0.03 and _seg_dist(b, s, e) < 0.03
            for n, s, e, _, ly in self.segments
        )

    def _has_segment(self, net: str, a: tuple[float, float], b: tuple[float, float], layer: str) -> bool:
        def same(p, q):
            return math.hypot(p[0] - q[0], p[1] - q[1]) < 0.01

        return any(
            n == net and ly == layer and ((same(s, a) and same(e, b)) or (same(s, b) and same(e, a)))
            for n, s, e, _, ly in self.segments
        )

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
        if self.footprint_dirs:  # so KiCad finds the project's own footprints when the board is opened
            rows = []
            for lib, d in sorted(self.footprint_dirs.items()):
                d = Path(d).resolve()
                try:
                    uri = "${KIPRJMOD}/" + d.relative_to(out_dir.resolve()).as_posix()
                except ValueError:
                    uri = d.as_posix()
                rows.append(f'  (lib (name "{lib}")(type "KiCad")(uri "{uri}")(options "")(descr ""))')
            table = out_dir / "fp-lib-table"
            table.write_text("(fp_lib_table\n  (version 7)\n" + "\n".join(rows) + "\n)\n", encoding="utf-8")
            files[table] = table.read_text(encoding="utf-8")
        if self.zones:
            pcb = out_dir / f"{self.name}.kicad_pcb"
            fill_zones(pcb)
            if self.segments:  # a routed board: tracks cut the pours, stitch the pieces back together
                added, self.islands = stitch_zones(self, pcb)
                if added:
                    pcb.write_text(self.board(), encoding="utf-8")
                    fill_zones(pcb)
        return list(files)


def pour_pieces(pcb: Path, net: str) -> dict:
    """How the filled pours of `net` hang together, read with KiCad's own geometry (pcbnew).

    Returns {"pieces": [(layer, polys, index, items)], "components": [set of piece ids]}: one piece per
    filled polygon, `items` the pads and vias of the net it touches, and components joined by the
    through-hole pads and vias shared between layers. Every piece that holds an item should end up in
    one component; the rest are the islands the DRC reports as unconnected zone-to-zone.
    """
    import pcbnew  # KiCad's own Python module; only present where KiCad is installed

    board = pcbnew.LoadBoard(str(pcb))
    code = board.GetNetcodeFromNetname(net)
    pieces: list[tuple[str, object, int, list]] = []
    for zone in board.Zones():
        if zone.GetNetCode() != code:
            continue
        for layer in zone.GetLayerSet().CuStack():
            polys = zone.GetFilledPolysList(layer)
            for i in range(polys.OutlineCount()):
                pieces.append((pcbnew.LayerName(layer), polys, i, []))
    items = []  # (position, layers, drill)
    copper = {pcbnew.LayerName(ly) for ly in board.GetEnabledLayers().CuStack()}  # a via spans them all
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetCode() == code:
                layers = {pcbnew.LayerName(ly) for ly in pad.GetLayerSet().CuStack()}
                items.append((pad.GetPosition(), layers, f"{fp.GetReference()}.{pad.GetNumber()}"))
    for track in board.GetTracks():
        if track.GetClass() == "PCB_VIA" and track.GetNetCode() == code:
            items.append(
                (
                    track.GetPosition(),
                    copper,
                    f"via@{track.GetPosition().x / 1e6:.2f},{track.GetPosition().y / 1e6:.2f}",
                )
            )
    parent = list(range(len(pieces)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for pos, layers, name in items:
        touched = [
            k for k, (layer, polys, i, _) in enumerate(pieces) if layer in layers and polys.Contains(pos, i)
        ]
        for k in touched:
            pieces[k][3].append(name)
        for k in touched[1:]:
            parent[find(k)] = find(touched[0])
    groups: dict[int, set[int]] = {}
    for k in range(len(pieces)):
        groups.setdefault(find(k), set()).add(k)

    def area(group: set[int]) -> float:
        return sum(pieces[k][1].Outline(pieces[k][2]).Area() for k in group)

    return {"pieces": pieces, "components": sorted(groups.values(), key=area, reverse=True)}


def stitch_zones(design: Design, pcb: Path, rounds: int = 6) -> int:
    """Add vias of a poured net wherever a track has cut a pad off from the rest of its pour.

    The router treats a pour as a plane and leaves its pads alone; KiCad then fills around the
    other nets' tracks, and a pad can end up on an island. Each round reads the filled board, finds
    the islands that hold pads, and drops a via through each one into the main pour on the other
    side; the board is re-filled and read again until every pad is on the main pour or no via fits.
    Returns (vias added, islands left), an island being the sorted pad names it holds.
    """
    try:
        import pcbnew
    except ImportError:
        print(
            "stitch: pcbnew (KiCad's Python module) is not importable; islands are left to the DRC",
            file=sys.stderr,
        )
        return 0, []
    added = 0
    left: list[list[str]] = []
    for _ in range(rounds):
        progress = False
        left = []
        # Once per poured net: pour_pieces reads every zone of the net, so a net with two zones (a plane
        # and a face pour) looped per zone would stitch each island twice in one round (M37).
        for net in dict.fromkeys(design.pcb_net_name(z["net"]) for z in design.zones):
            spec = design.class_of(net)
            size, drill = spec["via"], spec["via_drill"]
            graph = pour_pieces(pcb, net)
            pieces, components = graph["pieces"], graph["components"]
            if not components:
                continue
            holes = _holes(pcbnew, pcb)
            boxes = design.pad_boxes()
            copper = design.copper_names()
            for n, comp in enumerate(components[1:], start=1):
                if not any(pieces[k][3] for k in comp):
                    continue  # a bare island: KiCad drops it
                spot = None
                # Land the via in the biggest other component first; any merge is progress.
                for m_comp in components[:n] + components[n + 1 :]:
                    for k in comp:
                        layer, polys, i, names = pieces[k]
                        for other in (ly for ly in copper if ly != layer):
                            targets = [pieces[m] for m in m_comp if pieces[m][0] == other]
                            # The via passes every other layer too: there it sits in the net's own
                            # pour or keeps clear of the other nets' copper (P17).
                            rest = [ly for ly in copper if ly not in (layer, other)]
                            spot = _via_spot(
                                pcbnew,
                                polys,
                                i,
                                targets,
                                size / 2,
                                drill / 2,
                                holes,
                                blocked=_via_blocker(pcbnew, design, pieces, boxes, net, size / 2, rest),
                            )
                            if spot:
                                break
                        if spot:
                            break
                    if spot:
                        break
                if spot is None:
                    left.append(sorted({n for k in comp for n in pieces[k][3]}))
                    continue
                design.vias.append((net, spot, size, drill))
                holes.append((pcbnew.VECTOR2I_MM(*spot), drill / 2))
                added += 1
                progress = True
        if not progress:
            break
        pcb.write_text(design.board(), encoding="utf-8")
        fill_zones(pcb)
    return added, left


def _via_blocker(
    pcbnew, design: Design, pieces: list, boxes: list[PadBox], net: str, r: float, rest: list[str]
):
    """The `blocked` test for a stitching via of `net` and radius `r`: True where a keepout refuses
    it, or where on one of the `rest` layers (those it passes without joining) it is neither inside
    the net's own fill nor clear of the other nets' tracks and pads."""
    c = design.clearance

    def clear_on(layer: str, x: float, y: float) -> bool:
        if any(_inside_fill(pcbnew, polys, i, x, y, r + 0.05) for ly, polys, i, _ in pieces if ly == layer):
            return True
        for n, a, b, w, ly in design.segments:
            if ly == layer and n != net and _seg_dist((x, y), a, b) < r + w / 2 + c:
                return False
        for pad in boxes:
            if pad.layer == layer and pad.net != net:
                dx = max(pad.x1 - x, 0.0, x - pad.x2)
                dy = max(pad.y1 - y, 0.0, y - pad.y2)
                if math.hypot(dx, dy) < r + c:
                    return False
        return True

    def blocked(x: float, y: float) -> bool:
        return design.in_keepout(x, y, r) or not all(clear_on(ly, x, y) for ly in rest)

    return blocked


def _inside_fill(pcbnew, polys, index: int, x: float, y: float, margin: float) -> bool:
    """Is a disc of radius `margin` at (x, y) inside filled polygon `index` of `polys`? Tested at its
    centre and at 16 points round its rim."""
    if not polys.Contains(pcbnew.VECTOR2I_MM(x, y), index):
        return False
    return all(
        polys.Contains(
            pcbnew.VECTOR2I_MM(
                x + margin * math.cos(k * math.pi / 8), y + margin * math.sin(k * math.pi / 8)
            ),
            index,
        )
        for k in range(16)
    )


def _holes(pcbnew, pcb: Path) -> list:
    """(position, radius) of every drilled hole on the board: pads, mounting holes, vias."""
    board = pcbnew.LoadBoard(str(pcb))
    holes = []
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetDrillSizeX() > 0:
                holes.append((pad.GetPosition(), max(pad.GetDrillSizeX(), pad.GetDrillSizeY()) / 2e6))
    for track in board.GetTracks():
        if track.GetClass() == "PCB_VIA":
            holes.append((track.GetPosition(), track.GetDrillValue() / 2e6))
    return holes


def _via_spot(
    pcbnew, polys, index: int, targets: list, radius: float, hole: float, holes: list, blocked=None
):
    """A point where a via of `radius` sits inside filled polygon `index` of `polys` and inside one of
    the target polygons on the other layer, clear of every other hole and of every point `blocked`
    refuses (a keepout: the pour may fill one, a via may not sit in it). Scans a 0.1 mm grid from the
    polygon's centre outwards; None when nothing fits."""
    if not targets:
        return None
    bb = polys.Outline(index).BBox()
    cx, cy = (bb.GetLeft() + bb.GetRight()) / 2e6, (bb.GetTop() + bb.GetBottom()) / 2e6
    step = 0.1
    nx = int((bb.GetRight() - bb.GetLeft()) / 1e6 / step) + 1
    ny = int((bb.GetBottom() - bb.GetTop()) / 1e6 / step) + 1
    candidates = [
        (bb.GetLeft() / 1e6 + ix * step, bb.GetTop() / 1e6 + iy * step)
        for ix in range(nx)
        for iy in range(ny)
    ]
    candidates.sort(key=lambda c: (c[0] - cx) ** 2 + (c[1] - cy) ** 2)
    margin = radius + 0.05

    def inside(poly, i, x, y) -> bool:
        return _inside_fill(pcbnew, poly, i, x, y, margin)

    for x, y in candidates:
        if not inside(polys, index, x, y):
            continue
        if not any(inside(tp, ti, x, y) for _, tp, ti, _ in targets):
            continue
        if blocked is not None and blocked(x, y):
            continue
        p = pcbnew.VECTOR2I_MM(x, y)
        if any(math.hypot((p.x - hp.x) / 1e6, (p.y - hp.y) / 1e6) < hole + hr + 0.25 for hp, hr in holes):
            continue
        return (round(x, 3), round(y, 3))
    return None


def fill_zones(pcb: Path, kicad_cli: str = "kicad-cli") -> None:
    """Fill the board's zones in place with KiCad (headless) and save it in KiCad's own format."""
    exe = shutil.which(kicad_cli)
    if exe is None:
        raise FileNotFoundError("kicad-cli is needed to fill zones")
    with tempfile.TemporaryDirectory() as tmp:
        proc = subprocess.run(
            [
                exe,
                "pcb",
                "drc",
                "--refill-zones",
                "--save-board",
                "--format",
                "json",
                "--output",
                str(Path(tmp) / "fill.json"),
                str(pcb),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
    if proc.returncode not in (0, 5):  # 5: violations found, the gates report those
        raise RuntimeError(
            f"kicad-cli could not fill the zones of {pcb}: {proc.stderr.strip() or proc.stdout.strip()}"
        )


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
        dirs: dict[str, Path] = {}
        ids: list[str] = []
        rest = iter(argv[1:])
        for a in rest:
            if a == "--lib":  # --lib NAME=DIR: a project footprint library
                name, _, d = next(rest, "").partition("=")
                dirs[name] = Path(d)
            else:
                ids.append(a)
        for lib_id in ids:
            fp = load_footprint(lib_id, dirs)
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
