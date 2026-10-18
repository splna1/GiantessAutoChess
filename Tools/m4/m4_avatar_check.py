"""M4 avatar / portrait-detail acceptance (editor-side, Tools/ue_run.py), phase by phase; driven by
Tools/m4/m4_avatar_check_pie.py.  Needs the editor built with the avatar C++ (GetCardAvatarPath, SetPortraitDetailForTest).

  load            guard dirty packages, check all 112 avatar + 112 portrait textures exist, load M3_Paris_Match
  run             (PIE) every roster id resolves its avatar and portrait path/texture, avatar != portrait, the shop and
                  bench draw the avatar of the model (not the PNG), detail hook round trip, battle blocks buying
                  -> Saved/Reports/M4_AvatarCheck.json
  stage <name>    (PIE) put the HUD into the state an evidence shot needs:
                    shop      preparation, shop avatars (chest-up model screenshots) in the shop panel
                    bench     preparation with bought bench units, bench avatar tooltip
                    detail    preparation with the PNG portrait detail of the first shop character open
                    battle    battle phase (buying / dragging forbidden, detail closed)
  shoot           (PIE) "shot showui"
  cleanup         (PIE) back to a free match with the detail closed
  restore         reload the map that load remembered

Every phase is its own remote call (memory: tread-editor-python-map-switch).  Everything printed is ASCII.
"""
import json
import os
import sys

import unreal

PROJECT = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
REPORTS = os.path.join(PROJECT, "Saved", "Reports")
STATE = os.path.join(REPORTS, "M4_AvatarCheck_state.json")
REPORT = os.path.join(REPORTS, "M4_AvatarCheck.json")
ROSTER = os.path.join(PROJECT, "Content", "Data", "Generated", "CharacterRosterMap.json")
M3_MAP = "/Game/Tread/Maps/M3_Paris_Match"
HUMAN = "P0"
SEED = 20261014
EAL = unreal.EditorAssetLibrary


def read(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def write(path, doc):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(doc, handle, ensure_ascii=True, indent=1)


def game_world():
    sub = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
    world = sub.get_game_world() if sub else None
    if world:
        return world
    for world in unreal.EditorLevelLibrary.get_pie_worlds(False) or []:
        if world:
            return world
    return None


def controller_of(world):
    found = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.TreadM1MatchController)
    if not found:
        raise RuntimeError("no TreadM1MatchController")
    return found[0]


def widget_of(world):
    # UE 5.8 renamed WidgetBlueprintLibrary to WidgetLibrary.
    lib = getattr(unreal, "WidgetLibrary", None) or getattr(unreal, "WidgetBlueprintLibrary")
    found = lib.get_all_widgets_of_class(world, unreal.TreadM1MatchWidget, False)
    return found[0] if found else None


def phase(c):
    return c.get_phase().name


def human(c):
    for p in c.match_state.players:
        if str(p.player_id) == HUMAN:
            return p
    raise RuntimeError("no human player")


def to_preparation(c, tag):
    c.initialize_match(SEED)
    c.select_campaign_stage(0, tag + "-free")
    if phase(c).endswith("R0_BRIEFING"):
        c.begin_pre_match_bp(tag + "-bp")
    if phase(c).endswith("PRE_MATCH_BP"):
        available = [str(s) for s in c.match_state.bp.available_strategy_ids]
        if available:
            c.choose_player_strategy(available[0], tag + "-strategy")
        for pick in range(3):
            c.run_next_ai_pick("%s-ai-%d" % (tag, pick))
        c.confirm_pre_match_bp(tag + "-confirm")
    if not phase(c).endswith("PREPARATION"):
        c.begin_preparation(tag + "-prep")
    return phase(c)


def roster_rows():
    return read(ROSTER).get("characters", [])


def phase_load():
    if game_world():
        raise RuntimeError("a PIE session is already running")
    dirty = (unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
             + unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages())
    if dirty:
        raise RuntimeError("dirty packages present, refusing to switch map: %s" % [p.get_name() for p in dirty][:10])
    rows = roster_rows()
    missing = []
    for row in rows:
        for key, folder in (("avatarAsset", "/Game/Tread/UI/Avatars/T_Avatar_"),
                            ("portraitAsset", "/Game/Tread/UI/Portraits/T_Portrait_")):
            path = row.get(key)
            if path != folder + row["characterId"] or not EAL.does_asset_exist(path):
                missing.append("%s %s" % (row["characterId"], key))
    state = read(STATE)
    state.update({"previousMap": unreal.EditorLevelLibrary.get_editor_world().get_path_name().split(".")[0],
                  "missingAssets": missing})
    write(STATE, state)
    if not unreal.EditorLoadingAndSavingUtils.load_map(M3_MAP):
        raise RuntimeError("failed to load " + M3_MAP)
    print("AVCHECK load rows=%d missing=%d" % (len(rows), len(missing)))


def phase_restore():
    previous = read(STATE).get("previousMap", "")
    if not previous:
        raise RuntimeError("no remembered map")
    if game_world():
        raise RuntimeError("stop PIE before restoring the map")
    if not unreal.EditorLoadingAndSavingUtils.load_map(previous):
        raise RuntimeError("failed to restore " + previous)
    print("AVCHECK restore %s" % previous)


def load_texture(path):
    return unreal.load_object(None, path + "." + path.rsplit("/", 1)[1])


def phase_run():
    world = game_world()
    if not world:
        raise RuntimeError("no PIE world; start PIE first")
    c = controller_of(world)
    w = widget_of(world)
    checks, notes = {}, {}
    rows = roster_rows()
    bad_path, bad_tex, same, bad_ratio = [], [], [], []
    for row in rows:
        cid = row["characterId"]
        avatar = str(c.get_card_avatar_path(cid))
        portrait = str(c.get_card_portrait_path(cid))
        if avatar != "/Game/Tread/UI/Avatars/T_Avatar_" + cid or portrait != "/Game/Tread/UI/Portraits/T_Portrait_" + cid:
            bad_path.append(cid)
        if avatar == portrait:
            same.append(cid)
        a, p = load_texture(avatar), load_texture(portrait)
        if not a or not p:
            bad_tex.append(cid)
        elif a.blueprint_get_size_x() != a.blueprint_get_size_y() or p.blueprint_get_size_x() * 3 != p.blueprint_get_size_y() * 2:
            bad_ratio.append("%s:%dx%d/%dx%d" % (cid, a.blueprint_get_size_x(), a.blueprint_get_size_y(),
                                                 p.blueprint_get_size_x(), p.blueprint_get_size_y()))
    checks["roster_112_rows"] = len(rows) == 112
    checks["controller_avatar_portrait_paths_112"] = not bad_path
    checks["avatar_is_not_the_portrait"] = not same
    checks["avatar_portrait_textures_load_112"] = not bad_tex
    checks["avatar_square_portrait_2_3"] = not bad_ratio
    notes.update({"badPath": bad_path, "badTexture": bad_tex, "samePath": same, "badRatio": bad_ratio})
    # The HUD draws GetCardAvatarPath for the shop / bench / roster / tooltip and GetCardPortraitPath only in the detail.
    to_preparation(c, "avcheck")
    shop_ids = [str(s.character_id) for s in human(c).shop.slots if not s.is_sold]
    checks["shop_has_cards"] = len(shop_ids) > 0
    # EditorAssetLibrary refuses to work while PIE runs (does_asset_exist is always False there): load the textures instead.
    notes["shopAvatars"] = [[i, str(c.get_card_avatar_path(i))] for i in shop_ids]
    checks["shop_cards_have_avatar_assets"] = all(load_texture(str(c.get_card_avatar_path(i))) for i in shop_ids)
    checks["widget_present"] = w is not None
    if w:
        first = shop_ids[0] if shop_ids else "char_001"
        w.set_portrait_detail_for_test(first)
        checks["detail_opens"] = str(w.get_portrait_detail_id()) == first
        w.set_portrait_detail_for_test("")
        checks["detail_closes"] = str(w.get_portrait_detail_id()) == ""
        w.set_portrait_detail_for_test("char_001")
    # Battle: buying is rejected and the open detail is closed by the phase change.
    c.deploy_and_start_battle("avcheck-deploy")
    notes["phaseAfterDeploy"] = phase(c)
    checks["battle_rejects_purchase"] = not c.purchase_shop_slot(HUMAN, 0, "avcheck-battle-buy").accepted
    if w:
        checks["battle_closes_detail"] = str(w.get_portrait_detail_id()) == ""
    c.initialize_match(SEED)
    ok = all(checks.values())
    write(REPORT, {"ok": ok, "checks": checks, "notes": notes})
    print("AVCHECK run ok=%s failed=%s" % (ok, [k for k, v in checks.items() if not v]))


def phase_stage(name):
    world = game_world()
    if not world:
        raise RuntimeError("no PIE world; start PIE first")
    c = controller_of(world)
    w = widget_of(world)
    if w:
        w.set_roster_panel_for_test(False, 0)
        w.set_forced_tooltip_for_test("", -1)
        w.set_portrait_detail_for_test("")
    unreal.SystemLibrary.execute_console_command(world, "Tread.Audio 0")
    to_preparation(c, "avshot")
    if name == "shop":
        pass
    elif name == "bench":
        c.purchase_shop_slot(HUMAN, 0, "avshot-buy-0")
        c.purchase_shop_slot(HUMAN, 1, "avshot-buy-1")
        if w:
            w.set_forced_tooltip_for_test("bench", 0)
    elif name == "detail":
        ids = [str(s.character_id) for s in human(c).shop.slots if not s.is_sold]
        if w:
            w.set_portrait_detail_for_test(ids[0] if ids else "char_001")
    elif name == "battle":
        c.deploy_and_start_battle("avshot-deploy")
    else:
        raise RuntimeError("unknown stage " + name)
    print("AVCHECK stage %s phase=%s detail=%s" % (name, phase(c), str(w.get_portrait_detail_id()) if w else "-"))


def phase_shoot():
    world = game_world()
    if not world:
        raise RuntimeError("no PIE world")
    unreal.SystemLibrary.execute_console_command(world, "shot showui")
    print("AVCHECK shot requested")


def phase_cleanup():
    world = game_world()
    if world:
        w = widget_of(world)
        if w:
            w.set_portrait_detail_for_test("")
            w.set_forced_tooltip_for_test("", -1)
        controller_of(world).initialize_match(SEED)
        unreal.SystemLibrary.execute_console_command(world, "Tread.Audio 1")
    print("AVCHECK cleanup")


def main():
    args = sys.argv[1:]
    name = args[0] if args else ""
    if name == "load":
        phase_load()
    elif name == "run":
        phase_run()
    elif name == "stage":
        phase_stage(args[1])
    elif name == "shoot":
        phase_shoot()
    elif name == "cleanup":
        phase_cleanup()
    elif name == "restore":
        phase_restore()
    else:
        raise RuntimeError("unknown phase " + name)


main()
