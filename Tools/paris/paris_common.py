"""Shared constants and helpers for the M0 Paris realistic board (editor-side, `import unreal`).

World convention (UE, centimetres):
    +X = north (away from the default camera), +Y = east (screen right), +Z = up.
    Board 8x8, 200 m per cell, centred on the origin. cell(col,row): col 0..7 west->east, row 0..7 south->north.
    Seine runs north-south east of the board, Eiffel Tower stands west of the board (B1), Notre-Dame north (B2).
Every actor spawned by these scripts carries the tag "M0Paris" plus a per-step tag, so each step can
delete and rebuild its own actors (scripts are idempotent).
"""
import math
import os

import unreal

# ---------------------------------------------------------------- paths
UNITY_ROOT = "F:/AI/workbuddy/GiantessAutoChess"  # read-only source
PROJECT_DIR = "E:/AI/Tread/Tread"
SAVED_DIR = PROJECT_DIR + "/Saved"
REPORT_DIR = SAVED_DIR + "/Reports"
SHOT_DIR = SAVED_DIR + "/Screenshots"
STAGING_DIR = SAVED_DIR + "/Staging"  # converted copies of source assets (never write into UNITY_ROOT)

MAP_PATH = "/Game/Tread/Maps/M0_Paris_Board"
CITY = "/Game/Tread/City/Paris"
TEX = CITY + "/Textures"
MAT = CITY + "/Materials"
MESH = CITY + "/Meshes"
LANDMARK = CITY + "/Landmarks"
FX = CITY + "/FX"
CHAR = "/Game/Tread/Characters"

SRC = {
    "eiffel": UNITY_ROOT + "/model/_ 免费_ 埃菲尔铁塔(_ Free _ La tour E_爱给网_aigei_com/free__la_tour_eiffel.glb",
    "notre_dame": UNITY_ROOT + "/model/巴黎圣母院(Notre+Dame+De+Paris)_爱给网_aigei_com/notre_dame_de_paris.glb",
    "ruin": UNITY_ROOT + "/model/残破建筑模型_uaf_爱给网_aigei_com/BldgLG_J_grp/BldgLG_J_grp.fbx",
    "ruin_tex": UNITY_ROOT + "/model/残破建筑模型_uaf_爱给网_aigei_com/BldgLG_J_grp/textures",
    "am025": UNITY_ROOT + "/model/欧式建筑房屋_爱给网_aigei_com/AM229_025.fbx",
    "am030": UNITY_ROOT + "/model/欧式建筑房屋L_爱给网_aigei_com (1)/AM229_030.fbx",
    "paris_glb": UNITY_ROOT + "/MyProject/Assets/_Game/City/Source/Paris/paris_buildings.glb",
    "web_mats": UNITY_ROOT + "/web_backup/assets/materials",
    "vrm416": UNITY_ROOT + "/vrm/GilesFrontline/416.vrm",
}

# ---------------------------------------------------------------- layout (metres)
M = 100.0  # cm per metre
CELL = 200.0
N = 8
HALF = CELL * N / 2.0  # 800 m
STREET = 38.0  # facade-to-facade width of the street on every cell boundary
ROADWAY = 22.0  # asphalt carriageway (board grid line runs down its centre)
SIDEWALK = (STREET - ROADWAY) / 2.0  # 8 m, +0.15 m kerb
FACADE_HALF = (CELL - STREET) / 2.0  # 81 m: street facades of a block, relative to the cell centre
BLOCK_DEPTH = 16.0  # Haussmann building depth; inner courtyard = 2 * (81 - 16) = 130 m
COURT_HALF = FACADE_HALF - BLOCK_DEPTH
KERB = 0.15
PLAZA_CELLS = {(3, 3), (4, 3), (3, 4), (4, 4)}
DAMAGE_CELLS = {(5, 5), (6, 5), (5, 6), (6, 6), (1, 4), (2, 5)}
RUIN_CELL = (6, 6)
HERO_CELLS = {(1, 1): "am025", (6, 1): "am030"}

# The city is a regular grid of 200 m cells continuing the board (cell (col,row) outside 0..7 = backfield).
SEINE_COL = 9  # river cell column: y 1000..1200 m, quay walls at 1019 / 1181 (see citygen.py)
SEINE_Y0, SEINE_Y1 = 1019.0, 1181.0
BRIDGE_ROWS_X = (-1200.0, -600.0, 0.0, 600.0, 1200.0, 1800.0, 2400.0, 3000.0)  # bridges on these east-west streets
# B1 (125 schedule 2026-10-01): Eiffel moved to the west side, on the dividing line x = 0 (between rows 3 and 4).
# Cells are whole, so the tower cell is row 3 (x = -100 m, one cell south of the line) in column -2 (y = -1100 m);
# the Champ de Mars strip (rows 1..4, x in [-500, 300] m) is centred on the line. C1 (audience camera) calibrates y.
# zones.py mirrors EIFFEL_CELL / CHAMP_ROWS, so this is the single source for the tower position.
EIFFEL_CELL = (-2, 3)  # (col, row): tower at (-100, -1100) m
CHAMP_ROWS = (1, 4)  # Champ de Mars park cells: row 1 to 4, spanning the dividing line
EIFFEL_POS = ((EIFFEL_CELL[1] - (N - 1) / 2.0) * CELL, (EIFFEL_CELL[0] - (N - 1) / 2.0) * CELL)
EIFFEL_HEIGHT = 330.0
CITY_ROWS = (-6, 18)  # background city extents in cells (inclusive)
CITY_COLS = (-12, 18)

GIANT_HEIGHT = 115.0  # VRM display height (m); Haussmann blocks are ~24 m
TAG = "M0Paris"

EAL = unreal.EditorAssetLibrary
ASSET_TOOLS = unreal.AssetToolsHelpers.get_asset_tools()


def cell_center(col, row):
    """World centre of a board cell in metres (x north, y east)."""
    return ((row - (N - 1) / 2.0) * CELL, (col - (N - 1) / 2.0) * CELL)


def v(x, y, z=0.0):
    """Metres -> unreal.Vector in cm."""
    return unreal.Vector(x * M, y * M, z * M)


def log(*a):
    print("[paris]", *a)


# ---------------------------------------------------------------- editor helpers
def world():
    return unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()


def actor_sub():
    return unreal.get_editor_subsystem(unreal.EditorActorSubsystem)


def ensure_dir(path):
    if not EAL.does_directory_exist(path):
        EAL.make_directory(path)


def ensure_map_loaded():
    """Load the M0 map (it must have been created by 01_level_lighting.py)."""
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    cur = world().get_path_name()
    if not cur.startswith(MAP_PATH):
        if not EAL.does_asset_exist(MAP_PATH):
            raise RuntimeError("map missing, run 01_level_lighting.py first")
        les.load_level(MAP_PATH)
    return world()


def save_map():
    unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).save_current_level()


def clear_step(step_tag):
    """Delete all actors carrying the given step tag (idempotent rebuild)."""
    n = 0
    for a in actor_sub().get_all_level_actors():
        tags = [str(t) for t in a.tags]
        if step_tag in tags:
            a.destroy_actor()
            n += 1
    log("cleared", n, "actors with tag", step_tag)


def spawn(cls, loc_m=(0, 0, 0), rot=(0, 0, 0), step_tag="", label=None, folder=None):
    """Spawn an actor. loc in metres, rot=(pitch,yaw,roll) degrees."""
    a = actor_sub().spawn_actor_from_class(cls, v(*loc_m), unreal.Rotator(roll=rot[2], pitch=rot[0], yaw=rot[1]))
    a.tags = [unreal.Name(TAG), unreal.Name(step_tag)]
    if label:
        a.set_actor_label(label)
    if folder:
        a.set_folder_path(unreal.Name("M0Paris/" + folder))
    return a


def spawn_mesh(mesh, loc_m=(0, 0, 0), rot=(0, 0, 0), scale=(1, 1, 1), step_tag="", label=None, folder=None, materials=None):
    a = spawn(unreal.StaticMeshActor, loc_m, rot, step_tag, label, folder)
    a.set_actor_scale3d(unreal.Vector(*scale))
    c = a.static_mesh_component
    c.set_static_mesh(mesh)
    for i, m in enumerate(materials or []):
        if m:
            c.set_material(i, m)
    return a


def load(path):
    a = EAL.load_asset(path)
    if a is None:
        raise RuntimeError("asset not found: " + path)
    return a


def delete_asset_if_exists(path):
    if EAL.does_asset_exist(path):
        EAL.delete_asset(path)


def write_json(path, data):
    import json

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def yaw_for_normal(nx, ny):
    """Yaw (deg) that rotates a module whose street face points to local -Y so that it faces (nx, ny)."""
    return math.degrees(math.atan2(ny, nx)) + 90.0


def xform(loc_m, yaw=0.0, scale=1.0):
    s = scale if isinstance(scale, (tuple, list)) else (scale, scale, scale)
    return unreal.Transform(location=v(*loc_m), rotation=unreal.Rotator(roll=0.0, pitch=0.0, yaw=yaw), scale=unreal.Vector(*s))


def xform_rot(loc_m, rot=(0.0, 0.0, 0.0), scale=1.0):
    """Like xform() with a full (pitch, yaw, roll) rotation in degrees."""
    s = scale if isinstance(scale, (tuple, list)) else (scale, scale, scale)
    return unreal.Transform(location=v(*loc_m), rotation=unreal.Rotator(roll=rot[2], pitch=rot[0], yaw=rot[1]), scale=unreal.Vector(*s))


def stage(src, sub):
    """Copy a read-only source file into Saved/Staging/<sub>/ (only when missing or its size changed). Returns the copy."""
    import shutil

    dst_dir = os.path.join(STAGING_DIR, sub)
    os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir, os.path.basename(src))
    if not os.path.exists(dst) or os.path.getsize(dst) != os.path.getsize(src):
        shutil.copy2(src, dst)
    return dst.replace("\\", "/")


def spawn_instances(groups, step_tag, label, folder=None, shadows=True):
    """One actor holding an InstancedStaticMeshComponent per mesh (thousands of instances without thousands of actors).

    groups: {mesh_path_or_object: [unreal.Transform (world), ...]}. Returns the actor."""
    sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
    bfl = unreal.SubobjectDataBlueprintFunctionLibrary
    a = spawn(unreal.Actor, (0, 0, 0), step_tag=step_tag, label=label, folder=folder)
    handles = sds.k2_gather_subobject_data_for_instance(a)
    root = handles[1] if len(handles) > 1 else handles[0]
    n = 0
    for mesh, ts in groups.items():
        if not ts:
            continue
        nh, reason = sds.add_new_subobject(unreal.AddNewSubobjectParams(parent_handle=root, new_class=unreal.InstancedStaticMeshComponent))
        comp = bfl.get_object(bfl.get_data(nh))
        if comp is None:
            raise RuntimeError("ISM add failed: %s" % reason)
        comp.set_static_mesh(load(mesh) if isinstance(mesh, str) else mesh)
        comp.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
        comp.set_editor_property("cast_shadow", shadows)
        comp.add_instances(ts, False, True)
        n += len(ts)
    log("instanced %s: %d meshes, %d instances" % (label, len([g for g in groups.values() if g]), n))
    return a
