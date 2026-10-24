#!/usr/bin/env python3
"""wrlgen: parametric 3D bodies for parts the KiCad library has none for, as VRML 2.0.

KiCad reads `.wrl` bodies in 0.1 inch units and scales them by 2.54; every number here is entered
in millimetres and divided on output. The body's origin is the footprint's origin, X to the right,
Y toward the top of the footprint, Z up out of the board. Attach one with `Design.model()`.

    python3 tools/wrlgen.py usb-c-vertical models/usb_c_vertical.wrl --height 7.0
    python3 tools/wrlgen.py threaded-stud models/stud_m1p6.wrl --major 1.6 --pitch 0.35 --height 4
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

Point = tuple[float, float]


@dataclass
class Mesh:
    """Triangles and planar polygons in one colour."""

    color: tuple[float, float, float]
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


# -------------------------------------------------------------------- output


def write_wrl(path: Path, meshes: list[Mesh], comment: str = "") -> tuple[int, int]:
    """Write the meshes as one VRML 2.0 file in KiCad's units. Returns (vertices, faces)."""
    out = ["#VRML V2.0 utf8", f"# wrlgen: {comment}".rstrip(": ")]
    nv = nf = 0
    for mesh in meshes:
        if not mesh.faces:
            continue
        r, g, b = mesh.color
        pts = ", ".join(f"{x * MM:.5f} {y * MM:.5f} {z * MM:.5f}" for x, y, z in mesh.vertices)
        idx = ", ".join(" ".join(str(i) for i in f) + " -1" for f in mesh.faces)
        out.append(
            "Shape {\n"
            f"  appearance Appearance {{ material Material {{ diffuseColor {r:.3f} {g:.3f} {b:.3f} "
            "specularColor 0.35 0.35 0.35 shininess 0.45 } }\n"
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
    a = ap.parse_args(argv)
    if a.preset == "usb-c-vertical":
        meshes = usb_c_vertical(a.height, tuple(a.base), tuple(a.shell))
        comment = f"usb-c-vertical height={a.height} base={a.base} shell={a.shell}"
    else:
        meshes = threaded_stud(a.major, a.pitch, a.height, a.tail[0], a.tail[1], a.shoulder[0], a.shoulder[1])
        comment = f"threaded-stud M{a.major}x{a.pitch} height={a.height} tail={a.tail} shoulder={a.shoulder}"
    nv, nf = write_wrl(a.out, meshes, comment)
    print(f"wrote {a.out}: {nv} vertices, {nf} faces ({comment})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
