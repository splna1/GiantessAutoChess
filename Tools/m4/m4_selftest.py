"""M4 acceptance (editor-side, Tools/ue_run.py), phase by phase; driven by Tools/m4/m4_selftest_pie.py.

  load            guard dirty packages, check every M4 content asset exists, load M3_Paris_Match
  run             (PIE) roster / item / clone / campaign / leader checks -> Saved/Reports/M4_SelfTest.json
  stage <name>    (PIE) put the match into the state an evidence shot needs:
                    campaign  R0 briefing, stages 1-3 conquered, stage 4 selected
                    roster    preparation with the roster audit panel open (page 1)
                    items     preparation with equipment in the inventory, a 画卷 copy, an item tooltip
                    tooltip   preparation with a shop card tooltip
                    world     stage 16 won: the world domination ending
  shoot           (PIE) "shot showui" (game viewport with the UMG HUD)
  cleanup         (PIE) back to a free match with audio on (the host driver restores the campaign save file)
  restore         reload the map that load remembered

Every phase is its own remote call (memory: tread-editor-python-map-switch).
"""
import json
import os
import sys

import unreal

PROJECT = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
REPORTS = os.path.join(PROJECT, "Saved", "Reports")
STATE = os.path.join(REPORTS, "M4_SelfTest_state.json")
REPORT = os.path.join(REPORTS, "M4_SelfTest.json")
ROSTER = os.path.join(PROJECT, "Content", "Data", "Generated", "CharacterRosterMap.json")
M3_MAP = "/Game/Tread/Maps/M3_Paris_Match"
HUMAN = "P0"
SEED = 20261014


def read(path):
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def write(path, doc):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(doc, handle, ensure_ascii=False, indent=1)


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


def phase(controller):
    return controller.get_phase().name


def human(controller):
    for p in controller.match_state.players:
        if str(p.player_id) == HUMAN:
            return p
    raise RuntimeError("no human player")


def finish_bp(controller, tag):
    if phase(controller).endswith("R0_BRIEFING"):
        controller.begin_pre_match_bp(tag + "-bp")
    if phase(controller).endswith("PRE_MATCH_BP"):
        available = [str(s) for s in controller.match_state.bp.available_strategy_ids]
        if available:
            controller.choose_player_strategy(available[0], tag + "-strategy")
        for pick in range(3):
            controller.run_next_ai_pick("%s-ai-%d" % (tag, pick))
        controller.confirm_pre_match_bp(tag + "-confirm")
    if not phase(controller).endswith("PREPARATION"):
        controller.begin_preparation(tag + "-prep")
    return phase(controller)


# ------------------------------------------------------------------------------------------------ load / restore
def phase_load():
    if game_world():
        raise RuntimeError("a PIE session is already running")
    dirty = (unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
             + unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages())
    if dirty:
        raise RuntimeError("dirty packages present, refusing to switch map: %s" % [p.get_name() for p in dirty])
    roster = read(ROSTER)
    missing = []
    for row in roster.get("characters", []):
        for path in [row["meshAsset"]] + ([row["portraitAsset"]] if row.get("portraitAsset") else []) + row["voiceAssets"]:
            if not unreal.EditorAssetLibrary.does_asset_exist(path):
                missing.append(path)
    for path in list(roster.get("sfx", {}).values()) + list(roster.get("bgm", {}).values()):
        if not unreal.EditorAssetLibrary.does_asset_exist(path):
            missing.append(path)
    state = read(STATE)
    state.update({"previousMap": unreal.EditorLevelLibrary.get_editor_world().get_path_name().split(".")[0],
                  "missingAssets": missing, "assetsChecked": True})
    write(STATE, state)
    if not unreal.EditorLoadingAndSavingUtils.load_map(M3_MAP):
        raise RuntimeError("failed to load " + M3_MAP)
    print("M4TEST load missingAssets=%d" % len(missing))


def phase_restore():
    previous = read(STATE).get("previousMap", "")
    if not previous:
        raise RuntimeError("no remembered map")
    if game_world():
        raise RuntimeError("stop PIE before restoring the map")
    if not unreal.EditorLoadingAndSavingUtils.load_map(previous):
        raise RuntimeError("failed to restore " + previous)
    print("M4TEST restore %s" % previous)


# ------------------------------------------------------------------------------------------------ run
def strong_ids(count=8):
    """Highest-tier roster characters: stocked on the human board so the campaign run survives to R12."""
    order = {"VI": 6, "V": 5, "IV": 4, "III": 3, "II": 2, "I": 1}
    rows = sorted(read(ROSTER).get("characters", []), key=lambda r: (-order.get(r.get("operatorTier"), 0), r["characterId"]))
    return [r["characterId"] for r in rows[:count]]


def fresh_match(c, stage, tag):
    """Restart in the R0 briefing with the given campaign stage (0 = free match).

    InitializeMatch keeps the pending stage of the previous match, so the stage is always selected after it."""
    c.initialize_match(SEED)
    result = c.select_campaign_stage(stage, tag)
    return bool(result.accepted)


def run_items(c, checks, notes):
    fresh_match(c, 0, "m4-free")
    finish_bp(c, "m4items")
    p = human(c)
    bench = [u for u in p.bench_units]
    board = [u for u in p.board_units]
    unit = (bench or board)[0]
    uid = str(unit.unit_instance_id)
    before = c.get_unit_combat_summary(HUMAN, uid)
    funds0 = human(c).funds
    ok_coin = c.grant_item_for_test(HUMAN, "chess_item_1_03_e_a") and c.equip_item(HUMAN, "chess_item_1_03_e_a", uid, "m4-coin").accepted
    funds1 = human(c).funds
    ok_hammer = c.grant_item_for_test(HUMAN, "chess_item_1_01_e_a") and c.equip_item(HUMAN, "chess_item_1_01_e_a", uid, "m4-hammer").accepted
    after = c.get_unit_combat_summary(HUMAN, uid)
    ok_docs = c.grant_item_for_test(HUMAN, "chess_item_6_08_e_a") and c.equip_item(HUMAN, "chess_item_6_08_e_a", uid, "m4-docs").accepted
    limit = human(c).population_limit
    bench_before = len(human(c).bench_units)
    ok_scroll = c.grant_item_for_test(HUMAN, "chess_item_6_02_m") and c.equip_item(HUMAN, "chess_item_6_02_m", uid, "m4-scroll").accepted
    clones = [u for u in human(c).bench_units if u.is_transform_clone]
    ok_bounty_rejected = c.grant_item_for_test(HUMAN, "chess_item_6_03_m") and not c.equip_item(HUMAN, "chess_item_6_03_m", uid, "m4-bounty").accepted
    attack = lambda s: float(s.split("attack=")[1].split()[0]) if "attack=" in s else 0.0
    checks["item_coin_gives_one_fund"] = bool(ok_coin) and funds1 == funds0 + 1
    checks["item_hammer_attack_plus_15pct"] = bool(ok_hammer) and abs(attack(after) - attack(before) - 0.15) < 0.011
    checks["item_hr_docs_population_9"] = bool(ok_docs) and limit >= 9
    checks["spell_scroll_copies_unit_as_clone"] = bool(ok_scroll) and len(human(c).bench_units) == bench_before + 1 and len(clones) >= 1
    checks["spell_bounty_disabled"] = bool(ok_bounty_rejected)
    notes["items"] = {"combatBefore": before, "combatAfter": after, "funds": [funds0, funds1], "populationLimit": limit,
                      "clones": [str(u.copy_source_character_id) for u in clones]}


def run_campaign(c, checks, notes):
    c.set_campaign_progress_for_test(0)
    stages = c.get_campaign_stages()
    checks["campaign_16_stages"] = len(stages) == 16
    checks["campaign_only_stage1_unlocked"] = [s.unlocked for s in stages][:3] == [True, False, False]
    c.initialize_match(SEED)  # stages are chosen in the R0 briefing; run_items left a match in progress
    checks["campaign_locked_stage_rejected"] = not c.select_campaign_stage(2, "m4-locked").accepted
    ok = c.select_campaign_stage(1, "m4-stage1").accepted
    checks["campaign_stage1_selected"] = bool(ok) and c.match_state.campaign_stage == 1
    finish_bp(c, "m4camp")
    stocked = strong_ids(12)
    strong = False
    rounds = []
    for r in range(1, 13):
        if not phase(c).endswith("PREPARATION"):
            break
        # The starter board dies around R11, a strong board from R1 eliminates everyone by R7: switch to the strong
        # board only once the human is low, so the match (and the AI players) survive to the R12 data leader.
        if (strong or human(c).health < 50) and len(list(human(c).board_units)) < len(stocked):
            strong = c.stock_board_for_fixture(HUMAN, stocked) or strong
        c.deploy_and_start_battle("m4camp-deploy-%d" % r)
        st = c.match_state
        rounds.append({"round": st.round_index, "type": st.round_type.name,
                       "pairings": [[str(p.player_id), str(p.opponent_id)] for p in st.last_battle_result.pairings],
                       "opponent": str(st.scripted_opponent_name), "opponentUnits": len(st.scripted_opponent_units),
                       "leaderHealthBefore": st.scripted_opponent_health})
        c.resolve_battle("m4camp-resolve-%d" % r)
        st = c.match_state
        rounds[-1].update({"outcomes": [[str(o.player_id), str(o.outcome), o.health_before, o.health_after]
                                        for o in st.last_battle_result.outcomes],
                           "leaderHealthAfter": st.scripted_opponent_health})
        c.settle_round("m4camp-settle-%d" % r)
        c.advance_to_next_round("m4camp-next-%d" % r)
        if phase(c).endswith("GAME_OVER"):
            break
    scripted = lambda r: r["pairings"] and all(p[1] == "SCRIPTED" for p in r["pairings"])
    by_round = {r["round"]: r for r in rounds}
    checks["campaign_r1_r2_garrison"] = all(scripted(by_round[n]) and "守军" in by_round[n]["opponent"] for n in (1, 2) if n in by_round) and 1 in by_round
    checks["campaign_r3_pvp"] = 3 in by_round and not scripted(by_round[3])
    last = rounds[-1] if rounds else {}
    reached_r12 = 12 in by_round
    checks["campaign_r12_leader_from_data"] = (not reached_r12) or (scripted(by_round[12]) and "领袖" in by_round[12]["opponent"]
                                                                    and by_round[12]["opponentUnits"] >= 5)
    result = str(c.match_state.campaign_result)
    checks["campaign_result_recorded"] = phase(c).endswith("GAME_OVER") and result in ("Conquered", "Failed")
    checks["campaign_reached_r12"] = reached_r12
    notes["campaignRun"] = {"rounds": rounds, "result": result, "reachedR12": reached_r12, "stocked": stocked}

    # Win stage 1 -> stage 2 unlocks; a loss leaves the progress alone.
    c.set_campaign_progress_for_test(0)
    fresh_match(c, 1, "m4-stage1b")
    won = c.finish_campaign_for_test(True)
    stages = c.get_campaign_stages()
    checks["campaign_win_unlocks_next"] = won == "Conquered" and stages[0].conquered and stages[1].unlocked
    fresh_match(c, 1, "m4-stage1c")
    lost = c.finish_campaign_for_test(False)
    checks["campaign_loss_no_penalty"] = lost == "Failed" and c.get_campaign_stages()[0].conquered

    # Stage modifiers: stage 6 (初始金币-2, 备战时间-5秒).
    c.set_campaign_progress_for_test(5)
    fresh_match(c, 0, "m4-free3")
    free_funds = human(c).funds
    free_prep = c.match_state.rules.preparation_duration_sec
    c.select_campaign_stage(6, "m4-stage6")
    checks["campaign_stage6_modifiers"] = (c.match_state.campaign_stage == 6 and human(c).funds == max(0, free_funds - 2)
                                           and c.match_state.rules.preparation_duration_sec == free_prep - 5)
    # Stage 8: AI base health +15.
    c.set_campaign_progress_for_test(7)
    c.select_campaign_stage(8, "m4-stage8")
    ai_health = [p.health for p in c.match_state.players if str(p.player_id) != HUMAN]
    checks["campaign_stage8_ai_health"] = all(h == 115 for h in ai_health)
    # Stage 16 conquered -> world domination.
    c.set_campaign_progress_for_test(15)
    c.select_campaign_stage(16, "m4-stage16")
    checks["campaign_world_domination"] = c.finish_campaign_for_test(True) == "WorldDomination"
    notes["modifiers"] = {"freeFunds": free_funds, "freePrep": free_prep, "aiHealthStage8": ai_health}


def phase_run():
    world = game_world()
    if not world:
        raise RuntimeError("no PIE world; start PIE first")
    c = controller_of(world)
    state = read(STATE)
    checks, notes = {}, {}
    ids = [str(i) for i in c.get_roster_character_ids()]
    portraits = [c.get_card_portrait_path(i) for i in ids]
    checks["roster_112_cards"] = len(ids) == 112
    # 100 lihui + 12 mmd_12 detail portraits (document/154).
    checks["roster_112_portraits"] = sum(1 for p in portraits if p) == 112
    checks["roster_model_names"] = all(c.get_card_model_name(i) for i in ids)
    checks["content_assets_exist"] = state.get("assetsChecked") and not state.get("missingAssets")
    checks["audio_paths"] = all(c.get_sfx_asset_path(k) for k in ("purchase", "round_start", "victory", "defeat")) and \
        all(c.get_bgm_asset_path(k) for k in ("battle", "menu"))
    muelsyse = [i for i in ids if c.get_card_display_name(i) == "缪尔赛思"]
    checks["muelsyse_on_modernia_model"] = muelsyse == ["char_070"] and c.get_card_model_name("char_070") == "缪尔赛思"
    run_items(c, checks, notes)
    run_campaign(c, checks, notes)
    doc = {"schema": "Tread.M4.SelfTest.v1", "ok": all(bool(v) for v in checks.values()), "checks": checks, "notes": notes,
           "pactDataVersion": str(c.match_state.pact_data_version)}
    write(REPORT, doc)
    print("M4TEST run ok=%s failed=%s" % (doc["ok"], [k for k, v in checks.items() if not v]))


# ------------------------------------------------------------------------------------------------ evidence stages
def phase_stage(name):
    world = game_world()
    if not world:
        raise RuntimeError("no PIE world; start PIE first")
    c = controller_of(world)
    w = widget_of(world)
    if w:
        w.set_roster_panel_for_test(False, 0)
        w.set_forced_tooltip_for_test("", -1)
    unreal.SystemLibrary.execute_console_command(world, "Tread.Audio 0")
    if name == "campaign":
        c.set_campaign_progress_for_test(3)
        fresh_match(c, 4, "m4shot-stage4")
        # The front end (doc 157) covers the old R0 campaign map: jump it to the 16-stage select screen so the
        # evidence picture shows the new campaign UI. Without a front end the original R0 view is kept.
        try:
            mode = unreal.GameplayStatics.get_game_mode(world)
            fe = getattr(mode, "front_end_widget", None) if mode else None
            if fe:
                fe.jump_to_screen_for_test("select")
                fe.select_stage_for_test(4)
                print("M4TEST front end jumped to select screen=%s" % fe.get_screen_name())
        except Exception as exc:
            print("M4TEST front end jump skipped: %s" % exc)
    elif name in ("roster", "items", "tooltip"):
        c.set_campaign_progress_for_test(0)
        fresh_match(c, 0, "m4shot-free")
        finish_bp(c, "m4shot")
        if name == "roster" and w:
            w.set_roster_panel_for_test(True, 0)
        elif name == "items":
            p = human(c)
            uid = str((list(p.bench_units) or list(p.board_units))[0].unit_instance_id)
            c.grant_item_for_test(HUMAN, "chess_item_6_02_m")
            c.equip_item(HUMAN, "chess_item_6_02_m", uid, "m4shot-scroll")
            for item in ("chess_item_1_01_e_a", "chess_item_3_10_e_a", "chess_item_4_02_e_a", "chess_item_5_09_e_a",
                         "chess_item_6_09_e_a", "chess_item_3_02_e_a"):
                c.grant_item_for_test(HUMAN, item)
            if w:
                w.set_forced_tooltip_for_test("item", 1)
        elif name == "tooltip" and w:
            # A 2-star bench unit: the tooltip shows the elite stats and elite trait texts.
            bench = list(human(c).bench_units)
            if bench and c.set_unit_star_for_test(HUMAN, str(bench[0].unit_instance_id), 2):
                w.set_forced_tooltip_for_test("bench", 0)
            else:
                w.set_forced_tooltip_for_test("shop", 0)
    elif name == "world":
        c.set_campaign_progress_for_test(15)
        fresh_match(c, 16, "m4shot-stage16")
        c.finish_campaign_for_test(True)
    else:
        raise RuntimeError("unknown stage " + name)
    print("M4TEST stage %s phase=%s campaign=%d" % (name, phase(c), c.match_state.campaign_stage))


def phase_shoot():
    world = game_world()
    if not world:
        raise RuntimeError("no PIE world")
    unreal.SystemLibrary.execute_console_command(world, "shot showui")
    print("M4TEST shot requested")


def phase_cleanup():
    # The campaign save itself is backed up and restored by the host driver (Saved/SaveGames/TreadCampaign.sav).
    world = game_world()
    if world:
        c = controller_of(world)
        fresh_match(c, 0, "m4-cleanup")
        unreal.SystemLibrary.execute_console_command(world, "Tread.Audio 1")
    print("M4TEST cleanup")


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
        raise RuntimeError("phase must be load|run|stage <name>|shoot|cleanup|restore")


main()
