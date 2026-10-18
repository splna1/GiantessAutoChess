# -*- coding: utf-8 -*-
"""05 国家体育场 Stadion Narodowy — Warsaw landmark set.

Elliptical 310 x 280 m bowl.  Built as:
  * a closed concrete bowl swept from one profile (three seating tiers, risers,
    concourse, outer wall),
  * a woven basket facade: a dark closed shell with red / white / silver panels
    standing 6 cm proud in two crossing diagonal families,
  * the suspended PTFE roof ring with its compression ring and radial ribs,
  * four 70 m masts with cable fans,
  * the pitch with its markings.
"""
import bpy
import math
import os
import sys
import json
from mathutils import Matrix

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import lib_geom as G
import spec as S

OUT_BLEND = r"E:\AI\Tread\Tread\model\warsaw\landmarks\Warsaw_05_Stadion.blend"

SP = S.STADION
A, B = SP["outer"][0] / 2.0, SP["outer"][1] / 2.0        # 155, 140
PL = SP["plinth_h"]
BOWL = SP["bowl_h"]
TAU = math.tau


def ring_surface(mb, a0, b0, z0, a1, b1, z1, seg=96):
    va, vb = [], []
    for i in range(seg):
        t = TAU * i / seg
        va.append((a0 * math.cos(t), b0 * math.sin(t), z0))
        vb.append((a1 * math.cos(t), b1 * math.sin(t), z1))
    faces = [(i, (i + 1) % seg, seg + (i + 1) % seg, seg + i) for i in range(seg)]
    mb.add(va + vb, faces)


def sweep_ring(mb, profile, a, b, seg=96):
    """Sweep a closed (ra, rb, z) profile around the ellipse -> closed solid."""
    n = len(profile)
    verts = []
    for i in range(seg):
        t = TAU * i / seg
        ca, sa = math.cos(t), math.sin(t)
        for ra, rb, z in profile:
            verts.append((a * ra * ca, b * rb * sa, z))
    faces = []
    for i in range(seg):
        i2 = (i + 1) % seg
        for k in range(n):
            k2 = (k + 1) % n
            faces.append((i * n + k, i * n + k2, i2 * n + k2, i2 * n + k))
    mb.add(verts, faces)


def build_facade(shell, panels, a, b, z0, z1, nseg=96, nrow=24, thick=2.0):
    da, db = a - thick, b - thick
    outer, inner = [], []
    for r in range(nrow + 1):
        z = z0 + (z1 - z0) * r / nrow
        for i in range(nseg):
            t = TAU * i / nseg
            outer.append((a * math.cos(t), b * math.sin(t), z))
            inner.append((da * math.cos(t), db * math.sin(t), z))
    W = nseg
    no = len(outer)

    def oi(r, i):
        return r * W + (i % W)

    for r in range(nrow):
        for i in range(nseg):
            key = "dark"
            s1 = ((i + r) % 14) < 7
            s2 = ((i - r) % 14) < 7
            if s1 and s2:
                key = "white"
            elif s1:
                key = "red"
            elif s2:
                key = "silver"
            q = (oi(r, i), oi(r, i + 1), oi(r + 1, i + 1), oi(r + 1, i))
            if key != "dark":
                pts = [outer[k] for k in q]
                # push the panel 6 cm proud of the shell
                cx = sum(p[0] for p in pts) / 4.0
                cy = sum(p[1] for p in pts) / 4.0
                d = math.hypot(cx, cy) or 1.0
                nx, ny = cx / d * 0.06, cy / d * 0.06
                outer4 = [(p[0] + nx, p[1] + ny, p[2]) for p in pts]
                inner4 = [(p[0] + nx * 0.4, p[1] + ny * 0.4, p[2]) for p in pts]
                v8 = outer4 + inner4
                f6 = [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1),
                      (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
                panels[key].add(v8, f6)
            qi = (oi(r, i), oi(r + 1, i), oi(r + 1, i + 1), oi(r, i + 1))
            shell.add([(inner[k][0], inner[k][1], inner[k][2]) for k in qi], [(0, 1, 2, 3)])
    # shell outer skin (visible in the gaps) + caps
    for r in range(nrow):
        for i in range(nseg):
            q = (oi(r, i), oi(r, i + 1), oi(r + 1, i + 1), oi(r + 1, i))
            shell.add([outer[k] for k in q], [(0, 1, 2, 3)])
    for r in (0, nrow):
        for i in range(nseg):
            j = (i + 1) % nseg
            shell.add([outer[oi(r, i)], outer[oi(r, j)],
                       inner[oi(r, j)], inner[oi(r, i)]], [(0, 1, 2, 3)])


def main():
    G.scene_reset()
    col = G.collection("COL_LM_STADION")
    root = G.empty("LM_STADION", col)

    C = G.MB("STAD-shell")
    panels = {"red": G.MB("STAD-red"), "white": G.MB("STAD-white"),
              "silver": G.MB("STAD-silver")}
    R = G.MB("STAD-roof")
    M = G.MB("STAD-steel")
    D = G.MB("STAD-markings")
    Gr = G.MB("STAD-pitch")

    # ---- concrete bowl (closed solid) -----------------------------------
    profile = [
        (0.380, 0.300, 1.0),    # inner rim at pitch level
        (0.400, 0.320, 3.0),
        (0.470, 0.400, 10.5), (0.480, 0.410, 11.3),
        (0.560, 0.500, 17.0), (0.570, 0.510, 17.8),
        (0.650, 0.600, 23.5), (0.665, 0.615, 24.2),
        (0.930, 0.930, 25.0),
        (0.985, 0.985, BOWL),
        (0.985, 0.985, 0.0),
        (0.380, 0.300, 0.0),
    ]
    sweep_ring(C, profile, A, B, seg=96)
    # plinth
    ring_surface(C, A * 1.03, B * 1.03, 0.0, A * 0.995, B * 0.995, PL + 0.6, seg=96)

    # ---- woven facade ----------------------------------------------------
    build_facade(C, panels, A * 0.995, B * 0.995, PL + 0.6, BOWL + 2.0,
                 nseg=96, nrow=24, thick=2.4)

    # ---- pitch -----------------------------------------------------------
    pa, pb = SP["pitch"][0] / 2.0, SP["pitch"][1] / 2.0
    Gr.box(-pa, -pb, 0.2, pa, pb, 1.0)
    D.box(-pa, -0.12, 1.0, pa, 0.12, 1.03)
    D.lathe([(9.15, 1.0), (9.15, 1.03), (9.0, 1.03), (9.0, 1.0)], 0, 0, seg=48)
    for s in (-1, 1):
        D.box(s * pa - (0.12 if s < 0 else 16.5), -20.16, 1.0,
              s * pa - (16.5 if s < 0 else -0.12), 20.16, 1.03)
        D.box(s * pa - (0.12 if s < 0 else 5.5), -9.16, 1.0,
              s * pa - (5.5 if s < 0 else -0.12), 9.16, 1.03)

    # ---- suspended roof --------------------------------------------------
    ra, rb = (SP["outer"][0] / 2.0) + 4.0, (SP["outer"][1] / 2.0) + 4.0
    ia, ib = SP["roof_inner"][0] / 2.0, SP["roof_inner"][1] / 2.0
    z_out, z_in = 30.5, 34.0
    ring_surface(R, ra, rb, z_out, ia, ib, z_in, seg=96)
    ring_surface(R, ra - 1.4, rb - 1.4, z_out - 1.6, ia, ib, z_in - 1.4, seg=96)
    ring_surface(R, ra, rb, z_out, ra - 1.4, rb - 1.4, z_out - 1.6, seg=96)
    ring_surface(R, ia, ib, z_in, ia, ib, z_in - 1.4, seg=96)
    # compression ring + radial ribs
    ring_surface(M, ia + 3.0, ib + 3.0, z_in, ia, ib, z_in, seg=96)
    ring_surface(M, ia + 3.0, ib + 3.0, z_in - 1.6, ia + 3.0, ib + 3.0, z_in, seg=96)
    for i in range(48):
        t = TAU * i / 48
        p0 = (ia * math.cos(t), ib * math.sin(t), z_in - 0.5)
        p1 = (ra * 0.985 * math.cos(t), rb * 0.985 * math.sin(t), z_out - 0.5)
        mid = ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2, (p0[2] + p1[2]) / 2 + 0.6)
        M.tube([p0, mid, p1], 0.18, seg=5)

    # ---- masts + cables --------------------------------------------------
    mast_h = SP["mast_h"]
    for i in range(4):
        t = math.radians(45 + 90 * i)
        x, y = ra * 0.945 * math.cos(t), rb * 0.945 * math.sin(t)
        M.lathe([(3.2, 0.0), (2.6, PL + 1.0), (1.9, mast_h * 0.55), (1.2, mast_h - 2.5),
                 (0.70, mast_h), (0.0, mast_h + 1.4)], x, y, seg=12)
        D.lathe([(3.3, 0.0), (3.3, 1.2), (2.5, 1.5)], x, y, seg=12)
        for k in range(-3, 4):
            tk = t + k * 0.13
            M.tube([(x, y, mast_h - 1.2),
                    (ra * 0.88 * math.cos(tk), rb * 0.88 * math.sin(tk), z_out + 0.4)],
                   0.12, seg=4)
        # stay cables down to the plinth
        for s in (-1, 1):
            M.tube([(x, y, mast_h * 0.72),
                    (x + s * 26 * math.cos(t + math.pi / 2),
                     y + s * 26 * math.sin(t + math.pi / 2), 2.0)], 0.10, seg=4)

    # ---- gates on the main axes -----------------------------------------
    for i in range(4):
        t = math.radians(90 * i)
        C.push(Matrix.Translation((0, 0, 0)) @ Matrix.Rotation(t, 4, "Z"))
        C.box(A * 1.02 - 1.0, -13.0, 0.0, A * 1.02 + 3.5, 13.0, 10.0)
        D.box(A * 1.02 + 3.4, -9.0, 0.4, A * 1.02 + 3.6, 9.0, 8.0)
        C.pop()

    objs = []
    objs.append(C.emit(col, G.material("stad_shell", "#33383c", 0.62, 0.45),
                       "GEO-STADION-shell", parent=root))
    objs.append(panels["red"].emit(col, G.material("stad_red", "#a8271f", 0.42, 0.55),
                                   "GEO-STADION-red", parent=root))
    objs.append(panels["white"].emit(col, G.material("stad_white", "#e4dfd4", 0.40, 0.50),
                                     "GEO-STADION-white", parent=root))
    objs.append(panels["silver"].emit(col, G.material("stad_silver", "#9aa2aa", 0.34, 0.80),
                                      "GEO-STADION-silver", parent=root))
    objs.append(R.emit(col, G.material("stad_membrane", "#dcd6c8", 0.62, 0.05),
                       "GEO-STADION-roof", parent=root))
    objs.append(M.emit(col, G.material("stad_steel", "#b6bbc1", 0.35, 1.0),
                       "GEO-STADION-steel", parent=root))
    objs.append(D.emit(col, G.material("stad_light", "#d8d5cc", 0.6),
                       "GEO-STADION-markings", parent=root))
    objs.append(Gr.emit(col, G.material("stad_grass", "#4e7c3a", 0.92),
                        "GEO-STADION-pitch", parent=root))

    G.setup_world(strength=0.80, sky=(0.66, 0.76, 0.88))
    G.sun(rot=(math.radians(50), 0.0, math.radians(35)), energy=3.6)
    G.sun(rot=(math.radians(-40), 0.0, math.radians(-150)), energy=1.1)

    mn = [1e9] * 3
    mx = [-1e9] * 3
    for o in objs:
        for c in o.bound_box:
            w = o.matrix_world @ G.Vector(c)
            for i in range(3):
                mn[i] = min(mn[i], w[i])
                mx[i] = max(mx[i], w[i])
    stats = {"landmark": "Stadion Narodowy", "objects": len(objs),
             "verts": sum(len(o.data.vertices) for o in objs),
             "tris": sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in objs),
             "bbox": [round(v, 2) for v in mn] + [round(v, 2) for v in mx],
             "size": [round(mx[i] - mn[i], 2) for i in range(3)]}
    os.makedirs(os.path.dirname(OUT_BLEND), exist_ok=True)
    G.save(OUT_BLEND)
    stats["blend"] = OUT_BLEND
    print("HEADLESS " + json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
