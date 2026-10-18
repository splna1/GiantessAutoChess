"""Unit ring health material (document/159): the ring under each unit doubles as its health bar.

M_Tread_UnitRing - unlit, masked. Emissive = Color * Intensity * Pulse, and the mask cuts away everything that is
further than HealthFraction * 180 deg from the +X axis, so the remaining arc is centred on 12 o'clock and the gap is
centred on 6 o'clock and grows symmetrically on both sides. HealthFraction = 1 is a full ring (preparation, and any
unit that was never hit), 0 is no ring at all (the unit is knocked out and the presenter hides the ring anyway).

ATreadM3BoardPresenter builds one dynamic instance per unit from MI_UnitRing_Blue / MI_UnitRing_Red and drives
HealthFraction; MI_UnitRing_Track is the dark ring that shows through the gap.

    python Tools/ue_run.py Tools/battle/build_unit_ring_material.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "Tools", "paris"))

import unreal  # noqa: E402

import paris_common as pc  # noqa: E402
from matlib import Graph, get_or_create_mi  # noqa: E402

FOLDER = pc.CHAR + "/UnitRing"
MASTER = FOLDER + "/M_Tread_UnitRing"
BM = unreal.BlendMode
SM = unreal.MaterialShadingModel
CMOT = unreal.CustomMaterialOutputType
MEL = unreal.MaterialEditingLibrary

# 6 o'clock = object-local -X: the board camera looks along +X, so -X is the bottom of the screen on the board.
ARC = """
float2 p = WP.xy - OP.xy;
float a = atan2(abs(p.y), p.x);          // 0 at +X (12 o'clock) .. PI at -X (6 o'clock)
float lim = saturate(Frac) * 3.14159265;
return saturate((lim - a) * 200.0);
"""

PULSE = """
return lerp(1.0, 0.75 + 0.25 * sin(T * Speed * 6.2831), Amt);
"""


def build_master():
    g = Graph(MASTER, blend=BM.BLEND_MASKED, shading=SM.MSM_UNLIT, two_sided=True)
    arc = g.custom(ARC, [("WP", g.node(unreal.MaterialExpressionWorldPosition)),
                         ("OP", g.node(unreal.MaterialExpressionObjectPositionWS)),
                         ("Frac", g.scalar("HealthFraction", 1.0, group="UnitRing"))],
                   output_type=CMOT.CMOT_FLOAT1, desc="RingArc")
    g.out(unreal.MaterialProperty.MP_OPACITY_MASK, arc)
    pulse = g.custom(PULSE, [("T", g.node(unreal.MaterialExpressionTime)),
                             ("Speed", g.scalar("PulseSpeed", 0.6, group="UnitRing")),
                             ("Amt", g.scalar("PulseAmount", 0.0, group="UnitRing"))],
                     output_type=CMOT.CMOT_FLOAT1, desc="Pulse")
    color = g.vector("Color", (0.05, 0.35, 1.0), group="UnitRing")
    g.out(unreal.MaterialProperty.MP_EMISSIVE_COLOR,
          g.mul(g.mul(color, g.scalar("Intensity", 6.0, group="UnitRing")), pulse))
    material = g.finish()
    unreal.MaterialEditingLibrary.set_base_material_usage(material, unreal.MaterialUsage.MATUSAGE_INSTANCED_STATIC_MESHES)
    unreal.MaterialEditingLibrary.recompile_material(material)
    pc.EAL.save_asset(MASTER, only_if_is_dirty=False)
    return material


def build_instances(master):
    # Same colours as the M0 selection rings (Tools/paris/03_materials.py), so the board keeps its blue / red language.
    get_or_create_mi(FOLDER + "/MI_UnitRing_Blue", master,
                     scalars={"Intensity": 6.0, "PulseAmount": 0.35}, vectors={"Color": (0.05, 0.35, 1.0)})
    get_or_create_mi(FOLDER + "/MI_UnitRing_Red", master,
                     scalars={"Intensity": 2.5, "PulseAmount": 0.35}, vectors={"Color": (1.0, 0.07, 0.04)})
    # Dark track: barely emissive so it reads as a socket, never as a second health bar.
    get_or_create_mi(FOLDER + "/MI_UnitRing_Track", master,
                     scalars={"Intensity": 1.2, "PulseAmount": 0.0}, vectors={"Color": (0.02, 0.02, 0.025)})


def report():
    mesh = pc.load(pc.CHAR + "/SM_SelectionRing")
    if mesh:
        bounds = mesh.get_bounds()
        extent = bounds.box_extent
        pc.log("ring mesh extent x=%.1f y=%.1f z=%.1f (z must be the thin axis for the XY angle mask)"
               % (extent.x, extent.y, extent.z))
    for name in ("M_Tread_UnitRing", "MI_UnitRing_Blue", "MI_UnitRing_Red", "MI_UnitRing_Track"):
        pc.log("%s exists=%s" % (name, pc.EAL.does_asset_exist(FOLDER + "/" + name)))


def main():
    master = build_master()
    build_instances(master)
    report()
    print("RING material built in " + FOLDER)


main()
