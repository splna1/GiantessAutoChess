"""Step 05: city layout - streets, embedded 8x8 board, Haussmann blocks, Seine + bridges, street furniture.

The whole city is one regular grid of 200 m cells (the board is cells 0..7 x 0..7, see paris_common):
  * every cell has a generated ground module (road half, kerbed sidewalk, courtyard); board cells carry a
    light/dark checker pad in the courtyard and the glowing board grid runs down the street centre lines;
  * every building cell gets 4 Haussmann L-corners + 4 infills (04_haussmann_modules.py) rotated 0/90/180/270;
    damage cells use burnt/collapsed variants and scorched ground;
  * the four centre cells are an open plaza with an obelisk; column SEINE_COL is the river with quays and
    stone bridges; the Eiffel column gets the Champ de Mars park (the tower itself is step 06).
Everything is placed as InstancedStaticMeshComponents on a handful of actors (tag "City").
Meshes are rebuilt only when missing or with --rebuild.

B1 (125 schedule 2026-10-01): Eiffel tower moved to the west side (cell (-2, 3), (-100, -1100) m, Champ de Mars rows
1..4 centred on the dividing line); south blocks x ∈ [−1400,−800] cleared; western industrial belt (07_industrial.py).
B2 (2026-10-02): north side - zones "base_red" (basegen / 07_base_red.py props), "cathedral" (paved close under the
Notre-Dame scan placed by 06_landmarks.py) and "low" (SM_Hsm_Low* modules, <= 18 m). Board 8×8 interior unchanged:
cell_kind() classifies it before anything else and never consults zones.py, which is the single source of truth for
the background area types. The board's module variants, ground yaws and street furniture (|x|,|y| <= 830 m) come from
board_frozen.json (the B1 layout replayed by freeze_board_b1.py), not from the random stream, so background edits can
never reshuffle the board again.
B5 (2026-10-02): south side - zones "base_blue" are kept as low base ground and receive the deterministic blue-front
kit and staged vehicles from 07_base_blue.py. The frozen board branch remains the first branch in cell_kind().

Usage (through Tools/ue_run.py):
    05_city_layout.py [--rebuild] [--no-back] [--only SM_ChampDeMars ...]   (--only rebuilds just those meshes;
                      SM_ChampDeMars depends on EIFFEL_CELL / CHAMP_ROWS and must be rebuilt when they change;
                      --rebuild also regenerates the industrial and base meshes)
"""
import importlib.util
import json
import math
import os
import sys
import time

import unreal

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import basegen  # noqa: E402
import citygen as cg  # noqa: E402
import paris_common as pc  # noqa: E402
import ue_mesh  # noqa: E402
import zones  # noqa: E402


def load_step(filename):
    """Import a numbered step module (07_industrial.py, 07_base_red.py) from this folder by relative path."""
    spec = importlib.util.spec_from_file_location(filename.split("_", 1)[1][:-3], os.path.join(HERE, filename))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


industrial = load_step("07_industrial.py")  # west: chimneys, warehouses, water towers (B1)
base_red = load_step("07_base_red.py")  # north: red base meshes (B2); its lights/beams are its own step
base_blue = load_step("07_base_blue.py")  # south: blue command centre meshes and staged vehicles (B5)
ruins = load_step("09_ruins.py")

with open(os.path.join(HERE, "board_frozen.json"), encoding="utf-8") as _f:
    FROZEN = json.load(_f)  # B1 board interior (freeze_board_b1.py): cells "c,r" -> ground yaw + 4 x [L, infill]; furniture
FROZEN_REGION = float(FROZEN["region_m"])

STEP = "City"
OUT = pc.MESH + "/City"
HSM = pc.MESH + "/Haussmann/"
N = pc.N


def mats():
    return {s: pc.MAT + "/Instances/" + mi for s, mi in cg.SLOT_MATERIALS.items()}


PLAZA_KINDS = {}
for _c, _r in pc.PLAZA_CELLS:
    PLAZA_KINDS[(1 if _r >= N // 2 else -1, 1 if _c >= N // 2 else -1)] = "dark" if (_c + _r) % 2 == 0 else "light"

TREES = ["SM_Tree_%d" % i for i in range(4)]
CARS = ["SM_Car_%d" % i for i in range(5)]
CARS_BURNT = ["SM_Car_Burnt_%d" % i for i in range(2)]
BARGES = ["SM_Barge_%d" % i for i in range(2)]

MESHES = {
    "SM_Cell_Light": lambda: cg.ground_cell("light"),
    "SM_Cell_Dark": lambda: cg.ground_cell("dark"),
    "SM_Cell_LightScorched": lambda: cg.ground_cell("light", True, True, 11),
    "SM_Cell_DarkScorched": lambda: cg.ground_cell("dark", True, True, 12),
    "SM_Cell_Garden": lambda: cg.ground_cell("garden", False),
    "SM_Cell_Court": lambda: cg.ground_cell("court", False),
    "SM_Cell_Base": lambda: cg.ground_cell("base", False),
    "SM_CathedralClose": lambda: cg.cathedral_close(len(zones.CATHEDRAL_CELLS)),
    "SM_Plaza": lambda: cg.plaza(PLAZA_KINDS),
    "SM_ChampDeMars": lambda: cg.champ_de_mars(pc.CHAMP_ROWS[1] - pc.CHAMP_ROWS[0] + 1, pc.EIFFEL_CELL[1] - pc.CHAMP_ROWS[0]),
    "SM_BoardLines": lambda: cg.board_lines(N, pc.CELL),
    "SM_Seine": lambda: cg.seine_segment(False),
    "SM_Seine_Bridge": lambda: cg.seine_segment(True),
    "SM_Lamp": cg.lamp,
    "SM_Obelisk": cg.obelisk,
    "SM_FarGround": lambda: far_ground(),
}
for _i, _n in enumerate(TREES):
    MESHES[_n] = (lambda s: lambda: cg.tree(500 + s))(_i)
for _i, _n in enumerate(CARS):
    MESHES[_n] = (lambda s: lambda: cg.car(700 + s))(_i)
for _i, _n in enumerate(CARS_BURNT):
    MESHES[_n] = (lambda s: lambda: cg.car(800 + s, True))(_i)
for _i, _n in enumerate(BARGES):
    MESHES[_n] = (lambda s: lambda: cg.barge(900 + s))(_i)

L_OK = ["SM_Hsm_L_%02d" % i for i in range(8)]
L_BURNT = ["SM_Hsm_LBurnt_%02d" % i for i in range(3)]
L_RUIN = ["SM_Hsm_LRuin_%02d" % i for i in range(3)]
I_OK = ["SM_Hsm_Infill_%02d" % i for i in range(5)]
I_BURNT = ["SM_Hsm_InfillBurnt_00"]
I_RUIN = ["SM_Hsm_InfillRuin_%02d" % i for i in range(2)]
LOW_L = ["SM_Hsm_LowL_%02d" % i for i in range(6)]  # B2 low-rise district (04_haussmann_modules.py --group low)
LOW_I = ["SM_Hsm_LowInfill_%02d" % i for i in range(4)]
LOW_COURT = ["SM_Hsm_LowCourt_%02d" % i for i in range(4)]


def river_x_range(rows=None):
    """x extent (m) of the Seine segments laid out by main(): one 200 m segment centred on every street line."""
    rows = rows or pc.CITY_ROWS
    return 200.0 * (rows[0] - 4) - 100.0, 200.0 * (rows[1] - 3) + 100.0


def far_ground():
    """Ground plane under/around the city, with the Seine channel left open (the water sits at Z_WATER < 0)."""
    mb = cg.builder()
    E, z = 20000.0, -0.05
    xa, xb = river_x_range()
    ya = pc.cell_center(pc.SEINE_COL, 0)[1] - pc.CELL / 2.0
    yb = ya + pc.CELL
    cg.rect(mb, "bed", -E, xa, -E, E, z)
    cg.rect(mb, "bed", xb, E, -E, E, z)
    cg.rect(mb, "bed", xa, xb, -E, ya, z)
    cg.rect(mb, "bed", xa, xb, yb, E, z)
    return mb


def build_meshes(rebuild, only=()):
    m = mats()
    t0 = time.time()
    n = 0
    for name, fn in MESHES.items():
        path = OUT + "/" + name
        if rebuild or name in only or not pc.EAL.does_asset_exist(path):
            ue_mesh.build_static_mesh(path, fn(), m, nanite=True)
            n += 1
    unreal.SystemLibrary.execute_console_command(None, "obj gc")
    pc.log("city meshes built: %d in %.1fs" % (n, time.time() - t0))


# ---------------------------------------------------------------- cell classification
def cell_kind(c, r):
    """Classify cell (c, r) for layout generation.

    Board interior (8×8) is handled directly here and never routed through zones.
    Background cells delegate to zones.cell_zone() for area-type decisions.
    """
    # Board interior: 8×8 unchanged (B1 constraint)
    if 0 <= c < N and 0 <= r < N:
        return "plaza" if (c, r) in pc.PLAZA_CELLS else "board"

    # Seine river column (unchanged)
    if c == pc.SEINE_COL:
        return "river"

    # Champ de Mars park: now at west side middle via zones
    if c == zones.EIFFEL_NEW_COL and zones.CHAMP_NEW_ROWS[0] <= r <= zones.CHAMP_NEW_ROWS[1]:
        return "champ"

    # Background cells: delegate to zones for area type
    zone = zones.cell_zone(c, r)
    if zone in ("ruins", "ruins_low", "footprint"):
        zone = zones.base_zone(c, r)

    # B1: south_clear zone becomes empty (no buildings)
    if zone == "south_clear":
        return "empty"

    # B1: industrial zone (western tall buildings)
    if zone == "industrial":
        return "industrial"

    # B2: north side
    if zone in ("cathedral", "base_red", "base_blue", "low"):
        return zone

    # Default: treat all other zones as normal background ("back") for now
    # Future B5/B6 will handle base_blue/ruins here
    return "back"


def neighbours_damage(c, r):
    return any((c + dc, r + dr) in pc.DAMAGE_CELLS for dc in (-1, 0, 1) for dr in (-1, 0, 1))


def block_modules(c, r, rnd):
    """[(L, infill)] for the 4 quarters of the block in cell (c, r)."""
    out = []
    dmg = (c, r) in pc.DAMAGE_CELLS
    ruin = (c, r) == pc.RUIN_CELL
    near = not dmg and neighbours_damage(c, r) and 0 <= c < N and 0 <= r < N
    for k in range(4):
        x = rnd.random()
        if ruin:
            L, I = rnd.choice(L_RUIN if x < 0.7 else L_BURNT), rnd.choice(I_RUIN)
        elif dmg:
            L = rnd.choice(L_RUIN) if x < 0.3 else rnd.choice(L_BURNT) if x < 0.8 else rnd.choice(L_OK)
            I = rnd.choice(I_RUIN) if rnd.random() < 0.35 else rnd.choice(I_BURNT) if rnd.random() < 0.6 else rnd.choice(I_OK)
        elif near:
            L = rnd.choice(L_BURNT) if x < 0.25 else rnd.choice(L_OK)
            I = rnd.choice(I_BURNT) if rnd.random() < 0.2 else rnd.choice(I_OK)
        else:
            L = rnd.choice(L_BURNT) if x < 0.015 else rnd.choice(L_OK)
            I = rnd.choice(I_OK)
        out.append((L, I))
    return out


def add(groups, path, loc, yaw=0.0, scale=1.0):
    groups.setdefault(path, []).append(pc.xform(loc, yaw, scale))


# ---------------------------------------------------------------- street furniture
TREE_OFF = cg.ROAD_HALF + 1.8  # tree line from the street centre
LAMP_OFF = cg.ROAD_HALF + 0.55
CAR_OFF = cg.ROAD_HALF - 1.3


def ns_street_open(j, r):
    """Is there a north-south street on line y = 200*j along cell row r (x = cell centre)?"""
    cw, ce = j + 3, j + 4  # cells west / east of the line
    kw, ke = cell_kind(cw, r), cell_kind(ce, r)
    if kw == "plaza" and ke == "plaza":
        return False
    if kw == "cathedral" and ke == "cathedral":
        return False  # the close is one paved strip along y
    return True


def ew_street_open(i, c):
    """East-west street on line x = 200*i along cell column c."""
    rs, rn = i + 3, i + 4
    ks, kn = cell_kind(c, rs), cell_kind(c, rn)
    if ks == "plaza" and kn == "plaza":
        return False
    if ks == "champ" and kn == "champ":
        return False
    if ks == "river" or kn == "river":
        return (200.0 * i) in pc.BRIDGE_ROWS_X
    return True


def in_near(c, r):
    return -3 <= c <= 12 and -3 <= r <= 12


def furniture(rnd, rows, cols):
    trees, lamps, cars = {}, {}, {}
    # north-south streets (along x): trees on both sidewalks, lamps between them, parked cars
    for j in range(cols[0] - 4, cols[1] - 2):
        y = 200.0 * j
        board_line = -4 <= j <= 4
        boulevard = board_line or j % 2 == 0
        for r in range(rows[0], rows[1] + 1):
            if not ns_street_open(j, r):
                continue
            xc = (r - 3.5) * pc.CELL
            near = in_near(j + 3, r) or in_near(j + 4, r)
            for side in (-1.0, 1.0):
                cell = (j + 3 if side < 0 else j + 4, r)
                kind = cell_kind(*cell)
                if kind in ("base_blue", "empty"):
                    continue
                if boulevard and (near or rnd.random() < 0.8):
                    for t in range(13):
                        if rnd.random() < 0.06:
                            continue
                        x = xc - 75.0 + 12.5 * t + rnd.uniform(-0.6, 0.6)
                        add(trees, OUT + "/" + rnd.choice(TREES), (x, y + side * TREE_OFF, cg.KERB_H), rnd.uniform(0, 360), rnd.uniform(0.82, 1.0))
                if near and kind != "river":
                    for t in range(6):
                        x = xc - 68.75 + 25.0 * t
                        add(lamps, OUT + "/SM_Lamp", (x, y + side * LAMP_OFF, cg.KERB_H), 0.0)
                if near:
                    burnt = cell in pc.DAMAGE_CELLS
                    for _ in range(rnd.randint(0, 3)):
                        x = xc + rnd.uniform(-70.0, 70.0)
                        yaw = (0.0 if side > 0 else 180.0) + (rnd.uniform(-35, 35) if burnt else rnd.uniform(-2, 2))
                        mesh = rnd.choice(CARS_BURNT) if burnt and rnd.random() < 0.7 else rnd.choice(CARS)
                        add(cars, OUT + "/" + mesh, (x, y + side * CAR_OFF, 0.0), yaw)
    # east-west streets (along y): lamps + cars
    for i in range(rows[0] - 4, rows[1] - 2):
        x = 200.0 * i
        for c in range(cols[0], cols[1] + 1):
            if not ew_street_open(i, c) or not (in_near(c, i + 3) or in_near(c, i + 4)):
                continue
            if cell_kind(c, i + 3) in ("base_blue", "empty") or cell_kind(c, i + 4) in ("base_blue", "empty"):
                continue
            yc = (c - 3.5) * pc.CELL
            if cell_kind(c, i + 3) == "river" or cell_kind(c, i + 4) == "river":
                for (bx, by) in cg.bridge_lamp_positions():
                    add(lamps, OUT + "/SM_Lamp", (x + bx, by, 1.6), 0.0)
                continue
            for side in (-1.0, 1.0):
                cell = (c, i + 3 if side < 0 else i + 4)
                for t in range(7):
                    add(lamps, OUT + "/SM_Lamp", (x + side * LAMP_OFF, yc - 75.0 + 25.0 * t, cg.KERB_H), 0.0)
                burnt = cell in pc.DAMAGE_CELLS
                for _ in range(rnd.randint(0, 2)):
                    y = yc + rnd.uniform(-70.0, 70.0)
                    yaw = (90.0 if side < 0 else -90.0) + (rnd.uniform(-35, 35) if burnt else rnd.uniform(-2, 2))
                    mesh = rnd.choice(CARS_BURNT) if burnt and rnd.random() < 0.7 else rnd.choice(CARS)
                    add(cars, OUT + "/" + mesh, (x + side * CAR_OFF, y, 0.0), yaw)
    return trees, lamps, cars


# ---------------------------------------------------------------- main
def main(argv):
    rebuild = "--rebuild" in argv
    back = "--no-back" not in argv
    only = [argv[i + 1] for i, a in enumerate(argv) if a == "--only"]
    pc.ensure_map_loaded()
    build_meshes(rebuild, only)
    pc.clear_step(STEP)
    pc.clear_step("CityBaseBlue")
    pc.clear_step("BlockTest")
    rnd = cg.rng(20260927)
    rows = pc.CITY_ROWS if back else (0, N - 1)
    cols = pc.CITY_COLS if back else (0, N - 1)

    # Build industrial (B1), red base (B2) and blue base (B5) meshes.
    base_meshes = {}
    blue_meshes = {}
    if back:
        industrial.build_meshes(rebuild)
        base_meshes = base_red.build_meshes(rebuild)
        blue_meshes, _blue_meta = base_blue.build_meshes(rebuild)
        ruins.build_meshes(rebuild)

    ground, board_bld, back_bld, river, squares, industrial_bld = {}, {}, {}, {}, {}, {}
    low_bld, base_bld, blue_bld = {}, {}, {}
    stats = {"board_blocks": 0, "back_blocks": 0, "squares": 0, "south_cleared": 0, "industrial": 0,
             "low_blocks": 0, "base_red": 0, "base_blue": 0, "cathedral": 0}
    for r in range(rows[0], rows[1] + 1):
        for c in range(cols[0], cols[1] + 1):
            kind = cell_kind(c, r)
            x, y = pc.cell_center(c, r)
            if kind in ("plaza", "river", "champ"):
                continue
            # B1: empty cells (south_clear zone) get no buildings
            if kind == "empty":
                stats["south_cleared"] += 1
                continue
            # B2: Notre-Dame close - one paved 2-cell strip (yaw 90: local +x -> world +y), the scan is step 06
            if kind == "cathedral":
                if (c, r) == zones.CATHEDRAL_ANCHOR:
                    add(ground, OUT + "/SM_CathedralClose", (x, y, 0.0), 90.0)
                stats["cathedral"] += 1
                continue
            # B2: red base compound (deterministic per cell, shared with 07_base_red.py)
            if kind == "base_red":
                add(ground, OUT + "/SM_Cell_Base", (x, y, 0.0), 90.0 * rnd.randint(0, 3))
                for name, (px, py, pz), rot, _extra in basegen.cell_layout(c, r):
                    base_bld.setdefault(base_meshes[name], []).append(pc.xform_rot((x + px, y + py, pz), rot))
                stats["base_red"] += 1
                continue
            # B5: low ground cells are the footprint of one coherent blue base;
            # props are placed once below, rather than repeating a red-style
            # compound in every cell.
            if kind == "base_blue":
                add(ground, OUT + "/SM_Cell_Base", (x, y, 0.0), 90.0 * rnd.randint(0, 3))
                stats["base_blue"] += 1
                continue
            # B2: low-rise district - same block assembly with the SM_Hsm_Low* modules (<= 18 m)
            if kind == "low":
                add(ground, OUT + ("/SM_Cell_Garden" if rnd.random() < 0.5 else "/SM_Cell_Court"), (x, y, 0.0), 90.0 * rnd.randint(0, 3))
                add(low_bld, HSM + rnd.choice(LOW_COURT), (x, y, 0.0), 90.0 * rnd.randint(0, 3))
                for k in range(4):
                    add(low_bld, HSM + rnd.choice(LOW_L), (x, y, 0.0), 90.0 * k)
                    add(low_bld, HSM + rnd.choice(LOW_I), (x, y, 0.0), 90.0 * k)
                stats["low_blocks"] += 1
                continue
            # B1+B3: industrial zone - tall buildings + factories + damaged structures + auxiliary (chimneys, warehouses,
            # water towers, factory halls, pipelines, storage tanks, damaged buildings, silos, cooling towers, conveyor bridges)
            if kind == "industrial":
                add(ground, OUT + "/SM_Cell_Garden", (x, y, 0.0), 90.0 * rnd.randint(0, 3))
                # B3: increased module density - some cells get 2 structure groups
                for _ in range(1 if rnd.random() < 0.7 else 2):
                    for mesh_path, rel_pos, rot in industrial.generate_industrial_modules(c, r, rnd):
                        add(industrial_bld, mesh_path, (x + rel_pos[0], y + rel_pos[1], rel_pos[2]), rot[1])
                stats["industrial"] += 1
                continue
            if kind == "board":
                # frozen B1 table: no random draws, so the board never depends on the background layout
                parity = "Dark" if (c + r) % 2 == 0 else "Light"
                scorched = "Scorched" if (c, r) in pc.DAMAGE_CELLS else ""
                fz = FROZEN["cells"]["%d,%d" % (c, r)]
                add(ground, OUT + "/SM_Cell_%s%s" % (parity, scorched), (x, y, 0.0), 90.0 * fz["ground"])
                for k, (L, I) in enumerate(fz["modules"]):
                    add(board_bld, HSM + L, (x, y, 0.0), 90.0 * k)
                    add(board_bld, HSM + I, (x, y, 0.0), 90.0 * k)
                stats["board_blocks"] += 1
                continue
            if rnd.random() < 0.045:
                # small square (planted garden) breaks the regular block pattern of the backfield
                add(ground, OUT + "/SM_Cell_Garden", (x, y, 0.0))
                for gx in range(-3, 4):
                    for gy in range(-3, 4):
                        if abs(gx) + abs(gy) > 1 and rnd.random() < 0.8:
                            add(squares, OUT + "/" + rnd.choice(TREES), (x + gx * 22.0 + rnd.uniform(-3, 3), y + gy * 22.0 + rnd.uniform(-3, 3), 0.2),
                                rnd.uniform(0, 360), rnd.uniform(0.95, 1.25))
                stats["squares"] += 1
                continue
            else:
                add(ground, OUT + ("/SM_Cell_Garden" if rnd.random() < 0.5 else "/SM_Cell_Court"), (x, y, 0.0), 90.0 * rnd.randint(0, 3))
                add(back_bld, HSM + "SM_Hsm_Court_%02d" % rnd.randint(0, 5), (x, y, 0.0), 90.0 * rnd.randint(0, 3))
                stats["back_blocks"] += 1
            for k, (L, I) in enumerate(block_modules(c, r, rnd)):
                add(back_bld, HSM + L, (x, y, 0.0), 90.0 * k)
                add(back_bld, HSM + I, (x, y, 0.0), 90.0 * k)
    ruin_groups = ruins.apply_layout(ground, back_bld, low_bld, industrial_bld, squares) if back else {}
    # open cells
    add(ground, OUT + "/SM_Plaza", (0.0, 0.0, 0.0))
    add(ground, OUT + "/SM_BoardLines", (0.0, 0.0, 0.0))
    add(ground, OUT + "/SM_Obelisk", (0.0, 0.0, cg.KERB_H))
    add(ground, OUT + "/SM_FarGround", (0.0, 0.0, 0.0))
    if back:
        cx, cy = pc.cell_center(pc.EIFFEL_CELL[0], pc.CHAMP_ROWS[0])
        add(ground, OUT + "/SM_ChampDeMars", (cx, cy, 0.0))
        for i in range(rows[0] - 4, rows[1] - 2):  # keep in sync with river_x_range()
            xs = 200.0 * i
            if xs not in pc.BRIDGE_ROWS_X:
                river_mesh = "/SM_Seine"
            elif xs in (600.0, 1800.0):
                river_mesh = "/SM_Seine_Bridge_Gold"
            else:
                river_mesh = "/SM_Seine_Bridge"
            add(river, OUT + river_mesh, (xs, 0.0, 0.0))
        for k, (bx, side) in enumerate(((-350.0, 1), (130.0, -1), (870.0, 1), (1530.0, -1), (2250.0, 1))):
            by = (cg.Y_WATER0 + 3.2) if side > 0 else (cg.Y_WATER1 - 3.2)
            add(river, OUT + "/" + BARGES[k % 2], (bx, by, cg.Z_WATER), 0.0 if side > 0 else 180.0)
        blue_bld = base_blue.groups(blue_meshes)
    trees, lamps, cars = furniture(rnd, rows, cols)
    # board region: replace the freshly drawn trees / cars by the frozen B1 ones (lamps are deterministic anyway)
    lim = FROZEN_REGION * pc.M
    for g in (trees, cars):
        for k in list(g):
            g[k] = [t for t in g[k] if not (abs(t.translation.x) <= lim and abs(t.translation.y) <= lim)]
    for mesh, fx, fy, fz, yaw, s in FROZEN["furniture"]["trees"]:
        add(trees, OUT + "/" + mesh, (fx, fy, fz), yaw, s)
    for mesh, fx, fy, fz, yaw, s in FROZEN["furniture"]["cars"]:
        add(cars, OUT + "/" + mesh, (fx, fy, fz), yaw)
    for k, ts in squares.items():
        trees.setdefault(k, []).extend(ts)
    # plaza lamps: ring around the obelisk + along the kerb
    for k in range(12):
        a = 2 * math.pi * k / 12
        add(lamps, OUT + "/SM_Lamp", (24.0 * math.cos(a), 24.0 * math.sin(a), cg.KERB_H))
    if back:
        cx, cy = pc.cell_center(pc.EIFFEL_CELL[0], pc.CHAMP_ROWS[0])
        n = pc.CHAMP_ROWS[1] - pc.CHAMP_ROWS[0] + 1
        for t in range(n * 16):
            x = cx - 86.0 + t * 12.5
            if abs(x - pc.EIFFEL_POS[0]) < 82.0 or x > cx - 100.0 + pc.CELL * n - 14.0:
                continue
            for s in (-66.0, -12.0, 12.0, 66.0):
                add(trees, OUT + "/" + rnd.choice(TREES), (x, cy + s, cg.KERB_H), rnd.uniform(0, 360), rnd.uniform(0.9, 1.1))

    if back:
        ruins.clear_furniture(trees, cars, lamps)
    pc.spawn_instances(ground, STEP, "City_Ground", "City")
    pc.spawn_instances(board_bld, STEP, "City_Board_Buildings", "City")
    if ruin_groups:
        pc.spawn_instances(ruin_groups, STEP, "City_Ruins", "City")
    if back_bld:
        pc.spawn_instances(back_bld, STEP, "City_Back_Buildings", "City")
    if industrial_bld:
        pc.spawn_instances(industrial_bld, STEP, "City_Industrial_Buildings", "City")
    if low_bld:
        pc.spawn_instances(low_bld, STEP, "City_Low_Buildings", "City")
    if base_bld:
        pc.spawn_instances(base_bld, STEP, "City_Base_Red", "City")
    if blue_bld:
        pc.spawn_instances(blue_bld, "CityBaseBlue", "City_Base_Blue", "City")
    if river:
        pc.spawn_instances(river, STEP, "City_Seine", "City")
    pc.spawn_instances(trees, STEP, "City_Trees", "City")
    pc.spawn_instances(lamps, STEP, "City_Lamps", "City", shadows=False)
    pc.spawn_instances(cars, STEP, "City_Cars", "City")
    pc.save_map()
    count = lambda g: sum(len(t) for t in g.values())
    stats.update({"ground": count(ground), "board_modules": count(board_bld), "back_modules": count(back_bld),
                  "industrial_modules": count(industrial_bld), "low_modules": count(low_bld), "base_props": count(base_bld),
                  "base_blue_props": count(blue_bld),
                  "ruins_instances": count(ruin_groups), "ruins_zones": zones.ruin_stats(),
                  "river": count(river), "trees": count(trees), "lamps": count(lamps), "cars": count(cars),
                  "board_frozen": {"cells": len(FROZEN["cells"]), "region_m": FROZEN_REGION,
                                   "trees": len(FROZEN["furniture"]["trees"]), "cars": len(FROZEN["furniture"]["cars"])}})
    pc.write_json(pc.REPORT_DIR + "/M0_City_Layout.json", stats)
    pc.log("city layout", stats)


main(sys.argv[1:])
