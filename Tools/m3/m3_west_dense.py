"""M3 west industrial belt densification (editor-side, Tools/ue_run.py, map /Game/Tread/Maps/M3_Paris_Match).

Owner feedback 2026-10-08: the 8x8 board stays as it is; the west side is still too empty. The B1/B3 industrial
cells hold one or two loose modules on a grass ground. This step turns every industrial cell into a dense works
district like the reference image:
  * ground: the cell's SM_Cell_Garden (grass) becomes SM_Cell_Base (compacted yard) in City_Ground;
  * street walls: along the four street lines (+-81 m from the cell centre) rows of workers' houses and brick
    warehouses, fronts on the street, skipping spans blocked by existing modules;
  * interior: sawtooth works halls, warehouses and the odd gasholder packed into the free yard;
  * war damage: ~22 % burnt variants; flame cards (same mesh as 07_fx_industrial) on a share of the burnt roofs.
Obstacles = every instance already in the industrial / factory / ruin actors (world AABB from mesh bounds), so the
new buildings never intersect the B3 modules, the M3 roof-chimney factories or their FX. Deterministic per cell.
Everything new carries the tag "M3West" and is rebuilt on every run. Report: Saved/Reports/M3_West_Dense.json.

    python Tools/ue_run.py Tools/m3/m3_west_dense.py [--no-save]
"""
import json
import math
import os
import random
import sys

import unreal

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "paris"))
import paris_common as pc  # noqa: E402
import zones  # noqa: E402

M3_MAP = "/Game/Tread/Maps/M3_Paris_Match"
STEP = "M3West"
M3 = pc.MESH + "/M3/"
CITY = pc.MESH + "/City/"
FLAME_MESH = pc.FX + "/SM_FX_FlameCards"
REPORT = pc.REPORT_DIR + "/M3_West_Dense.json"
ASSET_REPORT = pc.REPORT_DIR + "/M3_Building_Assets.json"
OBSTACLE_ACTORS = ("City_Industrial_Buildings", "M3_Industrial_Factories", "City_Ruins")
SEED = 20261008
F = 80.6  # street facade line from the cell centre
GAP = 1.5
STREET_MESHES = [("SM_M3_WorkersRow_A", 4), ("SM_M3_WorkersRow_B", 4), ("SM_M3_Warehouse_A", 2), ("SM_M3_Warehouse_B", 2)]
YARD_MESHES = [("SM_M3_Sawtooth_A", 4), ("SM_M3_Sawtooth_B", 4), ("SM_M3_Warehouse_A", 3), ("SM_M3_Warehouse_B", 2),
               ("SM_M3_Gasholder", 0.6)]
BURNT = {"SM_M3_WorkersRow_A": "SM_M3_WorkersRow_Burnt", "SM_M3_WorkersRow_B": "SM_M3_WorkersRow_Burnt",
         "SM_M3_Warehouse_A": "SM_M3_Warehouse_Burnt", "SM_M3_Warehouse_B": "SM_M3_Warehouse_Burnt",
         "SM_M3_Sawtooth_A": "SM_M3_Sawtooth_Burnt", "SM_M3_Sawtooth_B": "SM_M3_Sawtooth_Burnt"}
BURNT_SHARE = 0.22
FLAME_SHARE = 0.3


def find_actor(label, required=True):
    for a in pc.actor_sub().get_all_level_actors():
        if a.get_actor_label() == label:
            return a
    if required:
        raise RuntimeError("actor %s missing" % label)
    return None


def extents():
    rep = json.load(open(ASSET_REPORT, encoding="utf-8"))
    return {n: rec["bounds_m"] for g in ("procedural", "imported") for n, rec in rep[g].items()}


def rot_box(b, yaw):
    """Local AABB [[x0,y0,z0],[x1,y1,z1]] rotated by a multiple of 90 deg -> (x0, y0, x1, y1)."""
    (x0, y0, _), (x1, y1, _) = b
    c, s = round(math.cos(math.radians(yaw))), round(math.sin(math.radians(yaw)))
    pts = [(px * c - py * s, px * s + py * c) for px, py in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
    return (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts))


def world_box(mesh, t):
    b = mesh.get_bounding_box()
    s = t.scale3d
    yaw = math.radians(t.rotation.rotator().yaw)
    c, si = math.cos(yaw), math.sin(yaw)
    xs, ys = [], []
    for px in (b.min.x * s.x, b.max.x * s.x):
        for py in (b.min.y * s.y, b.max.y * s.y):
            xs.append(t.translation.x + px * c - py * si)
            ys.append(t.translation.y + px * si + py * c)
    return (min(xs) / 100, min(ys) / 100, max(xs) / 100, max(ys) / 100)


def overlap(a, b, gap=0.0):
    return min(a[2], b[2]) - max(a[0], b[0]) > -gap and min(a[3], b[3]) - max(a[1], b[1]) > -gap


def weighted(rnd, items):
    tot = sum(w for _, w in items)
    x = rnd.uniform(0, tot)
    for k, w in items:
        x -= w
        if x <= 0:
            return k
    return items[-1][0]


def industrial_cells():
    out = []
    for r in range(pc.CITY_ROWS[0], pc.CITY_ROWS[1] + 1):
        for c in range(pc.CITY_COLS[0], pc.CITY_COLS[1] + 1):
            if 0 <= c < pc.N and 0 <= r < pc.N:
                continue
            zone = zones.cell_zone(c, r)
            if zone in ("ruins", "ruins_low", "footprint"):
                zone = zones.base_zone(c, r)
            if zone == "industrial":
                out.append((c, r))
    return out


def obstacles():
    boxes = []
    for label in OBSTACLE_ACTORS:
        a = find_actor(label, required=False)
        if a is None:
            continue
        for comp in a.get_components_by_class(unreal.InstancedStaticMeshComponent):
            mesh = comp.get_editor_property("static_mesh")
            for i in range(comp.get_instance_count()):
                boxes.append(world_box(mesh, comp.get_instance_transform(i, True)))
    return boxes


def grid(boxes, size=200.0):
    g = {}
    for b in boxes:
        for gx in range(int(math.floor(b[0] / size)), int(math.floor(b[2] / size)) + 1):
            for gy in range(int(math.floor(b[1] / size)), int(math.floor(b[3] / size)) + 1):
                g.setdefault((gx, gy), []).append(b)
    return g


def near(g, box, size=200.0):
    seen = []
    for gx in range(int(math.floor(box[0] / size)), int(math.floor(box[2] / size)) + 1):
        for gy in range(int(math.floor(box[1] / size)), int(math.floor(box[3] / size)) + 1):
            seen.extend(g.get((gx, gy), []))
    return seen


def try_place(rnd, he, cx, cy, mesh, yaw, lx, ly, taken, g, kind):
    rb = rot_box(he[mesh], yaw)
    box = (cx + lx + rb[0], cy + ly + rb[1], cx + lx + rb[2], cy + ly + rb[3])
    if box[0] < cx - F or box[2] > cx + F or box[1] < cy - F or box[3] > cy + F:
        return None
    if any(overlap(box, o, GAP) for o in near(g, box)) or any(overlap(box, o, GAP) for o in taken):
        return None
    if mesh in BURNT and rnd.random() < BURNT_SHARE:
        mesh = BURNT[mesh]
    taken.append(box)
    return {"mesh": mesh, "loc": (cx + lx, cy + ly), "yaw": yaw, "box": box, "kind": kind,
            "height": he[mesh][1][2]}


def street_wall(rnd, he, cx, cy, taken, g):
    """Rows along the four street lines, fronts facing the street (M3 models face local +Y in UE)."""
    out = []
    edge = F - 0.2
    for n in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        yaw = (math.degrees(math.atan2(n[1], n[0])) - 90.0 + 180.0) % 360.0 - 180.0  # local +Y -> outward normal n
        pos = -F + 2.0
        while pos < F - 6.0:
            mesh = weighted(rnd, STREET_MESHES)
            rb = rot_box(he[mesh], yaw)
            if n[0]:
                width = rb[3] - rb[1]
                lx = edge - rb[2] if n[0] > 0 else -edge - rb[0]
                ly = pos - rb[1]
            else:
                width = rb[2] - rb[0]
                ly = edge - rb[3] if n[1] > 0 else -edge - rb[1]
                lx = pos - rb[0]
            p = try_place(rnd, he, cx, cy, mesh, yaw, lx, ly, taken, g, "street")
            if p:
                out.append(p)
                pos += width + rnd.choice((0.0, 0.0, 3.0, 6.0))
            else:
                pos += 8.0
    return out


def yard(rnd, he, cx, cy, taken, g, tries=140):
    out = []
    for _ in range(tries):
        mesh = weighted(rnd, YARD_MESHES)
        yaw = rnd.choice((0.0, 90.0, 180.0, -90.0))
        p = try_place(rnd, he, cx, cy, mesh, yaw, rnd.uniform(-60, 60), rnd.uniform(-60, 60), taken, g, "yard")
        if p:
            out.append(p)
    return out


def regroundings(cells):
    """Swap SM_Cell_Garden instances at industrial cell centres for SM_Cell_Base (compacted yard) in City_Ground."""
    actor = find_actor("City_Ground")
    centres = {tuple(round(v, 1) for v in pc.cell_center(c, r)) for c, r in cells}
    garden = base = None
    for comp in actor.get_components_by_class(unreal.InstancedStaticMeshComponent):
        name = comp.get_editor_property("static_mesh").get_name()
        if name == "SM_Cell_Garden":
            garden = comp
        elif name == "SM_Cell_Base":
            base = comp
    if garden is None or base is None:
        raise RuntimeError("City_Ground lacks SM_Cell_Garden / SM_Cell_Base components")
    move, keep = [], []
    for i in range(garden.get_instance_count()):
        t = garden.get_instance_transform(i, True)
        key = (round(t.translation.x / 100, 1), round(t.translation.y / 100, 1))
        (move if key in centres else keep).append(t)
    if move:
        garden.clear_instances()
        if keep:
            garden.add_instances(keep, False, True)
        base.add_instances(move, False, True)
    return len(move)


def main():
    if not pc.world().get_path_name().startswith(M3_MAP):
        dirty = unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages() + unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
        if dirty:
            raise RuntimeError("dirty packages present, refusing to switch map: %s" % [p.get_name() for p in dirty])
        unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).load_level(M3_MAP)
    he = extents()
    cells = industrial_cells()
    pc.clear_step(STEP)
    g = grid(obstacles())
    groups, placed, flames = {}, [], {}
    per_cell = {}
    for c, r in cells:
        rnd = random.Random(SEED + c * 1009 + r * 7919)
        cx, cy = pc.cell_center(c, r)
        taken = []
        items = street_wall(rnd, he, cx, cy, taken, g) + yard(rnd, he, cx, cy, taken, g)
        per_cell["%d,%d" % (c, r)] = len(items)
        for p in items:
            groups.setdefault(M3 + p["mesh"], []).append(pc.xform((p["loc"][0], p["loc"][1], 0.05), p["yaw"]))
            placed.append(p)
            if p["mesh"].endswith("_Burnt") and rnd.random() < FLAME_SHARE:
                b = p["box"]
                for _ in range(4):
                    h = rnd.uniform(5.0, 10.0)
                    loc = (rnd.uniform(b[0] + 3, b[2] - 3), rnd.uniform(b[1] + 3, b[3] - 3), p["height"] - 1.0)
                    flames.setdefault(FLAME_MESH, []).append(pc.xform(loc, rnd.uniform(0, 360), (h * 0.9, h * 0.9, h)))
    pc.spawn_instances(groups, STEP, "M3_West_Industry", "M3West")
    if flames:
        pc.spawn_instances(flames, STEP, "M3_West_Flames", "M3West", shadows=False)
    regrounded = regroundings(cells)
    # audit: no new box intersects another new box or an obstacle
    errors = 0
    ng = grid([p["box"] for p in placed])
    for p in placed:
        others = [o for o in near(ng, p["box"]) if o is not p["box"]]
        if any(overlap(p["box"], o, -0.01) for o in others) or any(overlap(p["box"], o, -0.01) for o in near(g, p["box"])):
            errors += 1
    counts = {}
    for p in placed:
        counts[p["mesh"]] = counts.get(p["mesh"], 0) + 1
    vals = sorted(per_cell.values())
    report = {"schema": "Tread.M3.WestDense.v1", "map": M3_MAP, "seed": SEED, "cells": len(cells),
              "instances": len(placed), "flame_cards": sum(len(v) for v in flames.values()),
              "regrounded_cells": regrounded, "counts": dict(sorted(counts.items())),
              "per_cell_min_median_max": [vals[0], vals[len(vals) // 2], vals[-1]] if vals else [],
              "audit": {"ok": errors == 0, "overlapping": errors}, "per_cell": per_cell}
    pc.write_json(REPORT, report)
    if "--no-save" not in sys.argv:
        pc.save_map()
    pc.log("M3 west: %d cells, %d buildings, %d flames, reground %d, overlaps=%d" % (
        len(cells), len(placed), report["flame_cards"], regrounded, errors))


main()
