# -*- coding: utf-8 -*-
"""Warsaw board city kit — filler modules for the 8x8 / 200 m grid.

Board convention (doc 122 + project memory):
  cell 200 m, street 38 m (carriageway 22 + sidewalks 8 + curb 0.15),
  block facades on +-81 m, depth 16 m, courtyard 130 m left empty.
Chimneys only ever sit on multi-storey roofs.

Modules:
  A  apartment block, 5 storeys, pitched roof, dormers      (kamienica)
  B  apartment block, 6 storeys, flat roof, corner tower    (modernist)
  C  duplex / townhouse row, 3 storeys, steep gables
  D  substation (brick, louvered, fenced, transformers)
  E  water tower (concrete legs + conical tank)
  F  heating plant (2-storey hall + chimney on the roof)
  G  tram depot (sawtooth north-light roof, 5 bays)
"""
import bpy
import math
import os
import random
import sys
import json
from mathutils import Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import lib_geom as G
import spec as S

OUT_BLEND = r"E:\AI\Tread\Tread\model\warsaw\landmarks\Warsaw_CityKit.blend"
OUT_DIR = r"E:\AI\Tread\Tread\Saved\Warsaw\renders"

PAL_BODY = [("kit_brick", "#8d4234"), ("kit_ochre", "#c2a468"),
            ("kit_grey", "#b0aa9d"), ("kit_cream", "#d6cbb2")]
PAL_ROOF = ("kit_roof", "#8c4433")


def storey_bands(T, w, d, storeys, sh, z0=0.0, proud=0.10):
    for i in range(1, storeys):
        z = z0 + i * sh
        T.box(-w / 2 - proud, -0.14, z - 0.10, w / 2 + proud, d + 0.02, z + 0.05)


def facade_windows(W, T, w, d, storeys, sh, bays, z0=0.0, wy=0.0,
                   ww=1.15, wh=1.95, back=True):
    """Window grid on the -Y facade (and mirrored on +Y when back=True)."""
    for f in range(storeys):
        z = z0 + f * sh + 0.55
        for k in range(bays):
            x = -w / 2 + (k + 0.5) * (w / bays)
            W.at(x, wy, z); W.window_glass(ww, wh); W.pop()
            T.at(x, wy, z); T.window_frame(ww, wh, frame=0.09); T.pop()
            if back:
                W.at(x, d, z); W.push(Matrix.Rotation(math.pi, 4, "Z"))
                W.window_glass(ww, wh); W.pop(); W.pop()
                T.at(x, d, z); T.push(Matrix.Rotation(math.pi, 4, "Z"))
                T.window_frame(ww, wh, frame=0.09); T.pop(); T.pop()


# ------------------------------------------------------------------ A
def apartment_a(B, T, W, R, D, ox, oy, w, storeys=5):
    body = B
    d, sh = 16.0, 3.25
    h = storeys * sh
    for mb in (B, T, W, R, D):
        mb.at(ox, oy, 0)
    body.box(-w / 2, 0, 0, w / 2, d, h)
    T.box(-w / 2 - 0.12, -0.18, 0, w / 2 + 0.12, 0, 0.75)          # plinth
    storey_bands(T, w, d, storeys, sh)
    T.box(-w / 2 - 0.26, -0.34, h - 0.70, w / 2 + 0.26, 0.02, h + 0.05)   # cornice
    T.box(-w / 2 - 0.14, -0.22, h - 1.05, w / 2 + 0.14, 0, h - 0.70)

    # ground floor: shopfronts + doors
    nb = max(3, int(w / 9.0))
    for k in range(nb):
        x = -w / 2 + (k + 0.5) * (w / nb)
        W.at(x, 0, 0.9); W.window_glass(3.4, 2.5, y0=-0.05); W.pop()
        T.at(x, 0, 0.9); T.window_frame(3.4, 2.5, frame=0.16, sill=False); T.pop()
        T.box(x - 2.0, -0.34, 3.62, x + 2.0, 0.0, 3.80)            # shop cornice
    facade_windows(W, T, w, d, storeys - 1, sh, max(4, int(w / 3.4)),
                   z0=sh * 0.05, wy=0.0)

    # pitched roof + dormers + chimneys (never free-standing)
    R.gable_y(-w / 2 - 0.35, w / 2 + 0.35, 0.15, d - 0.15, h, 4.6)
    nd = max(2, int(w / 14.0))
    for k in range(nd):
        x = -w / 2 + (k + 0.5) * (w / nd)
        W.at(x, 1.05, h + 0.85); W.window_glass(0.95, 1.1, y0=-0.06, y1=0.06); W.pop()
        T.at(x, 1.05, h + 0.85); T.window_frame(0.95, 1.1, frame=0.08, sill=False); T.pop()
        R.at(x, 1.5, h); R.box(-0.75, -0.7, 0, 0.75, 0.7, 1.7)
        R.hip(-0.9, -0.85, 0.9, 0.85, 1.7, 0.8, ridge_axis="x"); R.pop()
    for k in range(2):
        x = -w / 2 + (k + 1) * w / 3.0
        R.box(x - 0.45, d * 0.42, h + 1.4, x + 0.45, d * 0.42 + 0.9, h + 5.0)
        T.box(x - 0.55, d * 0.42 - 0.08, h + 4.9, x + 0.55, d * 0.42 + 1.0, h + 5.15)
    for mb in (B, T, W, R, D):
        mb.pop()


# ------------------------------------------------------------------ B
def apartment_b(B, T, W, R, D, ox, oy, w, storeys=6):
    body = B
    d, sh = 16.0, 3.1
    h = storeys * sh
    for mb in (B, T, W, R, D):
        mb.at(ox, oy, 0)
    body.box(-w / 2, 0, 0, w / 2, d, h)
    T.box(-w / 2 - 0.14, -0.18, 0, w / 2 + 0.14, 0, 0.80)
    storey_bands(T, w, d, storeys, sh, proud=0.12)
    # flat roof: parapet + roof deck
    R.box(-w / 2, 0, h, w / 2, d, h + 0.25)
    T.box(-w / 2 - 0.20, -0.24, h, w / 2 + 0.20, 0.02, h + 1.05)
    T.box(-w / 2 - 0.20, -0.24, h + 1.05, w / 2 + 0.20, 0.02, h + 1.20)
    facade_windows(W, T, w, d, storeys, sh, max(4, int(w / 3.2)), wy=0.0)
    # corner tower
    tx = w / 2 - 4.0
    body.box(tx - 4.0, -1.2, 0, tx + 4.0, 8.0, h + 4.2)
    T.box(tx - 4.3, -1.5, h + 3.6, tx + 4.3, 8.3, h + 4.35)
    for z in (sh, sh * 2, sh * 3, sh * 4):
        T.box(tx - 4.05, -1.35, z - 0.12, tx + 4.05, -1.2, z + 0.04)
    for f in range(storeys - 1):
        for k in (-2.0, 2.0):
            W.push(Matrix.Translation((tx + k, 0, sh * (f + 1) + 0.6)))
            W.box(-0.55, -0.06, 0, 0.55, 0.03, 1.9); W.pop()
    R.pyramid(tx - 4.3, -1.5, tx + 4.3, 8.3, h + 4.35, h + 6.4)
    for mb in (B, T, W, R, D):
        mb.pop()


# ------------------------------------------------------------------ C
def duplex_row(B, T, W, R, D, ox, oy, units=8, uw=8.2, depth=13.0, storeys=3):
    body = B
    sh = 3.15
    h = storeys * sh
    for u in range(units):
        x0 = -units * uw / 2 + u * uw
        for mb in (B, T, W, R, D):
            mb.at(ox + x0 + uw / 2, oy, 0)
        body.box(-uw / 2, 0, 0, uw / 2, depth, h)
        T.box(-uw / 2 - 0.06, -0.14, 0, uw / 2 + 0.06, 0, 0.55)
        storey_bands(T, uw, depth, storeys, sh, proud=0.06)
        T.box(-uw / 2 - 0.18, -0.26, h - 0.5, uw / 2 + 0.18, 0.02, h + 0.04)
        # door + windows
        W.at(0, 0, 0.35); W.box(-0.55, -0.05, 0, 0.55, 0.03, 2.3); W.pop()
        T.at(0, 0, 0.35); T.box(-0.75, -0.16, 0, 0.75, 0, 2.5); T.pop()
        for f in range(storeys):
            z = f * sh + 0.7
            for sx in (-1, 1):
                W.at(sx * uw * 0.24, 0, z); W.window_glass(1.0, 1.75); W.pop()
                T.at(sx * uw * 0.24, 0, z); T.window_frame(1.0, 1.75, frame=0.08); T.pop()
        # steep gable roof, ridge along depth
        R.gable_y(-uw / 2 - 0.3, uw / 2 + 0.3, 0.1, depth - 0.1, h, 4.2)
        T.prism_y([(-uw / 2 + 0.2, h), (uw / 2 - 0.2, h), (0.0, h + 3.9)], -0.28, 0.05)
        for mb in (B, T, W, R, D):
            mb.pop()


# ------------------------------------------------------------------ D
def substation(B, T, W, R, D, ox, oy, w=24.0, d=15.0):
    body = B
    h = 7.0
    for mb in (B, T, W, R, D):
        mb.at(ox, oy, 0)
    body.box(-w / 2, 0, 0, w / 2, d, h)
    T.box(-w / 2 - 0.2, -0.2, 0, w / 2 + 0.2, 0, 0.8)
    T.box(-w / 2 - 0.3, -0.3, h - 0.5, w / 2 + 0.3, 0.02, h + 0.1)
    # louvered vents + steel doors
    for k in range(4):
        x = -w / 2 + (k + 0.5) * (w / 4)
        D.at(x, 0, 2.2)
        for i in range(9):
            D.box(-1.5, -0.16, i * 0.22, 1.5, -0.02, i * 0.22 + 0.12)
        D.pop()
    D.at(0, 0, 0); D.box(-1.6, -0.10, 0, 1.6, -0.02, 2.8); D.pop()
    # roof plant + cable racks
    R.box(-w / 2 + 1, 1, h, w / 2 - 1, d - 1, h + 0.3)
    for k in range(3):
        x = -w / 2 + 4 + k * 7
        D.lathe([(0.9, h + 0.3), (0.9, h + 2.4), (0.6, h + 2.6)], x, d * 0.5, seg=10)
    D.box(-w / 2, d * 0.5 - 0.2, h + 1.2, -w / 2 - 6, d * 0.5 + 0.2, h + 1.6)
    # fence
    for k in range(10):
        D.box(-w / 2 - 7 + k * 3.2, -6.0, 0, -w / 2 - 6.85 + k * 3.2, -5.85, 2.0)
    D.box(-w / 2 - 7, -6.1, 1.9, -w / 2 + 25, -5.75, 2.05)
    for mb in (B, T, W, R, D):
        mb.pop()


# ------------------------------------------------------------------ E
def water_tower(B, T, W, R, D, ox, oy, r=6.0, leg_h=22.0):
    for mb in (B, T, W, R, D):
        mb.at(ox, oy, 0)
    for k in range(4):
        a = math.radians(45 + 90 * k)
        x, y = math.cos(a) * (r * 0.62), math.sin(a) * (r * 0.62)
        T.box(x - 0.42, y - 0.42, 0, x + 0.42, y + 0.42, leg_h)
    for z in (leg_h * 0.35, leg_h * 0.70):
        T.lathe([(r * 0.66, z), (r * 0.66, z + 0.35), (r * 0.60, z + 0.35)], 0, 0, seg=8)
    T.lathe([(r * 0.75, leg_h), (r * 0.75, leg_h + 0.6)], 0, 0, seg=16)
    R.lathe([(r, leg_h + 0.6), (r, leg_h + 5.0), (r * 0.72, leg_h + 7.4),
             (r * 0.34, leg_h + 8.6), (0.0, leg_h + 9.3)], 0, 0, seg=16)
    T.lathe([(r * 1.04, leg_h + 0.6), (r * 1.04, leg_h + 1.2)], 0, 0, seg=16)
    D.lathe([(0.35, leg_h + 9.2), (0.0, leg_h + 10.4)], 0, 0, seg=8)
    for mb in (B, T, W, R, D):
        mb.pop()


# ------------------------------------------------------------------ F
def heating_plant(B, T, W, R, D, ox, oy, w=34.0, d=20.0):
    body = B
    h = 13.0
    for mb in (B, T, W, R, D):
        mb.at(ox, oy, 0)
    body.box(-w / 2, 0, 0, w / 2, d, h)
    T.box(-w / 2 - 0.25, -0.25, 0, w / 2 + 0.25, 0, 1.0)
    for z in (4.5, 9.0):
        T.box(-w / 2 - 0.15, -0.2, z - 0.12, w / 2 + 0.15, 0, z + 0.05)
    T.box(-w / 2 - 0.4, -0.45, h - 0.9, w / 2 + 0.4, 0.02, h + 0.1)
    # tall industrial windows
    for k in range(6):
        x = -w / 2 + (k + 0.5) * (w / 6)
        for f in range(3):
            W.at(x, 0, 1.2 + f * 4.4); W.window_glass(2.6, 3.2); W.pop()
            T.at(x, 0, 1.2 + f * 4.4); T.window_frame(2.6, 3.2, frame=0.14, sill=False); T.pop()
    # shallow sawtooth roof
    R.box(-w / 2, 0, h, w / 2, d, h + 0.35)
    for k in range(4):
        y0 = k * d / 4.0
        R.prism_y([(0.0, h + 0.35), (d / 4.0, h + 0.35), (d / 4.0, h + 2.3)], y0, y0 + 0.4)
    # chimney, standing on the hall roof
    R.box(w / 2 - 6.5, d * 0.62, h, w / 2 - 3.5, d * 0.62 + 3.0, h + 30.0)
    T.box(w / 2 - 7.0, d * 0.62 - 0.5, h + 29.6, w / 2 - 3.0, d * 0.62 + 3.5, h + 31.0)
    for z in (h + 6, h + 14, h + 22):
        T.box(w / 2 - 7.0, d * 0.62 - 0.4, z, w / 2 - 3.0, d * 0.62 + 3.4, z + 0.5)
    for mb in (B, T, W, R, D):
        mb.pop()


# ------------------------------------------------------------------ G
def tram_depot(B, T, W, R, D, ox, oy, w=62.0, d=26.0, bays=5):
    body = B
    h = 10.0
    for mb in (B, T, W, R, D):
        mb.at(ox, oy, 0)
    body.box(-w / 2, 0, 0, w / 2, d, h)
    T.box(-w / 2 - 0.25, -0.25, 0, w / 2 + 0.25, 0, 1.0)
    T.box(-w / 2 - 0.45, -0.45, h - 0.8, w / 2 + 0.45, 0.02, h + 0.15)
    for k in range(bays):
        x = -w / 2 + (k + 0.5) * (w / bays)
        # big sliding door + rail
        D.at(x, 0, 0)
        D.box(-3.6, -0.12, 0, 3.6, -0.02, 7.2)
        D.pop()
        T.at(x, 0, 7.2); T.box(-3.9, -0.20, 0, 3.9, 0, 0.5); T.pop()
        W.at(x, 0, 8.0); W.window_glass(4.6, 1.4); W.pop()
    # sawtooth north-light roof
    for k in range(bays):
        x0 = -w / 2 + k * (w / bays)
        R.prism_x([(0.0, h), (d * 0.72, h), (d * 0.72, h + 3.4)], x0 + 0.3, x0 + w / bays - 0.3)
        W.prism_x([(d * 0.72, h + 0.2), (d * 0.98, h + 0.2), (d * 0.98, h + 3.0)], x0 + 0.4, x0 + w / bays - 0.4)
    for mb in (B, T, W, R, D):
        mb.pop()


def main():
    G.scene_reset()
    col = G.collection("COL_CITYKIT")
    root = G.empty("LM_CITYKIT", col)

    bodies = [G.MB("KIT-body-%d" % i) for i in range(len(PAL_BODY))]
    T = G.MB("KIT-trim")
    W = G.MB("KIT-win")
    R = G.MB("KIT-roof")
    D = G.MB("KIT-iron")

    # ---- kit row (1:1), spread along X --------------------------------
    apartment_a(bodies[0], T, W, R, D, -168.0, 0.0, 48.0, 5)
    apartment_b(bodies[1], T, W, R, D, -104.0, 0.0, 44.0, 6)
    duplex_row(bodies[2], T, W, R, D, -22.0, 0.0, units=8)
    substation(bodies[0], T, W, R, D, 62.0, 0.0)
    water_tower(bodies[3], T, W, R, D, 116.0, 7.0)
    heating_plant(bodies[0], T, W, R, D, 150.0, 0.0)
    tram_depot(bodies[2], T, W, R, D, 225.0, 0.0)

    # ---- one 200 m cell, ringed, courtyard empty ----------------------
    CX, CY = 0.0, 430.0
    half, dep = 81.0, 16.0

    def rot(deg):
        return (Matrix.Translation((CX, CY, 0)) @ Matrix.Rotation(math.radians(deg), 4, "Z") @
                Matrix.Translation((-CX, -CY, 0)))

    # south side: facade must face the courtyard (+Y) -> build rotated 180
    south = (bodies[0], bodies[1], T, W, R, D)
    for mb in south:
        mb.push(rot(180.0))
    apartment_a(bodies[0], T, W, R, D, CX - 40.0, CY - half - dep, 44.0, 5)
    apartment_b(bodies[1], T, W, R, D, CX + 8.0, CY - half - dep, 40.0, 6)
    for mb in south:
        mb.pop()
    # north side, facing -Y (into the courtyard)
    duplex_row(bodies[2], T, W, R, D, CX - 30.0, CY + half + dep, units=8)
    heating_plant(bodies[0], T, W, R, D, CX + 40.0, CY + half + dep, 30.0, 18.0)
    # west side, rotate +90 so the facade faces +X
    west = (bodies[1], T, W, R, D)
    for mb in west:
        mb.push(rot(90.0))
    apartment_a(bodies[1], T, W, R, D, CX - half - dep, CY + 30.0, 52.0, 5)
    for mb in west:
        mb.pop()
    # east side, rotate -90 so the facade faces -X
    east = (bodies[3], T, W, R, D)
    for mb in east:
        mb.push(rot(-90.0))
    apartment_a(bodies[3], T, W, R, D, CX + half + dep, CY - 10.0, 48.0, 5)
    for mb in east:
        mb.pop()

    # street + sidewalk plate for the cell
    S_ = G.MB("KIT-street")
    S_.box(CX - 100, CY - 100, -0.35, CX + 100, CY + 100, -0.02)
    S_.box(CX - 81, CY - 81, -0.02, CX + 81, CY + 81, 0.0)
    st = S_.emit(col, G.material("kit_asphalt", "#3b3b39", 0.95), "GEO-KIT-street", parent=root)

    objs = []
    for mb, (nm, hx) in zip(bodies, PAL_BODY):
        if mb.v:
            objs.append(mb.emit(col, G.material(nm, hx, 0.82, pattern="brick" if "brick" in nm else "plaster",
                                                scale=0.5), "GEO-KIT-" + nm, parent=root))
    objs.append(T.emit(col, G.material("kit_stone", "#cfc7b4", 0.76, pattern="stone", scale=1.4),
                       "GEO-KIT-stone", parent=root))
    objs.append(W.emit(col, G.material("kit_glass", "#171c20", 0.14, 0.55), "GEO-KIT-glass", parent=root))
    objs.append(R.emit(col, G.material("kit_roofmat", "#7c4a37", 0.84, pattern="tile", scale=0.6),
                       "GEO-KIT-roof", parent=root))
    objs.append(D.emit(col, G.material("kit_steel", "#4a4a48", 0.55, 0.7), "GEO-KIT-steel", parent=root))

    G.setup_world(strength=0.42, sky=(0.60, 0.70, 0.84))
    G.sun(rot=(math.radians(46), 0.0, math.radians(40)), energy=4.2)

    mn = [1e9] * 3
    mx = [-1e9] * 3
    for o in objs + [st]:
        for c in o.bound_box:
            w = o.matrix_world @ G.Vector(c)
            for i in range(3):
                mn[i] = min(mn[i], w[i])
                mx[i] = max(mx[i], w[i])
    stats = {"objects": len(objs) + 1,
             "verts": sum(len(o.data.vertices) for o in objs + [st]),
             "tris": sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in objs + [st]),
             "bbox": [round(v, 1) for v in mn] + [round(v, 1) for v in mx]}
    os.makedirs(os.path.dirname(OUT_BLEND), exist_ok=True)
    G.save(OUT_BLEND)
    stats["blend"] = OUT_BLEND
    print("HEADLESS " + json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
