"""kistack's `ipc_board` module, read from the board file with KiCad's own Python module (pcbnew).

kistack's layout-placement checks (third_party/kistack/skills/layout-placement) read a board
through KiCad's IPC API: a KiCad server must have the board open. KiCad 10.0's kicad-cli has no
API server, and a GUI KiCad is not something the gates run. This module gives the checks the
same data from the `.kicad_pcb` file: `workcenter placement` puts it in `sys.modules` as
`ipc_board` before it runs a check, so the check imports this instead of its own.

Only the reading half is here. `move.py`, which edits the board in KiCad, is refused by the
command: a generated board changes in its design file, never in place.

`load()` returns what kistack's does: "footprints" (Footprint: ref, value, x, y, rot, layer,
courtyard, pads), "outline" (a shapely Polygon), "fixed_copper" [(layer, net, polygon)] for netted
graphic shapes on the outer copper, "board" (an object with the few calls kistack's rules module
makes) and "path". Millimetres, y down, as in KiCad. Like kistack, it models the outer copper
layers only.
"""

from __future__ import annotations

import os
import sys

import pcbnew  # KiCad's own Python module; present wherever KiCad is installed
from shapely.geometry import Polygon
from shapely.ops import unary_union

NM = 1e-6


def _mm(v) -> tuple[float, float]:
    return (v.x * NM, v.y * NM)


class Pad:
    def __init__(self, ref, num, net, poly, center, layers, through):
        self.ref, self.num, self.net, self.poly, self.center = ref, num, net, poly, center
        self.layers, self.through = layers, through
        self.kind = "thru_hole" if through else "smd"

    @property
    def name(self) -> str:
        return f"{self.ref}.{self.num}"


class Footprint:
    def __init__(self, ref, value, x, y, rot, layer, courtyard, pads):
        self.ref, self.value, self.x, self.y, self.rot = ref, value, x, y, rot
        self.layer, self.courtyard, self.pads = layer, courtyard, pads


def _polygons(polyset) -> list[Polygon]:
    """A SHAPE_POLY_SET as shapely polygons, holes kept."""
    out = []
    for i in range(polyset.OutlineCount()):
        ring = polyset.Outline(i)
        outer = [_mm(ring.CPoint(k)) for k in range(ring.PointCount())]
        holes = []
        for h in range(polyset.HoleCount(i)):
            hole = polyset.Hole(i, h)
            holes.append([_mm(hole.CPoint(k)) for k in range(hole.PointCount())])
        if len(outer) >= 3:
            out.append(Polygon(outer, holes))
    return out


def _one(polyset):
    polys = _polygons(polyset)
    if not polys:
        return None
    return polys[0] if len(polys) == 1 else unary_union(polys)


class _Text:
    def __init__(self, value):
        self.value = value


class _Field:
    def __init__(self, value):
        self.text = _Text(value)


class _Length:
    def __init__(self, nm):
        self.value_nm = nm


class _Overrides:
    """The protobuf message's HasField/attribute pair for a clearance override."""

    def __init__(self, name, nm):
        self._name, self._nm = name, nm
        if nm is not None:
            setattr(self, name, _Length(nm))

    def HasField(self, name):  # noqa: N802 - kipy's protobuf name
        return name == self._name and self._nm is not None


class _PadProto(_Overrides):
    def __init__(self, number, nm):
        super().__init__("copper_clearance_override", nm)
        self.number = number


class _PadDef:
    def __init__(self, number, nm):
        self.proto = _PadProto(number, nm)


class _FpProto:
    def __init__(self, nm):
        self.overrides = _Overrides("copper_clearance", nm)


class _FootprintDef:
    def __init__(self, pads):
        self.pads = pads


class _BoardFootprint:
    def __init__(self, fp):
        self.reference_field = _Field(fp.GetReference())
        self.proto = _FpProto(fp.GetLocalClearance())
        self.definition = _FootprintDef([_PadDef(p.GetNumber(), p.GetLocalClearance()) for p in fp.Pads()])


class _Net:
    def __init__(self, name):
        self.name = name


class _NetClass:
    def __init__(self, nc, name):
        self.name = name
        self.constituents = [name]
        self.track_width = nc.GetTrackWidth()
        self.clearance = nc.GetClearance()
        self.via_diameter = nc.GetViaDiameter()
        self.diff_pair_track_width = nc.GetDiffPairWidth() if nc.HasDiffPairWidth() else None


class Board:
    """The calls kistack's rules module makes on a kipy Board, answered from pcbnew."""

    def __init__(self, board):
        self._b = board

    def get_nets(self):
        return [_Net(str(name)) for name in self._b.GetNetsByName().keys() if str(name)]

    def get_netclass_for_nets(self, nets):
        settings = self._b.GetDesignSettings().m_NetSettings
        out = {}
        for net in nets:
            info = self._b.FindNet(net.name)
            if info is None:
                continue
            out[net.name] = _NetClass(settings.GetEffectiveNetClass(net.name), str(info.GetNetClassName()))
        return out

    def get_footprints(self):
        return [_BoardFootprint(fp) for fp in self._b.GetFootprints()]


def load(board_path, socket=None):
    if not board_path or not os.path.isfile(board_path):
        raise SystemExit(f"no board file {board_path!r}; name the .kicad_pcb")
    board = pcbnew.LoadBoard(str(board_path))
    fps = []
    for f in board.GetFootprints():
        ref = f.GetReference()
        f.BuildCourtyardCaches()
        crt = _one(f.GetCourtyard(pcbnew.B_CrtYd if f.IsFlipped() else pcbnew.F_CrtYd))
        pads = []
        for p in f.Pads():
            if not p.IsOnCopperLayer():
                continue  # paste- or mask-only apertures: no copper
            through = p.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH)
            on_f = through or p.IsOnLayer(pcbnew.F_Cu)
            on_b = through or p.IsOnLayer(pcbnew.B_Cu)
            if not (on_f or on_b):
                continue  # an inner-layer-only pad: kistack models the outer layers
            poly = _one(p.GetEffectivePolygon(pcbnew.F_Cu if on_f else pcbnew.B_Cu, pcbnew.ERROR_INSIDE))
            if poly is None:
                continue
            layers = (["F.Cu"] if on_f else []) + (["B.Cu"] if on_b else [])
            pads.append(
                Pad(ref, p.GetNumber(), p.GetNetname() or None, poly, _mm(p.GetPosition()), layers, through)
            )
        x, y = _mm(f.GetPosition())
        fps.append(
            Footprint(
                ref,
                f.GetValue(),
                x,
                y,
                f.GetOrientationDegrees(),
                "B.Cu" if f.IsFlipped() else "F.Cu",
                crt,
                pads,
            )
        )
    fixed = []
    for s in board.GetDrawings():
        layer = s.GetLayer()
        if layer in (pcbnew.F_Cu, pcbnew.B_Cu) and s.GetClass() == "PCB_SHAPE" and s.GetNetCode() > 0:
            ps = pcbnew.SHAPE_POLY_SET()
            s.TransformShapeToPolygon(ps, layer, 0, board.GetDesignSettings().m_MaxError, pcbnew.ERROR_INSIDE)
            for poly in _polygons(ps):
                fixed.append(("F.Cu" if layer == pcbnew.F_Cu else "B.Cu", s.GetNetname(), poly))
    outline = pcbnew.SHAPE_POLY_SET()
    board.GetBoardPolygonOutlines(outline, True)
    outl = _polygons(outline)
    missing = [f.ref for f in fps if f.courtyard is None]
    if missing:
        print("warning: no courtyard read for " + " ".join(missing), file=sys.stderr)
    return {
        "footprints": fps,
        "outline": max(outl, key=lambda p: p.area) if outl else None,
        "fixed_copper": fixed,
        "board": Board(board),
        "path": os.path.realpath(board_path),
    }


def by_ref(b):
    return {fp.ref: fp for fp in b["footprints"]}


def need(fps, ref, path):
    if ref not in fps:
        raise SystemExit(f"no footprint {ref} on {path}")
    return fps[ref]


def pads_by_net(b):
    d = {}
    for fp in b["footprints"]:
        for p in fp.pads:
            if p.net:
                d.setdefault(p.net, []).append(p)
    return d
