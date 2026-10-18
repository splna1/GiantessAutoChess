# -*- coding: utf-8 -*-
"""Warsaw board v2 — layout generator (system CPython + shapely, no bpy).

Turns the prototype data (board_proto.py) into a realistic pre-war city fabric:
  * streets: the prototype's 10 avenues + district boundary roads + a secondary street
    grid per district (warped in the old town), riverside boulevards, bridge approaches;
  * blocks: what is left between streets, plazas, parks, river and landmarks;
  * buildings: perimeter tenements (kamienice) split into narrow lots with their own
    height / roof / colour, rear wings (oficyny) into the courtyard, transverse rear houses,
    firewalls where a neighbour is lower, chamfered corners; villas, 1930s slabs and
    factories (chimneys only on multi-storey halls) by district;
  * named buildings (churches, theatre, palace, Prudential, gasholders);
  * trees (parks, avenues, courtyards, river banks), ground layers (triangulated), cells.

Output: Saved/Warsaw/board/warsaw_board_layout.json + plan preview PNG + stats.
Deterministic (seeded).  Run:  python Tools/warsaw/board_gen.py
"""
import json
import math
import os
import random
import sys
import time

import shapely
from shapely.geometry import (Polygon, MultiPolygon, LineString, MultiLineString, Point,
                              GeometryCollection, box)
from shapely.geometry.polygon import orient
from shapely.ops import unary_union, split
from shapely import affinity

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import board_proto as P  # noqa: E402

ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT_DIR = os.path.join(ROOT, "Saved", "Warsaw", "board")
OUT_JSON = os.path.join(OUT_DIR, "warsaw_board_layout.json")
OUT_PLAN = os.path.join(ROOT, "Saved", "Warsaw", "renders", "board2_plan.png")
SEED = 20261018

# board core: buildings inside get full detail, outside are background LOD
CORE = box(-1450.0, -1150.0, 1750.0, 1250.0)

# ------------------------------------------------------------------ district rules
DISTRICT = {
    # block size (u range, v range), street width, drop prob, warp amp
    "old":   {"bu": (52, 78),   "bv": (44, 66),   "sw": 11.0, "drop": 0.10, "warp": 7.0},
    "city":  {"bu": (105, 150), "bv": (82, 120),  "sw": 18.0, "drop": 0.16, "warp": 2.5},
    "wola":  {"bu": (120, 175), "bv": (95, 135),  "sw": 18.0, "drop": 0.20, "warp": 3.0},
    "south": {"bu": (115, 165), "bv": (95, 140),  "sw": 18.0, "drop": 0.18, "warp": 3.0},
    "praga": {"bu": (95, 140),  "bv": (78, 112),  "sw": 16.0, "drop": 0.18, "warp": 4.0},
}
BLOCK_MIX = {   # block programme probabilities
    "old":   [("tenement", 1.0)],
    "city":  [("tenement", 0.90), ("modern", 0.04), ("skwer", 0.04), ("industrial", 0.02)],
    "wola":  [("industrial", 0.42), ("tenement", 0.52), ("skwer", 0.06)],
    "south": [("tenement", 0.42), ("modern", 0.24), ("villa", 0.28), ("skwer", 0.06)],
    "praga": [("tenement", 0.58), ("industrial", 0.24), ("villa", 0.10), ("skwer", 0.08)],
}
TEN = {  # tenement lot rules
    "old":   {"lot": (24.0, 32.0), "wing2": 0.35, "rear": 0.75, "depth": (11.5, 13.5), "front": (7.5, 12.0), "st": (3, 4), "g": (3.8, 4.2), "s": (3.0, 3.3),
              "wing": 0.60, "roof": [("gable", 0.85), ("flat", 0.15)], "rh": (6.0, 8.5), "pal": "old",
              "rpal": ["tile", "tile", "tile_dark", "tile"]},
    "city":  {"lot": (40.0, 54.0), "wing2": 0.55, "rear": 0.85, "depth": (14.0, 16.5), "front": (14.0, 24.0), "st": (4, 6), "g": (4.4, 4.9), "s": (3.4, 3.7),
              "wing": 0.92, "roof": [("shed", 0.50), ("gable", 0.25), ("flat", 0.25)], "rh": (2.4, 3.6), "pal": "city",
              "rpal": ["tin", "tin", "tin_dark", "tar", "rust", "tin"]},
    "wola":  {"lot": (34.0, 46.0), "wing2": 0.40, "rear": 0.75, "depth": (13.0, 15.0), "front": (12.0, 20.0), "st": (3, 5), "g": (4.0, 4.4), "s": (3.2, 3.5),
              "wing": 0.80, "roof": [("shed", 0.45), ("gable", 0.35), ("flat", 0.20)], "rh": (2.4, 3.4), "pal": "work",
              "rpal": ["tin_dark", "tar", "rust", "tin"]},
    "south": {"lot": (34.0, 46.0), "wing2": 0.40, "rear": 0.70, "depth": (13.5, 15.5), "front": (16.0, 26.0), "st": (4, 6), "g": (4.2, 4.6), "s": (3.2, 3.5),
              "wing": 0.80, "roof": [("flat", 0.45), ("shed", 0.35), ("gable", 0.20)], "rh": (2.4, 3.2), "pal": "city",
              "rpal": ["tin", "tar", "tin_dark", "rust"]},
    "praga": {"lot": (34.0, 46.0), "wing2": 0.40, "rear": 0.75, "depth": (12.5, 14.5), "front": (11.0, 19.0), "st": (3, 5), "g": (4.0, 4.3), "s": (3.2, 3.4),
              "wing": 0.80, "roof": [("gable", 0.45), ("shed", 0.42), ("flat", 0.13)], "rh": (2.6, 3.6), "pal": "work",
              "rpal": ["tin_dark", "rust", "tar", "tin", "tile_dark"]},
}
FACADE = {
    "old":    [(0.82, 0.62, 0.32), (0.74, 0.40, 0.28), (0.86, 0.74, 0.44), (0.56, 0.62, 0.48),
               (0.56, 0.62, 0.72), (0.87, 0.82, 0.70), (0.80, 0.52, 0.40), (0.70, 0.30, 0.24)],
    "city":   [(0.78, 0.67, 0.49), (0.85, 0.80, 0.68), (0.68, 0.66, 0.62), (0.73, 0.68, 0.59),
               (0.76, 0.61, 0.53), (0.83, 0.76, 0.56), (0.58, 0.56, 0.52), (0.80, 0.74, 0.64)],
    "work":   [(0.55, 0.29, 0.22), (0.49, 0.25, 0.20), (0.63, 0.37, 0.28), (0.66, 0.63, 0.57),
               (0.72, 0.65, 0.52), (0.58, 0.55, 0.50)],
    "modern": [(0.90, 0.89, 0.85), (0.83, 0.83, 0.81), (0.87, 0.84, 0.77)],
    "villa":  [(0.89, 0.86, 0.77), (0.81, 0.76, 0.64), (0.86, 0.80, 0.66)],
    "brick":  [(0.54, 0.28, 0.21), (0.47, 0.24, 0.19), (0.61, 0.35, 0.26)],
}
ROOF = {"tin": (0.45, 0.46, 0.47), "tin_dark": (0.31, 0.32, 0.33), "tar": (0.20, 0.20, 0.21),
        "rust": (0.47, 0.30, 0.22), "tile": (0.60, 0.28, 0.18), "tile_dark": (0.45, 0.23, 0.17),
        "copper": (0.36, 0.53, 0.45), "slate": (0.27, 0.28, 0.31)}


# ------------------------------------------------------------------ helpers
def polys(g):
    if g is None or g.is_empty:
        return []
    if isinstance(g, Polygon):
        return [g]
    if isinstance(g, (MultiPolygon, GeometryCollection)):
        out = []
        for x in g.geoms:
            out.extend(polys(x))
        return out
    return []


def pick(rng, table):
    r = rng.random()
    acc = 0.0
    for k, p in table:
        acc += p
        if r <= acc:
            return k
    return table[-1][0]


def jit(rng, col, a=0.035):
    return tuple(max(0.0, min(1.0, c + rng.uniform(-a, a))) for c in col)


def noise2(x, y, s=0.0):
    """Cheap smooth value noise in [-1, 1]."""
    return (math.sin(x * 0.0131 + s) * math.cos(y * 0.0117 - s * 0.7) +
            0.5 * math.sin((x + y) * 0.0291 + s * 1.3)) / 1.5


def ccw_coords(poly):
    p = orient(poly, 1.0)
    return [(round(x, 2), round(y, 2)) for x, y in list(p.exterior.coords)[:-1]]


def clean(poly, tol=0.35):
    q = poly.simplify(tol, preserve_topology=True)
    if q.is_empty or not q.is_valid:
        q = poly.buffer(0)
    return q


def rot_rect(cx, cy, hw, hh, ang_deg, chamfer=0.0):
    if chamfer > 0:
        c = chamfer
        pts = [(-hw + c, -hh), (hw - c, -hh), (hw, -hh + c), (hw, hh - c),
               (hw - c, hh), (-hw + c, hh), (-hw, hh - c), (-hw, -hh + c)]
    else:
        pts = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
    a = math.radians(ang_deg)
    ca, sa = math.cos(a), math.sin(a)
    return Polygon([(cx + x * ca - y * sa, cy + x * sa + y * ca) for x, y in pts])


def local_rect(origin, ang, x0, y0, x1, y1):
    ca, sa = math.cos(ang), math.sin(ang)
    ox, oy = origin
    return Polygon([(ox + x * ca - y * sa, oy + x * sa + y * ca)
                    for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))])


def warp_line(pts, amp, lam=70.0, seed=0.0, step=12.0):
    if amp <= 0:
        return pts
    out = []
    for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
        L = math.hypot(x1 - x0, y1 - y0)
        n = max(1, int(L / step))
        for i in range(n):
            t = i / float(n)
            x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
            out.append((x + amp * math.sin(y / lam + seed), y + amp * math.cos(x / lam - seed * 0.6)))
    x, y = pts[-1]
    out.append((x + amp * math.sin(y / lam + seed), y + amp * math.cos(x / lam - seed * 0.6)))
    return out


def tri_layer(geom, z):
    """Constrained Delaunay triangulation -> {'v': [[x,y]], 't': [[a,b,c]], 'z': z}."""
    verts, idx, tris = [], {}, []
    for pg in polys(geom):
        if pg.area < 1.0:
            continue
        pg = shapely.set_precision(pg, 0.01)
        if pg.is_empty:
            continue
        try:
            tg = shapely.constrained_delaunay_triangles(pg)
        except Exception:
            continue
        for t in polys(tg):
            cs = list(t.exterior.coords)[:3]
            # CCW for an up-facing face
            ax, ay = cs[0]
            bx, by = cs[1]
            cx_, cy_ = cs[2]
            if (bx - ax) * (cy_ - ay) - (by - ay) * (cx_ - ax) < 0:
                cs = [cs[0], cs[2], cs[1]]
            tri = []
            for x, y in cs:
                k = (round(x, 2), round(y, 2))
                if k not in idx:
                    idx[k] = len(verts)
                    verts.append([k[0], k[1]])
                tri.append(idx[k])
            if len(set(tri)) == 3:
                tris.append(tri)
    return {"v": verts, "t": tris, "z": z}


# ------------------------------------------------------------------ generator
class Gen(object):
    def __init__(self):
        self.rng = random.Random(SEED)
        self.buildings = []
        self.chimneys = []
        self.trees = []
        self.specials = []
        self.report = {"warnings": []}
        self.WB = box(*P.WORLD_BOUNDS)

    # ---------------- river
    def build_river(self):
        L = [P.w(x, y) for x, y in P.bezier_bank(P.RIVER_LEFT)]
        R = [P.w(x, y) for x, y in P.bezier_bank(P.RIVER_RIGHT)]
        core = Polygon(L + R[::-1]).buffer(0)
        half = P.RIVER_W_PX * P.PX / 2.0
        n = LineString(P.wpts(P.RIVER_NORTH)).buffer(half, cap_style="flat")
        s = LineString(P.wpts(P.RIVER_SOUTH)).buffer(half, cap_style="flat")
        river = unary_union([core, n, s]).buffer(12, quad_segs=6).buffer(-12, quad_segs=6)
        self.river = river.intersection(self.WB)
        # centre line, used to tell banks apart
        cl = P.wpts(P.RIVER_NORTH[::-1]) + [((a[0] + b[0]) / 2, (a[1] + b[1]) / 2) for a, b in zip(L, R)] + \
            P.wpts(P.RIVER_SOUTH)
        cl.sort(key=lambda p: -p[1])
        x0, y0, x1, y1 = P.WORLD_BOUNDS
        cl = [(cl[0][0], y1 + 600.0)] + cl + [(cl[-1][0], y0 - 600.0)]
        self.river_cl = LineString(cl)
        self.west_side = Polygon([(x0 - 600, y1 + 600)] + cl + [(x0 - 600, y0 - 600)]).buffer(0)
        self.boulevard = self.river.buffer(28, quad_segs=6).difference(self.river).intersection(self.WB)
        self.riverside_road = self.river.buffer(48, quad_segs=6).difference(
            self.river.buffer(28, quad_segs=6)).intersection(self.WB)

    # ---------------- landmarks, cells, parks
    def build_static(self):
        self.landmarks = []
        excl = []
        for lm in P.LANDMARKS:
            x, y = P.w(*lm["px"])
            bx0, by0, bx1, by1 = lm["bbox"]
            r = affinity.rotate(box(bx0 - 5, by0 - 5, bx1 + 5, by1 + 5), lm["rot"], origin=(0, 0))
            r = affinity.translate(r, x, y)
            excl.append(r)
            self.landmarks.append({"key": lm["key"], "blend": lm["blend"], "coll": lm["coll"], "root": lm["root"],
                                   "x": round(x, 2), "y": round(y, 2), "rot": lm["rot"],
                                   "foot": ccw_coords(r)})
        self.lm_excl = unary_union(excl)
        # cells
        self.cells = []
        cpolys, ppolys = [], []
        self.parks = [(pk["name"], pk["kind"], Polygon(P.wpts(pk["pts"]))) for pk in P.PARKS]
        park_union = unary_union([p for _, _, p in self.parks])
        for cid, name, zone, (px, py), wpx, hpx, r in P.CELLS:
            cx, cy = P.w(px, py)
            if cid in P.CELL_OVERRIDE:
                cw, ch = P.CELL_OVERRIDE[cid]
                ang = P.LANDMARKS[0]["rot"]
            else:
                cw, ch = wpx * P.PX * P.CELL_SCALE, hpx * P.PX * P.CELL_SCALE
                ang = P.wang(r)
            c = rot_rect(cx, cy, cw / 2, ch / 2, ang, chamfer=min(cw, ch) * 0.16)
            in_park = park_union.contains(Point(cx, cy))
            plaza = c.buffer(12, join_style="mitre", mitre_limit=3) if cid != "E1" else c
            cpolys.append(c)
            ppolys.append(plaza)
            ov = c.intersection(self.lm_excl).area if cid != "E1" else 0.0
            if ov > 1.0:
                self.report["warnings"].append("cell %s overlaps landmark by %.0f m2" % (cid, ov))
            if c.intersection(self.river).area > 1.0:
                self.report["warnings"].append("cell %s in river" % cid)
            self.cells.append({"id": cid, "name": name, "zone": zone, "x": round(cx, 2), "y": round(cy, 2),
                               "w": round(cw, 1), "h": round(ch, 1), "ang": round(ang, 2), "park": in_park,
                               "poly": ccw_coords(c), "plaza": ccw_coords(plaza)})
        for i in range(len(cpolys)):
            for j in range(i + 1, len(cpolys)):
                if cpolys[i].intersects(cpolys[j]):
                    self.report["warnings"].append("cells %s/%s overlap" % (self.cells[i]["id"], self.cells[j]["id"]))
        self.cell_union = unary_union(cpolys)
        # E1 is inside the Rynek landmark: its plaza is the landmark's own square
        self.plaza_union = unary_union([p for p, c in zip(ppolys, self.cells) if c["id"] != "E1"]).difference(
            self.lm_excl)
        self.ponds = unary_union([affinity.scale(Point(*P.w(cx, cy)).buffer(1.0, quad_segs=12),
                                                 rx * P.PX, ry * P.PX) for cx, cy, rx, ry in P.PONDS])
        self.park_union = park_union

    # ---------------- streets
    def extend_ends(self, pts):
        fx0, fy0, fx1, fy1 = P.PROTO_FRAME
        out = [list(p) for p in pts]

        def edge(p):
            return p[0] <= fx0 + 20 or p[0] >= fx1 - 20 or p[1] <= fy0 + 20 or p[1] >= fy1 - 20

        if edge(out[-1]):
            a, b = out[-2], out[-1]
            d = math.hypot(b[0] - a[0], b[1] - a[1])
            out.append([b[0] + (b[0] - a[0]) / d * 2500, b[1] + (b[1] - a[1]) / d * 2500])
        if edge(out[0]):
            a, b = out[1], out[0]
            d = math.hypot(b[0] - a[0], b[1] - a[1])
            out.insert(0, [b[0] + (b[0] - a[0]) / d * 2500, b[1] + (b[1] - a[1]) / d * 2500])
        return out

    def build_main_streets(self):
        self.main_streets = []
        bufs, carr = [], []
        for name, pts, width, trees in P.STREETS:
            wp = P.wpts(self.extend_ends(pts))
            ln = LineString(wp)
            b = ln.buffer(width / 2.0, cap_style="flat", join_style="round", quad_segs=4)
            # do not let streets cross the river (bridges are separate)
            b = b.difference(self.river.buffer(26))
            bufs.append(b)
            carr.append(ln.buffer(width / 2.0 - 7.0, cap_style="flat", join_style="round", quad_segs=4))
            self.main_streets.append({"name": name, "pts": [[round(x, 1), round(y, 1)] for x, y in wp],
                                      "w": width, "trees": trees})
        # bridges + approaches
        self.bridges = []
        for br in P.BRIDGES:
            _, y = P.w(br["x"], br["y"])
            ln = LineString([(self.WB.bounds[0], y), (self.WB.bounds[2], y)])
            cut = ln.intersection(self.river)
            segs = [g for g in getattr(cut, "geoms", [cut]) if not g.is_empty]
            if not segs:
                self.report["warnings"].append("bridge %s misses river" % br["name"])
                continue
            seg = max(segs, key=lambda g: g.length)
            xa, xb = sorted([seg.coords[0][0], seg.coords[-1][0]])
            x0, x1 = xa - 30.0, xb + 30.0
            self.bridges.append({"name": br["name"], "kind": br["kind"], "y": round(y, 2),
                                 "x0": round(x0, 2), "x1": round(x1, 2), "bank0": round(xa, 2),
                                 "bank1": round(xb, 2), "w": br["w"]})
            # east approach to Targowa and west stub across the boulevard
            tx = P.w(1300, 0)[0]
            ap = LineString([(xa - 60, y), (xa, y)]).union(LineString([(xb, y), (max(tx, xb + 80), y)]))
            bufs.append(ap.buffer(br["w"] / 2 + 3, cap_style="flat"))
            carr.append(ap.buffer(br["w"] / 2 - 3, cap_style="flat"))
        self.main_buf = unary_union(bufs + [self.riverside_road])
        rr_carr = self.river.buffer(44, quad_segs=6).difference(self.river.buffer(32, quad_segs=6))
        self.main_carr = unary_union(carr + [rr_carr.intersection(self.WB)])

    # ---------------- districts
    def build_districts(self):
        rynek = P.w(*P.LANDMARKS[0]["px"])
        barb = P.w(*P.LANDMARKS[2]["px"])
        zamek = P.w(*P.LANDMARKS[1]["px"])
        # Old + New Town inside the medieval wall arc: one smooth hull, not three bubbles
        old = unary_union([Point(rynek).buffer(230, quad_segs=12), Point(barb).buffer(150, quad_segs=8),
                           Point(zamek).buffer(130, quad_segs=8)]).buffer(70, quad_segs=8).buffer(-70, quad_segs=8)
        old = old.difference(self.river.buffer(28)).intersection(self.WB)
        self.old_core = old
        regs = [("old_core", "old", 4.0, old)]
        claimed = old
        for r in P.REGIONS:
            g = Polygon(P.wpts(r["pts"])).buffer(0).difference(claimed)
            regs.append((r["name"], r["pal"], P.wang(r["ang"]), g))
        proto_union = unary_union([g for _, _, _, g in regs])
        # background fill split by bank / latitude
        bg = self.WB.difference(proto_union).difference(self.river)
        west = bg.intersection(self.west_side)
        east = bg.difference(self.west_side)
        south = west.intersection(box(-9000, -9000, 9000, -560))
        far_w = west.difference(south).intersection(box(-9000, -9000, -1100, 9000))
        city_bg = west.difference(south).difference(far_w)
        regs += [("bg_city", "city", 0.0, city_bg), ("bg_south", "south", 0.0, south),
                 ("bg_wola", "wola", 0.0, far_w), ("bg_praga", "praga", 2.0, east)]
        self.regions = regs

    def build_secondary_streets(self):
        sec_bufs, sec_carr = [], []
        for ri, (name, pal, ang, geom) in enumerate(self.regions):
            if geom.is_empty:
                continue
            D = DISTRICT[pal]
            rng = random.Random(SEED + ri * 101)
            a = math.radians(ang)
            # work in the rotated frame
            loc = affinity.rotate(geom, -ang, origin=(0, 0))
            x0, y0, x1, y1 = loc.bounds
            us, vs = [], []
            u = x0 - rng.uniform(0, D["bu"][1])
            while u < x1:
                us.append(u)
                u += rng.uniform(*D["bu"])
            v = y0 - rng.uniform(0, D["bv"][1])
            while v < y1:
                vs.append(v)
                v += rng.uniform(*D["bv"])
            lines = []
            for i, u in enumerate(us):
                for j in range(len(vs) - 1):
                    if rng.random() < D["drop"]:
                        continue
                    lines.append([(u, vs[j]), (u, vs[j + 1])])
            for j, v in enumerate(vs):
                for i in range(len(us) - 1):
                    if rng.random() < D["drop"] * 0.6:
                        continue
                    lines.append([(us[i], v), (us[i + 1], v)])
            ca, sa = math.cos(a), math.sin(a)
            segs = []
            for ln in lines:
                pts = [(x * ca - y * sa, x * sa + y * ca) for x, y in ln]
                pts = warp_line(pts, D["warp"], lam=55.0 if pal == "old" else 90.0, seed=ri * 1.7)
                segs.append(LineString(pts))
            # district boundary road
            for pg in polys(geom):
                segs.append(LineString(list(pg.exterior.coords)))
            ml = unary_union(segs).intersection(geom.buffer(D["sw"]))
            half = D["sw"] / 2.0
            sec_bufs.append(ml.buffer(half, cap_style="flat", join_style="mitre", mitre_limit=2.5))
            sec_carr.append(ml.buffer(max(3.0, half - (2.5 if pal == "old" else 4.0)), cap_style="flat",
                                      join_style="mitre", mitre_limit=2.5))
        self.sec_buf = unary_union(sec_bufs)
        self.sec_carr = unary_union(sec_carr)

    # ---------------- blocks
    def build_blocks(self):
        streets = unary_union([self.main_buf, self.sec_buf])
        self.street_union = streets
        blocked = unary_union([streets, self.river.buffer(28), self.park_union, self.plaza_union,
                               self.lm_excl, self.ponds, self.cell_union.buffer(10)])
        self.blocks = []
        for ri, (name, pal, ang, geom) in enumerate(self.regions):
            avail = geom.difference(blocked)
            for pg in polys(avail):
                for q in self.split_large(pg, pal):
                    if q.area < 220:
                        continue
                    self.blocks.append((pal, name, ang, q))
        if self.lanes:
            lanes = unary_union(self.lanes)
            self.sec_buf = unary_union([self.sec_buf, lanes])
            self.sec_carr = unary_union([self.sec_carr, lanes.buffer(-2.0)])
        self.report["blocks"] = len(self.blocks)

    MAX_BLOCK = {"old": 4800.0, "city": 17000.0, "wola": 21000.0, "south": 21000.0, "praga": 15000.0}

    def split_large(self, pg, pal, depth=0):
        """Percolating street drops can merge cells into huge blocks: cut them with a lane
        across the long axis until every block is a believable size."""
        if pg.area <= self.MAX_BLOCK[pal] or depth > 10:
            return [pg]
        mrr = shapely.oriented_envelope(pg)
        cs = list(mrr.exterior.coords)[:4]
        e0, e1 = math.dist(cs[0], cs[1]), math.dist(cs[1], cs[2])
        if e0 >= e1:
            a, b, L = cs[0], cs[1], e0
        else:
            a, b, L = cs[1], cs[2], e1
        ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
        c = mrr.centroid
        t = random.Random(int(abs(c.x * 7 + c.y * 13))).uniform(-0.12, 0.12) * L
        mx, my = c.x + ux * t, c.y + uy * t
        cut = LineString([(mx - uy * 5000, my + ux * 5000), (mx + uy * 5000, my - ux * 5000)])
        lane_w = 11.0 if pal == "old" else 15.0
        lane = cut.buffer(lane_w / 2.0, cap_style="flat").intersection(pg.buffer(lane_w))
        self.lanes.append(lane)
        out = []
        for q in polys(pg.difference(lane)):
            out.extend(self.split_large(q, pal, depth + 1))
        return out

    # ---------------- building records
    def add_building(self, poly, h, g, s, bay, roof, rh, hi, col, rcol, mat, kind, lod, dome=-1):
        pts = ccw_coords(poly)
        q = Polygon(pts) if len(pts) >= 3 else None
        if q is None or not q.is_valid or q.area < 8.0:
            # rounding / slivers can leave a bow-tie: keep the largest valid piece as a flat-roof volume
            fixed = polys(shapely.make_valid(poly).buffer(0)) if poly is not None else []
            fixed = [f for f in fixed if f.area >= 8.0]
            if not fixed:
                return None
            q = max(fixed, key=lambda x: x.area)
            pts = ccw_coords(q)
            if len(pts) < 3 or not Polygon(pts).is_valid:
                return None
            roof, hi, dome = "flat", 0, -1
        if hi >= len(pts):
            hi = 0
        if dome >= len(pts):
            dome = -1
        rec = {"p": pts, "h": round(h, 2), "g": round(g, 2), "s": round(s, 2), "b": round(bay, 2),
               "r": roof, "rh": round(rh, 2), "hi": hi, "c": [round(c, 3) for c in col],
               "rc": [round(c, 3) for c in rcol], "m": mat, "k": kind, "lod": lod, "dome": dome, "fw": []}
        self.buildings.append(rec)
        return rec

    def roof_for(self, poly, pal, rule, rng, front_idx):
        n = len(ccw_coords(poly))
        if n == 4 and front_idx >= 0:
            return pick(rng, rule["roof"])
        return "flat"

    def front_edge(self, poly, ext_line):
        pts = ccw_coords(poly)
        best, bi = 1e9, -1
        for i in range(len(pts)):
            a, b = pts[i], pts[(i + 1) % len(pts)]
            if math.hypot(b[0] - a[0], b[1] - a[1]) < 3.0:
                continue
            m = Point((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
            d = ext_line.distance(m)
            if d < best:
                best, bi = d, i
        return bi if best < 1.0 else -1

    def merge_slivers(self, lots, min_area=45.0, min_thin=1.6):
        lots = [l for l in lots if l.area > 0.5]
        changed = True
        while changed:
            changed = False
            for i, l in enumerate(lots):
                thin = l.area / max(l.length, 1e-6)
                if l.area < min_area or thin < min_thin:
                    best, bj = 0.0, -1
                    for j, m in enumerate(lots):
                        if j == i:
                            continue
                        sh = l.boundary.intersection(m.boundary).length
                        if sh > best:
                            best, bj = sh, j
                    if bj >= 0 and best > 0.5:
                        lots[bj] = unary_union([lots[bj], l]).buffer(0.01, join_style="mitre").buffer(
                            -0.01, join_style="mitre")
                        lots.pop(i)
                        changed = True
                        break
        return lots

    def tenement_block(self, pal, pg, ang, lod, rng):
        """Lot-based Warsaw tenement block.

        Every street frontage is cut into narrow lots.  Each lot reaches `lot_d` metres into the
        block and is built as a front house (kamienica frontowa), optional side wing(s) along the
        lot line (oficyna boczna) and an optional rear house (oficyna tylna), which leaves the
        typical 8-15 m 'well' courtyard (studnia) per lot instead of one big empty block centre.
        """
        rule = TEN[pal]
        depth = rng.uniform(*rule["depth"])
        if pal != "old" and rng.random() < 0.7:
            c = rng.uniform(3.5, 6.0)
            q = pg.buffer(-c, join_style="mitre", mitre_limit=5).buffer(c, join_style="bevel")
            if not q.is_empty and q.area > 0.8 * pg.area:
                pg = polys(q)[0] if isinstance(q, MultiPolygon) else q
        pg = clean(orient(pg, 1.0), 0.4)
        if not isinstance(pg, Polygon) or pg.area < 200:
            return
        self.ten_blocks.append(pg)
        ext = pg.exterior
        lot_d = rng.uniform(*rule["lot"])
        inner = pg.buffer(-depth, join_style="mitre", mitre_limit=3)
        solid = inner.is_empty or inner.area < 160
        ring = pg if solid else pg.difference(inner)
        core = pg.buffer(-lot_d, join_style="mitre", mitre_limit=3)
        if core.area < 250:
            core = Polygon()
        zone = pg if core.is_empty else pg.difference(core)
        pts = list(orient(pg, 1.0).exterior.coords)[:-1]
        n = len(pts)
        cuts = []
        base_st = rule["st"][0] + (rule["st"][1] - rule["st"][0]) * (0.5 + 0.5 * noise2(pts[0][0], pts[0][1], 3.1))
        longest = max(range(n), key=lambda i: math.dist(pts[i], pts[(i + 1) % n]))

        def convex(p0, p1, p2):
            return (p1[0] - p0[0]) * (p2[1] - p1[1]) - (p1[1] - p0[1]) * (p2[0] - p1[0]) > 0

        for i in range(n):
            a, b = pts[i], pts[(i + 1) % n]
            L = math.dist(a, b)
            if L < 6.0:
                continue
            if solid and i != longest and L < 2.2 * rule["front"][1]:
                continue
            ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
            nx, ny = -uy, ux
            prev, nxt = pts[i - 1], pts[(i + 2) % n]
            sa = depth + rng.uniform(2.5, 8.0) if convex(prev, a, b) else rng.uniform(1.0, 3.0)
            sb = depth + rng.uniform(2.5, 8.0) if convex(a, b, nxt) else rng.uniform(1.0, 3.0)
            s = sa
            reach = lot_d + 2.0 if not (solid or core.is_empty) else 400.0
            while s < L - sb - rule["front"][0] * 0.6:
                px_, py_ = a[0] + ux * s, a[1] + uy * s
                cuts.append(LineString([(px_ - nx * 1.5, py_ - ny * 1.5), (px_ + nx * reach, py_ + ny * reach)]))
                s += rng.uniform(*rule["front"])
        cut_ml = MultiLineString(cuts) if cuts else None
        pieces = []
        for zp in polys(zone):
            if cut_ml is not None:
                try:
                    pieces.extend(polys(split(zp, cut_ml)))
                except Exception:
                    pieces.append(zp)
            else:
                pieces.append(zp)
        lots = self.merge_slivers(pieces, 60.0, 2.2)
        cut_union = unary_union(cuts).buffer(0.25) if cuts else Polygon()
        rear_band = pg.buffer(-(lot_d - rng.uniform(8.5, 11.0)), join_style="mitre", mitre_limit=3)
        built_back = []
        for lot in lots:
            front = lot.intersection(ring)
            back = lot.difference(ring) if not solid else Polygon()
            for fp in polys(front):
                if fp.area <= 30:
                    continue
                for fq in polys(clean(fp, 0.3)):
                    if fq.area > 30:
                        self.front_house(pal, rule, fq, ext, base_st, lod, rng)
            if back.is_empty or back.area < 60:
                continue
            # ---- side wings along the lot lines
            side_lines = []
            if not cut_union.is_empty:
                sides = back.boundary.intersection(cut_union)
                for g in getattr(sides, "geoms", [sides]):
                    if not g.is_empty and g.geom_type == "LineString" and g.length > 6.0:
                        side_lines.append(g)
            wings = []
            nwing = 0
            if side_lines and rng.random() < rule["wing"]:
                nwing = 2 if (len(side_lines) > 1 and rng.random() < rule["wing2"]) else 1
            rng.shuffle(side_lines)
            ww = rng.uniform(6.5, 8.5)
            for sl in side_lines[:nwing]:
                wpg = back.intersection(sl.buffer(ww, cap_style="flat"))
                wpg = max(polys(wpg), key=lambda x: x.area) if polys(wpg) else None
                if wpg is not None and wpg.area > 50:
                    wings.append(wpg)
            # ---- rear house closing the lot
            rear = None
            if rng.random() < rule["rear"]:
                rp = back.intersection(rear_band)
                for wg in wings:
                    rp = rp.difference(wg)
                rp = max(polys(rp), key=lambda x: x.area) if polys(rp) else None
                if rp is not None and rp.area > 50:
                    rear = rp
            yard = back
            for x in wings + ([rear] if rear is not None else []):
                yard = yard.difference(x)
            # a well narrower than ~6 m is not a courtyard: give the back plot to one building
            if (wings or rear) and not yard.is_empty and yard.area / max(yard.length, 1e-6) < 1.6:
                wings, rear = [back], None
                yard = Polygon()
            st_b = max(2, int(round(base_st)) - rng.choice([0, 0, 1]))
            for wpg in wings:
                for wq in polys(clean(wpg, 0.3)):
                    if wq.area < 40:
                        continue
                    self.back_house(pal, rule, wq, st_b, "wing", lod, rng, lot.centroid)
                    built_back.append(wq)
            if rear is not None:
                for rq in polys(clean(rear, 0.3)):
                    if rq.area < 40:
                        continue
                    self.back_house(pal, rule, rq, max(2, st_b - rng.choice([0, 1])), "rear", lod, rng,
                                    lot.centroid)
                    built_back.append(rq)
            if not yard.is_empty:
                self.scatter_trees(yard.buffer(-2.0), 9.0, 0.10 if pal != "old" else 0.05, (0.5, 0.75), rng, tint=1)
        # ---- shared block centre: sheds (komorki) and a few trees
        if not core.is_empty:
            free = core.buffer(-2.0)
            if built_back:
                free = free.difference(unary_union(built_back).buffer(2.0))
            for fq in polys(free):
                if fq.area < 120:
                    continue
                mrr = shapely.oriented_envelope(fq)
                cs = list(mrr.exterior.coords)[:4]
                e0, e1 = math.dist(cs[0], cs[1]), math.dist(cs[1], cs[2])
                o, u = (cs[0], cs[1]) if e0 >= e1 else (cs[1], cs[2])
                L = max(e0, e1)
                ux, uy = (u[0] - o[0]) / L, (u[1] - o[1]) / L
                vx, vy = -uy, ux
                c = fq.representative_point()
                t = rng.uniform(1.0, 4.0)
                sheds = []
                while t < L - 6:
                    lw = rng.uniform(6.0, 14.0)
                    dp = rng.uniform(4.0, 6.0)
                    off = ((c.x - o[0]) * vx + (c.y - o[1]) * vy) + rng.uniform(-6, 6)
                    shp = Polygon([(o[0] + ux * t + vx * off, o[1] + uy * t + vy * off),
                                   (o[0] + ux * (t + lw) + vx * off, o[1] + uy * (t + lw) + vy * off),
                                   (o[0] + ux * (t + lw) + vx * (off + dp), o[1] + uy * (t + lw) + vy * (off + dp)),
                                   (o[0] + ux * t + vx * (off + dp), o[1] + uy * t + vy * (off + dp))])
                    if fq.contains(shp) and rng.random() < 0.6:
                        sheds.append(orient(shp, 1.0))
                    t += lw + rng.uniform(3.0, 9.0)
                for shp in sheds:
                    col = jit(rng, rng.choice(FACADE["brick"] if rng.random() < 0.5 else FACADE["work"]))
                    self.add_building(shp, rng.uniform(2.8, 3.6), 3.0, 3.0, 3.0, "shed", 0.9, 0, col,
                                      jit(rng, ROOF[rng.choice(["tar", "tin_dark", "rust"])]), "brick", "shed", lod)
                rest = fq.difference(unary_union(sheds).buffer(2.0)) if sheds else fq
                self.scatter_trees(rest, 9.0, 0.35, (0.6, 0.95), rng, tint=1)

    def front_house(self, pal, rule, lp, ext, base_st, lod, rng):
        st = int(round(base_st + rng.choice([-1, 0, 0, 0, 1])))
        if pal == "city" and rng.random() < 0.10:
            st = rng.choice([2, 3])            # an older low house between the tenements
        st = max(2, min(st, rule["st"][1] + 1))
        g = rng.uniform(*rule["g"])
        s = rng.uniform(*rule["s"])
        h = g + (st - 1) * s
        fi = self.front_edge(lp, ext)
        npts = len(ccw_coords(lp))
        roof = pick(rng, rule["roof"]) if (npts == 4 and fi >= 0) else "flat"
        if fi < 0:
            fi = 0
        fpal = rule["pal"]
        if pal in ("praga", "wola") and rng.random() < 0.45:
            fpal = "brick"
        col = jit(rng, rng.choice(FACADE[fpal]))
        rc = jit(rng, ROOF[rng.choice(rule["rpal"])], 0.025)
        dome = -1
        if npts > 4 and pal == "city" and st >= 5 and rng.random() < 0.22:
            dome = self.corner_vertex(lp, ext)
        bay = rng.uniform(3.1, 3.7) if pal != "old" else rng.uniform(2.6, 3.0)
        mat = "brick" if fpal == "brick" else ("old" if pal == "old" else "plaster")
        return self.add_building(lp, h, g, s, bay, roof, rng.uniform(*rule["rh"]), fi, col, rc, mat,
                                 "tenement", lod, dome)

    def back_house(self, pal, rule, wq, st, kind, lod, rng, lot_c):
        g = rng.uniform(*rule["g"]) - 0.4
        s = rng.uniform(*rule["s"])
        h = g + (st - 1) * s
        quad = len(ccw_coords(wq)) == 4
        roof = "shed" if (quad and rng.random() < 0.65) else "flat"
        fpal = rule["pal"] if not (pal in ("praga", "wola", "city") and rng.random() < 0.35) else "brick"
        col = jit(rng, rng.choice(FACADE[fpal]))
        rc = jit(rng, ROOF[rng.choice(rule["rpal"])], 0.025)
        hi = self.far_edge(wq, wq.centroid if kind == "rear" else lot_c) if roof == "shed" else 0
        return self.add_building(wq, h, g, s, rng.uniform(3.0, 3.5), roof, rng.uniform(1.6, 2.4), hi, col, rc,
                                 "brick" if fpal == "brick" else "plaster", kind, lod)

    def far_edge(self, poly, c):
        pts = ccw_coords(poly)
        best, bi = -1.0, 0
        for i in range(len(pts)):
            a, b = pts[i], pts[(i + 1) % len(pts)]
            if math.dist(a, b) < 4.0:
                continue
            d = Point((a[0] + b[0]) / 2, (a[1] + b[1]) / 2).distance(c)
            if d > best:
                best, bi = d, i
        return bi

    def corner_vertex(self, lot, block):
        pts = ccw_coords(lot)
        ext = getattr(block, "exterior", block)
        best, bi = 1e9, -1
        verts = list(ext.coords)
        for i, p in enumerate(pts):
            d = min(math.dist(p, v) for v in verts)
            if d < best:
                best, bi = d, i
        return bi if best < 1.5 else -1

    def villa_block(self, pal, pg, ang, lod, rng):
        inner = pg.buffer(-7.0)
        if inner.is_empty:
            return
        a = math.radians(ang)
        ca, sa = math.cos(a), math.sin(a)
        x0, y0, x1, y1 = affinity.rotate(inner, -ang, origin=(0, 0)).bounds
        houses = []
        step = rng.uniform(30, 38)
        y = y0 + step / 2
        while y < y1:
            x = x0 + step / 2 + rng.uniform(-3, 3)
            while x < x1:
                hw, hd = rng.uniform(6.0, 8.5), rng.uniform(5.0, 6.8)
                lx, ly = x + rng.uniform(-3, 3), y + rng.uniform(-3, 3)
                pts = [(lx - hw, ly - hd), (lx + hw, ly - hd), (lx + hw, ly + hd), (lx - hw, ly + hd)]
                h = Polygon([(px_ * ca - py_ * sa, px_ * sa + py_ * ca) for px_, py_ in pts])
                if inner.contains(h):
                    houses.append(h)
                x += step + rng.uniform(-4, 4)
            y += step + rng.uniform(-4, 4)
        for h in houses:
            st = rng.choice([2, 2, 3])
            g, s = 3.4, 3.1
            self.add_building(h, g + (st - 1) * s, g, s, 3.0, "hip", rng.uniform(3.0, 4.2), 0,
                              jit(rng, rng.choice(FACADE["villa"])),
                              jit(rng, ROOF[rng.choice(["tile", "tile_dark", "slate", "tile"])]),
                              "plaster", "villa", lod)
        garden = pg.buffer(-2.0).difference(unary_union(houses).buffer(3.5) if houses else Polygon())
        self.scatter_trees(garden, 9.5, 0.55, (0.7, 1.15), rng, tint=0)

    def modern_block(self, pal, pg, ang, lod, rng):
        inner = pg.buffer(-5.0)
        if inner.is_empty:
            return
        mrr = shapely.oriented_envelope(inner)
        cs = list(mrr.exterior.coords)[:4]
        e0, e1 = math.dist(cs[0], cs[1]), math.dist(cs[1], cs[2])
        if e0 >= e1:
            o, u, v, L, W = cs[0], cs[1], cs[3], e0, e1
        else:
            o, u, v, L, W = cs[1], cs[2], cs[0], e1, e0
        ux, uy = (u[0] - o[0]) / L, (u[1] - o[1]) / L
        vx, vy = (v[0] - o[0]) / W, (v[1] - o[1]) / W
        n = max(1, int((W + 22) / 40.0))
        slabs = []
        for k in range(n):
            off = (k + 0.5) * W / n - 6.0
            l0, l1 = L * rng.uniform(0.04, 0.12), L * rng.uniform(0.85, 0.96)
            pts = [(o[0] + ux * l0 + vx * off, o[1] + uy * l0 + vy * off),
                   (o[0] + ux * l1 + vx * off, o[1] + uy * l1 + vy * off),
                   (o[0] + ux * l1 + vx * (off + 12), o[1] + uy * l1 + vy * (off + 12)),
                   (o[0] + ux * l0 + vx * (off + 12), o[1] + uy * l0 + vy * (off + 12))]
            sp = Polygon(pts).intersection(inner)
            sp = max(polys(sp), key=lambda x: x.area) if polys(sp) else None
            if sp is None or sp.area < 200:
                continue
            sp = clean(sp, 0.3)
            slabs.append(sp)
            st = rng.choice([4, 5, 5, 6, 7])
            g, s = 3.6, 3.05
            self.add_building(sp, g + (st - 1) * s, g, s, 2.9, "flat", 0.0, 0,
                              jit(rng, rng.choice(FACADE["modern"])), jit(rng, ROOF["tar"]),
                              "modern", "modern", lod)
        rest = pg.buffer(-2.0).difference(unary_union(slabs).buffer(5.0) if slabs else Polygon())
        self.scatter_trees(rest, 10.0, 0.45, (0.7, 1.1), rng, tint=0)

    def industrial_block(self, pal, pg, ang, lod, rng):
        inner = pg.buffer(-6.0)
        if inner.is_empty or inner.area < 600:
            return self.tenement_block("wola" if pal != "praga" else "praga", pg, ang, lod, rng)
        mrr = shapely.oriented_envelope(inner)
        cs = list(mrr.exterior.coords)[:4]
        e0, e1 = math.dist(cs[0], cs[1]), math.dist(cs[1], cs[2])
        if e0 >= e1:
            o, u, v, L, W = cs[0], cs[1], cs[3], e0, e1
        else:
            o, u, v, L, W = cs[1], cs[2], cs[0], e1, e0
        ux, uy = (u[0] - o[0]) / L, (u[1] - o[1]) / L
        vx, vy = (v[0] - o[0]) / W, (v[1] - o[1]) / W
        halls = []
        t = 0.0
        while t < L - 12:
            hw = rng.uniform(20.0, 34.0)
            t1 = min(L, t + hw)
            ins = rng.uniform(0, 6)
            pts = [(o[0] + ux * t + vx * ins, o[1] + uy * t + vy * ins),
                   (o[0] + ux * t1 + vx * ins, o[1] + uy * t1 + vy * ins),
                   (o[0] + ux * t1 + vx * (W - ins), o[1] + uy * t1 + vy * (W - ins)),
                   (o[0] + ux * t + vx * (W - ins), o[1] + uy * t + vy * (W - ins))]
            hp = Polygon(pts).intersection(inner)
            hp = max(polys(hp), key=lambda x: x.area) if polys(hp) else None
            if hp is not None and hp.area > 250:
                halls.append(clean(hp, 0.3))
            t = t1 + rng.uniform(7.0, 12.0)
        best = None
        for hp in halls:
            quad = len(ccw_coords(hp)) == 4
            multi = rng.random() < 0.35
            if multi:
                st, g, s = 3, 4.6, 4.2           # multi-storey factory (can carry a chimney)
                roof = "flat"
            else:
                st, g, s = 1, rng.uniform(8.0, 11.0), 4.0
                roof = "saw" if quad else "flat"
            h = g + (st - 1) * s
            rec = self.add_building(hp, h, g, s, rng.uniform(4.5, 6.0), roof, rng.uniform(2.6, 3.4),
                                    self.far_edge(hp, Point(o)) if roof == "saw" else 0,
                                    jit(rng, rng.choice(FACADE["brick"])),
                                    jit(rng, ROOF[rng.choice(["tar", "tin_dark", "tin"])]),
                                    "brick", "hall", lod)
            if rec and multi and (best is None or hp.area > best[1].area):
                best = (rec, hp)
        if best and rng.random() < 0.85:
            rec, hp = best
            c = hp.buffer(-4.0)
            if not c.is_empty:
                pt = c.representative_point()
                self.chimneys.append({"x": round(pt.x, 2), "y": round(pt.y, 2), "z0": rec["h"],
                                      "h": round(rng.uniform(26.0, 40.0), 1), "w": round(rng.uniform(2.8, 3.6), 2)})

    def skwer_block(self, pal, pg, ang, lod, rng):
        self.skwers.append(pg)
        self.scatter_trees(pg.buffer(-3.0), 9.0, 0.7, (0.75, 1.2), rng, tint=0)

    # ---------------- trees
    def scatter_trees(self, geom, spacing, prob, size, rng, tint=0, mask=None):
        for pg in polys(geom):
            if pg.area < 30:
                continue
            x0, y0, x1, y1 = pg.bounds
            prep = shapely.prepared.prep(pg) if hasattr(shapely, "prepared") else None
            y = y0 + rng.uniform(0, spacing)
            while y < y1:
                x = x0 + rng.uniform(0, spacing)
                while x < x1:
                    if rng.random() < prob:
                        px_, py_ = x + rng.uniform(-spacing * 0.35, spacing * 0.35), y + rng.uniform(-spacing * 0.35, spacing * 0.35)
                        pt = Point(px_, py_)
                        if (prep.contains(pt) if prep else pg.contains(pt)) and (mask is None or mask(px_, py_)):
                            self.trees.append([round(px_, 2), round(py_, 2), round(rng.uniform(*size), 3), tint])
                    x += spacing
                y += spacing

    def park_trees(self):
        rng = random.Random(SEED + 7)
        keepout = unary_union([self.main_carr, self.sec_carr, self.plaza_union, self.cell_union.buffer(8),
                               self.lm_excl, self.ponds.buffer(4)])
        for name, kind, pg in self.parks:
            area = pg.difference(keepout)
            if kind == "forest":
                self.scatter_trees(area, 8.5, 0.82, (0.85, 1.35), rng, tint=0,
                                   mask=lambda x, y: noise2(x * 2.3, y * 2.3, 1.0) > -0.55)
            elif kind == "garden":
                self.scatter_trees(area, 10.5, 0.62, (0.8, 1.25), rng, tint=0,
                                   mask=lambda x, y: noise2(x * 3.1, y * 3.1, 2.0) > -0.35)
            else:   # 1939: Pole Mokotowskie was the Mokotow airfield — open grass, tree clumps at the rim
                rim = pg.difference(pg.buffer(-26))
                self.scatter_trees(rim.difference(keepout), 9.0, 0.6, (0.8, 1.2), rng, tint=0)
        for pg in self.skwers:
            pass

    def avenue_trees(self):
        rng = random.Random(SEED + 9)
        keep = unary_union([self.plaza_union, self.cell_union.buffer(6), self.lm_excl, self.river.buffer(30),
                            self.sec_carr, self.ponds])
        others = self.main_carr
        for st in self.main_streets:
            if not st["trees"]:
                continue
            ln = LineString(st["pts"]).intersection(CORE.buffer(600))
            for part in getattr(ln, "geoms", [ln]):
                if part.is_empty or part.length < 20:
                    continue
                for side in (-1, 1):
                    off = part.offset_curve(side * (st["w"] / 2.0 - 4.2))
                    for o in getattr(off, "geoms", [off]):
                        L = o.length
                        d = 5.0
                        while d < L:
                            p = o.interpolate(d)
                            if not keep.contains(p) and not others.contains(p):
                                self.trees.append([round(p.x, 2), round(p.y, 2), round(rng.uniform(0.8, 1.05), 3), 2])
                            d += 11.0
        # river banks: tree row on the left boulevard, wooded right bank
        left = self.boulevard.intersection(self.west_side)
        right = self.boulevard.difference(self.west_side)
        bk = unary_union([self.lm_excl, self.cell_union.buffer(8)] +
                         [box(b["x0"] - 5, b["y"] - b["w"], b["x1"] + 5, b["y"] + b["w"]) for b in self.bridges])
        edge = left.buffer(-6).difference(left.buffer(-10)).difference(bk)
        self.scatter_trees(edge, 11.0, 0.8, (0.8, 1.1), rng, tint=2)
        self.scatter_trees(right.buffer(-3).difference(bk), 8.0, 0.75, (0.85, 1.3), rng, tint=0)

    # ---------------- named buildings
    def place_specials(self):
        rng = random.Random(SEED + 13)
        for kind, name, anchor_px in P.SPECIALS:
            ax, ay = P.w(*anchor_px)
            A = Point(ax, ay)
            dims = {"church_twin": (34.0, 62.0), "church_single": (26.0, 52.0), "rotunda": (36.0, 40.0),
                    "tower": (30.0, 24.0), "theatre": (118.0, 64.0), "palace": (84.0, 24.0),
                    "gasworks": (150.0, 64.0)}[kind]
            Wd, Dp = dims
            # search the blocks near the anchor for the street edge that holds the footprint best
            best = None
            for pal, rname, rang, pg in self.blocks:
                dA = pg.distance(A)
                if dA > 220:
                    continue
                pts = list(orient(pg, 1.0).exterior.coords)[:-1]
                for i in range(len(pts)):
                    a, b = pts[i], pts[(i + 1) % len(pts)]
                    L = math.dist(a, b)
                    if L < Wd * 0.8:
                        continue
                    ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
                    t0 = (ax - a[0]) * ux + (ay - a[1]) * uy
                    for t in (t0, Wd / 2 + 1, L - Wd / 2 - 1, L / 2):
                        t = max(min(Wd / 2 + 1, L / 2), min(max(L - Wd / 2 - 1, L / 2), t))
                        org = (a[0] + ux * t, a[1] + uy * t)
                        foot = local_rect(org, math.atan2(uy, ux), -Wd / 2, 0.6, Wd / 2, 0.6 + Dp)
                        inside = foot.intersection(pg).area / foot.area
                        score = inside - Point(org).distance(A) / 600.0
                        if best is None or score > best[0]:
                            best = (score, inside, org, math.atan2(uy, ux), foot)
            if best is None:
                self.report["warnings"].append("special %s: no block nearby" % name)
                continue
            _, inside, org, ang, foot = best
            if inside < 0.86:
                self.report["warnings"].append("special %s only %.0f%% inside its block" % (name, inside * 100))
            # carve tenements under the footprint
            kill = foot.buffer(4.0)
            self.buildings = [bd for bd in self.buildings if not Polygon(bd["p"]).intersects(kill)]
            self.chimneys = [c for c in self.chimneys if not kill.contains(Point(c["x"], c["y"]))]
            self.trees = [tr for tr in self.trees if not kill.contains(Point(tr[0], tr[1]))]
            self.specials.append({"kind": kind, "name": name, "x": round(org[0], 2), "y": round(org[1], 2),
                                  "ang": round(math.degrees(ang), 2), "w": Wd, "d": Dp,
                                  "foot": ccw_coords(foot), "inside": round(inside, 3)})

    # ---------------- firewalls (needs the final building set)
    def mark_firewalls(self):
        geoms = [Polygon(b["p"]) for b in self.buildings]
        tree = shapely.STRtree(geoms)
        for bi, b in enumerate(self.buildings):
            pts = b["p"]
            n = len(pts)
            fw = []
            for i in range(n):
                a, c = pts[i], pts[(i + 1) % n]
                L = math.dist(a, c)
                if L < 0.5:
                    fw.append(0)
                    continue
                mx, my = (a[0] + c[0]) / 2, (a[1] + c[1]) / 2
                nx, ny = (c[1] - a[1]) / L, -(c[0] - a[0]) / L     # outward for CCW
                probe = Point(mx + nx * 0.8, my + ny * 0.8)
                hit = 0
                for j in tree.query(probe):
                    if j != bi and geoms[j].contains(probe):
                        hit = 1
                        break
                fw.append(hit)
            b["fw"] = fw

    # ---------------- ground
    def ground_layers(self):
        WB = self.WB
        plaza = self.plaza_union
        lawn_cells = unary_union([Polygon(c["plaza"]) for c in self.cells if c["park"]])
        plaza_paved = plaza.difference(lawn_cells)
        carr = unary_union([self.main_carr, self.sec_carr]).difference(plaza).difference(self.lm_excl).difference(
            self.river).intersection(WB)
        blocks = unary_union([pg for _, _, _, pg in self.blocks]).difference(unary_union(self.skwers)).intersection(WB)
        parks = unary_union([p for _, _, p in self.parks] + self.skwers).difference(
            unary_union([carr, plaza, self.lm_excl, self.ponds])).intersection(WB)
        left = self.boulevard.intersection(self.west_side).difference(carr)
        right = self.boulevard.difference(self.west_side).difference(carr)
        base = WB.difference(self.river)
        # special footprints get their own forecourt paving
        sp = unary_union([Polygon(s["foot"]).buffer(5) for s in self.specials])
        self.ground = {
            "base":     tri_layer(base, 0.0),
            "carriage": tri_layer(carr, 0.03),
            "courtyard": tri_layer(blocks.difference(sp), 0.15),
            "forecourt": tri_layer(sp.intersection(blocks.buffer(5)), 0.16),
            "park":     tri_layer(parks, 0.08),
            "plaza":    tri_layer(plaza_paved, 0.12),
            "plaza_lawn": tri_layer(lawn_cells.difference(self.lm_excl), 0.12),
            "boulevard": tri_layer(left, 0.06),
            "bank":     tri_layer(right, 0.05),
            "water":    tri_layer(unary_union([self.river, self.ponds]), -5.2),
        }
        self.river_outline = [ccw_coords(p) for p in polys(self.river)]
        self.pond_outline = [ccw_coords(p) for p in polys(self.ponds)]
        self.layer_geoms = {"carriage": carr, "courtyard": blocks, "park": parks, "plaza": plaza,
                            "boulevard": left, "bank": right}

    # ---------------- run
    def run(self):
        t0 = time.time()
        self.skwers = []
        self.ten_blocks = []
        self.lanes = []
        self.build_river()
        self.build_static()
        self.build_main_streets()
        self.build_districts()
        self.build_secondary_streets()
        self.build_blocks()
        rng = random.Random(SEED + 1)
        for pal, rname, ang, pg in self.blocks:
            lod = 0 if CORE.intersects(pg) else 1
            kind = pick(rng, BLOCK_MIX[pal])
            if pg.area < 900 and kind != "skwer":
                kind = "tenement"
            if self.old_core.contains(pg.representative_point()):
                kind = "tenement"
            {"tenement": self.tenement_block, "villa": self.villa_block, "modern": self.modern_block,
             "industrial": self.industrial_block, "skwer": self.skwer_block}[kind](pal, pg, ang, lod, rng)
        self.park_trees()
        self.avenue_trees()
        self.place_specials()
        self.mark_firewalls()
        self.ground_layers()
        # a tree must not stand in a building or on a carriageway
        bt = shapely.STRtree([Polygon(b["p"]).buffer(1.5) for b in self.buildings] +
                             [Polygon(s["foot"]).buffer(2) for s in self.specials])
        geoms = bt.geometries
        carr = shapely.prepared.prep(self.layer_geoms["carriage"])
        kept = []
        for tr in self.trees:
            p = Point(tr[0], tr[1])
            if carr.contains(p):
                continue
            if any(geoms[j].contains(p) for j in bt.query(p)):
                continue
            kept.append(tr)
        self.trees = kept
        self.report["seconds"] = round(time.time() - t0, 1)

    def stats(self):
        kinds = {}
        for b in self.buildings:
            kinds[b["k"]] = kinds.get(b["k"], 0) + 1
        roofs = {}
        for b in self.buildings:
            roofs[b["r"]] = roofs.get(b["r"], 0) + 1
        cmax = self.max_courtyard()
        hs = sorted(b["h"] for b in self.buildings)
        lod0 = sum(1 for b in self.buildings if b["lod"] == 0)
        return {"buildings": len(self.buildings), "lod0": lod0, "kinds": kinds, "roofs": roofs,
                "height_p10_p50_p90": [hs[len(hs) // 10], hs[len(hs) // 2], hs[len(hs) * 9 // 10]] if hs else [],
                "firewall_edges": sum(sum(b["fw"]) for b in self.buildings),
                "chimneys": len(self.chimneys), "trees": len(self.trees), "specials": len(self.specials),
                "cells": len(self.cells), "blocks": self.report.get("blocks"),
                "ground_tris": {k: len(v["t"]) for k, v in self.ground.items()},
                "courtyard_max_m2": round(cmax, 0),
                "courtyard_p50_p90": self.report.get("courtyard_p50_p90"),
                "courtyard_worst_at": self.report.get("courtyard_worst_at"),
                "warnings": self.report["warnings"], "seconds": self.report.get("seconds")}

    def max_courtyard(self):
        """Largest open patch inside any core tenement block: the 'no big courtyard' check (m2)."""
        geoms = [Polygon(b["p"]) for b in self.buildings if b["lod"] == 0]
        tree = shapely.STRtree(geoms)
        best, worst = 0.0, None
        areas = []
        for pg in self.ten_blocks:
            if not CORE.intersects(pg):
                continue
            near = [geoms[j] for j in tree.query(pg)]
            free = pg.difference(unary_union(near)) if near else pg
            free = free.buffer(-3.0).buffer(3.0)
            m = max([f.area for f in polys(free)] or [0.0])
            areas.append(m)
            if m > best:
                best, worst = m, pg.centroid
        areas.sort()
        self.report["courtyard_p50_p90"] = [round(areas[len(areas) // 2]), round(areas[len(areas) * 9 // 10])] if areas else []
        self.report["courtyard_worst_at"] = [round(worst.x), round(worst.y)] if worst else None
        return best

    def dump(self):
        os.makedirs(OUT_DIR, exist_ok=True)
        data = {"meta": {"px_m": P.PX, "origin_px": [P.OX, P.OY], "seed": SEED, "frame": "m, +X east, +Y north",
                         "world_bounds": P.WORLD_BOUNDS, "core": list(CORE.bounds)},
                "landmarks": self.landmarks, "cells": self.cells, "bridges": self.bridges,
                "streets": self.main_streets, "buildings": self.buildings, "chimneys": self.chimneys,
                "specials": self.specials, "trees": self.trees, "ground": self.ground,
                "river": self.river_outline, "ponds": self.pond_outline,
                "column": list(P.w(*P.SIGISMUND_COLUMN_PX))}
        with open(OUT_JSON, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        return os.path.getsize(OUT_JSON)


# ------------------------------------------------------------------ plan preview
def draw_plan(gen, path, view=(-1500.0, -1150.0, 1800.0, 1300.0), ppm=0.9):
    from PIL import Image, ImageDraw
    x0, y0, x1, y1 = view
    W, H = int((x1 - x0) * ppm), int((y1 - y0) * ppm)
    img = Image.new("RGB", (W, H), (205, 200, 188))
    d = ImageDraw.Draw(img, "RGBA")

    def tp(p):
        return ((p[0] - x0) * ppm, (y1 - p[1]) * ppm)

    def fill(geom, col, outline=None):
        for pg in polys(geom):
            d.polygon([tp(p) for p in pg.exterior.coords], fill=col, outline=outline)
            for h in pg.interiors:
                d.polygon([tp(p) for p in h.coords], fill=(205, 200, 188))

    L = gen.layer_geoms
    fill(L["courtyard"], (176, 168, 152))
    fill(L["carriage"], (92, 92, 90))
    fill(L["park"], (128, 150, 96))
    fill(L["boulevard"], (186, 180, 166))
    fill(L["bank"], (170, 160, 120))
    fill(gen.river, (70, 104, 128))
    fill(gen.ponds, (70, 104, 128))
    fill(L["plaza"], (214, 206, 186))
    for b in gen.bridges:
        d.rectangle([tp((b["x0"], b["y"] + b["w"] / 2)), tp((b["x1"], b["y"] - b["w"] / 2))], fill=(150, 144, 132))
    for lm in gen.landmarks:
        d.polygon([tp(p) for p in lm["foot"]], fill=(150, 120, 96, 200), outline=(60, 40, 30))
    for b in gen.buildings:
        h = b["h"]
        k = max(0.0, min(1.0, (h - 6.0) / 22.0))
        base = b["rc"]
        col = tuple(int(255 * min(1.0, c * (0.85 + 0.4 * k))) for c in base)
        edge = (40, 36, 32) if b["lod"] == 0 else (70, 66, 60)
        d.polygon([tp(p) for p in b["p"]], fill=col, outline=edge)
    for s in gen.specials:
        d.polygon([tp(p) for p in s["foot"]], fill=(220, 210, 180), outline=(120, 20, 20))
    for c in gen.chimneys:
        x, y = tp((c["x"], c["y"]))
        d.rectangle([x - 2, y - 2, x + 2, y + 2], fill=(20, 20, 20))
    for t in gen.trees:
        x, y = tp((t[0], t[1]))
        r = 4.5 * t[2] * ppm
        d.ellipse([x - r, y - r, x + r, y + r], fill=(66, 98, 52, 210))
    for c in gen.cells:
        col = {"enemy": (192, 57, 43), "mid": (184, 134, 11), "player": (31, 111, 214)}[c["zone"]]
        d.polygon([tp(p) for p in c["poly"]], outline=col + (255,), fill=col + (60,))
        d.line([tp(p) for p in c["poly"] + [c["poly"][0]]], fill=col + (255,), width=3)
        d.text(tp((c["x"] - 8, c["y"] + 6)), c["id"], fill=(255, 255, 255))
    img.save(path)
    return W, H


def main():
    g = Gen()
    g.run()
    size = g.dump()
    st = g.stats()
    st["json_bytes"] = size
    os.makedirs(os.path.dirname(OUT_PLAN), exist_ok=True)
    st["plan"] = draw_plan(g, OUT_PLAN)
    with open(os.path.join(OUT_DIR, "warsaw_board_layout_stats.json"), "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)
    print(json.dumps(st, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
