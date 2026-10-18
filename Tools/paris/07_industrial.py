"""Western industrial zone buildings (B1+B3).

B1: chimneys, warehouses, water towers (vertical landmarks 35-80m).
B3: factory halls, pipelines, storage tanks, damaged structures, conveyor bridges, silos, cooling towers.

Target height range: 15-80m, significantly taller than Haussmann buildings (~24m) to create visual contrast.

Loaded by 05_city_layout.py (relative path) for the meshes and the per-cell module lists; can also run alone:
    07_industrial.py [--rebuild] [--only SM_Ind_*]       --rebuild regenerates every industrial mesh in place
"""
import sys
import math
import time
import unreal
import paris_common as pc
import citygen as cg
import ue_mesh
import geom

OUT = pc.MESH + "/Industrial"

# Building parameters
CHIMNEY_HEIGHT_RANGE = (50.0, 80.0)
WAREHOUSE_HEIGHT_RANGE = (35.0, 50.0)
WATERTOWER_HEIGHT_RANGE = (40.0, 55.0)
CHIMNEY_RADIUS = 8.0


def mats():
    MI = pc.MAT + "/Instances/"
    return {
        "brick": MI + "MI_Paint_Terracotta",  # reuse terracotta for industrial brick
        "concrete": MI + "MI_Paint_Concrete",
        "steel": MI + "MI_Paint_Steel",
        "rust": MI + "MI_Paint_Iron",  # reuse iron for rusted metal
        "glass": MI + "MI_Glass",
        "roof": MI + "MI_Zinc_Dark",  # reuse dark zinc for industrial roofing
    }


def make_chimney_mesh(height, radius=CHIMNEY_RADIUS):
    """Tall cylindrical chimney with cap using citygen primitives."""
    mb = geom.MeshBuilder(["brick", "concrete"])
    # Main brick cylinder
    cg.prism(mb, "brick", (0, 0, 0), (0, 0, height), radius, radius * 0.98, 16)
    # Concrete cap at top
    cap_height = height + 2.0
    cg.prism(mb, "concrete", (0, 0, height), (0, 0, cap_height), radius * 1.1, radius * 1.1, 16)
    # Base platform
    cg.prism(mb, "concrete", (0, 0, 0), (0, 0, 1.0), radius * 1.3, radius * 1.3, 16)
    return mb


def make_warehouse_mesh(length, width, height):
    """Large rectangular warehouse with corrugated metal panels."""
    mb = geom.MeshBuilder(["concrete", "steel", "glass", "roof"])
    hl, hw = length / 2, width / 2
    # Concrete base
    mb.box("concrete", -hl - 1, hl + 1, -hw - 1, hw + 1, 0.0, 2.0)
    # Steel frame walls
    mb.box("steel", -hl, hl, -hw, hw, 2.0, height, skip=("pz",))
    # Glass windows on long sides
    for y in [-hw * 0.9, hw * 0.9]:
        for i in range(int(length / 10)):
            x = -hl + 5 + i * 10
            mb.box("glass", x, x + 6, y - 0.1, y + 0.1, height * 0.2, height * 0.8)
    # Flat metal roof
    mb.box("roof", -hl, hl, -hw, hw, height, height + 1.0)
    return mb


def make_watertower_mesh(height):
    """Elevated water tank on steel legs."""
    mb = geom.MeshBuilder(["steel", "rust", "concrete"])
    tank_r = 12.0
    tank_h = 10.0
    leg_h = height - tank_h
    # Four legs
    for x in [-8, 8]:
        for y in [-8, 8]:
            cg.prism(mb, "steel", (x, y, 0), (x, y, leg_h), 0.5, 0.5, 8)
            mb.box("concrete", x - 1.5, x + 1.5, y - 1.5, y + 1.5, 0.0, 1.0)
    # Cross braces
    for z in [leg_h * 0.3, leg_h * 0.6]:
        mb.box("steel", -8, 8, -0.3, 0.3, z, z + 0.6)
        mb.box("steel", -0.3, 0.3, -8, 8, z, z + 0.6)
    # Tank
    cg.prism(mb, "rust", (0, 0, leg_h), (0, 0, leg_h + tank_h), tank_r, tank_r, 16)
    # Tank top
    cg.prism(mb, "steel", (0, 0, leg_h + tank_h), (0, 0, leg_h + tank_h + 1.5), tank_r * 0.6, tank_r * 0.6, 16)
    return mb


# ---------------------------------------------------------------- B3: factory halls, pipelines, damage, auxiliary
def make_factory_hall_mesh(length, width, height, roof_type="sawtooth"):
    """Large factory hall with sawtooth or gable roof (steel frame, glass panels)."""
    mb = geom.MeshBuilder(["concrete", "steel", "glass", "roof"])
    hl, hw = length / 2, width / 2
    mb.box("concrete", -hl - 2, hl + 2, -hw - 2, hw + 2, 0.0, 1.5)
    # Steel columns every 12m
    for x in range(int(-hl), int(hl), 12):
        for y in [-hw + 2, hw - 2]:
            cg.prism(mb, "steel", (x, y, 1.5), (x, y, height), 0.6, 0.6, 8)
    # Wall panels (steel with glass strips)
    for side, (y0, y1) in [("long", (-hw, -hw + 0.3)), ("long", (hw - 0.3, hw))]:
        mb.box("steel", -hl, hl, y0, y1, 1.5, height * 0.3)
        mb.box("glass", -hl, hl, y0, y1, height * 0.3, height * 0.9)
        mb.box("steel", -hl, hl, y0, y1, height * 0.9, height)
    for side, (x0, x1) in [("short", (-hl, -hl + 0.3)), ("short", (hl - 0.3, hl))]:
        mb.box("steel", x0, x1, -hw, hw, 1.5, height)
    # Sawtooth roof
    if roof_type == "sawtooth":
        bay_w = 8.0
        bays = int(width / bay_w)
        for i in range(bays):
            y0 = -hw + i * bay_w
            y1 = y0 + bay_w
            # slant up from y0 to y1
            pts = [(-hl, y0, height), (hl, y0, height), (hl, y1, height + 3.0), (-hl, y1, height + 3.0)]
            mb.poly("roof", pts, geom.norm(geom.cross((pts[1][0] - pts[0][0], pts[1][1] - pts[0][1], pts[1][2] - pts[0][2]),
                                                       (pts[3][0] - pts[0][0], pts[3][1] - pts[0][1], pts[3][2] - pts[0][2]))))
            # vertical glass face at y1
            mb.box("glass", -hl, hl, y1, y1 + 0.2, height + 3.0, height + 5.0)
    else:  # gable
        ridge = height + 6.0
        for s in (-1.0, 1.0):
            pts = [(-hl, s * hw, height), (hl, s * hw, height), (hl, 0.0, ridge), (-hl, 0.0, ridge)]
            mb.poly("roof", pts, geom.norm(geom.cross((pts[1][0] - pts[0][0], pts[1][1] - pts[0][1], pts[1][2] - pts[0][2]),
                                                       (pts[3][0] - pts[0][0], pts[3][1] - pts[0][1], pts[3][2] - pts[0][2]))))
    return mb


def make_pipeline_mesh(length):
    """Elevated pipeline on supports (ground-level industrial plumbing)."""
    mb = geom.MeshBuilder(["steel", "rust", "concrete"])
    pipe_r = 0.8
    hl = length / 2
    # Pipe runs along x
    cg.prism(mb, "rust", (-hl, 0, 4.0), (hl, 0, 4.0), pipe_r, pipe_r, 12, caps=True)
    # Supports every 10m
    for x in range(int(-hl), int(hl) + 1, 10):
        mb.box("steel", x - 0.3, x + 0.3, -0.3, 0.3, 0.0, 4.5)
        mb.box("concrete", x - 1.0, x + 1.0, -1.0, 1.0, 0.0, 0.5)
    return mb


def make_storage_tank_mesh(radius, height):
    """Cylindrical storage tank (fuel/chemical)."""
    mb = geom.MeshBuilder(["rust", "steel", "concrete"])
    cg.prism(mb, "rust", (0, 0, 0), (0, 0, height), radius, radius, 16)
    # Top dome
    for i in range(4):
        z = height + i * 0.5
        r = radius * (1.0 - i * 0.15)
        cg.prism(mb, "steel", (0, 0, z), (0, 0, z + 0.5), r, r, 16, caps=(i == 3))
    # Base ring
    cg.prism(mb, "concrete", (0, 0, 0), (0, 0, 0.5), radius * 1.1, radius * 1.1, 16, caps=False)
    return mb


def make_damaged_chimney_mesh(height):
    """Broken chimney: intact base + jagged top."""
    mb = geom.MeshBuilder(["brick", "concrete"])
    break_h = height * 0.6
    cg.prism(mb, "brick", (0, 0, 0), (0, 0, break_h), CHIMNEY_RADIUS, CHIMNEY_RADIUS * 0.98, 16, caps=False)
    # Jagged break: irregular vertices at the top
    import random
    rnd = random.Random(42)
    pts_top = []
    for i in range(12):
        a = 2 * math.pi * i / 12.0
        r = CHIMNEY_RADIUS * rnd.uniform(0.7, 1.0)
        h_jag = break_h + rnd.uniform(-2.0, 0.5)
        pts_top.append((r * math.cos(a), r * math.sin(a), h_jag))
    # Triangulate the jagged rim (fan from centre)
    c = (0, 0, break_h + 0.5)
    for i in range(len(pts_top)):
        mb.poly("brick", [c, pts_top[i], pts_top[(i + 1) % len(pts_top)]], (0, 0, 1))
    # Base
    cg.prism(mb, "concrete", (0, 0, 0), (0, 0, 1.0), CHIMNEY_RADIUS * 1.3, CHIMNEY_RADIUS * 1.3, 16)
    return mb


def make_collapsed_warehouse_mesh(length, width):
    """Warehouse with collapsed roof section (angled roof plane, exposed beams)."""
    mb = geom.MeshBuilder(["concrete", "steel", "roof"])
    hl, hw = length / 2, width / 2
    h = 25.0
    mb.box("concrete", -hl - 1, hl + 1, -hw - 1, hw + 1, 0.0, 2.0)
    # Intact walls on 3 sides
    mb.box("steel", -hl, -hl + 0.5, -hw, hw, 2.0, h)
    mb.box("steel", -hl, hl, -hw, -hw + 0.5, 2.0, h)
    mb.box("steel", -hl, hl, hw - 0.5, hw, 2.0, h * 0.6)  # partially collapsed
    # Sagging roof: from h at -hl to h*0.3 at +hl
    for i in range(int(length / 5)):
        x0, x1 = -hl + i * 5, -hl + (i + 1) * 5
        z0, z1 = h - (x0 + hl) / length * h * 0.7, h - (x1 + hl) / length * h * 0.7
        pts = [(x0, -hw, z0), (x1, -hw, z1), (x1, hw, z1), (x0, hw, z0)]
        mb.poly("roof", pts, geom.norm(geom.cross((pts[1][0] - pts[0][0], pts[1][1] - pts[0][1], pts[1][2] - pts[0][2]),
                                                   (pts[3][0] - pts[0][0], pts[3][1] - pts[0][1], pts[3][2] - pts[0][2]))))
    # Exposed beams
    for x in range(int(-hl), int(hl), 12):
        z = h - (x + hl) / length * h * 0.7
        mb.box("steel", x - 0.4, x + 0.4, -hw, hw, 2.0, z)
    return mb


def make_conveyor_bridge_mesh(length, height):
    """Elevated conveyor bridge crossing between buildings."""
    mb = geom.MeshBuilder(["steel", "concrete"])
    hl = length / 2
    w = 3.0
    # Two support towers
    for x in [-hl, hl]:
        mb.box("concrete", x - 1.5, x + 1.5, -1.5, 1.5, 0.0, height)
    # Bridge deck
    mb.box("steel", -hl, hl, -w / 2, w / 2, height, height + 1.0)
    # Side rails
    for y in [-w / 2, w / 2]:
        mb.box("steel", -hl, hl, y - 0.1, y + 0.1, height + 1.0, height + 2.5)
    # Cross braces every 8m
    for x in range(int(-hl), int(hl), 8):
        mb.box("steel", x - 0.2, x + 0.2, -w / 2, w / 2, height, height + 1.0)
    return mb


def make_silo_mesh(height, radius=8.0):
    """Tall cylindrical silo (grain/material storage)."""
    mb = geom.MeshBuilder(["concrete", "steel"])
    cg.prism(mb, "concrete", (0, 0, 0), (0, 0, height), radius, radius, 16)
    # Conical top
    cone_h = radius * 0.8
    cg.prism(mb, "steel", (0, 0, height), (0, 0, height + cone_h), radius, 0.5, 16)
    # Base ring
    cg.prism(mb, "concrete", (0, 0, 0), (0, 0, 1.0), radius * 1.1, radius * 1.1, 16, caps=False)
    # Access ladder
    for i in range(int(height)):
        mb.box("steel", radius + 0.2, radius + 0.3, -0.05, 0.05, i, i + 1.0)
    return mb


def make_cooling_tower_mesh(height):
    """Hyperbolic cooling tower (classic power-plant silhouette)."""
    mb = geom.MeshBuilder(["concrete"])
    bot_r, mid_r, top_r = 18.0, 12.0, 15.0
    seg = 20
    # Hyperboloid profile: 3 sections
    h0, h1, h2 = 0.0, height * 0.3, height
    # Bottom cylinder
    cg.prism(mb, "concrete", (0, 0, h0), (0, 0, h1), bot_r, mid_r, seg, caps=False)
    # Middle hyperbolic waist
    steps = 12
    for i in range(steps):
        t0, t1 = i / steps, (i + 1) / steps
        z0, z1 = h1 + t0 * (h2 - h1), h1 + t1 * (h2 - h1)
        r0 = mid_r + (top_r - mid_r) * (t0 ** 0.7)  # flare out
        r1 = mid_r + (top_r - mid_r) * (t1 ** 0.7)
        cg.prism(mb, "concrete", (0, 0, z0), (0, 0, z1), r0, r1, seg, caps=False)
    # Top rim
    cg.prism(mb, "concrete", (0, 0, h2), (0, 0, h2 + 1.5), top_r, top_r, seg)
    return mb


# ---------------------------------------------------------------- Mesh registry
MESHES = {
    # B1 originals
    "SM_Ind_Chimney_0": lambda: make_chimney_mesh(65.0),
    "SM_Ind_Chimney_1": lambda: make_chimney_mesh(70.0),
    "SM_Ind_Chimney_2": lambda: make_chimney_mesh(75.0),
    "SM_Ind_Warehouse_0": lambda: make_warehouse_mesh(80.0, 60.0, 40.0),
    "SM_Ind_Warehouse_1": lambda: make_warehouse_mesh(100.0, 70.0, 45.0),
    "SM_Ind_WaterTower_0": lambda: make_watertower_mesh(48.0),
    "SM_Ind_WaterTower_1": lambda: make_watertower_mesh(55.0),
    # B3 additions
    "SM_Ind_FactoryHall_0": lambda: make_factory_hall_mesh(120.0, 60.0, 18.0, "sawtooth"),
    "SM_Ind_FactoryHall_1": lambda: make_factory_hall_mesh(100.0, 50.0, 22.0, "gable"),
    "SM_Ind_Pipeline_0": lambda: make_pipeline_mesh(80.0),
    "SM_Ind_StorageTank_0": lambda: make_storage_tank_mesh(10.0, 15.0),
    "SM_Ind_StorageTank_1": lambda: make_storage_tank_mesh(12.0, 18.0),
    "SM_Ind_ChimneyDamaged": lambda: make_damaged_chimney_mesh(50.0),
    "SM_Ind_WarehouseCollapsed": lambda: make_collapsed_warehouse_mesh(80.0, 50.0),
    "SM_Ind_ConveyorBridge": lambda: make_conveyor_bridge_mesh(60.0, 25.0),
    "SM_Ind_Silo_0": lambda: make_silo_mesh(45.0, 8.0),
    "SM_Ind_Silo_1": lambda: make_silo_mesh(50.0, 10.0),
    "SM_Ind_CoolingTower": lambda: make_cooling_tower_mesh(65.0),
}


def build_meshes(rebuild=False, only=()):
    """Build the industrial meshes that are missing (all of them with rebuild=True). Returns {name: asset path}."""
    m = mats()
    t0 = time.time()
    n = 0
    meshes = {}

    for name, fn in MESHES.items():
        path = OUT + "/" + name
        if rebuild or name in only or not pc.EAL.does_asset_exist(path):
            ue_mesh.build_static_mesh(path, fn(), m, nanite=True)
            n += 1
        meshes[name] = path

    unreal.SystemLibrary.execute_console_command(None, "obj gc")
    pc.log("industrial meshes built: %d in %.1fs" % (n, time.time() - t0))
    return meshes


def generate_industrial_modules(col, row, rnd):
    """Generate industrial modules for one cell (B1+B3 mixed). Returns list of (mesh_path, rel_pos, rotation)."""
    modules = []
    structure_type = rnd.choice(["chimney", "warehouse", "watertower", "mixed", "factory", "damaged", "storage", "auxiliary"])

    if structure_type == "chimney":
        for _ in range(rnd.randint(1, 2)):
            mesh_idx = rnd.randint(0, 2)
            mesh = OUT + f"/SM_Ind_Chimney_{mesh_idx}"
            x_offset = rnd.uniform(-80, 80)
            y_offset = rnd.uniform(-80, 80)
            modules.append((mesh, (x_offset, y_offset, 0), (0, 0, 0)))

    elif structure_type == "warehouse":
        mesh_idx = rnd.randint(0, 1)
        mesh = OUT + f"/SM_Ind_Warehouse_{mesh_idx}"
        x_offset = rnd.uniform(-60, 60)
        y_offset = rnd.uniform(-60, 60)
        yaw = rnd.choice([0, 90])
        modules.append((mesh, (x_offset, y_offset, 0), (0, yaw, 0)))

    elif structure_type == "watertower":
        mesh_idx = rnd.randint(0, 1)
        mesh = OUT + f"/SM_Ind_WaterTower_{mesh_idx}"
        x_offset = rnd.uniform(-70, 70)
        y_offset = rnd.uniform(-70, 70)
        modules.append((mesh, (x_offset, y_offset, 0), (0, 0, 0)))

    elif structure_type == "mixed":
        mesh_idx = rnd.randint(0, 1)
        mesh = OUT + f"/SM_Ind_Warehouse_{mesh_idx}"
        modules.append((mesh, (-40, -30, 0), (0, 0, 0)))
        mesh_idx = rnd.randint(0, 2)
        mesh = OUT + f"/SM_Ind_Chimney_{mesh_idx}"
        modules.append((mesh, (50, 40, 0), (0, 0, 0)))

    elif structure_type == "factory":
        mesh_idx = rnd.randint(0, 1)
        mesh = OUT + f"/SM_Ind_FactoryHall_{mesh_idx}"
        x_offset = rnd.uniform(-40, 40)
        y_offset = rnd.uniform(-40, 40)
        yaw = rnd.choice([0, 90])
        modules.append((mesh, (x_offset, y_offset, 0), (0, yaw, 0)))
        # Add pipeline nearby
        modules.append((OUT + "/SM_Ind_Pipeline_0", (x_offset + 40, y_offset, 0), (0, yaw, 0)))

    elif structure_type == "damaged":
        if rnd.random() < 0.5:
            modules.append((OUT + "/SM_Ind_ChimneyDamaged", (rnd.uniform(-60, 60), rnd.uniform(-60, 60), 0), (0, 0, 0)))
        else:
            modules.append((OUT + "/SM_Ind_WarehouseCollapsed", (rnd.uniform(-50, 50), rnd.uniform(-50, 50), 0), (0, rnd.choice([0, 90]), 0)))

    elif structure_type == "storage":
        # Cluster of storage tanks
        for _ in range(rnd.randint(2, 4)):
            mesh_idx = rnd.randint(0, 1)
            mesh = OUT + f"/SM_Ind_StorageTank_{mesh_idx}"
            x_offset = rnd.uniform(-60, 60)
            y_offset = rnd.uniform(-60, 60)
            modules.append((mesh, (x_offset, y_offset, 0), (0, 0, 0)))

    else:  # auxiliary: silos, cooling tower, conveyor
        aux_type = rnd.choice(["silo", "cooling", "conveyor"])
        if aux_type == "silo":
            for _ in range(rnd.randint(1, 3)):
                mesh_idx = rnd.randint(0, 1)
                mesh = OUT + f"/SM_Ind_Silo_{mesh_idx}"
                modules.append((mesh, (rnd.uniform(-70, 70), rnd.uniform(-70, 70), 0), (0, 0, 0)))
        elif aux_type == "cooling":
            modules.append((OUT + "/SM_Ind_CoolingTower", (rnd.uniform(-50, 50), rnd.uniform(-50, 50), 0), (0, 0, 0)))
        else:
            modules.append((OUT + "/SM_Ind_ConveyorBridge", (rnd.uniform(-40, 40), rnd.uniform(-40, 40), 0), (0, rnd.choice([0, 90]), 0)))

    return modules


def main(argv):
    t0 = time.time()
    rebuild = "--rebuild" in argv
    only = [argv[i + 1] for i, a in enumerate(argv) if a == "--only"]
    pc.ensure_map_loaded()

    meshes = build_meshes(rebuild, only)
    pc.log(f"industrial meshes ready: {len(meshes)} in {time.time() - t0:.1f}s (rebuild={rebuild})")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
