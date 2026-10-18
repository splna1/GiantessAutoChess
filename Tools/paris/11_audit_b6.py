"""Read back B6 meshes and instances; --snapshot records protected layout before construction."""
import hashlib
import importlib.util
import json
import math
import os
import sys
from collections import Counter

import unreal
import paris_common as pc
import ruingen
import zones

HERE = os.path.dirname(__file__)
BASELINE = pc.REPORT_DIR + "/M0_B6_Protected_Before.json"
FROZEN_SHA = "ae75559730266802e5166a4f5531d4c8b4eab06a135dbc409be71c351e2f714d"


def load_step(filename):
    spec = importlib.util.spec_from_file_location("audit_" + filename[:-3], os.path.join(HERE, filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def transform_record(mesh, transform):
    position = transform.translation
    rotation = transform.rotation.rotator()
    scale = transform.scale3d
    return [mesh.get_path_name()] + [round(value, 4) for value in (
        position.x, position.y, position.z, rotation.pitch, rotation.yaw, rotation.roll, scale.x, scale.y, scale.z)]


def protected_state():
    state = {}
    for actor in pc.actor_sub().get_all_level_actors():
        label = actor.get_actor_label()
        if label not in ("City_Board_Buildings", "City_Ground", "City_Trees", "City_Cars", "City_Lamps", "City_Base_Blue"):
            continue
        records = []
        for component in actor.get_components_by_class(unreal.InstancedStaticMeshComponent):
            mesh = component.static_mesh
            for index in range(component.get_instance_count()):
                transform = component.get_instance_transform(index, True)
                if isinstance(transform, tuple):
                    transform = transform[-1]
                position = transform.translation
                if label in ("City_Base_Blue", "City_Board_Buildings") or (abs(position.x) <= 83000 and abs(position.y) <= 83000):
                    records.append(transform_record(mesh, transform))
        state[label] = sorted(records)
    return state


def audit():
    with open(BASELINE, encoding="utf-8") as stream:
        before = json.load(stream)
    after = protected_state()
    errors = []
    protected = {}
    for label in sorted(set(before) | set(after)):
        equal = before.get(label) == after.get(label)
        protected[label] = {"count": len(after.get(label, [])), "unchanged": equal}
        if not equal:
            errors.append("Protected instances changed: " + label)
    with open(os.path.join(HERE, "board_frozen.json"), "rb") as stream:
        frozen_sha = hashlib.sha256(stream.read()).hexdigest()
    if frozen_sha != FROZEN_SHA:
        errors.append("Frozen board hash changed")
    ruins = load_step("09_ruins.py")
    with open(pc.REPORT_DIR + "/M0_B6_Layout.json", encoding="utf-8") as stream:
        expected = json.load(stream)["instances"]
    expected_records = Counter(tuple(transform_record(pc.load(record["asset"]), pc.xform(
        record["location_m"], record["yaw"], record["scale"]))) for record in expected)
    actual_records = Counter()
    mesh_stats = {}
    checked = []
    for actor in pc.actor_sub().get_all_level_actors():
        if actor.get_actor_label() != "City_Ruins":
            continue
        for component in actor.get_components_by_class(unreal.InstancedStaticMeshComponent):
            mesh = component.static_mesh
            stats = ruins.mesh_info(mesh)
            mesh_stats[mesh.get_name()] = stats
            if not stats["nanite"]:
                errors.append("Nanite disabled: " + mesh.get_name())
            if any(not item["material"] or "WorldGridMaterial" in item["material"] for item in stats["materials"]):
                errors.append("Missing material: " + mesh.get_name())
            bounds = stats["bounds_m"]
            for index in range(component.get_instance_count()):
                transform = component.get_instance_transform(index, True)
                if isinstance(transform, tuple):
                    transform = transform[-1]
                actual_records[tuple(transform_record(mesh, transform))] += 1
                position = transform.translation
                yaw = math.radians(transform.rotation.rotator().yaw)
                scale = transform.scale3d
                points = [(position.x / 100 + local_x * scale.x * math.cos(yaw) - local_y * scale.y * math.sin(yaw),
                           position.y / 100 + local_x * scale.x * math.sin(yaw) + local_y * scale.y * math.cos(yaw),
                           position.z / 100 + local_z * scale.z)
                          for local_x in (bounds[0][0], bounds[1][0])
                          for local_y in (bounds[0][1], bounds[1][1])
                          for local_z in (bounds[0][2], bounds[1][2])]
                minimum = [min(point[axis] for point in points) for axis in range(3)]
                maximum = [max(point[axis] for point in points) for axis in range(3)]
                clear = maximum[0] <= -800 or minimum[0] >= 800 or maximum[1] <= -800 or minimum[1] >= 800
                if not clear:
                    errors.append("B6 intersects board: " + mesh.get_name())
                if maximum[0] < -800:
                    allowed = min(25.0, 0.8 * 1202 * (-800 - maximum[0]) / 929)
                    if maximum[2] > allowed + 0.001:
                        errors.append("B6 south ceiling: " + mesh.get_name())
                checked.append({"mesh": mesh.get_name(), "world_bounds_m": [minimum, maximum], "board_clear": clear})
    if actual_records != expected_records:
        errors.append("Live B6 instances differ from deterministic manifest")
    geometry = ruingen.audit()
    if any(geometry[name]["zfight_m2"] > 0 for name in ruingen.CRACKS):
        errors.append("Cracked road coplanar overlap")
    report = {"ok": not errors, "errors": errors, "board_frozen_sha256": frozen_sha,
              "protected": protected, "instance_count": sum(actual_records.values()),
              "expected_count": len(expected), "zones": zones.ruin_stats(), "meshes": mesh_stats,
              "bounds": checked, "geometry": geometry,
              "zfight_scope": "Generated pieces; leaning includes two standard corners. FBX scan is not covered."}
    pc.write_json(pc.REPORT_DIR + "/M0_B6_Audit.json", report)
    pc.log("B6 audit", {key: report[key] for key in ("ok", "errors", "protected", "instance_count")})
    if errors:
        raise RuntimeError("B6 audit failed: " + repr(errors))


if __name__ == "__main__":
    pc.ensure_map_loaded()
    if "--snapshot" in sys.argv:
        if os.path.exists(BASELINE):
            raise RuntimeError("Protected baseline already exists; do not overwrite it")
        pc.write_json(BASELINE, protected_state())
    else:
        audit()
