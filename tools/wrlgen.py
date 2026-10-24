#!/usr/bin/env python3
"""wrlgen: parametric 3D bodies for parts the KiCad library has none for, as VRML 2.0.

KiCad reads `.wrl` bodies in 0.1 inch units and scales them by 2.54; every number here is entered
in millimetres and divided on output. The body's origin is the footprint's origin, X to the right,
Y toward the top of the footprint, Z up out of the board. Attach one with `Design.model()`.

    python3 tools/wrlgen.py usb-c-vertical models/usb_c_vertical.wrl --height 7.0
    python3 tools/wrlgen.py threaded-stud models/stud_m1p6.wrl --major 1.6 --pitch 0.35 --height 4
    python3 tools/wrlgen.py connector-510 models/connector_510.wrl
    python3 tools/wrlgen.py cartridge-510 models/cartridge_510.wrl --length 52
    python3 tools/wrlgen.py pouch-cell models/cell.wrl --size 25 8 35
    python3 tools/wrlgen.py display-module models/oled.wrl

The last two are mechanical context for assembly renders (a cell, a display on a side wall);
`cartridge-510` stands on a `connector-510`, its thread reaching down into the collar.
"""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

MM = 1.0 / 2.54  # millimetres to KiCad's VRML unit

SILVER = (0.78, 0.78, 0.80)
BRASS = (0.80, 0.62, 0.28)
BLACK = (0.10, 0.10, 0.10)
GREY = (0.25, 0.25, 0.27)
GOLD = (0.86, 0.70, 0.30)
WHITE = (0.92, 0.92, 0.90)
GLASS = (0.80, 0.86, 0.90)
OIL = (0.85, 0.55, 0.12)
FOIL = (0.72, 0.72, 0.74)
PCB_BLUE = (0.06, 0.16, 0.40)
OLED_LIT = (0.35, 0.75, 0.95)

Point = tuple[float, float]


@dataclass
class Mesh:
    """Triangles and planar polygons in one colour."""

    color: tuple[float, float, float]
    transparency: float = 0.0  # 0 opaque, 1 invisible (glass, oil)
    vertices: list[tuple[float, float, float]] = field(default_factory=list)
    faces: list[tuple[int, ...]] = field(default_factory=list)

    def vertex(self, x: float, y: float, z: float) -> int:
        self.vertices.append((x, y, z))
        return len(self.vertices) - 1

    def face(self, *idx: int) -> None:
        if len(idx) >= 3:
            self.faces.append(tuple(idx))


# ------------------------------------------------------------------ outlines


def circle(r: float, n: int = 48) -> list[Point]:
    return [(r * math.cos(2 * math.pi * i / n), r * math.sin(2 * math.pi * i / n)) for i in range(n)]


def rounded_rect(w: float, d: float, r: float, n: int = 8) -> list[Point]:
    """A w x d rectangle centred on the origin with corner radius r, counter-clockwise."""
    r = min(r, w / 2, d / 2)
    cx, cy = w / 2 - r, d / 2 - r
    pts: list[Point] = []
    for (sx, sy), a0 in (((cx, cy), 0.0), ((-cx, cy), 90.0), ((-cx, -cy), 180.0), ((cx, -cy), 270.0)):
        for i in range(n + 1):
            a = math.radians(a0 + 90.0 * i / n)
            pts.append((sx + r * math.cos(a), sy + r * math.sin(a)))
    return pts


# ---------------------------------------------------------------- primitives


def prism(m: Mesh, outline: list[Point], z0: float, z1: float, caps: bool = True) -> None:
    """Extrude a closed outline from z0 to z1."""
    n = len(outline)
    bottom = [m.vertex(x, y, z0) for x, y in outline]
    top = [m.vertex(x, y, z1) for x, y in outline]
    for i in range(n):
        j = (i + 1) % n
        m.face(bottom[i], bottom[j], top[j], top[i])
    if caps:
        m.face(*reversed(bottom))
        m.face(*top)


def tube(m: Mesh, outer: list[Point], inner: list[Point], z0: float, z1: float) -> None:
    """A wall between two outlines of equal length, closed top and bottom with rings."""
    if len(outer) != len(inner):
        raise ValueError("tube: outer and inner outlines need the same point count")
    n = len(outer)
    ob = [m.vertex(x, y, z0) for x, y in outer]
    ot = [m.vertex(x, y, z1) for x, y in outer]
    ib = [m.vertex(x, y, z0) for x, y in inner]
    it = [m.vertex(x, y, z1) for x, y in inner]
    for i in range(n):
        j = (i + 1) % n
        m.face(ob[i], ob[j], ot[j], ot[i])
        m.face(it[i], it[j], ib[j], ib[i])
        m.face(ot[i], ot[j], it[j], it[i])
        m.face(ib[i], ib[j], ob[j], ob[i])


def box(m: Mesh, cx: float, cy: float, z0: float, sx: float, sy: float, sz: float) -> None:
    hx, hy = sx / 2, sy / 2
    prism(m, [(cx - hx, cy - hy), (cx + hx, cy - hy), (cx + hx, cy + hy), (cx - hx, cy + hy)], z0, z0 + sz)


def cylinder(m: Mesh, cx: float, cy: float, z0: float, r: float, h: float, n: int = 48) -> None:
    prism(m, [(cx + x, cy + y) for x, y in circle(r, n)], z0, z0 + h)


def thread(
    m: Mesh,
    cx: float,
    cy: float,
    z0: float,
    z1: float,
    major: float,
    pitch: float,
    n_theta: int = 48,
    per_turn: int = 12,
    chamfer: float = 0.25,
) -> None:
    """A right-hand external thread of `major` diameter: a helical V ridge on a cylinder, with caps.

    The radius at (theta, z) is the minor radius plus a triangle wave of the helix phase, the ISO
    thread depth (0.54 x pitch). The top `chamfer` millimetres taper to the minor radius.
    """
    depth = 0.54 * pitch
    r_major = major / 2
    r_minor = r_major - depth
    dz = pitch / per_turn
    nz = max(1, int(math.ceil((z1 - z0) / dz)))
    rows: list[list[int]] = []
    for i in range(nz + 1):
        z = min(z0 + i * dz, z1)
        taper = 1.0 if z1 - z >= chamfer else max(0.0, (z1 - z) / chamfer)
        row = []
        for j in range(n_theta):
            t = j / n_theta
            u = ((z - z0) / pitch - t) % 1.0
            tri = 1.0 - abs(2.0 * u - 1.0)
            r = r_minor + depth * tri * taper
            a = 2 * math.pi * t
            row.append(m.vertex(cx + r * math.cos(a), cy + r * math.sin(a), z))
        rows.append(row)
    for i in range(nz):
        for j in range(n_theta):
            k = (j + 1) % n_theta
            m.face(rows[i][j], rows[i][k], rows[i + 1][k])
            m.face(rows[i][j], rows[i + 1][k], rows[i + 1][j])
    cb = m.vertex(cx, cy, z0)
    ct = m.vertex(cx, cy, z1)
    for j in range(n_theta):
        k = (j + 1) % n_theta
        m.face(cb, rows[0][k], rows[0][j])
        m.face(ct, rows[-1][j], rows[-1][k])


def threaded_bore(
    m: Mesh,
    cx: float,
    cy: float,
    z0: float,
    z1: float,
    major: float,
    pitch: float,
    outer_r: float,
    n_theta: int = 48,
    per_turn: int = 12,
) -> None:
    """A tube of outer radius `outer_r` with a right-hand internal thread of `major` diameter.

    The bore's radius is the major radius minus a triangle wave of the helix phase: the crests of
    an internal thread sit at the minor radius, the roots at the major one, depth 0.54 x pitch.
    """
    depth = 0.54 * pitch
    r_major = major / 2
    if outer_r <= r_major:
        raise ValueError("threaded_bore: the tube must be wider than the thread")
    dz = pitch / per_turn
    nz = max(1, int(math.ceil((z1 - z0) / dz)))
    rows: list[list[int]] = []
    for i in range(nz + 1):
        z = min(z0 + i * dz, z1)
        row = []
        for j in range(n_theta):
            t = j / n_theta
            u = ((z - z0) / pitch - t) % 1.0
            r = r_major - depth * (1.0 - abs(2.0 * u - 1.0))
            a = 2 * math.pi * t
            row.append(m.vertex(cx + r * math.cos(a), cy + r * math.sin(a), z))
        rows.append(row)
    for i in range(nz):
        for j in range(n_theta):
            k = (j + 1) % n_theta
            m.face(rows[i][j], rows[i + 1][k], rows[i][k])
            m.face(rows[i][j], rows[i + 1][j], rows[i + 1][k])
    ring = [
        (
            cx + outer_r * math.cos(2 * math.pi * j / n_theta),
            cy + outer_r * math.sin(2 * math.pi * j / n_theta),
        )
        for j in range(n_theta)
    ]
    ob = [m.vertex(x, y, z0) for x, y in ring]
    ot = [m.vertex(x, y, z1) for x, y in ring]
    for j in range(n_theta):
        k = (j + 1) % n_theta
        m.face(ob[j], ob[k], ot[k], ot[j])  # outer wall
        m.face(ot[j], ot[k], rows[-1][k], rows[-1][j])  # top ring
        m.face(rows[0][j], rows[0][k], ob[k], ob[j])  # bottom ring


# ------------------------------------------------------------------- presets


def usb_c_vertical(
    height: float = 7.0,
    base: tuple[float, float, float] = (9.9, 6.2, 1.6),
    shell: tuple[float, float, float] = (9.0, 3.6, 0.25),
    tongue: tuple[float, float] = (6.6, 0.7),
) -> list[Mesh]:
    """A vertical USB-C receptacle: plastic base, metal shell open at the top, tongue inside.

    `height` is the shell top above the board. The long axis of the opening runs along X, as the
    pad rows of KiCad's vertical receptacle footprints do.
    """
    bw, bd, bh = base
    sw, sd, wall = shell
    tw, td = tongue
    plastic = Mesh(GREY)
    box(plastic, 0.0, 0.0, 0.0, bw, bd, bh)
    prism(plastic, rounded_rect(sw - 2 * wall, sd - 2 * wall, sd / 2 - wall), bh, bh + 0.4)  # floor
    metal = Mesh(SILVER)
    tube(
        metal,
        rounded_rect(sw, sd, sd / 2),
        rounded_rect(sw - 2 * wall, sd - 2 * wall, sd / 2 - wall),
        bh,
        height,
    )
    black = Mesh(BLACK)
    box(black, 0.0, 0.0, bh + 0.4, tw, td, max(0.5, height - bh - 1.4))
    return [plastic, metal, black]


def threaded_stud(
    major: float = 1.6,
    pitch: float = 0.35,
    height: float = 4.0,
    tail_d: float = 0.7,
    tail_len: float = 1.6,
    shoulder_d: float = 1.5,
    shoulder_h: float = 0.4,
) -> list[Mesh]:
    """A threaded contact stud soldered into a through-hole pad: tail in the hole, shoulder on the
    pad, external thread above. Defaults are an M1.6 x 0.35 stud for a 1.5 mm pad."""
    m = Mesh(BRASS)
    if tail_len > 0:
        cylinder(m, 0.0, 0.0, -tail_len, tail_d / 2, tail_len)
    if shoulder_h > 0:
        cylinder(m, 0.0, 0.0, 0.0, shoulder_d / 2, shoulder_h)
    thread(m, 0.0, 0.0, shoulder_h, height, major, pitch)
    return [m]


def connector_510(
    collar_d: float = 9.5,
    height: float = 4.0,
    flange_h: float = 0.6,
    major: float = 7.0,
    pitch: float = 0.5,
    pin_d: float = 2.0,
    tab_radius: float = 4.0,
    tail: float = 1.6,
) -> list[Mesh]:
    """A PCB-mount 510 battery connector: a collar with an M7 x 0.5 internal thread, an insulator,
    and a spring centre pin; four collar tabs and the pin's tail reach down through the board."""
    metal = Mesh(SILVER)
    r = collar_d / 2
    prism(metal, circle(r), 0.0, flange_h)
    threaded_bore(metal, 0.0, 0.0, flange_h, height, major, pitch, r)
    for sx in (-1, 1):
        for sy in (-1, 1):
            k = tab_radius / math.sqrt(2.0)
            cylinder(metal, sx * k, sy * k, -tail, 0.35, tail, 16)
    insulator = Mesh(WHITE)
    cylinder(insulator, 0.0, 0.0, flange_h, major / 2 - 0.55, 1.6)
    pin = Mesh(GOLD)
    cylinder(pin, 0.0, 0.0, -tail, 0.45, tail + flange_h, 16)
    cylinder(pin, 0.0, 0.0, flange_h, pin_d / 2, 2.4, 32)
    return [metal, insulator, pin]


def cartridge_510(
    body_d: float = 10.5,
    length: float = 52.0,
    thread_len: float = 3.5,
    base_h: float = 3.0,
    mouth_h: float = 11.0,
    fill: float = 0.6,
) -> list[Mesh]:
    """A 510 cartridge standing on its connector: male M7 x 0.5 thread below z = 0, a metal base, a
    glass tank with oil and a centre post, and a flat mouthpiece. z = 0 is the collar's top face."""
    r = body_d / 2
    metal = Mesh(SILVER)
    thread(metal, 0.0, 0.0, -thread_len, 0.0, 7.0, 0.5)
    prism(metal, circle(r), 0.0, base_h)
    top = length - mouth_h
    cylinder(metal, 0.0, 0.0, base_h, 1.6, top - base_h, 24)  # centre post
    glass = Mesh(GLASS, transparency=0.6)
    tube(glass, circle(r), circle(r - 0.6), base_h, top)
    oil = Mesh(OIL, transparency=0.3)
    prism(oil, circle(r - 0.6), base_h + 0.3, base_h + 0.3 + fill * (top - base_h - 0.6))
    mouth = Mesh(BLACK)
    prism(mouth, rounded_rect(body_d, body_d * 0.62, body_d * 0.25), top, length)
    return [metal, glass, oil, mouth]


def pouch_cell(w: float = 25.0, d: float = 8.0, h: float = 35.0, r: float = 1.5) -> list[Mesh]:
    """A Li-polymer pouch cell standing on its long edge: foil body and a label band."""
    foil = Mesh(FOIL)
    prism(foil, rounded_rect(w, d, r), 0.0, h)
    label = Mesh((0.10, 0.35, 0.75))
    prism(label, rounded_rect(w + 0.1, d + 0.1, r), h * 0.25, h * 0.75)
    return [foil, label]


def display_module(
    pcb: tuple[float, float, float] = (38.0, 12.0, 1.2),
    glass: tuple[float, float, float] = (30.0, 11.5, 1.4),
    active: tuple[float, float] = (22.4, 5.6),
) -> list[Mesh]:
    """A 0.91 in 128 x 32 OLED module lying face up: carrier board, glass, and a lit active area."""
    pw, pd, pt = pcb
    gw, gd, gt = glass
    aw, ad = active
    board = Mesh(PCB_BLUE)
    box(board, 0.0, 0.0, 0.0, pw, pd, pt)
    panel = Mesh(BLACK)
    box(panel, 0.0, 0.0, pt, gw, gd, gt)
    lit = Mesh(OLED_LIT)
    box(lit, 0.0, 0.0, pt + gt, aw, ad, 0.02)
    return [board, panel, lit]


# -------------------------------------------------------------------- output


def write_wrl(path: Path, meshes: list[Mesh], comment: str = "") -> tuple[int, int]:
    """Write the meshes as one VRML 2.0 file in KiCad's units. Returns (vertices, faces)."""
    out = ["#VRML V2.0 utf8", f"# wrlgen: {comment}".rstrip(": ")]
    nv = nf = 0
    for mesh in meshes:
        if not mesh.faces:
            continue
        r, g, b = mesh.color
        clear = f" transparency {mesh.transparency:.2f}" if mesh.transparency > 0 else ""
        pts = ", ".join(f"{x * MM:.5f} {y * MM:.5f} {z * MM:.5f}" for x, y, z in mesh.vertices)
        idx = ", ".join(" ".join(str(i) for i in f) + " -1" for f in mesh.faces)
        out.append(
            "Shape {\n"
            f"  appearance Appearance {{ material Material {{ diffuseColor {r:.3f} {g:.3f} {b:.3f} "
            f"specularColor 0.35 0.35 0.35 shininess 0.45{clear} }} }}\n"
            "  geometry IndexedFaceSet {\n"
            "    solid FALSE\n"
            "    creaseAngle 0.9\n"
            f"    coord Coordinate {{ point [ {pts} ] }}\n"
            f"    coordIndex [ {idx} ]\n"
            "  }\n"
            "}"
        )
        nv += len(mesh.vertices)
        nf += len(mesh.faces)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return nv, nf


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="wrlgen", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="preset", required=True)
    u = sub.add_parser("usb-c-vertical", help="vertical USB-C receptacle: base, shell, tongue")
    u.add_argument("out", type=Path, help="the .wrl file to write")
    u.add_argument("--height", type=float, default=7.0, help="shell top above the board, mm (default 7.0)")
    u.add_argument(
        "--base",
        type=float,
        nargs=3,
        default=(9.9, 6.2, 1.6),
        metavar=("W", "D", "H"),
        help="plastic base, mm",
    )
    u.add_argument(
        "--shell",
        type=float,
        nargs=3,
        default=(9.0, 3.6, 0.25),
        metavar=("W", "D", "WALL"),
        help="metal shell, mm",
    )
    t = sub.add_parser("threaded-stud", help="threaded contact stud in a through-hole pad")
    t.add_argument("out", type=Path, help="the .wrl file to write")
    t.add_argument("--major", type=float, default=1.6, help="thread major diameter, mm (default 1.6)")
    t.add_argument("--pitch", type=float, default=0.35, help="thread pitch, mm (default 0.35)")
    t.add_argument(
        "--height", type=float, default=4.0, help="top of the thread above the board, mm (default 4.0)"
    )
    t.add_argument(
        "--tail", type=float, nargs=2, default=(0.7, 1.6), metavar=("D", "LEN"), help="tail in the hole, mm"
    )
    t.add_argument(
        "--shoulder",
        type=float,
        nargs=2,
        default=(1.5, 0.4),
        metavar=("D", "H"),
        help="shoulder on the pad, mm",
    )
    c = sub.add_parser(
        "connector-510", help="PCB-mount 510 connector: threaded collar, insulator, spring pin"
    )
    c.add_argument("out", type=Path, help="the .wrl file to write")
    c.add_argument("--collar", type=float, default=9.5, help="collar outside diameter, mm (default 9.5)")
    c.add_argument("--height", type=float, default=4.0, help="collar top above the board, mm (default 4.0)")
    c.add_argument(
        "--tab-radius", type=float, default=4.0, help="radius of the four collar tabs, mm (default 4.0)"
    )
    k = sub.add_parser(
        "cartridge-510", help="510 cartridge for assembly renders: thread, base, glass, oil, mouthpiece"
    )
    k.add_argument("out", type=Path, help="the .wrl file to write")
    k.add_argument("--diameter", type=float, default=10.5, help="body diameter, mm (default 10.5)")
    k.add_argument("--length", type=float, default=52.0, help="base to mouthpiece tip, mm (default 52)")
    k.add_argument("--fill", type=float, default=0.6, help="oil level as a share of the tank (default 0.6)")
    q = sub.add_parser("pouch-cell", help="Li-polymer pouch cell standing on its long edge")
    q.add_argument("out", type=Path, help="the .wrl file to write")
    q.add_argument(
        "--size", type=float, nargs=3, default=(25.0, 8.0, 35.0), metavar=("W", "D", "H"), help="mm"
    )
    o = sub.add_parser("display-module", help="0.91 in 128 x 32 OLED module, face up")
    o.add_argument("out", type=Path, help="the .wrl file to write")
    o.add_argument(
        "--pcb", type=float, nargs=3, default=(38.0, 12.0, 1.2), metavar=("W", "D", "T"), help="mm"
    )
    a = ap.parse_args(argv)
    if a.preset == "usb-c-vertical":
        meshes = usb_c_vertical(a.height, tuple(a.base), tuple(a.shell))
        comment = f"usb-c-vertical height={a.height} base={a.base} shell={a.shell}"
    elif a.preset == "threaded-stud":
        meshes = threaded_stud(a.major, a.pitch, a.height, a.tail[0], a.tail[1], a.shoulder[0], a.shoulder[1])
        comment = f"threaded-stud M{a.major}x{a.pitch} height={a.height} tail={a.tail} shoulder={a.shoulder}"
    elif a.preset == "connector-510":
        meshes = connector_510(collar_d=a.collar, height=a.height, tab_radius=a.tab_radius)
        comment = f"connector-510 collar={a.collar} height={a.height} tab_radius={a.tab_radius}"
    elif a.preset == "cartridge-510":
        meshes = cartridge_510(body_d=a.diameter, length=a.length, fill=a.fill)
        comment = f"cartridge-510 diameter={a.diameter} length={a.length} fill={a.fill}"
    elif a.preset == "pouch-cell":
        meshes = pouch_cell(*a.size)
        comment = f"pouch-cell size={list(a.size)}"
    else:
        meshes = display_module(pcb=tuple(a.pcb))
        comment = f"display-module pcb={list(a.pcb)}"
    nv, nf = write_wrl(a.out, meshes, comment)
    print(f"wrote {a.out}: {nv} vertices, {nf} faces ({comment})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
