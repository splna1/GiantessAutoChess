"""Step 03: master materials + instances for the Paris board (/Game/Tread/City/Paris/Materials).

Masters (legacy pins; Substrate converts them automatically):
    M_Paris_Stone    Haussmann limestone: procedural ashlar joints + photo grunge, per-instance tint
    M_Paris_Zinc     zinc mansard roof: standing seams, patina
    M_Paris_Glass    window glass: per-window hashed curtains / occasional lit window
    M_Paris_Paint    painted/metal parts: frames, wrought iron, shop fascias (palette), awnings (stripes)
    M_Paris_Ground   world-aligned ground (asphalt, sidewalk, plaza, grass, quay, damage)
    M_Paris_Water    Seine: panning normals, dark green-blue, glossy
    M_Paris_Emissive board rings / grid markers (pulse option)
    M_Paris_Foliage  tree canopies (per-instance hue variation)
    M_FX_Smoke / M_FX_Fire (particle), M_Decal_Scorch (deferred decal)
B6 additions: MI_KB_* (textured, one per slot of the BldgLG_J ruin scan) and MI_Ground_Compacted (footprint floor).
B2 additions:
    M_Paris_Textured photogrammetry / imported meshes: base-colour atlas sampled by UV0 (Notre-Dame), tint + roughness
    M_Paris_Cloth    flags and banners: red cloth with world-position-offset waves, pinned at the hoist (or both ends)
    M_FX_Beam        additive searchlight cone: fades along V, soft silhouette edges, depth fade
UV convention for generated meshes: UV0 in metres (u along the surface, v = -height); cloth quads use 0..1.

Usage (through Tools/ue_run.py):
    03_materials.py [--only textured cloth beam ...]   rebuild only the named masters (+ their instances and any
                                                       instance that does not exist yet); default rebuilds everything
"""
import sys

import unreal

import paris_common as pc
from matlib import Graph, get_or_create_mi, MP

T = pc.TEX + "/"
M = pc.MAT + "/"
FLAT_N = "/Engine/EngineMaterials/FlatNormal"
BM = unreal.BlendMode
SM = unreal.MaterialShadingModel


def stone():
    g = Graph(M + "M_Paris_Stone")
    uv = g.uv(0)
    ashlar = g.custom(
        """
float row = floor(UV.y / CourseH);
float u = UV.x / BlockL + row * 0.5;
float col = floor(u);
float fx = frac(u) * BlockL;
float fy = frac(UV.y / CourseH) * CourseH;
float d = min(min(fx, BlockL - fx), min(fy, CourseH - fy));
float j = 1.0 - saturate(d / JointW);
float h = frac(sin(dot(float2(col, row), float2(12.9898, 78.233))) * 43758.5453);
return float3(j, h, 0);
""",
        [("UV", uv), ("CourseH", g.scalar("CourseH", 0.62)), ("BlockL", g.scalar("BlockL", 1.35)), ("JointW", g.scalar("JointW", 0.014))],
        desc="Ashlar",
    )
    joint = g.mask(ashlar, r=True)
    svar = g.mask(ashlar, g=True)
    vc = g.vertex_color()
    tint = g.lerp(g.vector("TintA", (0.56, 0.48, 0.36)), g.vector("TintB", (0.66, 0.59, 0.46)), g.variation("R", vc))
    grunge = g.tex("Grunge", T + "T_KB_PlasterA_D", g.mul(uv, g.scalar("GrungeScale", 0.33)))
    macro = g.tex("Macro", T + "T_StoneGrunge", g.mul(uv, g.scalar("MacroScale", 0.08)), sampler=unreal.MaterialSamplerType.SAMPLERTYPE_MASKS)
    gl = g.mask(grunge, g=True)
    shade = g.custom(
        "return (0.80 + 0.40 * G) * (0.93 + 0.12 * S) * lerp(1.0, JD, J) * lerp(1.0 - Dirt, 1.0, M)"
        " * lerp(1.0, SootDark * (0.6 + 0.4 * M), saturate((1.0 - VA) * SootAmt));",
        [("G", gl), ("S", svar), ("J", joint), ("JD", g.scalar("JointDark", 0.55)), ("M", g.mask(macro, r=True)), ("Dirt", g.scalar("Dirt", 0.22)),
         ("VA", g.pin(vc, "A")), ("SootDark", g.scalar("SootDark", 0.12)), ("SootAmt", g.scalar("SootAmount", 1.0))],
        output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT1,
        desc="StoneShade",
    )
    g.out(MP.MP_BASE_COLOR, g.mul(tint, shade))
    g.out(MP.MP_ROUGHNESS, g.add(g.scalar("Roughness", 0.8), g.mul(joint, g.const(0.12))))
    g.out(MP.MP_SPECULAR, g.const(0.35))
    n = g.tex("Normal", T + "T_KB_PlasterA_N", g.mul(uv, g.scalar("GrungeScale2", 0.33)), sampler=unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
    g.out(MP.MP_NORMAL, g.flatten_normal(n, g.scalar("NormalFlatness", 0.45)))
    return g.finish()


def zinc():
    g = Graph(M + "M_Paris_Zinc")
    uv = g.uv(0)
    seam = g.custom(
        "float f = frac(UV.x / SeamW) * SeamW; return 1.0 - saturate(min(f, SeamW - f) / 0.025);",
        [("UV", uv), ("SeamW", g.scalar("SeamW", 0.55))],
        output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT1,
        desc="StandingSeam",
    )
    macro = g.tex("Macro", T + "T_StoneGrunge", g.mul(uv, g.scalar("MacroScale", 0.07)), sampler=unreal.MaterialSamplerType.SAMPLERTYPE_MASKS)
    streak = g.tex("Streak", T + "T_KB_ConcreteB_D", g.mul(uv, g.scalar("StreakScale", 0.12)))
    vc = g.vertex_color()
    tint = g.lerp(g.vector("TintA", (0.115, 0.13, 0.15)), g.vector("TintB", (0.16, 0.17, 0.18)), g.variation("R", vc))
    shade = g.custom(
        "return (0.75 + 0.5 * M) * (0.8 + 0.4 * S) * (1.0 + 0.5 * Seam) * lerp(1.0, 0.3, 1.0 - VA);",
        [("M", g.mask(macro, r=True)), ("S", g.mask(streak, g=True)), ("Seam", seam), ("VA", g.pin(vc, "A"))],
        output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT1,
        desc="ZincShade",
    )
    g.out(MP.MP_BASE_COLOR, g.mul(tint, shade))
    g.out(MP.MP_METALLIC, g.scalar("Metallic", 0.55))
    g.out(MP.MP_ROUGHNESS, g.lerp(g.scalar("Roughness", 0.42), g.const(0.6), g.mask(macro, r=True)))
    return g.finish()


def glass():
    g = Graph(M + "M_Paris_Glass")
    h = g.custom(
        """
float3 c = floor(WP / Cell);
float h1 = frac(sin(dot(c, float3(12.9898, 78.233, 37.719))) * 43758.5453);
float h2 = frac(sin(dot(c, float3(39.346, 11.135, 83.155))) * 24634.6345);
return float3(h1, h2, 0);
""",
        [("WP", g.world_pos()), ("Cell", g.scalar("WindowCell", 330.0))],
        desc="WindowHash",
    )
    h1 = g.mask(h, r=True)
    h2 = g.mask(h, g=True)
    base = g.custom(
        "float curtain = step(0.45, H1) * (0.35 + 0.65 * H2); return lerp(Dark, Curtain, curtain * CurtainAmt);",
        [("H1", h1), ("H2", h2), ("Dark", g.vector("GlassColor", (0.006, 0.008, 0.010))), ("Curtain", g.vector("CurtainColor", (0.20, 0.16, 0.11))), ("CurtainAmt", g.scalar("CurtainAmount", 0.55))],
        desc="GlassBase",
    )
    g.out(MP.MP_BASE_COLOR, base)
    g.out(MP.MP_ROUGHNESS, g.lerp(g.scalar("Roughness", 0.04), g.const(0.22), h2))
    g.out(MP.MP_SPECULAR, g.scalar("Specular", 0.6))
    lit = g.custom(
        "return step(1.0 - LitFrac, H1 * 0.7 + H2 * 0.3) * LitColor * LitIntensity;",
        [("H1", h1), ("H2", h2), ("LitFrac", g.scalar("LitFraction", 0.06)), ("LitColor", g.vector("LitColor", (1.0, 0.62, 0.32))), ("LitIntensity", g.scalar("LitIntensity", 0.6))],
        desc="LitWindows",
    )
    g.out(MP.MP_EMISSIVE_COLOR, lit)
    return g.finish()


def paint():
    g = Graph(M + "M_Paris_Paint")
    uv = g.uv(0)
    base = g.vector("BaseColor", (0.6, 0.57, 0.5))
    pal = g.custom(
        """
float i = floor(R * 5.0);
float3 c = float3(0.018, 0.055, 0.035);           // bottle green
c = (i >= 1.0) ? float3(0.075, 0.012, 0.016) : c; // burgundy
c = (i >= 2.0) ? float3(0.012, 0.02, 0.05) : c;   // navy
c = (i >= 3.0) ? float3(0.012, 0.012, 0.012) : c; // black
c = (i >= 4.0) ? float3(0.30, 0.27, 0.21) : c;    // cream
return c;
""",
        [("R", g.variation("G"))],
        desc="ShopPalette",
    )
    col = g.switch("UsePalette", False, pal, base)
    stripes = g.custom(
        "return (frac(UV.x / W) < 0.5) ? A : B;",
        [("UV", uv), ("W", g.scalar("StripeWidth", 0.7)), ("A", col), ("B", g.vector("StripeColor", (0.55, 0.52, 0.45)))],
        desc="Stripes",
    )
    col2 = g.switch("UseStripes", False, stripes, col)
    grunge = g.tex("Grunge", T + "T_StoneGrunge", g.mul(uv, g.scalar("GrungeScale", 0.25)), sampler=unreal.MaterialSamplerType.SAMPLERTYPE_MASKS)
    wear = g.lerp(g.const(1.0), g.mask(grunge, r=True), g.scalar("GrungeAmount", 0.3))
    g.out(MP.MP_BASE_COLOR, g.mul(col2, g.add(wear, g.const(0.15))))
    g.out(MP.MP_METALLIC, g.scalar("Metallic", 0.0))
    g.out(MP.MP_ROUGHNESS, g.scalar("Roughness", 0.55))
    return g.finish()


def railing():
    """Wrought-iron balcony railing on a flat quad: UV u = metres along, v = 0 (top) .. 1 (bottom)."""
    g = Graph(M + "M_Paris_Railing", blend=BM.BLEND_MASKED, two_sided=True)
    uv = g.uv(0)
    m = g.custom(
        """
float u = UV.x; float v = saturate(UV.y);
float rail = step(v, 0.07) + step(0.9, v) + step(abs(v - 0.62), 0.025);
float fb = frac(u / Pitch) * Pitch;
float bar = step(min(fb, Pitch - fb), BarW * 0.5) * step(v, 0.9);
float fc = frac(u / (Pitch * 2.0)) - 0.5;
float2 q = float2(fc * Pitch * 2.0, (v - 0.34) * 0.9);
float r = length(q);
float scroll = step(abs(r - 0.085), 0.012) * step(0.07, v) * step(v, 0.62);
return saturate(rail + bar + scroll);
""",
        [("UV", uv), ("Pitch", g.scalar("BarPitch", 0.13)), ("BarW", g.scalar("BarWidth", 0.022))],
        output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT1,
        desc="RailingMask",
    )
    g.out(MP.MP_OPACITY_MASK, m)
    g.out(MP.MP_BASE_COLOR, g.vector("BaseColor", (0.016, 0.016, 0.018)))
    g.out(MP.MP_METALLIC, g.scalar("Metallic", 0.6))
    g.out(MP.MP_ROUGHNESS, g.scalar("Roughness", 0.45))
    return g.finish()


def ground():
    g = Graph(M + "M_Paris_Ground")
    wuv = g.world_uv(1.0)
    uvt = g.div(wuv, g.scalar("TileM", 4.0))
    base = g.tex("BaseTex", T + "T_Web_Asphalt", uvt)
    macro = g.tex("Macro", T + "T_StoneGrunge", g.div(wuv, g.scalar("MacroTileM", 55.0)), sampler=unreal.MaterialSamplerType.SAMPLERTYPE_MASKS)
    macro2 = g.tex("Macro2", T + "T_StoneGrunge", g.div(wuv, g.const(13.0)), sampler=unreal.MaterialSamplerType.SAMPLERTYPE_MASKS)
    mv = g.custom(
        "return lerp(1.0, 0.7 + 0.45 * M1 * (0.6 + 0.4 * M2), Amt);",
        [("M1", g.mask(macro, r=True)), ("M2", g.mask(macro2, r=True)), ("Amt", g.scalar("MacroAmount", 0.6))],
        output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT1,
        desc="Macro",
    )
    col = g.mul(g.mul(g.mask(base, r=True, g=True, b=True), g.vector("Tint", (1, 1, 1))), mv)
    g.out(MP.MP_BASE_COLOR, g.custom(
        "float l = dot(C, float3(0.3, 0.59, 0.11)); return lerp(float3(l, l, l), C, Sat) * Bright;",
        [("C", col), ("Sat", g.scalar("Saturation", 1.0)), ("Bright", g.scalar("Brightness", 1.0))],
        desc="Grade",
    ))
    g.out(MP.MP_ROUGHNESS, g.lerp(g.scalar("Roughness", 0.85), g.scalar("RoughnessLow", 0.55), g.mul(g.sub(g.const(1.0), g.mask(macro2, r=True)), g.scalar("Wetness", 0.0))))
    g.out(MP.MP_SPECULAR, g.const(0.4))
    n = g.tex("NormalTex", FLAT_N, uvt, sampler=unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
    g.out(MP.MP_NORMAL, g.flatten_normal(n, g.scalar("NormalFlatness", 0.4)))
    return g.finish()


def water():
    g = Graph(M + "M_Paris_Water")
    wuv = g.world_uv(1.0)
    t = g.node(unreal.MaterialExpressionTime)
    uv1 = g.add(g.div(wuv, g.const(38.0)), g.mul(t, g.const((0.004, 0.011))))
    uv2 = g.add(g.div(wuv, g.const(17.0)), g.mul(t, g.const((-0.009, 0.006))))
    n1 = g.tex("WaveN", T + "T_Water_N", uv1, sampler=unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
    n2 = g.tex("WaveN2", T + "T_Water_N", uv2, sampler=unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
    n = g.custom("return normalize(float3(A.xy + B.xy, A.z * B.z));", [("A", n1), ("B", n2)], desc="BlendN")
    g.out(MP.MP_NORMAL, g.flatten_normal(n, g.scalar("NormalFlatness", 0.55)))
    photo = g.tex("Photo", T + "T_Web_SeineWater", g.div(wuv, g.const(60.0)))
    g.out(MP.MP_BASE_COLOR, g.lerp(g.vector("DeepColor", (0.012, 0.028, 0.026)), g.mul(g.mask(photo, r=True, g=True, b=True), g.const(0.25)), g.scalar("PhotoMix", 0.35)))
    g.out(MP.MP_ROUGHNESS, g.scalar("Roughness", 0.06))
    g.out(MP.MP_SPECULAR, g.const(0.5))
    return g.finish()


SLW_INPUTS = {  # SingleLayerWaterMaterialOutput pin -> candidate names (display name first, property name second)
    "scattering": ("Scattering Coefficients", "ScatteringCoefficients"),
    "absorption": ("Absorption Coefficients", "AbsorptionCoefficients"),
    "phase": ("Phase G", "PhaseG"),
    "behind": ("Color Scale Behind Water", "ColorScaleBehindWater"),
}


def link_slw(src, dst, key, path):
    for name in SLW_INPUTS[key]:
        if unreal.MaterialEditingLibrary.connect_material_expressions(src, "", dst, name):
            return name
    raise RuntimeError("SingleLayerWater pin %s not found in %s (tried %s)" % (key, path, SLW_INPUTS[key]))


def water_slw():
    """B4 Seine: Single Layer Water shading model (Lumen reflections, depth-based absorption, refraction of the bed).

    The water colour comes from the medium, not from BaseColor: Scattering / Absorption Coefficients (1/m) and Phase G
    feed a SingleLayerWaterMaterialOutput node (UE has no CustomData pins for this). Opacity on the main node blends in
    the opaque surface layer (foam) and must stay ~0 for open water. Two panning normal maps give the ripples."""
    path = M + "M_Paris_Water_SLW"
    # Keep the old graph compilable while get_or_create_material clears it. The water shading model
    # requires the special output node, so switching models before that node exists emits transient
    # SM6 compile errors during graph construction.
    if pc.EAL.does_asset_exist(path):
        existing = pc.load(path)
        existing.set_editor_property("shading_model", SM.MSM_DEFAULT_LIT)
    g = Graph(path)
    wuv = g.world_uv(1.0)
    t = g.node(unreal.MaterialExpressionTime)
    uv1 = g.add(g.div(wuv, g.const(42.0)), g.mul(t, g.const((0.003, 0.009))))
    uv2 = g.add(g.div(wuv, g.const(19.0)), g.mul(t, g.const((-0.007, 0.005))))
    n1 = g.tex("WaveN", T + "T_Water_N", uv1, sampler=unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
    n2 = g.tex("WaveN2", T + "T_Water_N", uv2, sampler=unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
    n = g.custom("return normalize(float3(A.xy + B.xy, A.z * B.z));", [("A", n1), ("B", n2)], desc="BlendN")
    g.out(MP.MP_BASE_COLOR, g.vector("FoamColor", (0.35, 0.34, 0.30)))
    g.out(MP.MP_NORMAL, g.flatten_normal(n, g.scalar("NormalFlatness", 0.45)))
    g.out(MP.MP_METALLIC, g.const(0.0))
    g.out(MP.MP_SPECULAR, g.scalar("Specular", 0.5))
    g.out(MP.MP_ROUGHNESS, g.scalar("Roughness", 0.05))
    g.out(MP.MP_OPACITY, g.scalar("Foam", 0.0))
    slw = g.node(unreal.MaterialExpressionSingleLayerWaterMaterialOutput)
    sc = g.mul(g.vector("Scattering", (0.05, 0.07, 0.045)), g.scalar("ScatteringScale", 1.0))
    ab = g.mul(g.vector("Absorption", (0.35, 0.18, 0.30)), g.scalar("AbsorptionScale", 1.0))
    link_slw(sc, slw, "scattering", g.path)
    link_slw(ab, slw, "absorption", g.path)
    link_slw(g.scalar("PhaseG", 0.3), slw, "phase", g.path)
    link_slw(g.scalar("ColorScaleBehindWater", 0.6), slw, "behind", g.path)
    unreal.MaterialEditingLibrary.set_base_material_usage(g.m, unreal.MaterialUsage.MATUSAGE_INSTANCED_STATIC_MESHES)
    g.m.set_editor_property("shading_model", SM.MSM_SINGLE_LAYER_WATER)
    return g.finish()


def emissive():
    g = Graph(M + "M_Paris_Emissive")
    t = g.node(unreal.MaterialExpressionTime)
    pulse = g.custom(
        "return lerp(1.0, 0.75 + 0.25 * sin(T * Speed * 6.2831), PulseAmt);",
        [("T", t), ("Speed", g.scalar("PulseSpeed", 0.6)), ("PulseAmt", g.scalar("PulseAmount", 0.0))],
        output_type=unreal.CustomMaterialOutputType.CMOT_FLOAT1,
        desc="Pulse",
    )
    c = g.vector("Color", (0.1, 0.4, 1.0))
    g.out(MP.MP_BASE_COLOR, g.mul(c, g.const(0.25)))
    g.out(MP.MP_EMISSIVE_COLOR, g.mul(g.mul(c, g.scalar("Intensity", 4.0)), pulse))
    g.out(MP.MP_ROUGHNESS, g.const(0.5))
    return g.finish()


def foliage():
    g = Graph(M + "M_Paris_Foliage")
    uv = g.uv(0)
    leaf = g.tex("LeafTex", T + "T_Web_Grass", g.mul(uv, g.scalar("LeafScale", 0.35)))
    tint = g.lerp(g.vector("TintA", (0.035, 0.06, 0.018)), g.vector("TintB", (0.075, 0.085, 0.025)), g.per_instance_random())
    g.out(MP.MP_BASE_COLOR, g.mul(tint, g.mul(g.mask(leaf, g=True), g.const(3.2))))
    g.out(MP.MP_ROUGHNESS, g.const(0.8))
    g.out(MP.MP_SPECULAR, g.const(0.25))
    return g.finish()


def smoke():
    g = Graph(M + "M_FX_Smoke", blend=BM.BLEND_TRANSLUCENT, shading=SM.MSM_DEFAULT_LIT,
              translucency_lighting_mode=unreal.TranslucencyLightingMode.TLM_VOLUMETRIC_PER_VERTEX_NON_DIRECTIONAL)
    pc_ = g.node(unreal.MaterialExpressionParticleColor)
    tex = g.tex("Puff", T + "T_SmokePuff")
    df = g.node(unreal.MaterialExpressionDepthFade, fade_distance_default=800.0)
    a = g.mul(g.mul(g.pin(tex, "A"), g.pin(pc_, "A")), g.scalar("Density", 0.8))
    g.link(a, df, "Opacity")
    g.out(MP.MP_OPACITY, df)
    g.out(MP.MP_BASE_COLOR, g.mul(g.mask(tex, r=True, g=True, b=True), g.mask(pc_, r=True, g=True, b=True)))
    g.out(MP.MP_ROUGHNESS, g.const(1.0))
    unreal.MaterialEditingLibrary.set_base_material_usage(g.m, unreal.MaterialUsage.MATUSAGE_NIAGARA_SPRITES)
    return g.finish()


def fire():
    g = Graph(M + "M_FX_Fire", blend=BM.BLEND_ADDITIVE, shading=SM.MSM_UNLIT)
    pc_ = g.node(unreal.MaterialExpressionParticleColor)
    tex = g.tex("Flame", T + "T_FlameTongue")
    df = g.node(unreal.MaterialExpressionDepthFade, fade_distance_default=300.0)
    g.link(g.pin(tex, "A"), df, "Opacity")
    e = g.mul(g.mul(g.mul(g.mask(tex, r=True, g=True, b=True), g.mask(pc_, r=True, g=True, b=True)), df), g.scalar("Intensity", 6.0))
    g.out(MP.MP_EMISSIVE_COLOR, g.mul(e, g.pin(pc_, "A")))
    return g.finish()


def scorch_decal():
    g = Graph(M + "M_Decal_Scorch", domain=unreal.MaterialDomain.MD_DEFERRED_DECAL, blend=BM.BLEND_TRANSLUCENT_COLORED_TRANSMITTANCE)
    tex = g.tex("Scorch", T + "T_Scorch")
    g.out(MP.MP_BASE_COLOR, g.mask(tex, r=True, g=True, b=True))
    g.out(MP.MP_OPACITY, g.mul(g.pin(tex, "A"), g.scalar("Opacity", 0.9)))
    g.out(MP.MP_ROUGHNESS, g.const(0.95))
    return g.finish()


def textured():
    """Imported meshes with their own UV0 atlas (Notre-Dame scan): texture x tint, flat normal."""
    g = Graph(M + "M_Paris_Textured")
    uv = g.uv(0)
    base = g.tex("BaseTex", T + "T_Web_PlazaStone", uv)
    col = g.mul(g.mask(base, r=True, g=True, b=True), g.vector("Tint", (1.0, 1.0, 1.0)))
    g.out(MP.MP_BASE_COLOR, g.mul(col, g.scalar("Brightness", 1.0)))
    g.out(MP.MP_ROUGHNESS, g.scalar("Roughness", 0.85))
    g.out(MP.MP_SPECULAR, g.scalar("Specular", 0.3))
    return g.finish()


def cloth():
    """Flags / banners: quads with UV u = hoist(0)..fly(1), v = top(0)..bottom(1). WPO waves grow with u (hoist pinned);
    PinEnds = 1 pins both ends (banners between two poles)."""
    g = Graph(M + "M_Paris_Cloth", two_sided=True)
    uv = g.uv(0)
    base = g.vector("BaseColor", (0.5, 0.03, 0.03))
    band = g.custom(
        "return (abs(UV.y - 0.5) < BandW) ? BandColor : Base;",
        [("UV", uv), ("BandW", g.scalar("BandWidth", 0.14)), ("BandColor", g.vector("BandColor", (0.85, 0.78, 0.55))), ("Base", base)],
        desc="Band",
    )
    col = g.switch("UseBand", False, band, base)
    grunge = g.tex("Grunge", T + "T_StoneGrunge", g.mul(uv, g.scalar("GrungeScale", 2.0)), sampler=unreal.MaterialSamplerType.SAMPLERTYPE_MASKS)
    wear = g.lerp(g.const(1.0), g.mask(grunge, r=True), g.scalar("GrungeAmount", 0.35))
    g.out(MP.MP_BASE_COLOR, g.mul(col, g.add(wear, g.const(0.1))))
    g.out(MP.MP_ROUGHNESS, g.scalar("Roughness", 0.85))
    g.out(MP.MP_SPECULAR, g.const(0.2))
    t = g.node(unreal.MaterialExpressionTime)
    wpo = g.custom(
        """
float pin = (PinEnds > 0.5) ? sin(3.14159 * UV.x) : UV.x;
float ph = T * Speed + UV.x * Freq + (WP.x + WP.y) * 0.02 + UV.y * 1.5;
float w = sin(ph) * 0.7 + sin(ph * 2.3 + 1.0) * 0.3;
return N * (w * Amp * 100.0 * pin);
""",
        [("UV", uv), ("T", t), ("WP", g.world_pos()), ("N", g.node(unreal.MaterialExpressionVertexNormalWS)),
         ("Speed", g.scalar("WaveSpeed", 4.0)), ("Freq", g.scalar("WaveFreq", 5.0)), ("Amp", g.scalar("WaveAmp", 0.22)),
         ("PinEnds", g.scalar("PinEnds", 0.0))],
        desc="ClothWave",
    )
    g.out(MP.MP_WORLD_POSITION_OFFSET, wpo)
    unreal.MaterialEditingLibrary.set_base_material_usage(g.m, unreal.MaterialUsage.MATUSAGE_INSTANCED_STATIC_MESHES)
    return g.finish()


def beam():
    """Searchlight cone (SM_Base_Beam_*: UV v = 0 at the lens .. 1 at the tip): additive, unlit, soft edges."""
    g = Graph(M + "M_FX_Beam", blend=BM.BLEND_ADDITIVE, shading=SM.MSM_UNLIT, two_sided=True)
    uv = g.uv(0)
    df = g.node(unreal.MaterialExpressionDepthFade, fade_distance_default=600.0)
    g.link(g.const(1.0), df, "Opacity")
    e = g.custom(
        """
float along = pow(saturate(1.0 - UV.y), Falloff);
float edge = pow(abs(dot(normalize(N), normalize(V))), EdgePow);
return Color * Intensity * along * edge * DF;
""",
        [("UV", uv), ("N", g.node(unreal.MaterialExpressionVertexNormalWS)), ("V", g.node(unreal.MaterialExpressionCameraVectorWS)),
         ("Color", g.vector("Color", (1.0, 0.92, 0.75))), ("Intensity", g.scalar("Intensity", 0.3)),
         ("Falloff", g.scalar("Falloff", 1.8)), ("EdgePow", g.scalar("EdgePow", 2.2)), ("DF", df)],
        desc="Beam",
    )
    g.out(MP.MP_EMISSIVE_COLOR, e)
    unreal.MaterialEditingLibrary.set_base_material_usage(g.m, unreal.MaterialUsage.MATUSAGE_INSTANCED_STATIC_MESHES)
    return g.finish()


MASTERS = {
    "stone": ("M_Paris_Stone", stone), "zinc": ("M_Paris_Zinc", zinc), "glass": ("M_Paris_Glass", glass),
    "paint": ("M_Paris_Paint", paint), "ground": ("M_Paris_Ground", ground), "water": ("M_Paris_Water", water),
    "water_slw": ("M_Paris_Water_SLW", water_slw), "emissive": ("M_Paris_Emissive", emissive),
    "foliage": ("M_Paris_Foliage", foliage), "railing": ("M_Paris_Railing", railing),
    "textured": ("M_Paris_Textured", textured), "cloth": ("M_Paris_Cloth", cloth),
    "smoke": ("M_FX_Smoke", smoke), "fire": ("M_FX_Fire", fire), "scorch": ("M_Decal_Scorch", scorch_decal), "beam": ("M_FX_Beam", beam),
}


def instances(ms, only=None, names=None):
    """ms: {master key: material}. With `only`, instances are (re)built only when their parent key is in `only`
    or when the instance asset does not exist yet."""
    I = M + "Instances/"
    mis = {
        # facades
        "MI_Stone_Limestone": ("stone", {}, {}, {}),
        "MI_Stone_Warm": ("stone", {"Dirt": 0.28}, {"TintA": (0.60, 0.48, 0.33), "TintB": (0.68, 0.57, 0.42)}, {}),
        "MI_Stone_Grey": ("stone", {"Dirt": 0.3}, {"TintA": (0.46, 0.44, 0.40), "TintB": (0.56, 0.53, 0.48)}, {}),
        "MI_Stone_Rustic": ("stone", {"CourseH": 0.46, "BlockL": 1.1, "JointW": 0.03, "JointDark": 0.42}, {}, {}),
        "MI_Stone_Soot": ("stone", {"Dirt": 0.55, "JointDark": 0.5}, {"TintA": (0.20, 0.18, 0.15), "TintB": (0.30, 0.26, 0.21)}, {}),
        "MI_Stone_Stucco": ("stone", {"JointDark": 1.0, "Dirt": 0.34, "NormalFlatness": 0.6}, {"TintA": (0.55, 0.50, 0.42), "TintB": (0.64, 0.58, 0.49)}, {}),
        "MI_Stone_Quay": ("stone", {"CourseH": 0.55, "BlockL": 1.3, "Dirt": 0.45, "JointDark": 0.5}, {"TintA": (0.44, 0.40, 0.33), "TintB": (0.52, 0.47, 0.39)}, {}),
        "MI_Stone_Chimney": ("stone", {"CourseH": 0.3, "BlockL": 0.6, "JointW": 0.01}, {"TintA": (0.36, 0.25, 0.19), "TintB": (0.44, 0.32, 0.25)}, {}),
        # roofs / glass / paint
        "MI_Zinc": ("zinc", {}, {}, {}),
        "MI_Zinc_Dark": ("zinc", {"Metallic": 0.4}, {"TintA": (0.06, 0.065, 0.075), "TintB": (0.09, 0.095, 0.1)}, {}),
        "MI_Glass": ("glass", {}, {}, {}),
        "MI_Glass_Shop": ("glass", {"CurtainAmount": 0.2, "LitFraction": 0.5, "LitIntensity": 0.9, "WindowCell": 280.0}, {"LitColor": (1.0, 0.72, 0.45)}, {}),
        "MI_Paint_Frame": ("paint", {"Roughness": 0.6, "GrungeAmount": 0.25}, {"BaseColor": (0.58, 0.55, 0.48)}, {}),
        "MI_Paint_Iron": ("paint", {"Roughness": 0.5, "Metallic": 0.55, "GrungeAmount": 0.15}, {"BaseColor": (0.018, 0.018, 0.02)}, {}),
        "MI_Paint_Door": ("paint", {"Roughness": 0.4, "GrungeAmount": 0.35}, {"BaseColor": (0.02, 0.045, 0.05)}, {}),
        "MI_Paint_ShopFascia": ("paint", {"Roughness": 0.45}, {}, {"UsePalette": True}),
        "MI_Paint_Awning_Red": ("paint", {"Roughness": 0.85, "StripeWidth": 0.6}, {"BaseColor": (0.25, 0.015, 0.02), "StripeColor": (0.55, 0.50, 0.42)}, {"UseStripes": True}),
        "MI_Paint_Awning_Green": ("paint", {"Roughness": 0.85, "StripeWidth": 0.6}, {"BaseColor": (0.02, 0.09, 0.04), "StripeColor": (0.55, 0.50, 0.42)}, {"UseStripes": True}),
        "MI_Paint_Terracotta": ("paint", {"Roughness": 0.8}, {"BaseColor": (0.36, 0.13, 0.06)}, {}),
        "MI_Paint_Bark": ("paint", {"Roughness": 0.9, "GrungeAmount": 0.6}, {"BaseColor": (0.05, 0.035, 0.025)}, {}),
        "MI_Paint_Eiffel": ("paint", {"Roughness": 0.6, "Metallic": 0.1, "GrungeAmount": 0.3, "GrungeScale": 0.08}, {"BaseColor": (0.15, 0.095, 0.06)}, {}),
        "MI_Paint_LampPost": ("paint", {"Roughness": 0.45, "Metallic": 0.5}, {"BaseColor": (0.012, 0.022, 0.016)}, {}),
        "MI_Paint_Gold": ("paint", {"Roughness": 0.3, "Metallic": 1.0, "GrungeAmount": 0.1}, {"BaseColor": (0.75, 0.52, 0.2)}, {}),
        "MI_Paint_Charred": ("paint", {"Roughness": 0.95, "GrungeAmount": 0.7}, {"BaseColor": (0.02, 0.018, 0.016)}, {}),
        "MI_Paint_Marking": ("paint", {"Roughness": 0.6, "GrungeAmount": 0.5}, {"BaseColor": (0.55, 0.53, 0.48)}, {}),
        "MI_Paint_Car": ("paint", {"Roughness": 0.3, "Metallic": 0.6}, {}, {"UsePalette": True}),
        # ground
        "MI_Ground_Asphalt": ("ground", {"TileM": 5.0, "Brightness": 0.55, "Saturation": 0.35, "Roughness": 0.8}, {}, {"BaseTex": pc.TEX + "/T_Web_Asphalt"}),
        "MI_Ground_Sidewalk": ("ground", {"TileM": 3.0, "Brightness": 0.75, "Saturation": 0.4}, {"Tint": (0.95, 0.9, 0.82)}, {"BaseTex": pc.TEX + "/T_KB_ConcreteA_D", "NormalTex": pc.TEX + "/T_KB_ConcreteA_N"}),
        "MI_Ground_Cobble": ("ground", {"TileM": 3.5, "Brightness": 0.62, "Saturation": 0.35, "Wetness": 0.4}, {}, {"BaseTex": pc.TEX + "/T_Web_Cobble"}),
        "MI_Ground_Plaza": ("ground", {"TileM": 5.0, "Brightness": 0.8, "Saturation": 0.5}, {"Tint": (1.0, 0.95, 0.86)}, {"BaseTex": pc.TEX + "/T_Web_PlazaStone"}),
        "MI_Ground_Grass": ("ground", {"TileM": 6.0, "Brightness": 0.7, "Saturation": 0.85, "Roughness": 0.9}, {}, {"BaseTex": pc.TEX + "/T_Web_Grass"}),
        "MI_Ground_Gravel": ("ground", {"TileM": 4.0, "Brightness": 0.85, "Saturation": 0.45}, {"Tint": (0.95, 0.85, 0.7)}, {"BaseTex": pc.TEX + "/T_KB_DamageA_D", "NormalTex": pc.TEX + "/T_KB_DamageA_N"}),
        "MI_Ground_Quay": ("ground", {"TileM": 5.0, "Brightness": 0.7, "Saturation": 0.4}, {"Tint": (1.0, 0.95, 0.85)}, {"BaseTex": pc.TEX + "/T_Web_QuayStone"}),
        "MI_Ground_Damaged": ("ground", {"TileM": 7.0, "Brightness": 0.62, "Saturation": 0.4}, {}, {"BaseTex": pc.TEX + "/T_Web_DamagedConcrete"}),
        "MI_Ground_Scorched": ("ground", {"TileM": 4.0, "Brightness": 0.5, "Saturation": 0.35}, {}, {"BaseTex": pc.TEX + "/T_Web_ScorchedCobble"}),
        "MI_Ground_Rubble": ("ground", {"TileM": 5.0, "Brightness": 0.8, "Saturation": 0.5, "NormalFlatness": 0.1}, {}, {"BaseTex": pc.TEX + "/T_KB_RubbleA_D", "NormalTex": pc.TEX + "/T_KB_RubbleA_N"}),
        "MI_Ground_PadLight": ("ground", {"TileM": 4.0, "Brightness": 1.0, "Saturation": 0.35}, {"Tint": (1.0, 0.96, 0.88)}, {"BaseTex": pc.TEX + "/T_Web_PlazaStone"}),
        "MI_Ground_PadDark": ("ground", {"TileM": 4.0, "Brightness": 0.42, "Saturation": 0.4}, {"Tint": (0.85, 0.82, 0.78)}, {"BaseTex": pc.TEX + "/T_Web_PlazaStone"}),
        "MI_Ground_Courtyard": ("ground", {"TileM": 3.0, "Brightness": 0.6, "Saturation": 0.4}, {}, {"BaseTex": pc.TEX + "/T_KB_ConcreteB_D"}),
        # water / board
        "MI_Water_Seine": ("water_slw", {"NormalFlatness": 0.4, "Roughness": 0.05}, {"Scattering": (0.05, 0.07, 0.045), "Absorption": (0.35, 0.18, 0.30)}, {}),
        "MI_Ring_Blue": ("emissive", {"Intensity": 6.0, "PulseAmount": 0.35}, {"Color": (0.05, 0.35, 1.0)}, {}),
        "MI_Ring_Red": ("emissive", {"Intensity": 2.5, "PulseAmount": 0.35}, {"Color": (1.0, 0.07, 0.04)}, {}),
        "MI_Board_Line": ("emissive", {"Intensity": 1.6}, {"Color": (1.0, 0.78, 0.42)}, {}),
        "MI_Lamp_Glow": ("emissive", {"Intensity": 6.0}, {"Color": (1.0, 0.75, 0.45)}, {}),
        "MI_Ember": ("emissive", {"Intensity": 10.0, "PulseAmount": 0.5, "PulseSpeed": 1.3}, {"Color": (1.0, 0.28, 0.05)}, {}),
        "MI_Foliage": ("foliage", {}, {}, {}),
        "MI_Railing": ("railing", {}, {}, {}),
        # B2: red base props (basegen.py) and the Notre-Dame scan (06_landmarks.py)
        "MI_Paint_Canvas": ("paint", {"Roughness": 0.92, "GrungeAmount": 0.5, "GrungeScale": 0.6}, {"BaseColor": (0.11, 0.115, 0.07)}, {}),
        "MI_Paint_CanvasDark": ("paint", {"Roughness": 0.92, "GrungeAmount": 0.5, "GrungeScale": 0.6}, {"BaseColor": (0.05, 0.055, 0.035)}, {}),
        "MI_Paint_Sandbag": ("paint", {"Roughness": 0.97, "GrungeAmount": 0.6, "GrungeScale": 1.2}, {"BaseColor": (0.30, 0.25, 0.16)}, {}),
        "MI_Paint_Concrete": ("paint", {"Roughness": 0.9, "GrungeAmount": 0.55, "GrungeScale": 0.8}, {"BaseColor": (0.40, 0.40, 0.37)}, {}),
        "MI_Paint_Steel": ("paint", {"Roughness": 0.45, "Metallic": 0.7, "GrungeAmount": 0.35}, {"BaseColor": (0.16, 0.165, 0.17)}, {}),
        "MI_Cloth_Red": ("cloth", {}, {"BaseColor": (0.55, 0.03, 0.03)}, {}),
        "MI_Cloth_RedBanner": ("cloth", {"PinEnds": 1.0, "WaveAmp": 0.12}, {"BaseColor": (0.55, 0.03, 0.03)}, {"UseBand": True}),
        "MI_Signal_Red": ("emissive", {"Intensity": 40.0, "PulseAmount": 0.6, "PulseSpeed": 1.1}, {"Color": (1.0, 0.05, 0.02)}, {}),
        "MI_Searchlight_Lens": ("emissive", {"Intensity": 60.0}, {"Color": (1.0, 0.95, 0.85)}, {}),
        # B5: blue command centre and its cloth / signal language.
        "MI_Paint_Blue": ("paint", {"Roughness": 0.58, "Metallic": 0.22, "GrungeAmount": 0.3}, {"BaseColor": (0.035, 0.12, 0.38)}, {}),
        "MI_Paint_BlueDark": ("paint", {"Roughness": 0.78, "Metallic": 0.42, "GrungeAmount": 0.45}, {"BaseColor": (0.012, 0.035, 0.11)}, {}),
        "MI_Paint_BlueCanvas": ("paint", {"Roughness": 0.92, "GrungeAmount": 0.45, "GrungeScale": 0.7}, {"BaseColor": (0.035, 0.10, 0.22)}, {}),
        "MI_Paint_BlueSandbag": ("paint", {"Roughness": 0.98, "GrungeAmount": 0.65, "GrungeScale": 1.15}, {"BaseColor": (0.11, 0.18, 0.26)}, {}),
        "MI_Paint_BlueConcrete": ("paint", {"Roughness": 0.9, "GrungeAmount": 0.55, "GrungeScale": 0.8}, {"BaseColor": (0.23, 0.29, 0.36)}, {}),
        "MI_Paint_BlueSteel": ("paint", {"Roughness": 0.42, "Metallic": 0.78, "GrungeAmount": 0.3}, {"BaseColor": (0.06, 0.13, 0.22)}, {}),
        "MI_Cloth_Blue": ("cloth", {}, {"BaseColor": (0.02, 0.16, 0.78)}, {}),
        "MI_Cloth_BlueBanner": ("cloth", {"PinEnds": 1.0, "WaveAmp": 0.10}, {"BaseColor": (0.02, 0.16, 0.78)}, {"UseBand": True}),
        "MI_Signal_Blue": ("emissive", {"Intensity": 34.0, "PulseAmount": 0.52, "PulseSpeed": 1.2}, {"Color": (0.03, 0.22, 1.0)}, {}),
        "MI_Glow_Blue": ("emissive", {"Intensity": 7.0}, {"Color": (0.04, 0.35, 1.0)}, {}),
        # B5 densify: eagle shields (saturated blue field, white charge), olive hangar / trucks.
        "MI_Paint_BlueBright": ("paint", {"Roughness": 0.45, "Metallic": 0.1, "GrungeAmount": 0.15}, {"BaseColor": (0.015, 0.16, 0.72)}, {}),
        "MI_Paint_BlueWhite": ("paint", {"Roughness": 0.5, "GrungeAmount": 0.15}, {"BaseColor": (0.62, 0.66, 0.72)}, {}),
        "MI_Paint_Olive": ("paint", {"Roughness": 0.9, "GrungeAmount": 0.4, "GrungeScale": 0.7}, {"BaseColor": (0.10, 0.15, 0.06)}, {}),
        "MI_NotreDame": ("textured", {"Roughness": 0.88, "Brightness": 1.0}, {}, {"BaseTex": pc.TEX + "/T_NotreDame_D"}),
        # B6: the BldgLG_J ruin scan (one instance per KB3D slot, UV0 atlas) and the pale floor of the giant footprints
        "MI_KB_AssetsA": ("textured", {"Roughness": 0.8}, {}, {"BaseTex": pc.TEX + "/T_KB_AssetsA_D"}),
        "MI_KB_BricksA": ("textured", {"Roughness": 0.9}, {}, {"BaseTex": pc.TEX + "/T_KB_BricksA_D"}),
        "MI_KB_BricksADamage": ("textured", {"Roughness": 0.92}, {}, {"BaseTex": pc.TEX + "/T_KB_BricksADamage_D"}),
        "MI_KB_ConcreteA": ("textured", {"Roughness": 0.9}, {}, {"BaseTex": pc.TEX + "/T_KB_ConcreteA_D"}),
        "MI_KB_ConcreteB": ("textured", {"Roughness": 0.9}, {}, {"BaseTex": pc.TEX + "/T_KB_ConcreteB_D"}),
        "MI_KB_DamageA": ("textured", {"Roughness": 0.92}, {}, {"BaseTex": pc.TEX + "/T_KB_DamageA_D"}),
        "MI_KB_FloorA": ("textured", {"Roughness": 0.85}, {}, {"BaseTex": pc.TEX + "/T_KB_FloorA_D"}),
        "MI_KB_FloorB": ("textured", {"Roughness": 0.85}, {}, {"BaseTex": pc.TEX + "/T_KB_FloorB_D"}),
        "MI_KB_MetalFrameA": ("textured", {"Roughness": 0.6, "Specular": 0.45}, {}, {"BaseTex": pc.TEX + "/T_KB_MetalFrameA_D"}),
        "MI_KB_MetalRustA": ("textured", {"Roughness": 0.75, "Specular": 0.4}, {}, {"BaseTex": pc.TEX + "/T_KB_MetalRustA_D"}),
        "MI_KB_PlasterA": ("textured", {"Roughness": 0.9}, {}, {"BaseTex": pc.TEX + "/T_KB_PlasterA_D"}),
        "MI_KB_PlasterB": ("textured", {"Roughness": 0.9}, {}, {"BaseTex": pc.TEX + "/T_KB_PlasterB_D"}),
        "MI_KB_PlasterC": ("textured", {"Roughness": 0.9}, {}, {"BaseTex": pc.TEX + "/T_KB_PlasterC_D"}),
        "MI_KB_RubbleA": ("textured", {"Roughness": 0.95}, {}, {"BaseTex": pc.TEX + "/T_KB_RubbleA_D"}),
        "MI_KB_WoodA": ("textured", {"Roughness": 0.85}, {}, {"BaseTex": pc.TEX + "/T_KB_WoodA_D"}),
        "MI_Ground_Compacted": ("ground", {"TileM": 6.0, "Brightness": 1.05, "Saturation": 0.3, "NormalFlatness": 0.5, "MacroAmount": 0.35},
                                {"Tint": (1.0, 0.94, 0.84)}, {"BaseTex": pc.TEX + "/T_KB_ConcreteA_D", "NormalTex": pc.TEX + "/T_KB_ConcreteA_N"}),
    }
    two_sided = {"MI_Paint_Eiffel", "MI_Cloth_Red", "MI_Cloth_RedBanner", "MI_Cloth_Blue", "MI_Cloth_BlueBanner", "MI_NotreDame"}  # open ribbons / cloth quads / scan
    two_sided |= {n for n in mis if n.startswith("MI_KB_")}  # B6 ruin scan: torn single-sided panels
    n = 0
    for name, (pkey, sc, vec, rest) in mis.items():
        if names is not None and name not in names:
            continue
        # A targeted build must stay targeted even if an unrelated instance is missing.
        if only and pkey not in only:
            continue
        textures = {k: val for k, val in rest.items() if isinstance(val, str)}
        switches = {k: val for k, val in rest.items() if isinstance(val, bool)}
        get_or_create_mi(I + name, ms[pkey], sc, vec, textures, switches, True if name in two_sided else None)
        n += 1
    pc.log("instances: %d built of %d" % (n, len(mis)))
    return n


def build_masters(only=None):
    """Build and return requested masters, or every master when no filter is given."""
    selected = set(only) if only else set(MASTERS)
    unknown = selected.difference(MASTERS)
    if unknown:
        raise RuntimeError("unknown master keys %s (known: %s)" % (sorted(unknown), sorted(MASTERS)))
    ms = {}
    for key, (name, fn) in MASTERS.items():
        if key not in selected:
            continue
        path = M + name
        ms[key] = fn()
    return ms


def build_instances(ms, only=None):
    """Build material instances for selected master keys (or all instances)."""
    return instances(ms, set(only) if only else None)


def main(argv):
    if "--b6" in argv:
        selected = {"MI_KB_" + suffix for suffix in (
            "AssetsA", "BricksA", "BricksADamage", "ConcreteA", "ConcreteB", "DamageA", "FloorA", "FloorB",
            "MetalFrameA", "MetalRustA", "PlasterA", "PlasterB", "PlasterC", "RubbleA", "WoodA")}
        selected.add("MI_Ground_Compacted")
        instances({key: pc.load(M + MASTERS[key][0]) for key in ("textured", "ground")}, names=selected)
        return
    only = [argv[i + 1] for i, a in enumerate(argv) if a == "--only"]
    unknown = [k for k in only if k not in MASTERS]
    if unknown:
        raise RuntimeError("unknown master keys %s (known: %s)" % (unknown, sorted(MASTERS)))
    ms = build_masters(only)
    build_instances(ms, only)


if __name__ == "__main__":
    main(sys.argv[1:])
