"""Validate native, PIE, standalone-game and screenshot evidence; fail closed."""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "Saved" / "Reports"
SCREENSHOTS = ROOT / "Saved" / "Screenshots"
POOL_TOTALS = {"I": 12, "II": 14, "III": 18, "IV": 16, "V": 8, "VI": 5}
TARGET_RESOLUTION = (1920, 1080)
STAGES = ("BP", "Preparation", "Scout", "Battle", "Result")
FULL_GAME_STAGES = STAGES + ("BP_Revised", "Scout_Player_0", "Scout_Player_1",
                             "Scout_Player_2", "Round_2_Result", "GameOver")
FULL12_STAGES = ("Round_3_PvP", "Round_12_Leader", "GameOver")
PROMOTED_SCREENSHOTS = {
    "BP": "M1_PreMatch_BP_4Players.png",
    "Scout": "M1_Scout_Roster_4Players.png",
    "Preparation": "M1_Prepare_Shop_Deploy.png",
    "Result": "M1_Battle_Result.png",
}
REQUIRED_UI_CHECKS = {
    "initial_menu", "menu_click_opens_bp", "bp_card_selects_strategy",
    "confirm_ai_1", "two_ai_confirmed_before_revision", "bp_revision_candidate_available",
    "bp_revised_before_final_ai", "confirm_ai_3", "bp_confirm_enters_preparation",
    "bench_to_board_release", "board_swap", "board_to_bench_release",
    "illegal_enemy_half_returns_source", "illegal_outside_returns_source",
    "sell_release_once", "duplicate_release_does_not_sell_twice",
    "shop_has_affordable_card", "shop_purchase_click", "lock_shop_click",
    "unlock_shop_click", "refresh_shop_click", "experience_click",
    "scout_player_0_read_only", "scout_player_1_read_only",
    "scout_player_2_read_only", "scout_player_3_read_only",
    "scout_blocks_drag", "close_scout_click",
    "deploy_click_starts_battle", "natural_battle_reaches_settlement",
    "continue_click_starts_next_round",
}


def read(name: str) -> dict:
    try:
        raw = (REPORTS / name).read_bytes()
        encoding = "utf-16" if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8-sig"
        value = json.loads(raw.decode(encoding))
        return value if isinstance(value, dict) else {}
    except (OSError, UnicodeError, ValueError):
        return {}


def write(name: str, value: dict) -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def native_match_checks(match: dict) -> dict[str, bool]:
    steps = match.get("stepResults", [])
    rounds = match.get("acceptedRounds", [])
    named_checks = match.get("namedChecks", {})
    return {
        "nativeSchema": match.get("schema") == "Tread.M1.MatchSelfTest.v2"
        and match.get("producer") == "Tread C++ RunDeterministicSelfTest",
        "ok": match.get("ok") is True,
        "fourParticipants": match.get("players") == 4,
        "settledTwelveRounds": match.get("roundsCompleted") == 12,
        "twelveAcceptedRounds": isinstance(rounds, list) and rounds == list(range(1, 13))
        and all(type(round_index) is int for round_index in rounds),
        "canonicalRoundTypes": match.get("acceptedRoundTypes") == ["PvE", "PvE"] + ["PvP"] * 9 + ["Leader"],
        "gameOver": match.get("gameOver") is True,
        "idempotency": match.get("requestIdempotency") is True
        and type(match.get("processedRequestCount")) is int and match["processedRequestCount"] > 0,
        "replay": match.get("sameSeedReplayEqual") is True
        and bool(re.fullmatch(r"[0-9a-fA-F]{8}", str(match.get("replaySignatureCrc32", "")))),
        "allNativeStepsPassed": isinstance(steps, list) and bool(steps) and all(step is True for step in steps),
        "allNamedChecksPassed": isinstance(named_checks, dict) and bool(named_checks)
        and all(value is True for value in named_checks.values()),
    }


def bp_checks(bp: dict) -> dict[str, bool]:
    banned, available, chosen = (bp.get(name, []) for name in ("banned", "available", "chosen"))
    if not all(isinstance(ids, list) and all(isinstance(item, str) and item for item in ids)
               for ids in (banned, available, chosen)):
        return {"validStrategyIds": False}
    return {
        "fourUniqueBans": len(banned) == len(set(banned)) == 4,
        "twentyEightUniqueOffers": len(available) == len(set(available)) == 28,
        "thirtyTwoDisjointStrategies": not (set(banned) & set(available))
        and len(set(banned) | set(available)) == 32,
        "fourUniqueAvailablePicks": len(chosen) == len(set(chosen)) == 4 and set(chosen) <= set(available),
    }


def ui_smoke_checks(report: dict, world_type: str) -> dict[str, bool]:
    rows = report.get("checks")
    rows = rows if isinstance(rows, list) else []
    valid_rows = bool(rows) and all(
        isinstance(row, dict) and isinstance(row.get("name"), str)
        and row.get("passed") is True for row in rows
    )
    names = {row["name"] for row in rows
             if isinstance(row, dict) and isinstance(row.get("name"), str)}
    inputs = report.get("inputs")
    inputs = inputs if isinstance(inputs, list) else []
    events = {item.get("event") for item in inputs if isinstance(item, dict)}
    return {
        "passed": report.get("passed") is True,
        "worldType": report.get("worldType") == world_type,
        "allChecksPassed": valid_rows,
        "requiredInteractions": REQUIRED_UI_CHECKS <= names,
        "slateMouseInputs": str(report.get("inputPath", "")).startswith("Live FSlateApplication mouse events")
        and {"Move", "Down", "Up"} <= events
        and any(isinstance(item, dict) and item.get("event") == "Down" and item.get("handled") is True
                for item in inputs)
        and any(isinstance(item, dict) and item.get("event") == "Up" and item.get("handled") is True
                for item in inputs),
    }


def image_dimensions(path: Path) -> tuple[int, int] | None:
    from PIL import Image

    try:
        with Image.open(path) as image:
            size = image.size
            image.verify()
        return size
    except (OSError, ValueError):
        return None


def sha256_file(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def reported_screenshot_sources(
    report: dict, report_stem: str, required_stages: tuple[str, ...], written_check: str,
) -> tuple[dict[str, Path], list[dict], dict[str, bool]]:
    raw_paths = report.get("screenshots")
    raw_paths = raw_paths if isinstance(raw_paths, list) else []
    source_dir = (REPORTS / report_stem).resolve()
    valid_paths = len(raw_paths) >= len(required_stages) and all(isinstance(raw, str) and raw for raw in raw_paths)
    sources: dict[str, Path] = {}
    source_rows = []
    for raw in raw_paths:
        if not isinstance(raw, str) or not raw:
            valid_paths = False
            continue
        try:
            path = Path(raw)
            resolved = path.resolve()
        except (OSError, ValueError):
            valid_paths = False
            continue
        stage = path.stem
        valid_location = path.is_absolute() and resolved.parent.parent == source_dir
        if (not re.fullmatch(r"[A-Za-z0-9_]+", stage) or path.suffix.lower() != ".png"
                or stage in sources or not valid_location):
            valid_paths = False
            continue
        sources[stage] = resolved
        dimensions = image_dimensions(resolved)
        source_rows.append({
            "stage": stage, "path": str(resolved), "exists": resolved.is_file(),
            "width": dimensions[0] if dimensions else None,
            "height": dimensions[1] if dimensions else None,
            "atTargetResolution": dimensions == TARGET_RESOLUTION,
            "sha256": sha256_file(resolved),
        })
    valid_paths = (valid_paths and set(required_stages) <= set(sources) and len(sources) == len(raw_paths)
                   and len({p.parent for p in sources.values()}) == 1)
    written_rows = report.get("checks")
    written_rows = written_rows if isinstance(written_rows, list) else []
    written = [row.get("detail") for row in written_rows
               if isinstance(row, dict) and row.get("name") == written_check
               and row.get("passed") is True and isinstance(row.get("detail"), str)]
    try:
        written_paths = {str(Path(raw).resolve()) for raw in written}
    except (OSError, ValueError):
        written_paths = set()
    checks = {
        "coreStagePathsFromOneRun": valid_paths,
        "allScreenshotWriteChecks": len(written) == len(raw_paths)
        and len(set(written)) == len(raw_paths)
        and written_paths == set(map(str, sources.values())),
        "allSourceScreenshotsAtTargetResolution": valid_paths and len(source_rows) == len(raw_paths)
        and all(row["atTargetResolution"] and row["sha256"] for row in source_rows),
    }
    return sources, source_rows, checks


def game_screenshot_sources(report: dict) -> tuple[dict[str, Path], list[dict], dict[str, bool]]:
    return reported_screenshot_sources(report, "M1_UI_Smoke", STAGES, "screenshot_written")


def full_game_checks(report: dict) -> dict[str, bool]:
    ui = ui_smoke_checks(report, "Game")
    rows = report.get("checks") if isinstance(report.get("checks"), list) else []
    check_names = [row.get("name") for row in rows if isinstance(row, dict)]
    names = set(name for name in check_names if isinstance(name, str))
    rounds = report.get("rounds") if isinstance(report.get("rounds"), list) else []
    ranking = report.get("finalRanking") if isinstance(report.get("finalRanking"), dict) else {}
    players = ranking.get("rankedPlayers") if isinstance(ranking.get("rankedPlayers"), list) else []
    timer = report.get("roundTwoAutoPreparationSeconds")
    inputs = report.get("inputs") if isinstance(report.get("inputs"), list) else []
    expected_types = ["ETreadM1RoundType::PvE"] * 2 + ["ETreadM1RoundType::PvP"] * 4
    round_rows_ok = len(rounds) == 6 and all(
        isinstance(row, dict) and type(row.get("round")) is int and row["round"] == index
        and row.get("roundType") == expected_types[index - 1]
        and type(row.get("outcomes")) is int and row["outcomes"] == 4
        and type(row.get("pairings")) is int and row["pairings"] == 2
        for index, row in enumerate(rounds, 1)
    )
    required_round_checks = {f"round_{number}_result" for number in range(1, 7)}
    required_round_checks |= {f"round_{number}_preparation" for number in range(3, 7)}
    required_round_checks |= {f"round_{number}_deploy_button" for number in range(3, 7)}
    required_round_checks |= {f"round_{number}_continue_button_visible" for number in range(2, 6)}
    required_round_checks |= {f"round_{number}_continue" for number in range(3, 6)}
    required_round_checks |= {"round_2_preparation_timer_auto_deploy", "round_3_after_continue",
                              "natural_game_over", "four_final_ranks", "final_ranking_modal_visible"}
    ordered_results = [check_names.index(f"round_{number}_result")
                       for number in range(1, 7) if f"round_{number}_result" in names]
    round_check_sequence = [
        "round_1_result", "round_2_preparation_timer_auto_deploy",
        "battle_rejects_mouse_drag", "battle_rejects_shop_click",
        "round_2_result", "round_2_continue_button_visible", "round_3_after_continue",
    ]
    for number in range(3, 7):
        round_check_sequence.extend(f"round_{number}_{suffix}"
                                    for suffix in ("preparation", "deploy_button", "result"))
        if number < 6:
            round_check_sequence.extend(f"round_{number}_{suffix}"
                                        for suffix in ("continue_button_visible", "continue"))
    round_check_sequence.extend(("round_6_continue_button_visible", "natural_game_over"))
    sequence_positions = [check_names.index(name) for name in round_check_sequence if name in names]
    ranked_players_ok = len(players) == 4 and all(
        isinstance(player, dict) and isinstance(player.get("playerId"), str)
        and player["playerId"] and isinstance(player.get("displayName"), str)
        and player["displayName"] and type(player.get("rank")) is int
        and type(player.get("health")) is int and type(player.get("eliminated")) is bool
        for player in players
    )
    return {
        "passedGameMouseRun": all(ui.values()) and report.get("mode") == "fullGame",
        "substantialSlateTrace": len(rows) >= 70 and len(inputs) >= 100,
        "targetViewport": type(report.get("viewportWidth")) is int
        and type(report.get("viewportHeight")) is int
        and (report["viewportWidth"], report["viewportHeight"]) == TARGET_RESOLUTION,
        "naturalGameOverAtRoundSix": report.get("phase") == "ETreadM1Phase::GameOver"
        and type(report.get("round")) is int and report["round"] == 6,
        "continuousRoundResults": round_rows_ok and required_round_checks <= names
        and len(ordered_results) == 6 and ordered_results == sorted(ordered_results),
        "roundCheckOrder": len(sequence_positions) == len(round_check_sequence)
        and sequence_positions == sorted(sequence_positions),
        "naturalRoundTwoTimer": type(timer) in (int, float) and math.isfinite(timer)
        and 25.0 <= timer <= 35.0,
        "battleRejectsMouseActions": {"battle_rejects_mouse_drag", "battle_rejects_shop_click"} <= names,
        "fourUniqueFinalRanks": ranking.get("round") == 6 and ranking.get("lastRoundOutcomes") == 4
        and ranked_players_ok and {player["playerId"] for player in players} == {"P0", "P1", "P2", "P3"}
        and sorted(player["rank"] for player in players) == [1, 2, 3, 4],
    }


def full12_checks(report: dict) -> dict[str, bool]:
    ui = ui_smoke_checks(report, "Game")
    rows = report.get("checks") if isinstance(report.get("checks"), list) else []
    check_names = [row.get("name") for row in rows if isinstance(row, dict)]
    names = {name for name in check_names if isinstance(name, str)}
    rounds = report.get("rounds") if isinstance(report.get("rounds"), list) else []
    huds = report.get("roundHuds") if isinstance(report.get("roundHuds"), list) else []
    ranking = report.get("finalRanking") if isinstance(report.get("finalRanking"), dict) else {}
    players = ranking.get("rankedPlayers") if isinstance(ranking.get("rankedPlayers"), list) else []
    timer = report.get("roundTwoAutoPreparationSeconds")
    expected_types = ["ETreadM1RoundType::PvE"] * 2 + ["ETreadM1RoundType::PvP"] * 9
    expected_types.append("ETreadM1RoundType::Leader")
    rounds_ok = len(rounds) == 12 and all(
        isinstance(row, dict) and type(row.get("round")) is int and row["round"] == number
        and row.get("roundType") == expected_types[number - 1]
        and type(row.get("outcomes")) is int and row["outcomes"] == 4
        and type(row.get("pairings")) is int and row["pairings"] == 2
        for number, row in enumerate(rounds, 1)
    )
    huds_ok = len(huds) == 12 and all(
        isinstance(hud, dict) and type(hud.get("round")) is int and hud["round"] == number
        and hud.get("hudPhase") == "ETreadM1Phase::Preparation"
        and hud.get("hudRoundType") == expected_types[number - 1]
        and type(hud.get("timerRemainingSeconds")) in (int, float)
        and math.isfinite(hud["timerRemainingSeconds"])
        and 0 < hud["timerRemainingSeconds"] <= 35
        and hud.get("deployButtonVisible") is True
        and type(hud.get("viewportWidth")) is int and type(hud.get("viewportHeight")) is int
        and (hud["viewportWidth"], hud["viewportHeight"]) == TARGET_RESOLUTION
        for number, hud in enumerate(huds, 1)
    )
    battle_timers_ok = rounds_ok and all(
        type(row.get("battleElapsedSeconds")) in (int, float)
        and math.isfinite(row["battleElapsedSeconds"])
        and 38.0 <= row["battleElapsedSeconds"] <= 55.0
        for row in rounds
    )
    required_checks = {f"round_{number}_result" for number in range(1, 13)}
    required_checks |= {f"round_{number}_45s_battle_timer" for number in range(1, 13)}
    required_checks |= {f"round_{number}_preparation_hud" for number in range(1, 13)}
    required_checks |= {f"round_{number}_preparation" for number in range(3, 13)}
    required_checks |= {f"round_{number}_deploy_button" for number in range(3, 13)}
    required_checks |= {f"round_{number}_continue_button_visible" for number in range(2, 13)}
    required_checks |= {f"round_{number}_continue" for number in range(3, 12)}
    required_checks |= {
        "full12_fixture_four_players", "round_2_preparation_timer_auto_deploy",
        "battle_rejects_mouse_drag", "battle_rejects_shop_click",
        "full12_no_early_game_over", "full12_leader_game_over",
        "full12_final_viewport_1920x1080", "natural_game_over",
        "four_final_ranks", "final_ranking_modal_visible",
    }
    result_positions = [check_names.index(f"round_{number}_result")
                        for number in range(1, 13) if f"round_{number}_result" in names]
    hud_positions = [check_names.index(f"round_{number}_preparation_hud")
                     for number in range(1, 13) if f"round_{number}_preparation_hud" in names]
    ordered_checks = (len(result_positions) == len(hud_positions) == 12
                      and result_positions == sorted(result_positions)
                      and hud_positions == sorted(hud_positions)
                      and all(hud < result for hud, result in zip(hud_positions, result_positions)))
    ranked_players_ok = len(players) == 4 and all(
        isinstance(player, dict) and isinstance(player.get("playerId"), str)
        and player["playerId"] and isinstance(player.get("displayName"), str)
        and player["displayName"] and type(player.get("rank")) is int
        and type(player.get("health")) is int and type(player.get("eliminated")) is bool
        for player in players
    )
    return {
        "passedGameMouseRun": all(ui.values()) and report.get("mode") == "full12",
        "highHealthFixtureOnlyAtRoundOne": report.get("fixtureAppliedAtRound1") is True
        and type(report.get("fixturePlayerHealth")) is int and report["fixturePlayerHealth"] == 1000
        and isinstance(report.get("fixtureScope"), str)
        and "once after BP" in report["fixtureScope"],
        "targetViewport": type(report.get("viewportWidth")) is int
        and type(report.get("viewportHeight")) is int
        and (report["viewportWidth"], report["viewportHeight"]) == TARGET_RESOLUTION,
        "leaderGameOverAtRoundTwelve": report.get("phase") == "ETreadM1Phase::GameOver"
        and type(report.get("round")) is int and report["round"] == 12,
        "continuousRoundTypesAndResults": rounds_ok and required_checks <= names and ordered_checks,
        "allPreparationHuds": huds_ok,
        "allFortyFiveSecondBattles": battle_timers_ok,
        "naturalRoundTwoTimer": type(timer) in (int, float) and math.isfinite(timer)
        and 25.0 <= timer <= 35.0,
        "fourUniqueFinalRanks": ranking.get("round") == 12 and ranking.get("lastRoundOutcomes") == 4
        and ranked_players_ok and {player["playerId"] for player in players} == {"P0", "P1", "P2", "P3"}
        and sorted(player["rank"] for player in players) == [1, 2, 3, 4],
    }


def game_build_checks(report: dict) -> dict[str, bool]:
    binary = (ROOT / "Binaries" / "Win64" / "Tread.exe").resolve()
    build_log = (REPORTS / "M1_Game_Build.log").resolve()
    try:
        reported_binary = Path(report.get("binary", "")).resolve()
        reported_log = Path(report.get("buildLog", "")).resolve()
    except (OSError, TypeError, ValueError):
        reported_binary = reported_log = Path()
    digest = sha256_file(binary)
    try:
        binary_size = binary.stat().st_size
    except OSError:
        binary_size = None
    return {
        "schema": report.get("schema") == "Tread.M1.GameBuild.v1",
        "successfulTarget": report.get("ok") is True and report.get("target") == "Tread Win64 Development"
        and type(report.get("exitCode")) is int and report["exitCode"] == 0,
        "binaryPath": reported_binary == binary and binary.is_file(),
        "binarySize": type(report.get("binaryBytes")) is int and report["binaryBytes"] == binary_size
        and bool(binary_size),
        "binarySha256": isinstance(report.get("binarySha256"), str)
        and bool(re.fullmatch(r"[0-9a-fA-F]{64}", report["binarySha256"]))
        and report["binarySha256"].lower() == digest,
        "savedBuildLog": reported_log == build_log and build_log.is_file(),
    }


def main() -> int:
    match = read("M1_Match_SelfTest.json")
    match_checks = native_match_checks(match)
    native_ok = all(match_checks.values())
    bp = match.get("bp", {})
    bp = bp if isinstance(bp, dict) else {}
    bp_validation = bp_checks(bp)
    bp_ok = native_ok and all(bp_validation.values())
    write("M1_BP_32_4_Report.json", {
        "schema": "Tread.M1.PreMatchBP.32x4.Report.v1", "ok": bp_ok,
        "sourceReport": "M1_Match_SelfTest.json", "evidenceSource": "native C++ self-test",
        "seed": match.get("seed"), "bannedStrategyIds": bp.get("banned", []),
        "availableStrategyIds": bp.get("available", []), "chosenStrategyIds": bp.get("chosen", []),
        "checks": bp_validation,
        "missingNativeEvidence": "" if bp else "Native self-test did not record BP strategy IDs.",
    })

    ledger = read("M1_PoolLedger_Conservation.json")
    pool_checks = {
        "nativeSchema": ledger.get("schema") == "Tread.M1.PoolLedger.Conservation.v1",
        "conservation": ledger.get("ok") is True,
        "fourParticipants": ledger.get("participants") == 4,
        "tierTotals": ledger.get("tierTotals") == POOL_TOTALS,
        "nativeMatchAcceptance": native_ok,
        "nativeBP": bp_ok,
    }
    write("M1_PoolLedger_StrategyBP_Report.json", {
        "schema": "Tread.M1.PoolLedger.StrategyBP.Report.v1", "ok": all(pool_checks.values()),
        "seed": match.get("seed"), "participants": ledger.get("participants"),
        "tierTotals": ledger.get("tierTotals", {}), "ledger": ledger.get("ledger", {}),
        "sourceReport": "M1_PoolLedger_Conservation.json", "bpReport": "M1_BP_32_4_Report.json",
        "checks": pool_checks,
    })

    pie = read("M1_PIE_UI_Smoke.json")
    game = read("M1_UI_Smoke.json")
    pie_checks = ui_smoke_checks(pie, "PIE")
    game_checks = ui_smoke_checks(game, "Game")
    game_checks["targetViewport"] = (
        type(game.get("viewportWidth")) is int and type(game.get("viewportHeight")) is int
        and (game["viewportWidth"], game["viewportHeight"]) == TARGET_RESOLUTION
    )
    sources, source_rows, source_checks = game_screenshot_sources(game)
    full_game = read("M1_UI_FullGame.json")
    full_checks = full_game_checks(full_game)
    _, full_source_rows, full_source_checks = reported_screenshot_sources(
        full_game, "M1_UI_FullGame", FULL_GAME_STAGES, "full_game_screenshot_written"
    )
    full_source_checks["gameOverImageAtTargetResolution"] = any(
        row["stage"] == "GameOver" and row["atTargetResolution"] and row["sha256"]
        for row in full_source_rows
    )
    full12 = read("M1_UI_Full12.json")
    full12_validation = full12_checks(full12)
    _, full12_source_rows, full12_source_checks = reported_screenshot_sources(
        full12, "M1_UI_Full12", FULL12_STAGES, "full_game_screenshot_written"
    )
    full12_source_checks["threeMilestoneImagesAtTargetResolution"] = all(
        any(row["stage"] == stage and row["atTargetResolution"] and row["sha256"]
            for row in full12_source_rows)
        for stage in FULL12_STAGES
    )
    screenshot_rows = []
    for stage, name in PROMOTED_SCREENSHOTS.items():
        path = SCREENSHOTS / name
        source = sources.get(stage)
        dimensions = image_dimensions(path)
        source_hash = sha256_file(source) if source else None
        promoted_hash = sha256_file(path)
        screenshot_rows.append({
            "name": name, "stage": stage, "path": str(path),
            "sourcePath": str(source) if source else None,
            "exists": path.is_file(),
            "width": dimensions[0] if dimensions else None,
            "height": dimensions[1] if dimensions else None,
            "atTargetResolution": dimensions == TARGET_RESOLUTION,
            "sha256": promoted_hash,
            "sourceSha256": source_hash,
            "byteIdenticalToSource": bool(promoted_hash and source_hash and promoted_hash == source_hash),
        })

    required_reports = ["M1_Match_SelfTest.json", "M1_DataContract_Validation.json",
                        "M1_Economy_SelfTest.json", "M1_CloneInstance_SelfTest.json",
                        "M1_PoolLedger_Conservation.json", "M1_PoolLedger_StrategyBP_Report.json",
                        "M1_BP_32_4_Report.json", "M4_CharacterRosterMap_Audit.json"]
    report_checks = {name: read(name).get("ok") is True for name in required_reports}
    run = read("M1_Match_Run.json")
    build = read("M1_Game_Build.json")
    build_checks = game_build_checks(build)
    match_path = REPORTS / "M1_Match_SelfTest.json"
    native_hash = hashlib.sha256(match_path.read_bytes()).hexdigest() if match_path.is_file() else None
    runner_checks = run.get("checks") if isinstance(run.get("checks"), dict) else {}
    runner_ok = (run.get("schema") == "Tread.M1.MatchRun.v1" and run.get("ok") is True
                 and run.get("buildExitCode") == 0 and run.get("nativeExitCode") == 0
                 and run.get("nativeReportSha256") == native_hash
                 and runner_checks.get("freshReport") is True)
    checks = {
        "nativeR1ThroughR12": native_ok,
        "successfulBuildAndFreshNativeRun": runner_ok,
        "successfulGameBuild": all(build_checks.values()),
        "allRequiredReportsPassed": all(report_checks.values()),
        "pieSlateInteractions": all(pie_checks.values()),
        "gameSlateInteractions": all(game_checks.values()),
        "gameScreenshotSources": all(source_checks.values()),
        "fullGameMouseRun": all(full_checks.values()),
        "fullGameScreenshotEvidence": all(full_source_checks.values()),
        "fullTwelveRoundMouseRun": all(full12_validation.values()),
        "fullTwelveRoundScreenshots": all(full12_source_checks.values()),
        "allScreenshotsAtTargetResolution": all(row["atTargetResolution"] for row in screenshot_rows)
        and source_checks["allSourceScreenshotsAtTargetResolution"],
        "promotedScreenshotsMatchGameSources": all(row["byteIdenticalToSource"] for row in screenshot_rows),
    }
    result = {
        "schema": "Tread.M1.Closeout.Report.v5", "ok": all(checks.values()),
        "scope": "native regression, PIE/standalone Slate interaction, natural game, R1-R12 UI fixture and screenshot provenance",
        "targetResolution": [1920, 1080], "checks": checks,
        "nativeMatchChecks": match_checks, "requiredReportChecks": report_checks,
        "gameBuildChecks": build_checks, "gameBuildReport": "M1_Game_Build.json",
        "pieSmokeChecks": pie_checks, "gameSmokeChecks": game_checks,
        "gameScreenshotSourceChecks": source_checks,
        "fullGameChecks": full_checks, "fullGameScreenshotChecks": full_source_checks,
        "fullTwelveRoundChecks": full12_validation,
        "fullTwelveRoundScreenshotChecks": full12_source_checks,
        "allScreenshotsAtTargetResolution": checks["allScreenshotsAtTargetResolution"],
        "runnerReport": "M1_Match_Run.json", "reports": required_reports,
        "uiReports": ["M1_PIE_UI_Smoke.json", "M1_UI_Smoke.json", "M1_UI_FullGame.json",
                      "M1_UI_Full12.json"],
        "sourceScreenshots": source_rows, "fullGameScreenshots": full_source_rows,
        "fullTwelveRoundScreenshots": full12_source_rows,
        "screenshots": screenshot_rows,
        "knownBoundaries": [
            "CharacterRosterMap is the audited M1 graybox; operatorTier and pacts await authoritative M4 data.",
            "Automated Slate interaction and screenshot provenance do not replace the owner's visual and feel acceptance.",
            "M1_Match_PythonOracle.json is a one-round model and is excluded from native acceptance.",
        ],
    }
    write("M1_Closeout_Report.json", result)
    print("M1_CLOSEOUT=" + ("PASS" if result["ok"] else "FAIL"))
    print("M1_CLOSEOUT_REPORT=" + str(REPORTS / "M1_Closeout_Report.json"))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
