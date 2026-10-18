"""Step 01: create/load /Game/Tread/Maps/M0_Paris_Board and build the lighting stack.

DirectionalLight (sun, VSM, atmosphere sun), SkyAtmosphere, SkyLight (real-time capture),
ExponentialHeightFog, VolumetricCloud and an unbound PostProcessVolume with LOCKED manual exposure.
Re-running rebuilds only actors tagged "Lighting".
"""
import unreal
import paris_common as pc

STEP = "Lighting"

SUN_PITCH = -27.0  # late-afternoon sun: long shadows, but streets and courtyards stay lit
SUN_YAW = 38.0  # light travels towards NNE: sun sits behind-left of the default camera
SUN_LUX = 10.0
SUN_TEMP = 4800.0  # warm, slightly smoky light over the battle
EXPOSURE_BIAS = 0.0  # manual EV100 = 0 + bias, see 09_camera_capture.py report


def make_level():
    les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
    pc.ensure_dir("/Game/Tread/Maps")
    if pc.EAL.does_asset_exist(pc.MAP_PATH):
        if not pc.world().get_path_name().startswith(pc.MAP_PATH):
            les.load_level(pc.MAP_PATH)
        pc.log("loaded", pc.MAP_PATH)
    else:
        ok = les.new_level(pc.MAP_PATH, False)
        pc.log("new_level", pc.MAP_PATH, ok)


def build():
    pc.clear_step(STEP)

    sun = pc.spawn(unreal.DirectionalLight, (0, 0, 600), (SUN_PITCH, SUN_YAW, 0), STEP, "Sun_Directional", "Lighting")
    lc = sun.get_component_by_class(unreal.DirectionalLightComponent)
    lc.set_mobility(unreal.ComponentMobility.MOVABLE)
    lc.set_editor_property("intensity", SUN_LUX)
    lc.set_editor_property("use_temperature", True)
    lc.set_editor_property("temperature", SUN_TEMP)
    lc.set_editor_property("atmosphere_sun_light", True)
    lc.set_editor_property("cast_shadows", True)
    lc.set_editor_property("cast_cloud_shadows", True)
    lc.set_editor_property("cast_shadows_on_clouds", True)
    lc.set_editor_property("light_source_angle", 0.8)
    lc.set_editor_property("dynamic_shadow_distance_movable_light", 400000.0)
    lc.set_editor_property("volumetric_scattering_intensity", 1.0)

    sky = pc.spawn(unreal.SkyAtmosphere, (0, 0, 0), (0, 0, 0), STEP, "SkyAtmosphere", "Lighting")
    sc = sky.get_component_by_class(unreal.SkyAtmosphereComponent)
    # default aerial perspective; the height fog adds the late-afternoon haze beyond ~1.5 km
    sc.set_editor_property("aerial_pespective_view_distance_scale", 1.0)
    sc.set_editor_property("mie_scattering_scale", 0.004)
    sc.set_editor_property("height_fog_contribution", 1.0)

    sl = pc.spawn(unreal.SkyLight, (0, 0, 800), (0, 0, 0), STEP, "SkyLight_RealTime", "Lighting")
    slc = sl.get_component_by_class(unreal.SkyLightComponent)
    slc.set_mobility(unreal.ComponentMobility.MOVABLE)
    slc.set_editor_property("real_time_capture", True)
    slc.set_editor_property("intensity", 1.0)
    slc.set_editor_property("lower_hemisphere_is_black", False)
    slc.set_editor_property("lower_hemisphere_color", unreal.LinearColor(0.10, 0.09, 0.08, 1.0))

    fog = pc.spawn(unreal.ExponentialHeightFog, (0, 0, -50), (0, 0, 0), STEP, "HeightFog", "Lighting")
    fc = fog.get_component_by_class(unreal.ExponentialHeightFogComponent)
    fc.set_editor_property("fog_density", 0.0045)
    fc.set_editor_property("fog_height_falloff", 0.12)
    fc.set_editor_property("start_distance", 120000.0)
    fc.set_editor_property("fog_max_opacity", 0.6)
    fc.set_editor_property("fog_inscattering_luminance", unreal.LinearColor(0.34, 0.33, 0.36, 1.0))
    fc.set_editor_property("directional_inscattering_luminance", unreal.LinearColor(0.62, 0.42, 0.24, 1.0))
    fc.set_editor_property("directional_inscattering_exponent", 6.0)
    fc.set_editor_property("enable_volumetric_fog", False)

    cloud = pc.spawn(unreal.VolumetricCloud, (0, 0, 0), (0, 0, 0), STEP, "VolumetricCloud", "Lighting")
    cc = cloud.get_component_by_class(unreal.VolumetricCloudComponent)
    cm = pc.EAL.load_asset("/Engine/EngineSky/VolumetricClouds/m_SimpleVolumetricCloud_Inst")
    if cm:
        cc.set_material(cm)
    cc.set_editor_property("layer_bottom_altitude", 3.0)
    cc.set_editor_property("layer_height", 6.0)

    ppv = pc.spawn(unreal.PostProcessVolume, (0, 0, 0), (0, 0, 0), STEP, "PPV_LockedExposure", "Lighting")
    ppv.set_editor_property("unbound", True)
    ppv.set_editor_property("priority", 10.0)
    s = ppv.get_editor_property("settings")
    setp = [
        # locked exposure: manual method, no physical camera, fixed bias -> no eye adaptation pumping
        ("auto_exposure_method", unreal.AutoExposureMethod.AEM_MANUAL),
        ("auto_exposure_apply_physical_camera_exposure", False),
        ("auto_exposure_bias", EXPOSURE_BIAS),
        ("auto_exposure_min_brightness", 1.0),
        ("auto_exposure_max_brightness", 1.0),
        ("bloom_intensity", 0.35),
        ("vignette_intensity", 0.25),
        ("lumen_scene_view_distance", 400000.0),
        ("lumen_max_trace_distance", 200000.0),
        ("lumen_final_gather_quality", 1.5),
        ("lumen_scene_lighting_quality", 1.0),
        ("lumen_reflection_quality", 1.0),
        ("film_toe", 0.5),
        ("film_shoulder", 0.3),
        ("color_saturation", unreal.Vector4(0.97, 0.97, 0.97, 1.0)),
        ("white_temp", 6300.0),
    ]
    for name, val in setp:
        s.set_editor_property(name, val)
        try:
            s.set_editor_property("override_" + name, True)
        except Exception:  # noqa: BLE001
            pc.log("no override flag for", name)
    s.set_editor_property("dynamic_global_illumination_method", unreal.DynamicGlobalIlluminationMethod.LUMEN)
    s.set_editor_property("override_dynamic_global_illumination_method", True)
    s.set_editor_property("reflection_method", unreal.ReflectionMethod.LUMEN)
    s.set_editor_property("override_reflection_method", True)
    ppv.set_editor_property("settings", s)
    pc.log("lighting stack built: sun %.0f lux pitch %.0f yaw %.0f, exposure manual bias %.2f" % (SUN_LUX, SUN_PITCH, SUN_YAW, EXPOSURE_BIAS))


make_level()
build()
pc.save_map()
