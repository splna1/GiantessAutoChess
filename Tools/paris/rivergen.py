"""B4 Seine river props (pure Python on geom.MeshBuilder, no `unreal`; testable with CPython).

Meshes (local frame: +x = bow / along the quay, z = 0 at the waterline, so every prop is placed at z = Z_WATER):
    tour_boat(seed, burnt)   glass-roofed bateau-mouche (~45 m): black lower hull, cream upper hull, glazed cabin with
                             iron ribs, wheelhouse forward, open stern deck; burnt = charred shell, roof glazing gone
    dock(seed)               floating landing stage: steel pontoon, timber deck, bollards, railing, gangway rising
                             +y to the lower quay (GANGWAY_RISE above the water)

river_layout() is deterministic and shared by 05_city_layout.py (meshes, quay tree rows) and 07_fx.py (fires on the
burning boat), the same pattern as basegen.cell_layout(). It keeps clear of the bridges, the quay stairs
(citygen.STAIRS_X), the existing barges (05_city_layout BARGE_SPOTS) and the mid-channel bridge piers.
"""
import math

import citygen as cg
import geom
from geom import Z, norm, rng

BOAT_W = 6.4
DOCK_W = 4.5
DOCK_GAP = 4.0  # water gap between the quay edge and the pontoon (bridged by the gangway)
GANGWAY_RISE = cg.Z_LOWQ - cg.Z_WATER  # 1.9 m
X_RANGE = (-2050.0, 3050.0)  # river segments laid out by 05_city_layout (river_x_range)
BARGE_SPOTS = ((-350.0, 1), (130.0, -1), (870.0, 1), (1530.0, -1), (2250.0, 1))  # mirrors 05_city_layout
GOLD_BRIDGES_X = (600.0, 1800.0)  # Pont Alexandre III treatment (citygen style "gold")

# (x, quay side +1 west / -1 east, boat moored: None | "boat" | "burnt")
DOCKS = ((-150.0, 1, "boat"), (1050.0, 1, "boat"), (2000.0, 1, None),
         (-300.0, -1, "boat"), (420.0, -1, "burnt"), (1000.0, -1, "boat"))
# mid-channel traffic: (x, y, yaw, kind) ; kind "boat" | "capsized"
SAILING = ((300.0, 1098.0, 0.0, "boat"), (1500.0, 1088.0, 180.0, "boat"), (-850.0, 1108.0, 8.0, "capsized"))
TREE_STEP = 12.5


def builder():
    return cg.builder()


def _hull_outline(L, W):
    return [(-L / 2, -W / 2 + 0.5), (-L / 2 + 1.0, -W / 2), (L / 2 - 7.0, -W / 2), (L / 2, 0.0),
            (L / 2 - 7.0, W / 2), (-L / 2 + 1.0, W / 2), (-L / 2, W / 2 - 0.5)]


def tour_boat(seed=0, burnt=False):
    """Bateau-mouche: local x = bow, z = 0 waterline (draught 1.2 m)."""
    r = rng(seed)
    mb = builder()
    L, W = r.uniform(42.0, 50.0), BOAT_W
    hull = _hull_outline(L, W)
    low = "char" if burnt else "hull"
    up = "char" if burnt else "deck"
    trim = "char" if burnt else "cabin"
    mb.band(low, hull, True, -0.15, 0.0, -1.2, 0.6, bottom=False)
    mb.band(up, hull, True, -0.15, 0.0, 0.6, 1.3, bottom=False)
    mb.band(trim, hull, True, -0.15, 0.08, 1.3, 1.42)
    mb.polygon2d(up, geom.offset_polyline(hull, -0.15, True), 1.0)  # deck floor below the gunwale
    # glazed cabin
    ca, cb = -L / 2 + 5.0, L / 2 - 10.0
    hw = W / 2 - 0.55
    z0, z1, zr = 1.0, 2.5, 3.25
    glass = "char" if burnt else "glass"
    for s in (-1.0, 1.0):
        y = s * hw
        mb.poly(up, [(ca, y, z0), (cb, y, z0), (cb, y, z0 + 0.45), (ca, y, z0 + 0.45)], (0, s, 0))  # sill
        mb.poly(glass, [(ca, y, z0 + 0.45), (cb, y, z0 + 0.45), (cb, y, z1), (ca, y, z1)], (0, s, 0))
        if not (burnt and s > 0):  # burnt: one roof slope gone, ribs bare
            mb.poly(glass, [(ca, y, z1), (cb, y, z1), (cb, 0.0, zr), (ca, 0.0, zr)], norm((0.0, s * (zr - z1), hw)))
    for x, sx in ((ca, -1.0), (cb, 1.0)):
        mb.poly(up, [(x, -hw, z0), (x, hw, z0), (x, hw, z1), (x, -hw, z1)], (sx, 0, 0))
        mb.poly(up, [(x, -hw, z1), (x, hw, z1), (x, 0.0, zr)], (sx, 0, 0))
    x = ca
    while x <= cb + 1e-6:
        for s in (-1.0, 1.0):
            cg.bar(mb, "iron", (x, s * (hw + 0.03), z0), (x, s * (hw + 0.03), z1), 0.05)
            cg.bar(mb, "iron", (x, s * (hw + 0.03), z1), (x, 0.0, zr + 0.03), 0.05)
        x += 1.6
    cg.bar(mb, "iron", (ca, 0.0, zr + 0.03), (cb, 0.0, zr + 0.03), 0.07)  # ridge
    # wheelhouse forward of the cabin, open bow deck beyond
    wa, wb = cb + 0.6, cb + 3.6
    mb.box(up, wa, wb, -1.3, 1.3, z0, 3.4, skip=("nz",))
    mb.box("glass" if not burnt else "char", wb - 0.02, wb + 0.02, -1.1, 1.1, 2.3, 3.2)
    mb.box(trim, wa - 0.1, wb + 0.1, -1.4, 1.4, 3.4, 3.55)
    # stern rail + flag staff
    for y in (-hw, hw):
        cg.bar(mb, "iron", (-L / 2 + 1.0, y, 1.42), (ca - 0.3, y, 1.42 + 0.0), 0.03)
    for k in range(5):
        xx = -L / 2 + 1.0 + k * (ca - 0.3 - (-L / 2 + 1.0)) / 4.0
        for y in (-hw, hw):
            cg.bar(mb, "iron", (xx, y, 1.0), (xx, y, 1.45), 0.025)
    cg.bar(mb, "iron", (-L / 2 + 0.6, 0.0, 1.3), (-L / 2 + 0.6, 0.0, 4.6), 0.04)
    return mb


def dock(seed=0):
    """Floating landing stage: local x along the quay, -y = river side, +y = quay side; z = 0 waterline."""
    r = rng(seed)
    mb = builder()
    L, W = r.uniform(20.0, 26.0), DOCK_W
    mb.box("hull", -L / 2, L / 2, -W / 2, W / 2, -0.7, 0.45, skip=("nz",))  # steel pontoon
    mb.box("deck", -L / 2 + 0.1, L / 2 - 0.1, -W / 2 + 0.1, W / 2 - 0.1, 0.45, 0.52, skip=("nz",))  # timber deck
    for x in (-L / 2 + 0.8, L / 2 - 0.8):
        for y in (-W / 2 + 0.5, W / 2 - 0.5):
            cg.prism(mb, "iron", (x, y, 0.52), (x, y, 1.0), 0.2, 0.16, 8)
    # railing on the river side ends and the quay side (gangway gap in the middle)
    ys = -W / 2 + 0.15
    for k in range(int(L / 2.0) + 1):
        x = -L / 2 + 0.3 + k * (L - 0.6) / int(L / 2.0)
        if abs(x) < 1.6:
            continue  # gangway opening
        cg.bar(mb, "iron", (x, W / 2 - 0.15, 0.52), (x, W / 2 - 0.15, 1.6), 0.03)
    cg.bar(mb, "iron", (-L / 2 + 0.3, W / 2 - 0.15, 1.6), (-1.6, W / 2 - 0.15, 1.6), 0.035)
    cg.bar(mb, "iron", (1.6, W / 2 - 0.15, 1.6), (L / 2 - 0.3, W / 2 - 0.15, 1.6), 0.035)
    for x in (-L / 2 + 0.3, L / 2 - 0.3):
        cg.bar(mb, "iron", (x, ys, 0.52), (x, ys, 1.6), 0.03)
        cg.bar(mb, "iron", (x, ys, 1.6), (x, W / 2 - 0.15, 1.6), 0.035)
    # gangway: deck edge (y = W/2, z 0.52) -> quay edge (y = W/2 + DOCK_GAP, z = GANGWAY_RISE)
    y0, y1 = W / 2, W / 2 + DOCK_GAP + 0.3
    p = [(-1.2, y0, 0.52), (1.2, y0, 0.52), (1.2, y1, GANGWAY_RISE + 0.02), (-1.2, y1, GANGWAY_RISE + 0.02)]
    n = norm(geom.cross(geom.sub(p[1], p[0]), geom.sub(p[3], p[0])))
    mb.poly("deck", p, n)
    mb.poly("hull", p[::-1], geom.mul(n, -1.0))
    for x in (-1.25, 1.25):
        cg.bar(mb, "iron", (x, y0, 0.52 + 1.0), (x, y1, GANGWAY_RISE + 1.0), 0.03)
        cg.bar(mb, "iron", (x, y0, 0.52), (x, y0, 1.52), 0.03)
        cg.bar(mb, "iron", (x, y1, GANGWAY_RISE), (x, y1, GANGWAY_RISE + 1.0), 0.03)
    return mb


MESHES = {
    "SM_TourBoat_0": lambda: tour_boat(4100),
    "SM_TourBoat_1": lambda: tour_boat(4101),
    "SM_TourBoat_Burnt": lambda: tour_boat(4102, burnt=True),
    "SM_Dock_0": lambda: dock(4200),
    "SM_Dock_1": lambda: dock(4201),
}


def _quay_edge(side):
    return cg.Y_WATER0 if side > 0 else cg.Y_WATER1


def _bridges_x():
    return (-1200.0, -600.0, 0.0, 600.0, 1200.0, 1800.0, 2400.0, 3000.0)  # paris_common.BRIDGE_ROWS_X


def river_layout(bridges_x=None, x_range=X_RANGE):
    """[(mesh, (x, y, z) world m, (pitch, yaw, roll) deg, tag)] for docks, boats and the lower-quay tree rows.

    mesh is a key of MESHES, or "tree" (05 picks a SM_Tree_* variant). Tags: "dock", "boat", "burning", "capsized",
    "tree". Deterministic (seeded), no dependency on the editor."""
    bridges_x = bridges_x or _bridges_x()
    r = rng(4004)
    out = []
    dock_x = {1: [], -1: []}
    for i, (x, side, moored) in enumerate(DOCKS):
        edge = _quay_edge(side)
        y = edge + side * (DOCK_GAP + DOCK_W / 2.0)
        yaw = 180.0 if side > 0 else 0.0  # local +y (gangway) must point at the quay
        out.append(("SM_Dock_%d" % (i % 2), (x, y, cg.Z_WATER), (0.0, yaw, 0.0), "dock"))
        dock_x[side].append(x)
        if moored:
            by = y + side * (DOCK_W / 2.0 + 0.6 + BOAT_W / 2.0)
            mesh = "SM_TourBoat_Burnt" if moored == "burnt" else "SM_TourBoat_%d" % r.randint(0, 1)
            byaw = r.choice((0.0, 180.0))
            pitch, roll = (0.0, 0.0) if moored != "burnt" else (1.5, -4.0)  # burnt hull lists and settles
            z = cg.Z_WATER - (0.35 if moored == "burnt" else 0.0)
            out.append((mesh, (x + r.uniform(-3.0, 3.0), by, z), (pitch, byaw, roll), "burning" if moored == "burnt" else "boat"))
    for x, y, yaw, kind in SAILING:
        if kind == "capsized":
            out.append(("SM_TourBoat_1", (x, y, cg.Z_WATER + 0.25), (0.0, yaw, 168.0), "capsized"))
        else:
            out.append(("SM_TourBoat_%d" % r.randint(0, 1), (x, y, cg.Z_WATER), (0.0, yaw, 0.0), "boat"))
    # lower-quay tree rows (river side of the promenade), clear of bridges, stairs and landing stages
    for side in (1, -1):
        wall = cg.Y_WALL0 if side > 0 else cg.Y_WALL1
        y = wall + side * 7.0
        x = x_range[0] + 6.0
        while x < x_range[1] - 6.0:
            seg = round(x / 200.0) * 200.0
            lx = x - seg
            s0, s1 = cg.stair_span(side)
            clear = (all(abs(x - bx) > 26.0 for bx in bridges_x)
                     and not (s0 - 3.0 < lx < s1 + 3.0 and seg not in bridges_x)
                     and all(abs(x - dx) > 16.0 for dx in dock_x[side]))
            if clear and r.random() > 0.05:
                out.append(("tree", (x + r.uniform(-0.6, 0.6), y + r.uniform(-0.4, 0.4), cg.Z_LOWQ), (0.0, r.uniform(0, 360), 0.0), "tree"))
            x += TREE_STEP
    return out


def check_layout(items, bridges_x=None):
    """Clearance problems of boats / docks against bridges, barges and each other (list of strings, empty = ok)."""
    bridges_x = bridges_x or _bridges_x()
    errs = []
    bodies = [(m, p, t) for m, p, _, t in items if t != "tree"]
    for m, (x, y, z), t in bodies:
        half = 26.0 if "Boat" in m else 14.0
        if not (cg.Y_WATER0 + 0.5 < y < cg.Y_WATER1 - 0.5):
            errs.append("%s at %.0f,%.0f is outside the water" % (m, x, y))
        for bx in bridges_x:
            if abs(x - bx) < half + 21.0:
                errs.append("%s at x %.0f within %.0f m of the bridge at %.0f" % (m, x, abs(x - bx), bx))
        for bx, side in BARGE_SPOTS:
            by = (cg.Y_WATER0 + 3.2) if side > 0 else (cg.Y_WATER1 - 3.2)
            if abs(x - bx) < half + 21.0 and abs(y - by) < 9.0:
                errs.append("%s at %.0f,%.0f overlaps the barge at %.0f" % (m, x, y, bx))
    for i, (m1, p1, _) in enumerate(bodies):
        for m2, p2, _ in bodies[i + 1:]:
            if abs(p1[0] - p2[0]) < 24.0 and abs(p1[1] - p2[1]) < 5.4:
                errs.append("%s and %s overlap near %.0f,%.0f" % (m1, m2, p1[0], p1[1]))
    return errs


if __name__ == "__main__":
    import time
    from collections import Counter

    for name, fn in MESHES.items():
        t0 = time.time()
        mb = fn()
        print("%-20s tris=%6d slots=%-34s bounds=%s %.2fs" % (name, mb.tri_count(), ",".join(mb.used_slots())[:34],
                                                          tuple(tuple(round(v, 1) for v in b) for b in mb.bounds()), time.time() - t0))
    items = river_layout()
    print("layout:", dict(Counter(t for *_, t in items)))
    errs = check_layout(items)
    print("clearance:", "OK" if not errs else errs)
