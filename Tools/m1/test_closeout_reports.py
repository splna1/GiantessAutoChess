"""Regression tests for evidence gates that previously accepted false completion."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import generate_closeout_reports as closeout
import run_match_selftest as oracle


class CloseoutEvidenceTests(unittest.TestCase):
    EXTRA_STAGES = ("BP_Revised", "Scout_Player_0", "Scout_Player_1", "Scout_Player_2")

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.reports = self.root / "Reports"
        self.screenshots = self.root / "Screenshots"
        self.reports.mkdir()
        self.screenshots.mkdir()
        self.match = {
            "schema": "Tread.M1.MatchSelfTest.v2", "ok": True, "players": 4,
            "producer": "Tread C++ RunDeterministicSelfTest", "roundsCompleted": 12,
            "namedChecks": {"requestIdempotency": True},
            "acceptedRoundTypes": ["PvE", "PvE"] + ["PvP"] * 9 + ["Leader"],
            "acceptedRounds": list(range(1, 13)), "gameOver": True,
            "requestIdempotency": True, "processedRequestCount": 40,
            "sameSeedReplayEqual": True, "replaySignatureCrc32": "a123bc45", "stepResults": [True, True],
            "bp": {"banned": [f"s{i}" for i in range(4)], "available": [f"s{i}" for i in range(4, 32)],
                   "chosen": [f"s{i}" for i in range(4, 8)]},
        }
        self.save_match()
        self.write("M1_PoolLedger_Conservation.json", {
            "schema": "Tread.M1.PoolLedger.Conservation.v1", "ok": True,
            "participants": 4, "tierTotals": closeout.POOL_TOTALS,
        })
        for name in ("M1_DataContract_Validation.json", "M1_Economy_SelfTest.json",
                     "M1_CloneInstance_SelfTest.json", "M4_CharacterRosterMap_Audit.json"):
            self.write(name, {"ok": True})
        self.source_dir = self.reports / "M1_UI_Smoke" / "run-1"
        self.source_dir.mkdir(parents=True)
        for index, stage in enumerate(closeout.STAGES + self.EXTRA_STAGES):
            Image.new("RGB", (1920, 1080), (index * 40, 20, 30)).save(self.source_dir / f"{stage}.png")
        for stage, name in closeout.PROMOTED_SCREENSHOTS.items():
            shutil.copyfile(self.source_dir / f"{stage}.png", self.screenshots / name)
        self.pie = self.ui_report("PIE", 1914, 994)
        self.game = self.ui_report("Game", 1920, 1080)
        self.save_ui()
        self.full_source_dir = self.reports / "M1_UI_FullGame" / "run-1"
        self.full_source_dir.mkdir(parents=True)
        for index, stage in enumerate(closeout.FULL_GAME_STAGES):
            Image.new("RGB", (1920, 1080), (index * 17, 30, 50)).save(
                self.full_source_dir / f"{stage}.png"
            )
        self.full = self.full_game_report()
        self.save_full()
        self.full12_source_dir = self.reports / "M1_UI_Full12" / "run-1"
        self.full12_source_dir.mkdir(parents=True)
        for index, stage in enumerate(closeout.FULL12_STAGES):
            Image.new("RGB", (1920, 1080), (index * 30, 70, 50)).save(
                self.full12_source_dir / f"{stage}.png"
            )
        self.full12 = self.full12_report()
        self.save_full12()
        self.binary = self.root / "Binaries" / "Win64" / "Tread.exe"
        self.binary.parent.mkdir(parents=True)
        self.binary.write_bytes(b"M1 test game binary")
        self.build_log = self.reports / "M1_Game_Build.log"
        self.build_log.write_text("Build succeeded", encoding="utf-8")
        self.save_build()

    def ui_report(self, world_type: str, width: int, height: int) -> dict:
        paths = [str(self.source_dir / f"{stage}.png") for stage in closeout.STAGES + self.EXTRA_STAGES]
        return {
            "passed": True, "worldType": world_type,
            "inputPath": "Live FSlateApplication mouse events -> native/WBP widget -> MatchController",
            "viewportWidth": width, "viewportHeight": height,
            "checks": [{"name": name, "passed": True} for name in sorted(closeout.REQUIRED_UI_CHECKS)]
            + [{"name": "screenshot_written", "passed": True, "detail": path} for path in paths],
            "inputs": [{"event": "Move", "handled": True}, {"event": "Down", "handled": True},
                       {"event": "Up", "handled": True}],
            "screenshots": paths,
        }

    def save_ui(self) -> None:
        self.write("M1_PIE_UI_Smoke.json", self.pie)
        self.write("M1_UI_Smoke.json", self.game)

    def full_game_report(self) -> dict:
        screenshot_paths = [str(self.full_source_dir / f"{stage}.png")
                            for stage in closeout.FULL_GAME_STAGES]
        checks = [{"name": name, "passed": True} for name in sorted(closeout.REQUIRED_UI_CHECKS)]
        checks.extend({"name": name, "passed": True} for name in (
            "round_1_result", "round_2_preparation_timer_auto_deploy",
            "battle_rejects_mouse_drag", "battle_rejects_shop_click", "round_2_result",
            "round_2_continue_button_visible", "round_3_after_continue",
        ))
        for number in range(3, 7):
            checks.extend({"name": f"round_{number}_{suffix}", "passed": True}
                          for suffix in ("preparation", "deploy_button", "result"))
            if number < 6:
                checks.extend({"name": f"round_{number}_{suffix}", "passed": True}
                              for suffix in ("continue_button_visible", "continue"))
            else:
                checks.append({"name": "round_6_continue_button_visible", "passed": True})
        checks.extend({"name": name, "passed": True} for name in (
            "natural_game_over", "four_final_ranks", "final_ranking_modal_visible",
        ))
        checks.extend({"name": "trace_check", "passed": True} for _ in range(20))
        checks.extend({"name": "full_game_screenshot_written", "passed": True, "detail": path}
                      for path in screenshot_paths)
        return {
            "passed": True, "mode": "fullGame", "worldType": "Game",
            "inputPath": "Live FSlateApplication mouse events -> native/WBP widget -> MatchController",
            "phase": "ETreadM1Phase::GameOver", "round": 6,
            "viewportWidth": 1920, "viewportHeight": 1080,
            "roundTwoAutoPreparationSeconds": 29.6,
            "checks": checks,
            "inputs": [{"event": event, "handled": True} for _ in range(40)
                       for event in ("Move", "Down", "Up")],
            "screenshots": screenshot_paths,
            "rounds": [{"round": number,
                        "roundType": "ETreadM1RoundType::PvE" if number <= 2 else "ETreadM1RoundType::PvP",
                        "outcomes": 4, "pairings": 2}
                       for number in range(1, 7)],
            "finalRanking": {
                "round": 6, "lastRoundOutcomes": 4,
                "rankedPlayers": [{"playerId": f"P{index}", "displayName": name,
                                   "rank": index + 1, "health": 90 - index * 30,
                                   "eliminated": index == 3}
                                  for index, name in enumerate(("玩家", "AI-1", "AI-2", "AI-3"))],
            },
        }

    def save_full(self) -> None:
        self.write("M1_UI_FullGame.json", self.full, encoding="utf-16")

    def full12_report(self) -> dict:
        paths = [str(self.full12_source_dir / f"{stage}.png") for stage in closeout.FULL12_STAGES]
        checks = [{"name": name, "passed": True} for name in sorted(closeout.REQUIRED_UI_CHECKS)]
        checks.extend({"name": name, "passed": True} for name in (
            "full12_fixture_four_players", "round_1_preparation_hud",
            "round_1_result", "round_1_45s_battle_timer",
            "round_2_preparation_hud", "round_2_preparation_timer_auto_deploy",
            "battle_rejects_mouse_drag", "battle_rejects_shop_click",
            "round_2_result", "round_2_45s_battle_timer", "round_2_continue_button_visible",
        ))
        for number in range(3, 13):
            checks.extend({"name": f"round_{number}_{suffix}", "passed": True}
                          for suffix in ("preparation", "preparation_hud", "deploy_button",
                                         "result", "45s_battle_timer", "continue_button_visible"))
            if number < 12:
                checks.append({"name": f"round_{number}_continue", "passed": True})
        checks.extend({"name": name, "passed": True} for name in (
            "full12_no_early_game_over", "natural_game_over", "full12_leader_game_over",
            "full12_final_viewport_1920x1080", "four_final_ranks", "final_ranking_modal_visible",
        ))
        checks.extend({"name": "full_game_screenshot_written", "passed": True, "detail": path}
                      for path in paths)
        expected_types = ["ETreadM1RoundType::PvE"] * 2 + ["ETreadM1RoundType::PvP"] * 9
        expected_types.append("ETreadM1RoundType::Leader")
        return {
            "passed": True, "mode": "full12", "worldType": "Game",
            "inputPath": "Live FSlateApplication mouse events -> native/WBP widget -> MatchController",
            "fixtureAppliedAtRound1": True, "fixturePlayerHealth": 1000,
            "fixtureScope": "Set four player Health fields once after BP; all subsequent actions use Slate input or live timers",
            "phase": "ETreadM1Phase::GameOver", "round": 12,
            "viewportWidth": 1920, "viewportHeight": 1080,
            "roundTwoAutoPreparationSeconds": 30.0,
            "checks": checks,
            "inputs": [{"event": event, "handled": True}
                       for event in ("Move", "Down", "Up")],
            "screenshots": paths,
            "rounds": [{"round": number, "roundType": expected_types[number - 1],
                        "outcomes": 4, "pairings": 2, "battleElapsedSeconds": 45.0}
                       for number in range(1, 13)],
            "roundHuds": [{"round": number, "hudPhase": "ETreadM1Phase::Preparation",
                           "hudRoundType": expected_types[number - 1],
                           "timerRemainingSeconds": 29.0, "deployButtonVisible": True,
                           "viewportWidth": 1920, "viewportHeight": 1080}
                          for number in range(1, 13)],
            "finalRanking": {
                "round": 12, "lastRoundOutcomes": 4,
                "rankedPlayers": [{"playerId": f"P{index}", "displayName": f"Player {index}",
                                   "rank": index + 1, "health": 800 - 100 * index,
                                   "eliminated": False}
                                  for index in range(4)],
            },
        }

    def save_full12(self) -> None:
        self.write("M1_UI_Full12.json", self.full12)

    def save_build(self) -> None:
        self.write("M1_Game_Build.json", {
            "schema": "Tread.M1.GameBuild.v1", "ok": True,
            "target": "Tread Win64 Development", "exitCode": 0,
            "binary": str(self.binary), "binaryBytes": self.binary.stat().st_size,
            "binarySha256": hashlib.sha256(self.binary.read_bytes()).hexdigest(),
            "buildLog": str(self.build_log),
        })

    def write(self, name: str, value: dict, encoding: str = "utf-8") -> None:
        (self.reports / name).write_text(json.dumps(value, ensure_ascii=False), encoding=encoding)

    def save_match(self) -> None:
        self.write("M1_Match_SelfTest.json", self.match)
        self.write("M1_Match_Run.json", {
            "schema": "Tread.M1.MatchRun.v1", "ok": True, "buildExitCode": 0, "nativeExitCode": 0,
            "nativeReportSha256": hashlib.sha256((self.reports / "M1_Match_SelfTest.json").read_bytes()).hexdigest(),
            "checks": {"freshReport": True},
        })

    def generate(self) -> tuple[int, dict]:
        with patch.object(closeout, "ROOT", self.root), patch.object(closeout, "REPORTS", self.reports), patch.object(closeout, "SCREENSHOTS", self.screenshots):
            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = closeout.main()
        return exit_code, json.loads((self.reports / "M1_Closeout_Report.json").read_text(encoding="utf-8"))

    def test_complete_native_evidence_passes(self) -> None:
        exit_code, report = self.generate()
        self.assertEqual(exit_code, 0)
        self.assertIs(report["ok"], True)

    def test_one_round_oracle_cannot_pass_native_acceptance(self) -> None:
        self.match = oracle.run()
        self.save_match()
        exit_code, report = self.generate()
        self.assertEqual(exit_code, 1)
        self.assertIs(report["checks"]["nativeR1ThroughR12"], False)
        self.assertNotEqual(oracle.REPORT.name, "M1_Match_SelfTest.json")

    def test_existing_wrong_size_screenshot_fails(self) -> None:
        Image.new("RGB", (1349, 762)).save(self.screenshots / "M1_Battle_Result.png")
        exit_code, report = self.generate()
        self.assertEqual(exit_code, 1)
        self.assertIs(report["allScreenshotsAtTargetResolution"], False)

    def test_missing_pie_report_fails(self) -> None:
        (self.reports / "M1_PIE_UI_Smoke.json").unlink()
        exit_code, report = self.generate()
        self.assertEqual(exit_code, 1)
        self.assertIs(report["checks"]["pieSlateInteractions"], False)

    def test_pie_requires_successful_drag_checks(self) -> None:
        self.pie["checks"] = [row for row in self.pie["checks"] if row["name"] != "board_swap"]
        self.save_ui()
        exit_code, report = self.generate()
        self.assertEqual(exit_code, 1)
        self.assertIs(report["pieSmokeChecks"]["requiredInteractions"], False)

    def test_failed_reported_ui_check_fails(self) -> None:
        self.game["checks"][0]["passed"] = False
        self.save_ui()
        exit_code, report = self.generate()
        self.assertEqual(exit_code, 1)
        self.assertIs(report["gameSmokeChecks"]["allChecksPassed"], False)

    def test_standalone_report_requires_game_and_target_viewport(self) -> None:
        self.game["worldType"] = "PIE"
        self.game["viewportWidth"] = 1914
        self.save_ui()
        exit_code, report = self.generate()
        self.assertEqual(exit_code, 1)
        self.assertIs(report["gameSmokeChecks"]["worldType"], False)
        self.assertIs(report["gameSmokeChecks"]["targetViewport"], False)

    def test_missing_or_wrong_size_source_screenshot_fails(self) -> None:
        Image.new("RGB", (1349, 762)).save(self.source_dir / "Battle.png")
        exit_code, report = self.generate()
        self.assertEqual(exit_code, 1)
        self.assertIs(report["gameScreenshotSourceChecks"]["allSourceScreenshotsAtTargetResolution"], False)

    def test_unrelated_source_path_fails(self) -> None:
        unrelated = self.root / "Elsewhere" / "BP.png"
        unrelated.parent.mkdir()
        shutil.copyfile(self.source_dir / "BP.png", unrelated)
        self.game["screenshots"][0] = str(unrelated)
        self.save_ui()
        exit_code, report = self.generate()
        self.assertEqual(exit_code, 1)
        self.assertIs(report["gameScreenshotSourceChecks"]["coreStagePathsFromOneRun"], False)

    def test_mixed_game_screenshot_runs_fail(self) -> None:
        other = self.reports / "M1_UI_Smoke" / "run-2" / "Scout.png"
        other.parent.mkdir(parents=True)
        shutil.copyfile(self.source_dir / "Scout.png", other)
        self.game["screenshots"][2] = str(other)
        self.save_ui()
        exit_code, report = self.generate()
        self.assertEqual(exit_code, 1)
        self.assertIs(report["gameScreenshotSourceChecks"]["coreStagePathsFromOneRun"], False)

    def test_claimed_source_requires_screenshot_write_check(self) -> None:
        self.game["checks"] = [row for row in self.game["checks"]
                               if row.get("detail") != self.game["screenshots"][2]]
        self.save_ui()
        exit_code, report = self.generate()
        self.assertEqual(exit_code, 1)
        self.assertIs(report["gameScreenshotSourceChecks"]["allScreenshotWriteChecks"], False)

    def test_missing_core_stage_fails_even_with_extra_stages(self) -> None:
        self.game["screenshots"] = [path for path in self.game["screenshots"]
                                    if Path(path).stem != "Battle"]
        self.game["checks"] = [row for row in self.game["checks"]
                               if row.get("detail") != str(self.source_dir / "Battle.png")]
        self.save_ui()
        exit_code, report = self.generate()
        self.assertEqual(exit_code, 1)
        self.assertIs(report["gameScreenshotSourceChecks"]["coreStagePathsFromOneRun"], False)

    def test_extra_stage_must_have_real_full_resolution_image(self) -> None:
        Image.new("RGB", (1349, 762)).save(self.source_dir / "BP_Revised.png")
        exit_code, report = self.generate()
        self.assertEqual(exit_code, 1)
        self.assertIs(report["gameScreenshotSourceChecks"]["allSourceScreenshotsAtTargetResolution"], False)

    def test_extra_stage_requires_its_write_check(self) -> None:
        self.game["checks"] = [row for row in self.game["checks"]
                               if row.get("detail") != str(self.source_dir / "Scout_Player_2.png")]
        self.save_ui()
        exit_code, report = self.generate()
        self.assertEqual(exit_code, 1)
        self.assertIs(report["gameScreenshotSourceChecks"]["allScreenshotWriteChecks"], False)

    def test_new_bp_revision_and_all_scout_reads_required(self) -> None:
        self.game["checks"] = [row for row in self.game["checks"]
                               if row["name"] not in {"bp_revised_before_final_ai", "scout_player_2_read_only"}]
        self.save_ui()
        exit_code, report = self.generate()
        self.assertEqual(exit_code, 1)
        self.assertIs(report["gameSmokeChecks"]["requiredInteractions"], False)

    def test_promoted_screenshot_must_be_byte_identical(self) -> None:
        Image.new("RGB", (1920, 1080), (9, 9, 9)).save(self.screenshots / closeout.PROMOTED_SCREENSHOTS["Result"])
        exit_code, report = self.generate()
        self.assertEqual(exit_code, 1)
        self.assertIs(report["checks"]["promotedScreenshotsMatchGameSources"], False)

    def test_stale_game_binary_hash_fails(self) -> None:
        self.binary.write_bytes(b"changed since build")
        exit_code, report = self.generate()
        self.assertEqual(exit_code, 1)
        self.assertIs(report["gameBuildChecks"]["binarySha256"], False)

    def test_missing_game_build_report_fails(self) -> None:
        (self.reports / "M1_Game_Build.json").unlink()
        exit_code, report = self.generate()
        self.assertEqual(exit_code, 1)
        self.assertIs(report["checks"]["successfulGameBuild"], False)

    def test_utf8_sig_full_game_report_is_accepted(self) -> None:
        self.write("M1_UI_FullGame.json", self.full, encoding="utf-8-sig")
        exit_code, report = self.generate()
        self.assertEqual(exit_code, 0)
        self.assertIs(report["checks"]["fullGameMouseRun"], True)

    def test_missing_full_game_report_fails(self) -> None:
        (self.reports / "M1_UI_FullGame.json").unlink()
        exit_code, report = self.generate()
        self.assertEqual(exit_code, 1)
        self.assertIs(report["checks"]["fullGameMouseRun"], False)

    def test_full_game_must_end_in_game_over_at_target_viewport(self) -> None:
        self.full["worldType"] = "PIE"
        self.full["phase"] = "ETreadM1Phase::Settlement"
        self.full["viewportWidth"] = 1914
        self.save_full()
        exit_code, report = self.generate()
        self.assertEqual(exit_code, 1)
        self.assertIs(report["fullGameChecks"]["passedGameMouseRun"], False)
        self.assertIs(report["fullGameChecks"]["naturalGameOverAtRoundSix"], False)
        self.assertIs(report["fullGameChecks"]["targetViewport"], False)

    def test_full_game_timer_must_be_natural_thirty_seconds(self) -> None:
        self.full["roundTwoAutoPreparationSeconds"] = 20.0
        self.save_full()
        exit_code, report = self.generate()
        self.assertEqual(exit_code, 1)
        self.assertIs(report["fullGameChecks"]["naturalRoundTwoTimer"], False)

    def test_battle_must_reject_drag_and_shop_click(self) -> None:
        self.full["checks"] = [row for row in self.full["checks"]
                               if row["name"] != "battle_rejects_shop_click"]
        self.save_full()
        exit_code, report = self.generate()
        self.assertEqual(exit_code, 1)
        self.assertIs(report["fullGameChecks"]["battleRejectsMouseActions"], False)

    def test_full_game_round_sequence_and_result_checks_required(self) -> None:
        self.full["rounds"][3]["round"] = 5
        self.full["checks"] = [row for row in self.full["checks"] if row["name"] != "round_4_result"]
        self.save_full()
        exit_code, report = self.generate()
        self.assertEqual(exit_code, 1)
        self.assertIs(report["fullGameChecks"]["continuousRoundResults"], False)

    def test_full_game_round_checks_must_be_chronological(self) -> None:
        checks = self.full["checks"]
        result_index = next(index for index, row in enumerate(checks)
                            if row["name"] == "round_4_result")
        preparation_index = next(index for index, row in enumerate(checks)
                                 if row["name"] == "round_4_preparation")
        checks[result_index], checks[preparation_index] = checks[preparation_index], checks[result_index]
        self.save_full()
        exit_code, report = self.generate()
        self.assertEqual(exit_code, 1)
        self.assertIs(report["fullGameChecks"]["roundCheckOrder"], False)

    def test_full_game_final_ranks_must_be_unique(self) -> None:
        self.full["finalRanking"]["rankedPlayers"][3]["rank"] = 3
        self.save_full()
        exit_code, report = self.generate()
        self.assertEqual(exit_code, 1)
        self.assertIs(report["fullGameChecks"]["fourUniqueFinalRanks"], False)

    def test_full_game_game_over_screenshot_must_exist_at_full_resolution(self) -> None:
        Image.new("RGB", (1349, 762)).save(self.full_source_dir / "GameOver.png")
        exit_code, report = self.generate()
        self.assertEqual(exit_code, 1)
        self.assertIs(report["fullGameScreenshotChecks"]["gameOverImageAtTargetResolution"], False)

    def test_full_game_screenshot_needs_written_check(self) -> None:
        game_over_path = str(self.full_source_dir / "GameOver.png")
        self.full["checks"] = [row for row in self.full["checks"]
                               if row.get("detail") != game_over_path]
        self.save_full()
        exit_code, report = self.generate()
        self.assertEqual(exit_code, 1)
        self.assertIs(report["fullGameScreenshotChecks"]["allScreenshotWriteChecks"], False)

    def test_missing_full12_report_fails(self) -> None:
        (self.reports / "M1_UI_Full12.json").unlink()
        exit_code, report = self.generate()
        self.assertEqual(exit_code, 1)
        self.assertIs(report["checks"]["fullTwelveRoundMouseRun"], False)

    def test_full12_fixture_and_leader_game_over_required(self) -> None:
        self.full12["fixtureAppliedAtRound1"] = False
        self.full12["round"] = 11
        self.save_full12()
        exit_code, report = self.generate()
        self.assertEqual(exit_code, 1)
        self.assertIs(report["fullTwelveRoundChecks"]["highHealthFixtureOnlyAtRoundOne"], False)
        self.assertIs(report["fullTwelveRoundChecks"]["leaderGameOverAtRoundTwelve"], False)

    def test_full12_rounds_must_be_continuous_with_leader_at_twelve(self) -> None:
        self.full12["rounds"][10]["round"] = 12
        self.full12["rounds"][11]["roundType"] = "ETreadM1RoundType::PvP"
        self.save_full12()
        exit_code, report = self.generate()
        self.assertEqual(exit_code, 1)
        self.assertIs(report["fullTwelveRoundChecks"]["continuousRoundTypesAndResults"], False)

    def test_full12_huds_must_show_preparation_and_expected_type(self) -> None:
        self.full12["roundHuds"][11]["hudRoundType"] = "ETreadM1RoundType::PvP"
        self.full12["roundHuds"][11]["timerRemainingSeconds"] = 0
        self.save_full12()
        exit_code, report = self.generate()
        self.assertEqual(exit_code, 1)
        self.assertIs(report["fullTwelveRoundChecks"]["allPreparationHuds"], False)

    def test_full12_each_battle_requires_forty_five_second_timer(self) -> None:
        self.full12["rounds"][6]["battleElapsedSeconds"] = 15.0
        self.save_full12()
        exit_code, report = self.generate()
        self.assertEqual(exit_code, 1)
        self.assertIs(report["fullTwelveRoundChecks"]["allFortyFiveSecondBattles"], False)

    def test_full12_failed_or_missing_round_check_fails(self) -> None:
        self.full12["checks"] = [row for row in self.full12["checks"]
                                 if row["name"] != "round_12_45s_battle_timer"]
        self.full12["checks"][0]["passed"] = False
        self.save_full12()
        exit_code, report = self.generate()
        self.assertEqual(exit_code, 1)
        self.assertIs(report["fullTwelveRoundChecks"]["continuousRoundTypesAndResults"], False)
        self.assertIs(report["fullTwelveRoundChecks"]["passedGameMouseRun"], False)

    def test_full12_four_unique_final_ranks_required(self) -> None:
        self.full12["finalRanking"]["rankedPlayers"][3]["rank"] = 3
        self.save_full12()
        exit_code, report = self.generate()
        self.assertEqual(exit_code, 1)
        self.assertIs(report["fullTwelveRoundChecks"]["fourUniqueFinalRanks"], False)

    def test_full12_milestone_image_must_be_real_full_resolution(self) -> None:
        Image.new("RGB", (1349, 762)).save(self.full12_source_dir / "Round_12_Leader.png")
        exit_code, report = self.generate()
        self.assertEqual(exit_code, 1)
        self.assertIs(report["fullTwelveRoundScreenshotChecks"]["threeMilestoneImagesAtTargetResolution"], False)

    def test_full12_milestone_images_need_write_checks(self) -> None:
        leader_path = str(self.full12_source_dir / "Round_12_Leader.png")
        self.full12["checks"] = [row for row in self.full12["checks"]
                                 if row.get("detail") != leader_path]
        self.save_full12()
        exit_code, report = self.generate()
        self.assertEqual(exit_code, 1)
        self.assertIs(report["fullTwelveRoundScreenshotChecks"]["allScreenshotWriteChecks"], False)

    def test_full12_extra_listed_image_must_be_full_resolution(self) -> None:
        extra = self.full12_source_dir / "BP.png"
        Image.new("RGB", (1349, 762)).save(extra)
        self.full12["screenshots"].append(str(extra))
        self.full12["checks"].append({"name": "full_game_screenshot_written",
                                      "passed": True, "detail": str(extra)})
        self.save_full12()
        exit_code, report = self.generate()
        self.assertEqual(exit_code, 1)
        self.assertIs(report["fullTwelveRoundScreenshotChecks"]["allSourceScreenshotsAtTargetResolution"], False)

    def test_full12_milestones_must_come_from_one_run(self) -> None:
        other = self.reports / "M1_UI_Full12" / "run-2" / "Round_12_Leader.png"
        other.parent.mkdir(parents=True)
        shutil.copyfile(self.full12_source_dir / "Round_12_Leader.png", other)
        self.full12["screenshots"][1] = str(other)
        self.full12["checks"][-2]["detail"] = str(other)
        self.save_full12()
        exit_code, report = self.generate()
        self.assertEqual(exit_code, 1)
        self.assertIs(report["fullTwelveRoundScreenshotChecks"]["coreStagePathsFromOneRun"], False)

    def test_stale_runner_hash_fails(self) -> None:
        self.match["seed"] = 999
        self.write("M1_Match_SelfTest.json", self.match)
        exit_code, report = self.generate()
        self.assertEqual(exit_code, 1)
        self.assertIs(report["checks"]["successfulBuildAndFreshNativeRun"], False)

    def test_overlapping_bans_fail(self) -> None:
        self.match["bp"]["banned"][0] = "s4"
        self.save_match()
        exit_code, report = self.generate()
        self.assertEqual(exit_code, 1)
        self.assertIs(report["requiredReportChecks"]["M1_BP_32_4_Report.json"], False)

    def test_failed_native_step_fails_even_if_ok_is_true(self) -> None:
        self.match["stepResults"].append(False)
        self.save_match()
        exit_code, report = self.generate()
        self.assertEqual(exit_code, 1)
        self.assertIs(report["nativeMatchChecks"]["allNativeStepsPassed"], False)


if __name__ == "__main__":
    unittest.main()
