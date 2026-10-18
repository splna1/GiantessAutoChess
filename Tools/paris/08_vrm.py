"""Step 08: VRM 416 -> /Game/Tread/Characters/Clukay416, toon materials, giant placed in a board cell with rings.

  * stage 416.vrm (read-only Unity source) as Saved/Staging/vrm/416.glb (VRM 0.x is glTF 2.0 + extension)
  * UE Interchange import (skeletal body U_Char_0 -> SK_Clukay416, face U_Char_1 shares the skeleton)
  * M_Char_Toon: unlit MToon approximation (two-tone step on N.L around ShadeShift/ShadeToony, ShadeColor, rim);
    the sun direction is a parameter taken from the level's DirectionalLight (LightVector is not available in
    surface materials). One MI per opaque VRM material, parameters read from the VRM JSON; translucent / masked
    face overlays keep their Interchange unlit instances.
  * spawn body + face (face follows the body via leader pose), scaled to GIANT_HEIGHT, standing in the courtyard
    of a Haussmann block board cell; blue selection ring under her, red ring on an enemy cell.
Usage: 08_vrm.py [--reimport]
"""
import json
import math
import os
import shutil
import struct
import sys
import time

import unreal

import geom
import matlib
import paris_common as pc
import ue_mesh

STEP = "VRM"
VRM_SRC = pc.SRC["vrm416"]
STAGING = pc.STAGING_DIR + "/vrm"
GLB_PATH = STAGING + "/416.glb"
SKEL_BASE = pc.CHAR + "/Clukay416"
SKEL_MESH = SKEL_BASE + "/SK_Clukay416"
IMPORTED = SKEL_BASE + "/416"
FACE_MESH = IMPORTED + "/SkeletalMeshes/U_Char_1"
CHAR_MAT = pc.CHAR + "/Materials/M_Char_Toon"
CHAR_MI = SKEL_BASE + "/Materials/"
RING_MESH = pc.CHAR + "/SM_SelectionRing"
RING_BLUE = pc.MAT + "/Instances/MI_Ring_Blue"
RING_RED = pc.MAT + "/Instances/MI_Ring_Red"

HERO_CELL = (3, 1)  # board cell the giant stands in (Haussmann block, front of the board)
ENEMY_CELL = (4, 5)  # red "enemy" selection ring
PAD_Z = 0.2  # courtyard board pad height (citygen)
RING_R = 38.0  # ring centre-line radius (m); board pad half size is 45 m
RING_W = 6.0  # ring width
RING_H = 0.6  # ring thickness


# ---------------------------------------------------------------- import
def stage_vrm():
    os.makedirs(STAGING, exist_ok=True)
    if not os.path.exists(GLB_PATH):
        shutil.copy(VRM_SRC, GLB_PATH)
        pc.log("staged %s -> %s" % (VRM_SRC.split("/")[-1], GLB_PATH))


def vrm_json():
    with open(GLB_PATH, "rb") as f:
        data = f.read()
    n = struct.unpack_from("<I", data, 12)[0]
    return json.loads(data[20:20 + n])


def import_vrm(reimport):
    if pc.EAL.does_asset_exist(SKEL_MESH) and not reimport:
        return pc.load(SKEL_MESH)
    for p in (SKEL_MESH, IMPORTED):
        if pc.EAL.does_asset_exist(p):
            pc.EAL.delete_asset(p)
        elif pc.EAL.does_directory_exist(p):
            pc.EAL.delete_directory(p)
    pc.ensure_dir(SKEL_BASE)
    task = unreal.AssetImportTask()
    task.set_editor_property("filename", GLB_PATH.replace("/", "\\"))
    task.set_editor_property("destination_path", SKEL_BASE)
    task.set_editor_property("automated", True)
    task.set_editor_property("replace_existing", True)
    task.set_editor_property("save", True)
    t0 = time.time()
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    imported = [str(p) for p in task.get_editor_property("imported_object_paths")]
    pc.log("imported %d assets in %.1fs" % (len(imported), time.time() - t0))
    src = next((p for p in imported if "/SkeletalMeshes/" in p and p.split(".")[0].endswith("U_Char_0")), None)
    if src is None:
        raise RuntimeError("no body skeletal mesh (U_Char_0) in the import")
    pc.EAL.rename_asset(src.split(".")[0], SKEL_MESH)
    return pc.load(SKEL_MESH)


def cleanup_scratch():
    """Remove the probe import folder left by the early API tests."""
    p = pc.CHAR + "/Test416"
    if pc.EAL.does_directory_exist(p):
        pc.EAL.delete_directory(p)
        pc.log("deleted", p)


# ---------------------------------------------------------------- toon material
def build_toon_material():
    """Unlit MToon approximation (rebuilt on every run; matlib.Graph clears the old expressions)."""
    g = matlib.Graph(CHAR_MAT, blend=unreal.BlendMode.BLEND_OPAQUE, shading=unreal.MaterialShadingModel.MSM_UNLIT)
    base = g.tex("BaseTex", "/Engine/EngineResources/WhiteSquareTexture", group="MToon")
    sun = g.vector("SunDir", (0.0, 0.0, 1.0), group="MToon")  # direction TO the sun, set per MI
    shift = g.scalar("ShadeShift", 0.0, group="MToon")
    toony = g.scalar("ShadeToony", 0.9, group="MToon")
    shade = g.vector("ShadeColor", (0.8, 0.8, 0.8), group="MToon")
    rim = g.vector("RimColor", (0.0, 0.0, 0.0), group="MToon")
    rim_pow = g.scalar("RimPower", 3.0, group="MToon")
    bright = g.scalar("Brightness", 1.0, group="MToon")
    code = (
        "float3 n = normalize(N);\n"
        "float nl = dot(n, normalize(L));\n"
        "float lit = smoothstep(Shift, Shift + max(1.0 - Toony, 1e-3), nl);\n"  # MToon linearstep band
        "float3 col = lerp(Base * Shade, Base, lit);\n"
        "float rim = pow(saturate(1.0 - abs(dot(n, normalize(V)))), RimPow);\n"
        "return (col + Rim * rim) * Bright;\n"
    )
    out = g.custom(code, [("Base", g.mask(base, r=True, g=True, b=True)), ("N", g.node(unreal.MaterialExpressionVertexNormalWS)),
                          ("L", g.mask(sun, r=True, g=True, b=True)), ("V", g.node(unreal.MaterialExpressionCameraVectorWS)),
                          ("Shift", shift), ("Toony", toony), ("Shade", g.mask(shade, r=True, g=True, b=True)),
                          ("Rim", g.mask(rim, r=True, g=True, b=True)), ("RimPow", rim_pow), ("Bright", bright)], desc="MToon")
    g.out(unreal.MaterialProperty.MP_EMISSIVE_COLOR, out)
    return g.finish()


def sun_dir():
    for a in pc.actor_sub().get_all_level_actors():
        if isinstance(a, unreal.DirectionalLight):
            f = a.get_actor_forward_vector()
            return (-f.x, -f.y, -f.z)
    return (0.0, 0.0, 1.0)


def apply_toon(meshes, parent, props):
    """Replace every opaque slot with an MI of M_Char_Toon; returns the slot report."""
    L = sun_dir()
    report = []
    for sk in meshes:
        mats = sk.get_editor_property("materials")
        changed = False
        for i, slot in enumerate(mats):
            name = str(slot.get_editor_property("material_slot_name"))
            src = pc.load(IMPORTED + "/Materials/" + name)  # original Interchange instance (kept for reference / overlays)
            p = props.get(name)
            blend = src.get_editor_property("base_property_overrides").get_editor_property("blend_mode")
            if p is None or p["blend"] != 0 or blend != unreal.BlendMode.BLEND_OPAQUE:
                slot.set_editor_property("material_interface", src)
                report.append({"slot": name, "material": src.get_name(), "toon": False})
                mats[i] = slot
                changed = True
                continue
            tex = None
            for tp in src.get_editor_property("texture_parameter_values"):
                if str(tp.parameter_info.name) == "BaseColorTexture":
                    tex = tp.parameter_value
            mi = matlib.get_or_create_mi(CHAR_MI + "MI_Toon_" + name, parent,
                                         scalars={"ShadeShift": p["shift"], "ShadeToony": p["toony"], "RimPower": p["rim_pow"]},
                                         vectors={"ShadeColor": p["shade"][:3], "RimColor": p["rim"][:3], "SunDir": L},
                                         textures={"BaseTex": tex} if tex else None,
                                         two_sided=True if p["cull"] == 0 else None)
            slot.set_editor_property("material_interface", mi)
            mats[i] = slot
            changed = True
            report.append({"slot": name, "material": mi.get_name(), "toon": True, "shade_shift": p["shift"]})
        if changed:
            sk.set_editor_property("materials", mats)
            pc.EAL.save_loaded_asset(sk, only_if_is_dirty=False)
    return report


def mtoon_props():
    out = {}
    for m in vrm_json()["extensions"]["VRM"]["materialProperties"]:
        fp, vp = m["floatProperties"], m["vectorProperties"]
        out[m["name"].replace(".", "_")] = {
            "shift": fp.get("_ShadeShift", 0.0), "toony": fp.get("_ShadeToony", 0.9), "blend": int(fp.get("_BlendMode", 0)),
            "cull": int(fp.get("_CullMode", 2)), "shade": vp.get("_ShadeColor", [0.8, 0.8, 0.8, 1]),
            "rim": vp.get("_RimColor", [0, 0, 0, 1]), "rim_pow": fp.get("_RimFresnelPower", 1.0)}
    return out


# ---------------------------------------------------------------- rings
def ring_builder(r_mid, width, thickness):
    """Flat torus (ring) lying on the ground, centred on the origin."""
    NSEG, NRING = 96, 10
    mb = geom.MeshBuilder(["ring"])

    def P(a, b):
        rr = r_mid + width / 2.0 * math.cos(b)
        return (rr * math.cos(a), rr * math.sin(a), thickness / 2.0 * math.sin(b))

    for i in range(NSEG):
        a0, a1 = 2 * math.pi * i / NSEG, 2 * math.pi * (i + 1) / NSEG
        for j in range(NRING):
            b0, b1 = 2 * math.pi * j / NRING, 2 * math.pi * (j + 1) / NRING
            p00, p10, p11, p01 = P(a0, b0), P(a1, b0), P(a1, b1), P(a0, b1)
            mid = P((a0 + a1) / 2, (b0 + b1) / 2)
            ctr = (r_mid * math.cos((a0 + a1) / 2), r_mid * math.sin((a0 + a1) / 2), 0.0)
            n = geom.norm(geom.sub(mid, ctr))
            mb.poly("ring", [p00, p10, p11, p01], n)
    return mb


# ---------------------------------------------------------------- placement
def place_character(body, face):
    pc.ensure_map_loaded()
    pc.clear_step(STEP)
    b = body.get_bounds()
    height_m = b.box_extent.z * 2.0 / 100.0
    scale = pc.GIANT_HEIGHT / height_m
    x, y = pc.cell_center(*HERO_CELL)
    yaw = -90.0  # Interchange body faces +X at yaw 90 (checked in capture), so -90 turns her towards the board camera (-X)
    a = pc.spawn(unreal.SkeletalMeshActor, (x, y, PAD_Z), (0.0, yaw, 0.0), step_tag=STEP, label="Char_Clukay416", folder="Characters")
    a.tags = [unreal.Name(pc.TAG), unreal.Name(STEP), unreal.Name("M0Selectable")]
    a.set_actor_scale3d(unreal.Vector(scale, scale, scale))
    comp = a.get_editor_property("skeletal_mesh_component")
    comp.set_skeletal_mesh(body)
    f = pc.spawn(unreal.SkeletalMeshActor, (x, y, PAD_Z), (0.0, yaw, 0.0), step_tag=STEP, label="Char_Clukay416_Face", folder="Characters")
    f.set_actor_scale3d(unreal.Vector(scale, scale, scale))
    fcomp = f.get_editor_property("skeletal_mesh_component")
    fcomp.set_skeletal_mesh(face)
    fcomp.set_leader_pose_component(comp)
    f.attach_to_actor(a, unreal.Name(), unreal.AttachmentRule.KEEP_WORLD, unreal.AttachmentRule.KEEP_WORLD,
                      unreal.AttachmentRule.KEEP_WORLD, False)

    ring, _ = ue_mesh.build_static_mesh(RING_MESH, ring_builder(RING_R, RING_W, RING_H), {"ring": RING_BLUE}, nanite=False)
    rz = PAD_Z + RING_H / 2.0 + 0.05
    blue_ring = pc.spawn_mesh(ring, (x, y, rz), step_tag=STEP, label="Ring_Blue_Clukay", folder="Characters", materials=[pc.load(RING_BLUE)])
    blue_ring.tags = [unreal.Name(pc.TAG), unreal.Name(STEP), unreal.Name("M0SelectionRing")]
    ex, ey = pc.cell_center(*ENEMY_CELL)
    red_ring = pc.spawn_mesh(ring, (ex, ey, rz), step_tag=STEP, label="Ring_Red_Enemy", folder="Characters", materials=[pc.load(RING_RED)])
    red_ring.tags = [unreal.Name(pc.TAG), unreal.Name(STEP), unreal.Name("M0SelectionRing"), unreal.Name("M0EnemyRing")]
    pc.save_map()
    pc.log("giant at cell %s (%.0f, %.0f) scale %.2f -> %.0f m" % (HERO_CELL, x, y, scale, pc.GIANT_HEIGHT))
    return {"cell": HERO_CELL, "location_m": (x, y, PAD_Z), "yaw": yaw, "scale": round(scale, 3), "model_height_m": round(height_m, 3),
            "display_height_m": pc.GIANT_HEIGHT, "enemy_ring_cell": ENEMY_CELL, "ring_radius_m": RING_R}


def main(argv):
    t0 = time.time()
    stage_vrm()
    cleanup_scratch()
    body = import_vrm("--reimport" in argv)
    face = pc.load(FACE_MESH)
    parent = build_toon_material()
    slots = apply_toon([body, face], parent, mtoon_props())
    stats = place_character(body, face)
    sk = body.get_editor_property("skeleton")
    pose = unreal.AnimPoseExtensions.get_reference_pose(sk)
    bones = [str(n) for n in unreal.AnimPoseExtensions.get_bone_names(pose)]
    stats.update({"vrm_source": VRM_SRC, "staged": GLB_PATH, "body": SKEL_MESH, "face": FACE_MESH, "skeleton": sk.get_path_name(),
                  "bones": len(bones), "slots": slots, "toon_material": CHAR_MAT, "sun_dir": sun_dir(),
                  "seconds": round(time.time() - t0, 2)})
    pc.write_json(pc.REPORT_DIR + "/M0_VRM_Import_Report.json", stats)
    pc.log("VRM done: %d slots (%d toon) in %.1fs" % (len(slots), sum(s["toon"] for s in slots), time.time() - t0))


main(sys.argv[1:])
