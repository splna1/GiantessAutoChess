"""M3 board city (editor-side, run through Tools/ue_run.py): library-model street blocks on the 8x8 board.

Map: /Game/Tread/Maps/M3_Paris_Match, created once by duplicating M1_Match_Graybox (editor asset API); M0 and the
M1/M2 regression map are never touched.

Owner feedback 2026-10-07: buildings packed into the courtyards made the board messy and no longer read as a grid.
So the courtyards stay empty (as in M0) and every board cell keeps its "ring" street block with facades on the
+-81 m street lines. What changes is WHO builds the ring in a deterministic subset of cells (hero cells):
  * the four corners take the owner's L-shaped corner buildings (AM229_025/030/037/042) or the Blender corner
    rotunda, outer corner on the street corner (orientation measured by blender_orient_probe.py);
  * the four street sides between the corners are filled with row buildings whose fronts face the street: the
    3d66 Paris set (Oushi_01..05) and the Blender townhouses / pavilion, butted together like a Paris street wall.
In those cells the frozen B1 Haussmann L/infill modules are removed from the map's City_Board_Buildings actor; the
actor is first restored from Tools/paris/board_frozen.json, so re-runs are idempotent. All other cells, the plaza
and the damaged cells keep their M0 modules. Aircraft: SE5 biplanes (south), dive bombers (north) and one crashed
dive bomber in the ruined cell's courtyard. No collision anywhere (board clicks are unaffected).
Report + audit: Saved/Reports/M3_Board_City.json.

    python Tools/ue_run.py Tools/m3/m3_board_city.py [--no-save]
"""
import json
import math
import os
import random
import sys

import unreal

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "paris"))
import paris_common as pc  # noqa: E402

M1_MAP = "/Game/Tread/Maps/M1_Match_Graybox"
M3_MAP = "/Game/Tread/Maps/M3_Paris_Match"
STEP = "M3Board"
M3 = pc.MESH + "/M3/"
ASSET_REPORT = pc.REPORT_DIR + "/M3_Building_Assets.json"
FROZEN_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "paris", "board_frozen.json")
REPORT = pc.REPORT_DIR + "/M3_Board_City.json"
BOARD_LABEL = "City_Board_Buildings"

SEED = 20261007
F = 80.6  # facade line (street facades of the frozen blocks are at 81 m; 0.4 m keeps cornices off the pavement)
HERO_COUNT = 18
MAX_DEPTH = 40.0
UNIT_STAND = 22.0  # half size of the free square at the cell centre (unit, rings, drag highlight)
# corner buildings: outer-corner quadrant in UE local coordinates (blender_orient_probe.py, empty quadrant opposite)
CORNERS = {"SM_M3_AM025": (1, 1), "SM_M3_AM030": (1, 1), "SM_M3_AM042": (1, 1), "SM_M3_AM037": (-1, 1),
           "SM_M3_CornerRotunda": (-1, 1)}
CORNER_WEIGHT = {"SM_M3_AM025": 3, "SM_M3_AM030": 2, "SM_M3_AM042": 3, "SM_M3_AM037": 2, "SM_M3_CornerRotunda": 2}
# row buildings: front direction in UE local (+1 = +Y, -1 = -Y) and weight
SIDES = {"SM_M3_Oushi_01": (1, 2), "SM_M3_Oushi_02": (1, 4), "SM_M3_Oushi_03": (1, 4), "SM_M3_Oushi_04": (1, 3),
         "SM_M3_Oushi_05": (-1, 1), "SM_M3_Townhouse_A": (1, 2), "SM_M3_Townhouse_C": (1, 2), "SM_M3_Townhouse_D": (1, 2),
         "SM_M3_Pavilion": (1, 1)}
LIBRARY = {"SM_M3_AM025", "SM_M3_AM030", "SM_M3_AM037", "SM_M3_AM042", "SM_M3_Oushi_01", "SM_M3_Oushi_02",
           "SM_M3_Oushi_03", "SM_M3_Oushi_04", "SM_M3_Oushi_05", "SM_M3_SE5", "SM_M3_Stuka"}
CRASH_LOCAL = (36.0, -34.0)  # crashed dive bomber in pc.RUIN_CELL's courtyard


def save_own_dirty():
    """Save dirty packages created by the M3 import step (paths containing /M3/); never touches anything else."""
    own = [p for p in unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages() if "/M3/" in p.get_name()]
    if own:
        unreal.EditorLoadingAndSavingUtils.save_packages(own, True)


def ensure_map():
    created = False
    if not pc.EAL.does_asset_exist(M3_MAP):
        if not pc.EAL.duplicate_asset(M1_MAP, M3_MAP):
            raise RuntimeError("cannot duplicate %s -> %s" % (M1_MAP, M3_MAP))
        pc.EAL.save_asset(M3_MAP, only_if_is_dirty=False)
        created = True
    if not pc.world().get_path_name().startswith(M3_MAP):
        save_own_dirty()
        dirty = unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages() + unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
        if dirty:
            raise RuntimeError("dirty packages present, refusing to switch map: %s" % [p.get_name() for p in dirty])
        unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).load_level(M3_MAP)
    return created


def extents():
    rep = json.load(open(ASSET_REPORT, encoding="utf-8"))
    he = {}
    for group in ("procedural", "imported"):
        for name, rec in rep[group].items():
            (x0, y0, _), (x1, y1, z1) = rec["bounds_m"]
            he[name] = (x0, y0, x1, y1, z1)
    return he


def norm_yaw(a):
    a = (a + 180.0) % 360.0 - 180.0
    return 180.0 if abs(a + 180.0) < 1e-6 else a


def rotate_box(b, yaw):
    """Local AABB (x0, y0, x1, y1) rotated by a multiple of 90 degrees (UE yaw: +X towards +Y)."""
    x0, y0, x1, y1 = b[:4]
    c, s = round(math.cos(math.radians(yaw))), round(math.sin(math.radians(yaw)))
    rp = [(px * c - py * s, px * s + py * c) for px, py in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))]
    return (min(p[0] for p in rp), min(p[1] for p in rp), max(p[0] for p in rp), max(p[1] for p in rp))


def weighted(rnd, items):
    tot = sum(w for _, w in items)
    x = rnd.uniform(0, tot)
    for k, w in items:
        x -= w
        if x <= 0:
            return k
    return items[-1][0]


def hero_block(rnd, he):
    """Placements (mesh, lx, ly, yaw, scale_x, kind, local box) of one library street block."""
    out = []
    corner_box = {}
    for cx, cy in ((-1, -1), (-1, 1), (1, 1), (1, -1)):
        mesh = weighted(rnd, list(CORNER_WEIGHT.items()))
        sx, sy = CORNERS[mesh]
        yaw = norm_yaw(math.degrees(math.atan2(cy, cx) - math.atan2(sy, sx)))
        bx0, by0, bx1, by1 = rotate_box(he[mesh], yaw)
        px = cx * F - (bx1 if cx > 0 else bx0)  # outer corner of the rotated box onto the street corner
        py = cy * F - (by1 if cy > 0 else by0)
        box = (px + bx0, py + by0, px + bx1, py + by1)
        out.append((mesh, px, py, yaw, 1.0, "corner", box))
        corner_box[(cx, cy)] = box
    for n in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        if n[0] != 0:
            start, end = corner_box[(n[0], -1)][3], corner_box[(n[0], 1)][1]
        else:
            start, end = corner_box[(-1, n[1])][2], corner_box[(1, n[1])][0]
        pos, row = start, []
        while True:
            cands = []
            for mesh, (front, w) in SIDES.items():
                x0, y0, x1, y1, _ = he[mesh]
                if x1 - x0 <= end - pos and y1 - y0 <= MAX_DEPTH:
                    cands.append(((mesh, front, x1 - x0), w))
            if not cands:
                break
            mesh, front, width = weighted(rnd, cands)
            row.append((mesh, front, width))
            pos += width
        # what is left: a slight stretch of every facade (<= 12 %), the rest as equal alleys
        leftover = end - pos
        total_w = sum(r[2] for r in row) or 1.0
        stretch = min(0.12, leftover / total_w) if row else 0.0
        gap = (leftover - stretch * total_w) / (len(row) + 1) if row else 0.0
        p = start + gap
        for mesh, front, width in row:
            w = width * (1.0 + stretch)
            centre_along = p + w / 2.0
            p += w + gap
            yaw = norm_yaw(math.degrees(math.atan2(n[1], n[0])) - (90.0 if front > 0 else -90.0))
            x0, y0, x1, y1, _ = he[mesh]
            rb = rotate_box((x0 * (1 + stretch), y0, x1 * (1 + stretch), y1), yaw)  # stretch runs along local x
            if n[0] != 0:
                px = n[0] * F - (rb[2] if n[0] > 0 else rb[0])
                py = centre_along - (rb[1] + rb[3]) / 2.0
            else:
                py = n[1] * F - (rb[3] if n[1] > 0 else rb[1])
                px = centre_along - (rb[0] + rb[2]) / 2.0
            out.append((mesh, px, py, yaw, round(1.0 + stretch, 4), "side", (px + rb[0], py + rb[1], px + rb[2], py + rb[3])))
    return out


def overlap(a, b, tol=0.05):
    return min(a[2], b[2]) - max(a[0], b[0]) > tol and min(a[3], b[3]) - max(a[1], b[1]) > tol


def find_actor(label):
    for a in pc.actor_sub().get_all_level_actors():
        if a.get_actor_label() == label:
            return a
    raise RuntimeError("actor %s missing" % label)


def restore_board(frozen, hero):
    """Rebuild the frozen B1 module instances from board_frozen.json, leaving out the hero cells."""
    want, removed = {}, 0
    for key, cell in frozen["cells"].items():
        c, r = (int(v) for v in key.split(","))
        x, y = pc.cell_center(c, r)
        for k, pair in enumerate(cell["modules"]):
            for m in pair:
                if (c, r) in hero:
                    removed += 1
                else:
                    want.setdefault(m, []).append(pc.xform((x, y, 0.0), 90.0 * k))
    kept = 0
    for comp in find_actor(BOARD_LABEL).get_components_by_class(unreal.InstancedStaticMeshComponent):
        ts = want.get(comp.get_editor_property("static_mesh").get_name(), [])
        comp.clear_instances()
        if ts:
            comp.add_instances(ts, False, True)
        kept += len(ts)
    return kept, removed


def aircraft():
    out = []
    for i, (dx, dy) in enumerate(((0, 0), (-28, -22), (-28, 22))):
        out.append(("SM_M3_SE5", (-760 + dx, -180 + dy, 150 + 4 * i), (4.0, 0.0, -8.0 + 8 * i), "flying"))
    for i, (dx, dy) in enumerate(((0, 0), (36, 30))):
        out.append(("SM_M3_Stuka", (720 + dx, 260 + dy, 230 + 10 * i), (-18.0, 180.0, 12.0), "flying"))
    x, y = pc.cell_center(*pc.RUIN_CELL)
    out.append(("SM_M3_Stuka", (x + CRASH_LOCAL[0], y + CRASH_LOCAL[1], 1.2), (-24.0, 135.0, 18.0), "crashed"))
    return out


def main():
    created = ensure_map()
    he = extents()
    frozen = json.load(open(FROZEN_PATH, encoding="utf-8"))
    eligible = [(c, r) for r in range(pc.N) for c in range(pc.N)
                if (c, r) not in pc.PLAZA_CELLS and (c, r) not in pc.DAMAGE_CELLS]
    hero = set(random.Random(SEED).sample(eligible, HERO_COUNT))
    pc.clear_step(STEP)
    kept, removed = restore_board(frozen, hero)
    groups, cells, counts, errors = {}, {}, {}, []
    for c, r in sorted(hero, key=lambda t: (t[1], t[0])):
        x0, y0 = pc.cell_center(c, r)
        recs = []
        for mesh, lx, ly, yaw, sx, kind, box in hero_block(random.Random(SEED + c * 1009 + r * 7919), he):
            groups.setdefault(M3 + mesh, []).append(pc.xform((x0 + lx, y0 + ly, 0.05), yaw, (sx, 1.0, 1.0)))
            counts[mesh] = counts.get(mesh, 0) + 1
            recs.append({"mesh": mesh, "kind": kind, "local_m": [round(lx, 2), round(ly, 2)], "yaw": yaw,
                         "scale_x": sx, "box_m": [round(v, 2) for v in box]})
            if min(box[0], box[1]) < -F - 0.05 or max(box[2], box[3]) > F + 0.05:
                errors.append("%d,%d %s crosses the facade line" % (c, r, mesh))
            if overlap(box, (-UNIT_STAND, -UNIT_STAND, UNIT_STAND, UNIT_STAND)):
                errors.append("%d,%d %s reaches the unit stand" % (c, r, mesh))
        for i in range(len(recs)):
            for j in range(i + 1, len(recs)):
                if overlap(recs[i]["box_m"], recs[j]["box_m"]):
                    errors.append("%d,%d overlap %s / %s" % (c, r, recs[i]["mesh"], recs[j]["mesh"]))
        cells["%d,%d" % (c, r)] = recs
    pc.spawn_instances(groups, STEP, "M3_Board_LibraryBlocks", "M3Board")
    planes = aircraft()
    for mesh, loc, rot, role in planes:
        a = pc.spawn_mesh(pc.load(M3 + mesh), loc, rot, (1, 1, 1), STEP, "M3_%s_%s" % (mesh[6:], role), "M3Board")
        a.static_mesh_component.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
        counts[mesh] = counts.get(mesh, 0) + 1
    used = sorted(k for k in counts if k in LIBRARY)
    report = {
        "schema": "Tread.M3.BoardCity.v2", "map": M3_MAP, "map_created_this_run": created, "seed": SEED,
        "rule": "courtyards empty; hero cells rebuilt as library street blocks on the facade line",
        "hero_cells": sorted([list(h) for h in hero]), "frozen_modules_kept": kept, "frozen_modules_removed": removed,
        "instances": sum(len(v) for v in groups.values()) + len(planes), "counts": dict(sorted(counts.items())),
        "library_models_used": used, "library_models_missing": sorted(LIBRARY - set(used)),
        "aircraft": [{"mesh": m, "loc_m": l, "rot": r_, "role": role} for m, l, r_, role in planes],
        "audit": {"ok": not errors, "errors": errors[:50]}, "cells": cells,
    }
    pc.write_json(REPORT, report)
    if "--no-save" not in sys.argv:
        pc.save_map()
    pc.log("M3 board: %d hero cells, frozen kept %d / removed %d, %d instances, library %d/%d, errors=%d" % (
        len(hero), kept, removed, report["instances"], len(used), len(LIBRARY), len(errors)))


main()
