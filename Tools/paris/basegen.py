"""Red-faction field base generator (pure Python on geom.MeshBuilder, no `unreal` import; testable with CPython).

B2 (125 §3.3): the two cell rows north of the board (zones.BASE_RED_ROWS x BASE_RED_COLS) become fortified
compounds. Everything is procedural:
    sandbag walls + concrete jersey barriers around the compound (inside the sidewalk ring, |x|,|y| <= 78 m)
    gates on the four sides with red flags, a red banner across the gate and a red signal lamp
    two sandbagged watch towers on a diagonal, each with a searchlight (07_base_red.py adds the SpotLight + beam cone);
    every searchlight points into the northern half-plane (yaw within +-SEARCH_YAW_SPREAD of +x) so no beam crosses the board
    a command tent with red banner strips, rows of field tents, crates and fuel drums, a central flag mast

Cell-local frame in metres (cell centre = origin); cell_layout(c, r) is deterministic per cell so 05_city_layout.py
(meshes) and 07_base_red.py (lights, beams) place matching instances without sharing state.
Flags / banners are single quads with UV u = hoist(0)..fly(1), v = top(0)..bottom(1): M_Paris_Cloth animates them
with world-position-offset waves (pinned at u = 0, or at both ends for banners).
"""
import math

import geom
from geom import Frame, MeshBuilder, Z, norm, rng
import citygen as cg

SLOT_MATERIALS = {
    "canvas": "MI_Paint_Canvas", "canvas2": "MI_Paint_CanvasDark", "sandbag": "MI_Paint_Sandbag", "concrete": "MI_Paint_Concrete",
    "iron": "MI_Paint_Iron", "steel": "MI_Paint_Steel", "wood": "MI_Paint_Frame", "pole": "MI_Paint_LampPost",
    "cloth": "MI_Cloth_Red", "banner": "MI_Cloth_RedBanner", "signal": "MI_Signal_Red", "lens": "MI_Searchlight_Lens",
    "beam": "M_FX_Beam",  # master material (additive, unlit), not an instance
}
SLOTS = list(SLOT_MATERIALS)

BOUND = 78.0  # compound wall line (inside the 81 m facade line of a normal block)
GATE_HALF = 6.0
TOWER_H = 7.0  # platform height of the watch towers
SEARCH_ELEV = {"A": 55.0, "B": 40.0}  # searchlight elevation (deg) of the two variants
SEARCH_PIVOT = (0.0, 0.0, 1.2)
SEARCH_LENS = 0.55  # pivot -> lens along the drum axis
BEAM_LEN = {"A": 150.0, "B": 120.0}
BEAM_R1 = 7.0
SEARCH_YAW_SPREAD = 65.0  # deg either side of north (+x); the board lies south, so beams never lean over it


def builder():
    return MeshBuilder(SLOTS)


def disc(mb, slot, c, axis, r, sides=12, uvs=None):
    ax = norm(axis)
    up = (1.0, 0.0, 0.0) if abs(ax[2]) > 0.9 else Z
    u = norm(geom.cross(ax, up))
    w = geom.cross(ax, u)
    pts = []
    for i in range(sides):
        a = 2 * math.pi * i / sides
        d = geom.add(geom.mul(u, math.cos(a)), geom.mul(w, math.sin(a)))
        pts.append(geom.add(c, geom.mul(d, r)))
    mb.poly(slot, pts, ax, uvs)


# ---------------------------------------------------------------- fortifications
def sandbags(seed=0, length=6.0, height=1.5, depth=0.8):
    """Stacked sandbag wall segment along local x, centred on the origin, base at z 0."""
    r = rng(seed)
    mb = builder()
    bag = (0.30, 0.20, 0.125)  # half sizes
    rows = int(round(height / (bag[2] * 2 * 0.9)))
    n = int(length / (bag[0] * 2 * 0.95))
    for k in range(rows):
        z = bag[2] + k * bag[2] * 2 * 0.9
        shrink = 1.0 - 0.06 * k
        for j in range(n + (k % 2)):
            x = -length / 2 + bag[0] + (j - 0.5 * (k % 2)) * bag[0] * 2 * 0.95
            if abs(x) > length / 2 - bag[0] * 0.6:
                continue
            for y in (-depth / 2 + bag[1], depth / 2 - bag[1]):
                c = (x + r.uniform(-0.03, 0.03), y * shrink + r.uniform(-0.03, 0.03), z)
                cg.blob(mb, "sandbag", c, bag[0] * r.uniform(0.95, 1.05), bag[1] * r.uniform(0.95, 1.1), bag[2], r, 0.12, 0)
    return mb


def barrier(length=3.0):
    """Concrete jersey barrier along local x (0.85 m high)."""
    mb = builder()
    fr = Frame((0.0, 0.0), (0.0, 1.0))  # a = y, b = x
    prof = [(-0.4, 0.0), (0.4, 0.0), (0.4, 0.1), (0.2, 0.36), (0.12, 0.85), (-0.12, 0.85), (-0.2, 0.36), (-0.4, 0.1)]
    mb.extrude_profile("concrete", fr, prof, -length / 2, length / 2)
    return mb


# ---------------------------------------------------------------- cloth
def flag_card(mb, slot, hoist, height, width, direction=(1.0, 0.0, 0.0)):
    """Flag hanging from the vertical hoist edge at `hoist` (top point), flying along `direction`."""
    d = norm(direction)
    p0 = hoist
    p1 = geom.add(hoist, geom.mul(d, width))
    p2 = (p1[0], p1[1], p1[2] - height)
    p3 = (p0[0], p0[1], p0[2] - height)
    n = norm(geom.cross(d, Z))
    mb.poly(slot, [p0, p1, p2, p3], n, [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)])


def flag(height=9.0, w=2.4, h=1.6):
    """Flag pole with a red flag at the top (fly along +x)."""
    mb = builder()
    cg.prism(mb, "pole", (0, 0, 0), (0, 0, height), 0.07, 0.05, 8)
    cg.prism(mb, "pole", (0, 0, 0), (0, 0, 0.25), 0.2, 0.16, 8)
    cg.blob(mb, "pole", (0, 0, height + 0.1), 0.1, 0.1, 0.1, rng(1), 0.0, 0)
    flag_card(mb, "cloth", (0.06, 0.0, height - 0.1), h, w)
    return mb


def mast(height=14.0):
    mb = builder()
    cg.prism(mb, "steel", (0, 0, 0), (0, 0, height), 0.12, 0.08, 10)
    mb.box("concrete", -0.8, 0.8, -0.8, 0.8, 0.0, 0.5)
    flag_card(mb, "cloth", (0.1, 0.0, height - 0.15), 2.6, 4.0)
    return mb


def banner(span=8.0, height=1.2, pole_h=5.5):
    """Banner stretched between two poles at x = +-span/2 (cloth pinned at both ends by the material)."""
    mb = builder()
    for x in (-span / 2, span / 2):
        cg.prism(mb, "pole", (x, 0, 0), (x, 0, pole_h), 0.06, 0.05, 8)
        cg.prism(mb, "pole", (x, 0, 0), (x, 0, 0.2), 0.18, 0.15, 8)
    z1 = pole_h - 0.3
    p0, p1 = (-span / 2 + 0.2, 0.0, z1), (span / 2 - 0.2, 0.0, z1)
    p2, p3 = (p1[0], 0.0, z1 - height), (p0[0], 0.0, z1 - height)
    mb.poly("banner", [p0, p1, p2, p3], (0.0, -1.0, 0.0), [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)])
    return mb


# ---------------------------------------------------------------- tents
def tent(length, width, wall, ridge, command=False):
    """Ridge tent along local x: canvas walls, gable roof, dark entrance flap on the -x gable."""
    mb = builder()
    hl, hw = length / 2, width / 2
    mb.box("canvas", -hl, hl, -hw, hw, 0.0, wall, skip=("pz", "nz"))
    for s in (-1.0, 1.0):
        quad = [(-hl, s * hw, wall), (hl, s * hw, wall), (hl, 0.0, ridge), (-hl, 0.0, ridge)]
        mb.poly("canvas", quad, norm((0.0, s * (ridge - wall), hw)))
    for s in (-1.0, 1.0):
        tri = [(s * hl, -hw, wall), (s * hl, hw, wall), (s * hl, 0.0, ridge)]
        mb.poly("canvas", tri, (s, 0.0, 0.0))
    # entrance flap and eave line
    mb.poly("canvas2", [(-hl - 0.02, -0.7, 0.0), (-hl - 0.02, 0.7, 0.0), (-hl - 0.02, 0.7, wall * 0.9), (-hl - 0.02, -0.7, wall * 0.9)], (-1.0, 0.0, 0.0))
    # guy ropes / stakes as thin dark pegs
    for x in (-hl + 0.6, 0.0, hl - 0.6):
        for s in (-1.0, 1.0):
            mb.box("iron", x - 0.04, x + 0.04, s * (hw + 0.9) - 0.04, s * (hw + 0.9) + 0.04, 0.0, 0.3)
    if command:
        # red banner strips under both eaves + pennants on the ridge ends
        for s in (-1.0, 1.0):
            y = s * (hw + 0.03)
            pts = [(-hl + 0.3, y, wall + 0.05), (hl - 0.3, y, wall + 0.05), (hl - 0.3, y, wall - 0.55), (-hl + 0.3, y, wall - 0.55)]
            if s < 0:
                pts = pts[::-1]
            mb.poly("banner", pts, (0.0, s, 0.0), [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)] if s > 0 else [(0.0, 1.0), (1.0, 1.0), (1.0, 0.0), (0.0, 0.0)])
        for s in (-1.0, 1.0):
            x = s * (hl - 0.4)
            cg.prism(mb, "pole", (x, 0, ridge - 0.1), (x, 0, ridge + 1.6), 0.04, 0.03, 6)
            flag_card(mb, "cloth", (x + 0.04, 0.0, ridge + 1.55), 0.8, 1.2)
    return mb


# ---------------------------------------------------------------- towers, searchlights, lamps
def tower(h=TOWER_H, half=1.8):
    """Sandbagged watch tower: 4 tapered steel legs, cross braces, plank platform, sandbag parapet."""
    mb = builder()
    legs = [(s * half, t * half) for s in (-1, 1) for t in (-1, 1)]
    for lx, ly in legs:
        cg.prism(mb, "steel", (lx * 1.15, ly * 1.15, 0.0), (lx, ly, h), 0.13, 0.1, 8)
        mb.box("concrete", lx * 1.15 - 0.35, lx * 1.15 + 0.35, ly * 1.15 - 0.35, ly * 1.15 + 0.35, 0.0, 0.25)
    for k in range(4):
        (ax_, ay_), (bx_, by_) = legs[[0, 1, 3, 2][k]], legs[[1, 3, 2, 0][k]]
        for z0, z1 in ((0.4, h * 0.55), (h * 0.55, h - 0.3)):
            a, b = (ax_ * 1.1, ay_ * 1.1, z0), (bx_ * 1.02, by_ * 1.02, z1)
            c = geom.mul(geom.add(a, b), 0.5)
            ax = norm(geom.sub(b, a))
            ay = norm(geom.cross(Z, ax)) if abs(ax[2]) < 0.95 else (1.0, 0.0, 0.0)
            az = geom.cross(ax, ay)
            mb.obox("steel", c, ax, ay, az, geom.length(geom.sub(b, a)) / 2, 0.05, 0.05)
    mb.box("wood", -half - 0.2, half + 0.2, -half - 0.2, half + 0.2, h, h + 0.25)
    sq = [(-half - 0.2, -half - 0.2), (half + 0.2, -half - 0.2), (half + 0.2, half + 0.2), (-half - 0.2, half + 0.2)]
    mb.band("sandbag", sq, True, -0.45, 0.0, h + 0.25, h + 1.15)
    # ladder on the -x side
    for z in range(1, int(h)):
        mb.box("steel", -half * 1.1 - 0.4, -half * 1.1 - 0.35, -0.3, 0.3, z - 0.02, z + 0.02)
    for y in (-0.3, 0.3):
        mb.box("steel", -half * 1.1 - 0.4, -half * 1.1 - 0.35, y - 0.03, y + 0.03, 0.2, h + 0.2)
    return mb


def search_dir(variant):
    e = math.radians(SEARCH_ELEV[variant])
    return (math.cos(e), 0.0, math.sin(e))


def lens_point(variant):
    return geom.add(SEARCH_PIVOT, geom.mul(search_dir(variant), SEARCH_LENS))


def searchlight(variant="A"):
    """Tripod searchlight: drum on a yoke, pointing along +x at SEARCH_ELEV[variant] degrees elevation."""
    mb = builder()
    d = search_dir(variant)
    pv = SEARCH_PIVOT
    for k in range(3):
        a = math.radians(90.0 + 120.0 * k)
        foot = (0.75 * math.cos(a), 0.75 * math.sin(a), 0.0)
        cg.prism(mb, "steel", foot, (0.0, 0.0, pv[2] - 0.25), 0.05, 0.04, 6)
    mb.box("steel", -0.12, 0.12, -0.12, 0.12, pv[2] - 0.3, pv[2] - 0.05)
    for s in (-1.0, 1.0):
        mb.box("steel", -0.06, 0.06, s * 0.66 - 0.03, s * 0.66 + 0.03, pv[2] - 0.05, pv[2] + 0.4)
        mb.box("steel", -0.06, 0.06, s * 0.66 - 0.03, s * 0.66 + 0.03 if s > 0 else s * 0.66 + 0.03, pv[2] - 0.05, pv[2])
    p0 = geom.sub(pv, geom.mul(d, 0.35))
    p1 = geom.add(pv, geom.mul(d, SEARCH_LENS))
    cg.prism(mb, "steel", p0, p1, 0.55, 0.6, 14, caps=False)
    disc(mb, "steel", p0, geom.mul(d, -1.0), 0.55, 14)
    disc(mb, "lens", geom.add(p1, geom.mul(d, 0.01)), d, 0.58, 14)
    return mb


def beam(variant="A"):
    """Additive light cone starting at the searchlight lens (same local frame as searchlight()): v = 0 lens .. 1 tip."""
    mb = builder()
    d = search_dir(variant)
    p0 = geom.add(lens_point(variant), geom.mul(d, 0.05))
    p1 = geom.add(p0, geom.mul(d, BEAM_LEN[variant]))
    up = (1.0, 0.0, 0.0) if abs(d[2]) > 0.9 else Z
    u = norm(geom.cross(d, up))
    w = geom.cross(d, u)
    n = 16
    for i in range(n):
        a0, a1 = 2 * math.pi * i / n, 2 * math.pi * (i + 1) / n
        d0 = geom.add(geom.mul(u, math.cos(a0)), geom.mul(w, math.sin(a0)))
        d1 = geom.add(geom.mul(u, math.cos(a1)), geom.mul(w, math.sin(a1)))
        q = [geom.add(p0, geom.mul(d0, 0.58)), geom.add(p0, geom.mul(d1, 0.58)), geom.add(p1, geom.mul(d1, BEAM_R1)), geom.add(p1, geom.mul(d0, BEAM_R1))]
        nn = geom.add(d0, d1)
        mb.poly("beam", q, nn, [(i / n, 0.0), ((i + 1) / n, 0.0), ((i + 1) / n, 1.0), (i / n, 1.0)])
    return mb


def signal_lamp(h=6.0):
    """Red signal lamp on a pole (the sphere is emissive; 07_base_red.py adds a PointLight at the gates)."""
    mb = builder()
    cg.prism(mb, "pole", (0, 0, 0), (0, 0, h), 0.05, 0.04, 8)
    mb.box("steel", -0.15, 0.15, -0.15, 0.15, h, h + 0.25)
    cg.blob(mb, "signal", (0, 0, h + 0.55), 0.3, 0.3, 0.3, rng(2), 0.0, 1)
    mb.box("steel", -0.05, 0.05, -0.05, 0.05, h + 0.85, h + 1.2)
    return mb


def drum():
    mb = builder()
    cg.prism(mb, "canvas2", (0, 0, 0), (0, 0, 0.9), 0.3, 0.3, 12)
    cg.prism(mb, "steel", (0, 0, 0.28), (0, 0, 0.34), 0.31, 0.31, 12, caps=False)
    cg.prism(mb, "steel", (0, 0, 0.58), (0, 0, 0.64), 0.31, 0.31, 12, caps=False)
    return mb


def crate(seed=0):
    r = rng(seed)
    mb = builder()
    L, W, H = r.uniform(1.0, 1.6), r.uniform(0.8, 1.2), r.uniform(0.7, 1.1)
    mb.box("wood", -L / 2, L / 2, -W / 2, W / 2, 0.0, H)
    for x in (-L / 2 + 0.08, L / 2 - 0.08):
        mb.box("iron", x - 0.02, x + 0.02, -W / 2 - 0.01, W / 2 + 0.01, 0.0, H + 0.01)
    return mb


MESHES = {
    "SM_Base_Sandbags_0": lambda: sandbags(0),
    "SM_Base_Sandbags_1": lambda: sandbags(1),
    "SM_Base_Barrier": barrier,
    "SM_Base_Flag": flag,
    "SM_Base_Mast": mast,
    "SM_Base_Banner": banner,
    "SM_Base_Tent_Cmd": lambda: tent(12.0, 8.0, 2.0, 4.6, True),
    "SM_Base_Tent_Field": lambda: tent(6.0, 4.0, 1.4, 3.0),
    "SM_Base_Tent_Long": lambda: tent(10.0, 4.5, 1.6, 3.4),
    "SM_Base_Tower": tower,
    "SM_Base_Searchlight_A": lambda: searchlight("A"),
    "SM_Base_Searchlight_B": lambda: searchlight("B"),
    "SM_Base_Beam_A": lambda: beam("A"),
    "SM_Base_Beam_B": lambda: beam("B"),
    "SM_Base_Signal": signal_lamp,
    "SM_Base_Drum": drum,
    "SM_Base_Crate_0": lambda: crate(0),
    "SM_Base_Crate_1": lambda: crate(1),
}
NON_NANITE = {"SM_Base_Flag", "SM_Base_Mast", "SM_Base_Banner", "SM_Base_Beam_A", "SM_Base_Beam_B"}  # WPO cloth / additive beams


# ---------------------------------------------------------------- cell layout
def cell_seed(c, r):
    return 31000 + c * 101 + r * 7


def rot2(x, y, yaw):
    a = math.radians(yaw)
    return (x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a))


def cell_layout(c, r):
    """Props of one base cell: [(mesh_name, (x, y, z) cell-local m, (pitch, yaw, roll) deg, extra dict)].

    extra: {"light": "spot", "variant": "A"|"B"} for searchlights, {"light": "point"} for the gate signal lamps."""
    rd = rng(cell_seed(c, r))
    out = []

    def put(name, x, y, z=0.0, yaw=0.0, **extra):
        out.append((name, (x, y, z), (0.0, yaw, 0.0), extra))

    B = BOUND
    # perimeter: side k has outward normal (nx, ny); wall runs along the tangent
    for k, (nx, ny) in enumerate(((0, -1), (1, 0), (0, 1), (-1, 0))):
        tx, ty = -ny, nx  # tangent
        yaw = math.degrees(math.atan2(ty, tx))
        t = -B + 1.0
        while t < B - 1.0:
            if -GATE_HALF - 0.5 < t + 3.0 < GATE_HALF + 0.5 or -GATE_HALF - 0.5 < t < GATE_HALF + 0.5:
                t = GATE_HALF + 0.5
                continue
            sand = rd.random() < 0.7
            ln = 6.0 if sand else 3.0
            if t + ln > B - 0.5:
                break
            cx, cy = nx * B + tx * (t + ln / 2), ny * B + ty * (t + ln / 2)
            put("SM_Base_Sandbags_%d" % rd.randint(0, 1) if sand else "SM_Base_Barrier", cx, cy, 0.0, yaw + rd.uniform(-3, 3))
            t += ln + 0.3
        # gate: flags either side, banner across, signal lamp
        inset = B - 2.0
        for s in (-1.0, 1.0):
            put("SM_Base_Flag", nx * inset + tx * s * 7.5, ny * inset + ty * s * 7.5, 0.0, yaw + 180.0 + rd.uniform(-20, 20))
        put("SM_Base_Banner", nx * (B - 3.5), ny * (B - 3.5), 0.0, yaw)
        put("SM_Base_Signal", nx * (B - 5.0) + tx * 9.5, ny * (B - 5.0) + ty * 9.5, 0.0, 0.0, light="point")
    # towers on one diagonal, signal lamps on the other
    diag = rd.choice((1.0, -1.0))
    tv = rd.choice(("A", "B"))
    for s in (-1.0, 1.0):
        tx_, ty_ = s * 70.0, s * diag * 70.0
        put("SM_Base_Tower", tx_, ty_, 0.0, 0.0)
        yaw = rd.uniform(-SEARCH_YAW_SPREAD, SEARCH_YAW_SPREAD)  # northern half-plane only
        put("SM_Base_Searchlight_" + tv, tx_, ty_, TOWER_H + 0.25, yaw, light="spot", variant=tv, beam=True)
        put("SM_Base_Signal", -s * 70.0, s * diag * 70.0, 0.0, 0.0)
    # command tent, mast, field tents
    cmd_yaw = rd.choice((0.0, 90.0))
    put("SM_Base_Tent_Cmd", 0.0, 0.0, 0.0, cmd_yaw)
    mx, my = rot2(-16.0, 0.0, cmd_yaw)  # in front of the entrance (-x gable)
    put("SM_Base_Mast", mx, my, 0.0, rd.uniform(0, 360))
    gv = "B" if tv == "A" else "A"
    gx, gy = rot2(-24.0, 9.0, cmd_yaw)
    put("SM_Base_Searchlight_" + gv, gx, gy, 0.0, rd.uniform(-SEARCH_YAW_SPREAD, SEARCH_YAW_SPREAD), variant=gv)  # prop only
    for x in (-58.0, -44.0, -30.0, 30.0, 44.0, 58.0):
        for y in (-48.0, -32.0, -16.0, 0.0, 16.0, 32.0, 48.0):
            if rd.random() < 0.28:
                continue
            long = rd.random() < 0.15
            put("SM_Base_Tent_Long" if long else "SM_Base_Tent_Field", x + rd.uniform(-1.5, 1.5), y + rd.uniform(-1.5, 1.5), 0.0,
                (90.0 if abs(x) > 50 else 0.0) + rd.uniform(-6, 6))
    for _ in range(rd.randint(6, 10)):
        cx, cy = rd.uniform(-66, 66), rd.uniform(-60, 60)
        if abs(cx) < 20 and abs(cy) < 14:
            continue
        for _ in range(rd.randint(2, 5)):
            name = "SM_Base_Drum" if rd.random() < 0.5 else "SM_Base_Crate_%d" % rd.randint(0, 1)
            put(name, cx + rd.uniform(-2.2, 2.2), cy + rd.uniform(-2.2, 2.2), 0.0, rd.uniform(0, 360))
    return out


def cell_lights(c, r):
    """[(kind 'spot'|'point', light pos (x, y, z) cell-local m, (pitch, yaw, roll), variant, prop origin (x, y, z))]
    derived from cell_layout(); the beam cone of a spot is placed at the prop origin with the same yaw."""
    out = []
    for name, (x, y, z), (pitch, yaw, roll), extra in cell_layout(c, r):
        if extra.get("light") == "spot":
            v = extra["variant"]
            lp = lens_point(v)
            lx, ly = rot2(lp[0], lp[1], yaw)
            out.append(("spot", (x + lx, y + ly, z + lp[2]), (SEARCH_ELEV[v], yaw, 0.0), v, (x, y, z)))
        elif extra.get("light") == "point":
            out.append(("point", (x, y, z + 6.55), (0.0, 0.0, 0.0), None, (x, y, z)))
    return out


if __name__ == "__main__":
    import time

    for name, fn in MESHES.items():
        t0 = time.time()
        mb = fn()
        print("%-24s tris=%6d slots=%-28s bounds=%s %.2fs" % (name, mb.tri_count(), ",".join(mb.used_slots())[:28],
                                                          tuple(tuple(round(v, 1) for v in b) for b in mb.bounds()), time.time() - t0))
    props = cell_layout(3, 8)
    from collections import Counter
    print("cell (3,8): %d props" % len(props), dict(Counter(p[0] for p in props)))
    print("lights:", cell_lights(3, 8))
