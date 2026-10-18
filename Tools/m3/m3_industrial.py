"""M3 west industrial belt (editor-side, run through Tools/ue_run.py on /Game/Tread/Maps/M3_Paris_Match).

Owner feedback 2026-10-07: free-standing chimneys on the ground look wrong; in the reference image the chimneys rise
from multi-storey factory buildings. This step removes every chimney instance (SM_Ind_Chimney_0/1/2 and
SM_Ind_ChimneyDamaged) from the map's City_Industrial_Buildings actor and puts a brick factory with a roof chimney
(SM_M3_FactoryStack_A/B/C/Damaged, blender_paris_buildings.py) in its place. The factory pivot is its chimney axis
and its chimney top matches the old chimney height, so the existing chimney smoke / fire FX stay aligned. The yaw
(0/90/180/270) is the one whose footprint overlaps the other industrial modules least and stays inside its cell.

Only the M3 map is edited (M0 / M1 keep their chimneys). The original chimney transforms are recorded in
Saved/Reports/M3_Industrial_Stacks.json the first time and reused on re-runs, so the step is idempotent.

    python Tools/ue_run.py Tools/m3/m3_industrial.py [--no-save]
"""
import json
import math
import os
import sys

import unreal

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "paris"))
import paris_common as pc  # noqa: E402

M3_MAP = "/Game/Tread/Maps/M3_Paris_Match"
STEP = "M3Industrial"
LABEL = "City_Industrial_Buildings"
REPORT = pc.REPORT_DIR + "/M3_Industrial_Stacks.json"
REPLACE = {"SM_Ind_Chimney_0": "SM_M3_FactoryStack_A", "SM_Ind_Chimney_1": "SM_M3_FactoryStack_B",
           "SM_Ind_Chimney_2": "SM_M3_FactoryStack_C", "SM_Ind_ChimneyDamaged": "SM_M3_FactoryStack_Damaged"}
CELL_HALF = 81.0  # buildable half size of a cell (street facades)
OFFSETS = [(dx, dy) for dx in range(-40, 41, 10) for dy in range(-40, 41, 10)]
FX_STEP = "FX_Industrial"
FX_FLAMES = "City_Industrial_Flames"
FX_RADIUS = 16.0  # FX within this XY distance of a chimney belong to it and move with it


def find_actor(label):
    for a in pc.actor_sub().get_all_level_actors():
        if a.get_actor_label() == label:
            return a
    raise RuntimeError("actor %s not found in %s" % (label, pc.world().get_path_name()))


def box_world(mesh, t):
    """World XY AABB (metres) of a mesh instance with yaw-only rotation."""
    b = mesh.get_bounding_box()
    s = t.scale3d
    yaw = math.radians(t.rotation.yaw if hasattr(t.rotation, "yaw") else t.rotation.rotator().yaw)
    c, si = math.cos(yaw), math.sin(yaw)
    xs, ys = [], []
    for px in (b.min.x * s.x, b.max.x * s.x):
        for py in (b.min.y * s.y, b.max.y * s.y):
            xs.append(t.translation.x + px * c - py * si)
            ys.append(t.translation.y + px * si + py * c)
    return (min(xs) / 100, min(ys) / 100, max(xs) / 100, max(ys) / 100)


def area_overlap(a, b):
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return w * h if w > 0 and h > 0 else 0.0


def cell_box(x, y):
    r = round(x / pc.CELL + (pc.N - 1) / 2.0)
    c = round(y / pc.CELL + (pc.N - 1) / 2.0)
    cx, cy = pc.cell_center(c, r)
    return (cx - CELL_HALF, cy - CELL_HALF, cx + CELL_HALF, cy + CELL_HALF), (c, r)


def fx_items():
    """(kind, handle, location cm) for the industrial FX that can belong to a chimney."""
    items = []
    for a in pc.actor_sub().get_all_level_actors():
        tags = [str(t) for t in a.tags]
        if FX_STEP not in tags:
            continue
        if a.get_actor_label() == FX_FLAMES:
            for comp in a.get_components_by_class(unreal.InstancedStaticMeshComponent):
                for i in range(comp.get_instance_count()):
                    items.append(("ism", (comp, i), comp.get_instance_transform(i, True).translation))
        else:
            items.append(("actor", a, a.get_actor_location()))
    return items


def shift(kind, handle, loc, dx_cm, dy_cm):
    new = unreal.Vector(loc.x + dx_cm, loc.y + dy_cm, loc.z)
    if kind == "actor":
        handle.set_actor_location(new, False, False)
    else:
        comp, i = handle
        t = comp.get_instance_transform(i, True)
        t.translation = new
        comp.update_instance_transform(i, t, True, True, True)


def move_fx(x, y, dx, dy):
    moves = []
    for kind, handle, loc in fx_items():
        if math.hypot(loc.x / 100 - x, loc.y / 100 - y) <= FX_RADIUS:
            shift(kind, handle, loc, dx * 100.0, dy * 100.0)
            moves.append({"kind": kind, "from_m": [round(loc.x / 100, 2), round(loc.y / 100, 2), round(loc.z / 100, 2)],
                          "delta_m": [dx, dy]})
    return moves


def revert_fx(moves):
    """Undo the FX shifts of a previous run (matched by their shifted location) so re-runs start from the M1 state."""
    if not moves:
        return
    items = fx_items()
    for m in moves:
        tx, ty, tz = m["from_m"][0] + m["delta_m"][0], m["from_m"][1] + m["delta_m"][1], m["from_m"][2]
        for kind, handle, loc in items:
            if kind == m["kind"] and abs(loc.x / 100 - tx) < 0.05 and abs(loc.y / 100 - ty) < 0.05 and abs(loc.z / 100 - tz) < 0.05:
                shift(kind, handle, loc, -m["delta_m"][0] * 100.0, -m["delta_m"][1] * 100.0)
                break


def main():
    if not pc.world().get_path_name().startswith(M3_MAP):
        raise RuntimeError("open %s first (m3_board_city.py creates it)" % M3_MAP)
    actor = find_actor(LABEL)
    comps = actor.get_components_by_class(unreal.InstancedStaticMeshComponent)
    prev = json.load(open(REPORT, encoding="utf-8")) if os.path.exists(REPORT) else {}
    chimneys = []  # (old mesh name, x_m, y_m, z_m, yaw)
    others = []
    for comp in comps:
        mesh = comp.get_editor_property("static_mesh")
        name = mesh.get_name()
        n = comp.get_instance_count()
        for i in range(n):
            t = comp.get_instance_transform(i, True)
            if name in REPLACE:
                chimneys.append((name, t.translation.x / 100, t.translation.y / 100, t.translation.z / 100,
                                 t.rotation.rotator().yaw))
            else:
                others.append(box_world(mesh, t))
        if name in REPLACE and n:
            comp.clear_instances()
    if not chimneys:
        chimneys = [tuple(c) for c in prev.get("source_chimneys", [])]
        if not chimneys:
            raise RuntimeError("no chimney instances and no recorded source in %s" % REPORT)
    pc.clear_step(STEP)
    groups = {}
    placed = []
    meshes = {v: pc.load(pc.MESH + "/M3/" + v) for v in REPLACE.values()}
    revert_fx(prev.get("fx_moves", []))
    fx_moves = []
    for old, x, y, z, _ in sorted(chimneys):
        new = REPLACE[old]
        cbox, cell = cell_box(x, y)
        best = None
        # the chimney may shift (whole factory) up to 40 m to find free ground; distance is penalised lightly
        for dx, dy in OFFSETS:
            for yaw in (0.0, 90.0, 180.0, 270.0):
                t = pc.xform((x + dx, y + dy, z), yaw)
                box = box_world(meshes[new], t)
                out = sum(max(0.0, v) for v in (cbox[0] - box[0], cbox[1] - box[1], box[2] - cbox[2], box[3] - cbox[3]))
                ov = sum(area_overlap(box, o) for o in others + [p["box"] for p in placed])
                score = ov + 400.0 * out + 3.0 * math.hypot(dx, dy)
                if best is None or score < best[0] - 1e-6:
                    best = (score, yaw, box, out, ov, dx, dy)
        score, yaw, box, out, ov, dx, dy = best
        groups.setdefault(pc.MESH + "/M3/" + new, []).append(pc.xform((x + dx, y + dy, z), yaw))
        if dx or dy:
            fx_moves += move_fx(x, y, dx, dy)
        placed.append({"old": old, "new": new, "cell": list(cell), "chimney_m": [round(x, 2), round(y, 2), round(z, 2)],
                       "shift_m": [dx, dy], "yaw": yaw, "overlap_m2": round(ov, 1), "outside_cell_m": round(out, 2),
                       "box": [round(v, 2) for v in box]})
    pc.spawn_instances(groups, STEP, "M3_Industrial_Factories", "M3Industrial")
    report = {
        "schema": "Tread.M3.IndustrialStacks.v1", "map": M3_MAP,
        "source_chimneys": [list(c) for c in sorted(chimneys)],
        "replaced": len(placed), "by_mesh": {k: sum(1 for p in placed if p["new"] == k) for k in REPLACE.values()},
        "free_standing_chimneys_left": sum(c.get_instance_count() for c in comps
                                           if c.get_editor_property("static_mesh").get_name() in REPLACE),
        "max_overlap_m2": max([p["overlap_m2"] for p in placed] or [0]),
        "outside_cell": sum(1 for p in placed if p["outside_cell_m"] > 0.01),
        "shifted": sum(1 for p in placed if p["shift_m"] != [0, 0]), "fx_moves": fx_moves,
        "placements": placed,
    }
    pc.write_json(REPORT, report)
    if "--no-save" not in sys.argv:
        pc.save_map()
    pc.log("M3 industrial: %d chimneys -> factories, left=%d, max overlap %.0f m2, outside=%d" % (
        len(placed), report["free_standing_chimneys_left"], report["max_overlap_m2"], report["outside_cell"]))


main()
