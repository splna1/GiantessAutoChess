"""Generate the versioned M1 data contract and a deterministic sample state."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "Content" / "Data" / "Generated"
STRATEGY_SOURCE = ROOT / "Content" / "Data" / "Strategies.json"
REJECT_REASONS = ("None", "InvalidPhase", "InsufficientFunds", "BenchFull", "ShopSlotEmpty", "ShopSlotSold",
                  "ShopLocked", "MaxLevelReached", "PopulationLimitReached", "InvalidTarget", "NotOwnUnit",
                  "InvalidBoardCell", "StrategyUnavailable", "StrategyAlreadyChosen", "StrategyLocked",
                  "PlayerHealthInsufficient", "AlreadyConfirmed", "AlreadyProcessed", "PlayerEliminated",
                  "ScoutUnavailable", "Unknown")


def obj(properties, required=(), additional=False):
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": additional,
    }


def enum(values):
    return {"type": "string", "enum": list(values)}


def make_schema():
    string = {"type": "string"}
    nonnegative = {"type": "integer", "minimum": 0}
    positive = {"type": "integer", "minimum": 1}
    id_array = {"type": "array", "items": string}
    unit = obj(
        {
            "unitInstanceId": string,
            "characterId": string,
            "originalOperatorName": string,
            "operatorTier": enum(("I", "II", "III", "IV", "V", "VI")),
            "unitStar": {"type": "integer", "minimum": 1, "maximum": 3},
            "cost": {"type": "integer", "minimum": 1, "maximum": 5},
            "location": enum(("Bench", "Board", "Removed")),
            "boardCell": {
                "type": "object",
                "properties": {"x": {"type": "integer", "minimum": 0, "maximum": 7},
                                "y": {"type": "integer", "minimum": 0, "maximum": 7}},
                "required": ["x", "y"],
                "additionalProperties": False,
            },
            "ownerPlayerId": string,
            "equipmentIds": id_array,
            "isTransformClone": {"type": "boolean"},
            "copySourceCharacterId": string,
            "cloneInstanceId": string,
        },
        required=("unitInstanceId", "characterId", "operatorTier", "unitStar", "cost", "location",
                  "ownerPlayerId", "equipmentIds", "isTransformClone", "copySourceCharacterId", "cloneInstanceId"),
    )
    shop_slot = obj(
        {
            "slotIndex": {"type": "integer", "minimum": 0, "maximum": 4},
            "characterId": string,
            "operatorTier": enum(("I", "II", "III", "IV", "V", "VI")),
            "cost": {"type": "integer", "minimum": 1, "maximum": 5},
            "isSold": {"type": "boolean"},
            "isLockedByPlayer": {"type": "boolean"},
        },
        required=("slotIndex", "characterId", "operatorTier", "cost", "isSold", "isLockedByPlayer"),
    )
    shop = obj(
        {
            "slots": {"type": "array", "minItems": 5, "maxItems": 5, "items": {"$ref": "#/$defs/shopSlot"}},
            "locked": {"type": "boolean"},
            "lockMode": enum(("AutoRefreshOnly",)),
            "refreshCost": {"type": "integer", "const": 2},
            "refreshIndex": nonnegative,
        },
        required=("slots", "locked", "refreshCost", "refreshIndex"),
    )
    player = obj(
        {
            "playerId": string,
            "displayName": string,
            "isHuman": {"type": "boolean"},
            "isEliminated": {"type": "boolean"},
            "rank": {"type": "integer", "minimum": 0, "maximum": 4},
            "health": nonnegative,
            "funds": nonnegative,
            "level": {"type": "integer", "minimum": 1, "maximum": 9},
            "experience": nonnegative,
            "experienceToNextLevel": nonnegative,
            "populationUsed": nonnegative,
            "populationLimit": nonnegative,
            "winStreak": nonnegative,
            "lossStreak": nonnegative,
            "initialStrategyId": {"type": ["string", "null"]},
            "shop": {"$ref": "#/$defs/shopState"},
            "benchUnitInstanceIds": {"type": "array", "minItems": 8, "maxItems": 8, "items": {"type": ["string", "null"]}},
            "benchUnits": {"type": "array", "maxItems": 8, "items": {"$ref": "#/$defs/unitInstance"}},
            "boardUnits": {"type": "array", "items": {"$ref": "#/$defs/unitInstance"}},
            "nextRoundIncome": {"$ref": "#/$defs/incomeBreakdown"},
            "equipmentIds": id_array,
            "activePactIds": id_array,
        },
        required=("playerId", "displayName", "isHuman", "isEliminated", "rank", "health", "funds", "level",
                  "experience", "experienceToNextLevel", "populationUsed", "populationLimit", "winStreak", "lossStreak", "initialStrategyId",
                  "shop", "benchUnitInstanceIds", "benchUnits", "boardUnits", "nextRoundIncome", "equipmentIds", "activePactIds"),
    )
    strategy = obj(
        {
            "strategyId": string,
            "issuerCharacterId": string,
            "offerText": string,
            "hpCost": nonnegative,
            "effects": {"type": "array", "items": string},
            "trigger": string,
            "unlockCondition": string,
            "initialOnly": {"type": "boolean"},
            "bpEligible": {"type": "boolean"},
            "uniqueScope": enum(("StrategyId",)),
        },
        required=("strategyId", "issuerCharacterId", "offerText", "hpCost", "effects", "trigger", "unlockCondition",
                  "initialOnly", "bpEligible", "uniqueScope"),
    )
    bp = obj(
        {
            "candidateCount": {"type": "integer", "const": 32},
            "systemBanCount": {"type": "integer", "const": 4},
            "playerPickCount": {"type": "integer", "const": 1},
            "aiPickCount": {"type": "integer", "const": 3},
            "aiPickOrder": {"type": "array", "minItems": 3, "maxItems": 3, "items": string},
            "playerCanReviseUntilAiConfirmed": {"type": "boolean", "const": True},
            "hasCountdown": {"type": "boolean", "const": False},
            "aiSelectionStartsAfterPlayerPick": {"type": "boolean", "const": True},
            "seed": {"type": "integer"},
            "bannedStrategyIds": {"type": "array", "minItems": 4, "maxItems": 4, "items": string},
            "availableStrategyIds": {"type": "array", "minItems": 28, "maxItems": 28, "items": string},
            "playerStrategyId": {"type": ["string", "null"]},
            "aiStrategyIds": {"type": "array", "minItems": 3, "maxItems": 3, "items": {"type": ["string", "null"]}},
            "aiPickStates": {"type": "array", "minItems": 3, "maxItems": 3, "items": enum(("Waiting", "Thinking", "Selected", "Confirmed"))},
            "confirmed": {"type": "boolean"},
        },
        required=("candidateCount", "systemBanCount", "playerPickCount", "aiPickCount", "aiPickOrder", "playerCanReviseUntilAiConfirmed", "hasCountdown", "aiSelectionStartsAfterPlayerPick",
                  "seed", "bannedStrategyIds", "availableStrategyIds", "playerStrategyId", "aiStrategyIds", "aiPickStates", "confirmed"),
    )
    pact_stack = obj({"pactId": string, "stackCount": nonnegative}, required=("pactId", "stackCount"))
    scout = obj(
        {
            "playerId": string,
            "displayName": string,
            "rank": {"type": "integer", "minimum": 0, "maximum": 4},
            "health": nonnegative,
            "funds": nonnegative,
            "level": {"type": "integer", "minimum": 1, "maximum": 9},
            "populationUsed": nonnegative,
            "populationLimit": nonnegative,
            "nextRoundIncome": {"$ref": "#/$defs/incomeBreakdown"},
            "boardUnits": {"type": "array", "items": {"$ref": "#/$defs/unitInstance"}},
            "benchUnitInstanceIds": {"type": "array", "minItems": 8, "maxItems": 8, "items": {"type": ["string", "null"]}},
            "benchUnits": {"type": "array", "maxItems": 8, "items": {"$ref": "#/$defs/unitInstance"}},
            "equipmentIds": id_array,
            "activePactIds": id_array,
            "pactStacks": {"type": "array", "items": {"$ref": "#/$defs/pactStack"}},
            "readOnly": {"type": "boolean", "const": True},
        },
        required=("playerId", "displayName", "rank", "health", "funds", "level", "populationUsed", "populationLimit", "nextRoundIncome", "boardUnits", "benchUnitInstanceIds",
                  "benchUnits", "equipmentIds", "activePactIds", "pactStacks", "readOnly"),
    )
    ledger = obj(
        {
            "entryId": string,
            "revision": nonnegative,
            "action": enum(("Initialize", "Reserve", "Purchase", "RefreshReturn", "SellReturn", "CombineConsume", "EliminationReturn", "CloneCreate", "CloneDestroy")),
            "playerId": {"type": ["string", "null"]},
            "characterId": string,
            "operatorTier": enum(("I", "II", "III", "IV", "V", "VI")),
            "unitInstanceId": {"type": ["string", "null"]},
            "cloneInstanceId": {"type": ["string", "null"]},
            "copySourceCharacterId": {"type": ["string", "null"]},
            "poolCopiesTotal": nonnegative,
            "poolCopiesAvailable": nonnegative,
            "reservedCopies": nonnegative,
            "ownedCopies": nonnegative,
            "delta": {"type": "integer"},
        },
        required=("entryId", "revision", "action", "playerId", "characterId", "operatorTier", "unitInstanceId", "cloneInstanceId", "copySourceCharacterId",
                  "poolCopiesTotal", "poolCopiesAvailable", "reservedCopies", "ownedCopies", "delta"),
    )
    pool_balance = obj(
        {
            "characterId": string,
            "operatorTier": enum(("I", "II", "III", "IV", "V", "VI")),
            "poolCopiesTotal": nonnegative,
            "poolCopiesAvailable": nonnegative,
            "reservedCopies": nonnegative,
            "ownedCopies": nonnegative,
        },
        required=("characterId", "operatorTier", "poolCopiesTotal", "poolCopiesAvailable", "reservedCopies", "ownedCopies"),
    )
    level_rule = obj(
        {"level": {"type": "integer", "minimum": 1, "maximum": 9}, "experienceToNextLevel": nonnegative},
        required=("level", "experienceToNextLevel"),
    )
    rules = obj(
        {
            "levelExperienceTable": {"type": "array", "minItems": 9, "maxItems": 9, "items": {"$ref": "#/$defs/levelRule"}},
            "benchPurchasePolicy": enum(("RejectWhenFull",)),
            "shopLockMode": enum(("AutoRefreshOnly",)),
            "bpHasCountdown": {"type": "boolean", "const": False},
            "aiSelectionStartsAfterPlayerPick": {"type": "boolean", "const": True},
            "deployCompletesPreparation": {"type": "boolean", "const": True},
            "autoBattleMode": enum(("AlwaysOn",)),
            "playerEliminationFlow": enum(("DirectSettlement",)),
            "preparationDurationSec": {"type": "integer", "const": 30},
            "baseIncome": {"type": "integer", "const": 5},
            "interestFundsStep": {"type": "integer", "const": 10},
            "maxInterest": {"type": "integer", "const": 5},
            "experiencePurchaseCost": {"type": "integer", "const": 4},
            "experiencePurchaseAmount": {"type": "integer", "const": 4},
            "shopSlotCount": {"type": "integer", "const": 5},
            "shopRefreshCost": {"type": "integer", "const": 2},
            "maxBenchSlots": {"type": "integer", "const": 8},
        },
        required=("levelExperienceTable", "benchPurchasePolicy", "shopLockMode", "bpHasCountdown",
                  "aiSelectionStartsAfterPlayerPick", "deployCompletesPreparation", "autoBattleMode", "playerEliminationFlow",
                  "preparationDurationSec", "baseIncome", "interestFundsStep", "maxInterest", "experiencePurchaseCost",
                  "experiencePurchaseAmount", "shopSlotCount", "shopRefreshCost", "maxBenchSlots"),
    )
    pairing = obj({"playerId": string, "opponentId": string}, required=("playerId", "opponentId"))
    outcome = obj(
        {"playerId": string, "outcome": enum(("Win", "Lose", "Draw")), "survivingUnitCount": nonnegative,
         "healthBefore": nonnegative, "healthAfter": nonnegative, "rankBefore": {"type": "integer", "minimum": 0, "maximum": 4},
         "rankAfter": {"type": "integer", "minimum": 0, "maximum": 4}},
        required=("playerId", "outcome", "survivingUnitCount", "healthBefore", "healthAfter", "rankBefore", "rankAfter"),
    )
    income = obj(
        {"base": nonnegative, "interest": nonnegative, "streak": nonnegative, "other": nonnegative},
        required=("base", "interest", "streak", "other"),
    )
    battle_result = obj(
        {"roundIndex": {"type": "integer", "minimum": 0, "maximum": 12},
         "pairings": {"type": "array", "items": {"$ref": "#/$defs/battlePairing"}},
         "outcomes": {"type": "array", "items": {"$ref": "#/$defs/battleOutcome"}},
         "incomeBreakdown": {"$ref": "#/$defs/incomeBreakdown"},
         "eliminatedPlayerIds": {"type": "array", "items": string}},
        required=("roundIndex", "pairings", "outcomes", "incomeBreakdown", "eliminatedPlayerIds"),
    )
    battle_event = obj(
        {"eventId": string, "sequence": nonnegative, "roundIndex": {"type": "integer", "minimum": 0, "maximum": 12},
         "eventType": enum(("UnitDamaged", "UnitDied", "UnitTargetChanged")), "sourcePlayerId": string,
         "sourceUnitInstanceId": string, "targetPlayerId": string, "targetUnitInstanceId": string,
         "amount": {"type": "integer", "minimum": 0}, "targetHealthAfter": nonnegative,
         "newTargetUnitInstanceId": string, "timeSec": {"type": "number", "minimum": 0}},
        required=("eventId", "sequence", "roundIndex", "eventType", "sourcePlayerId", "sourceUnitInstanceId",
                  "targetPlayerId", "targetUnitInstanceId", "amount", "targetHealthAfter", "newTargetUnitInstanceId", "timeSec"),
    )
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "tread://schemas/m1-data-contract-v1",
        "title": "TREAD M1 Match Data Contract",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "schemaVersion": {"type": "string", "const": "Tread.M1.DataContract.v1"},
            "matchId": string,
            "seed": {"type": "integer"},
            "randomStreamAlgorithm": {"type": "string", "const": "UE.FRandomStream.v1"},
            "randomStreamState": {"type": "integer"},
            "mode": enum(("FreeCompetition",)),
            "phase": enum(("MainMenu", "R0Briefing", "PreMatchBP", "Preparation", "Battle", "Settlement", "GameOver")),
            "roundIndex": {"type": "integer", "minimum": 0, "maximum": 12},
            "roundType": enum(("Briefing", "PvE", "PvP", "Leader")),
            "phaseTimeRemainingSec": {"type": "number", "minimum": 0},
            "rules": {"$ref": "#/$defs/matchRules"},
            "players": {"type": "array", "minItems": 4, "maxItems": 4, "items": {"$ref": "#/$defs/playerState"}},
            "strategies": {"type": "array", "minItems": 32, "maxItems": 32, "items": {"$ref": "#/$defs/strategyState"}},
            "bp": {"$ref": "#/$defs/bpState"},
            "poolLedger": {"$ref": "#/$defs/poolLedger"},
            "scoutSnapshots": {"type": "array", "minItems": 4, "maxItems": 4, "items": {"$ref": "#/$defs/scoutSnapshot"}},
            "lastBattleResult": {"$ref": "#/$defs/battleResult"},
            "battleEvents": {"type": "array", "items": {"$ref": "#/$defs/battleEvent"}},
        },
        "required": ("schemaVersion", "matchId", "seed", "randomStreamAlgorithm", "randomStreamState", "mode", "phase", "roundIndex", "roundType", "phaseTimeRemainingSec",
                      "rules", "players", "strategies", "bp", "poolLedger", "scoutSnapshots", "lastBattleResult", "battleEvents"),
        "$defs": {
            "unitInstance": unit,
            "shopSlot": shop_slot,
            "shopState": shop,
            "playerState": player,
            "strategyState": strategy,
            "bpState": bp,
            "pactStack": pact_stack,
            "scoutSnapshot": scout,
            "ledgerEntry": ledger,
            "poolBalance": pool_balance,
            "poolLedger": obj(
                {"revision": nonnegative,
                 "balances": {"type": "array", "minItems": 192, "maxItems": 192, "items": {"$ref": "#/$defs/poolBalance"}},
                 "entries": {"type": "array", "items": {"$ref": "#/$defs/ledgerEntry"}}},
                required=("revision", "balances", "entries"),
            ),
            "levelRule": level_rule,
            "matchRules": rules,
            "battlePairing": pairing,
            "battleOutcome": outcome,
            "incomeBreakdown": income,
            "battleResult": battle_result,
            "battleEvent": battle_event,
        },
    }


def make_sample():
    source = json.loads(STRATEGY_SOURCE.read_text(encoding="utf-8"))
    strategies = source["strategies"]
    if len(strategies) != 32 or len({item["strategyId"] for item in strategies}) != 32:
        raise ValueError("Strategies.json must contain exactly 32 unique strategies")
    players = []
    snapshots = []
    for index in range(4):
        pid = f"P{index}"
        slots = [
            {"slotIndex": slot, "characterId": f"placeholder_char_{index + 1:02d}_{slot + 1:02d}", "operatorTier": "I",
             "cost": 1, "isSold": False, "isLockedByPlayer": False}
            for slot in range(5)
        ]
        player = {
            "playerId": pid,
            "displayName": "玩家" if index == 0 else f"AI-{index}",
            "isHuman": index == 0,
            "isEliminated": False,
            "rank": 0,
            "health": 100,
            "funds": 5,
            "level": 3,
            "experience": 0,
            "experienceToNextLevel": 6,
            "populationUsed": 0,
            "populationLimit": 3,
            "winStreak": 0,
            "lossStreak": 0,
            "initialStrategyId": None,
            "nextRoundIncome": {"base": 5, "interest": 0, "streak": 0, "other": 0},
            "shop": {"slots": slots, "locked": False, "lockMode": "AutoRefreshOnly", "refreshCost": 2, "refreshIndex": 0},
            "benchUnitInstanceIds": [None] * 8,
            "benchUnits": [],
            "boardUnits": [],
            "equipmentIds": [],
            "activePactIds": [],
        }
        players.append(player)
        snapshots.append({
            "playerId": pid, "displayName": player["displayName"], "rank": 0, "health": 100,
            "funds": 5, "level": 3, "populationUsed": 0, "populationLimit": 3,
            "nextRoundIncome": {"base": 5, "interest": 0, "streak": 0, "other": 0},
            "boardUnits": [], "benchUnitInstanceIds": [None] * 8, "benchUnits": [],
            "equipmentIds": [], "activePactIds": [], "pactStacks": [], "readOnly": True,
        })
    tier_totals = {"I": 12, "II": 14, "III": 18, "IV": 16, "V": 8, "VI": 5}
    tiers = list(tier_totals)
    balances = [
        {"characterId": f"char_{character:03d}", "operatorTier": tier,
         "poolCopiesTotal": tier_totals[tier], "poolCopiesAvailable": tier_totals[tier],
         "reservedCopies": 0, "ownedCopies": 0}
        for character in range(1, 33) for tier in tiers
    ]
    initialize_entries = [
        {"entryId": f"ledger_{index + 1:06d}", "revision": index + 1, "action": "Initialize", "playerId": None,
         "characterId": balance["characterId"], "operatorTier": balance["operatorTier"], "unitInstanceId": None,
         "cloneInstanceId": None, "copySourceCharacterId": None, "poolCopiesTotal": balance["poolCopiesTotal"],
         "poolCopiesAvailable": balance["poolCopiesAvailable"], "reservedCopies": 0, "ownedCopies": 0, "delta": 0}
        for index, balance in enumerate(balances)
    ]
    return {
        "schemaVersion": "Tread.M1.DataContract.v1",
        "matchId": "m1-contract-sample-20261004",
        "seed": 20260926,
        "randomStreamAlgorithm": "UE.FRandomStream.v1",
        "randomStreamState": 20260926,
        "mode": "FreeCompetition",
        "phase": "R0Briefing",
        "roundIndex": 0,
        "roundType": "Briefing",
        "phaseTimeRemainingSec": 0,
        "rules": {
            "levelExperienceTable": [
                {"level": 1, "experienceToNextLevel": 2},
                {"level": 2, "experienceToNextLevel": 2},
                {"level": 3, "experienceToNextLevel": 6},
                {"level": 4, "experienceToNextLevel": 10},
                {"level": 5, "experienceToNextLevel": 20},
                {"level": 6, "experienceToNextLevel": 36},
                {"level": 7, "experienceToNextLevel": 56},
                {"level": 8, "experienceToNextLevel": 80},
                {"level": 9, "experienceToNextLevel": 0},
            ],
            "benchPurchasePolicy": "RejectWhenFull",
            "shopLockMode": "AutoRefreshOnly",
            "bpHasCountdown": False,
            "aiSelectionStartsAfterPlayerPick": True,
            "deployCompletesPreparation": True,
            "autoBattleMode": "AlwaysOn",
            "playerEliminationFlow": "DirectSettlement",
            "preparationDurationSec": 30,
            "baseIncome": 5,
            "interestFundsStep": 10,
            "maxInterest": 5,
            "experiencePurchaseCost": 4,
            "experiencePurchaseAmount": 4,
            "shopSlotCount": 5,
            "shopRefreshCost": 2,
            "maxBenchSlots": 8,
        },
        "players": players,
        "strategies": strategies,
        "bp": {
            "candidateCount": 32, "systemBanCount": 4, "playerPickCount": 1, "aiPickCount": 3,
            "aiPickOrder": ["P1", "P2", "P3"], "playerCanReviseUntilAiConfirmed": True,
            "hasCountdown": False, "aiSelectionStartsAfterPlayerPick": True, "seed": 20260926,
            "bannedStrategyIds": [f"strategy_{i:03d}" for i in range(1, 5)],
            "availableStrategyIds": [f"strategy_{i:03d}" for i in range(5, 33)],
            "playerStrategyId": None, "aiStrategyIds": [None, None, None],
            "aiPickStates": ["Waiting", "Waiting", "Waiting"], "confirmed": False,
        },
        "poolLedger": {
            "revision": len(initialize_entries), "balances": balances, "entries": initialize_entries,
        },
        "scoutSnapshots": snapshots,
        "lastBattleResult": {"roundIndex": 0, "pairings": [], "outcomes": [],
                              "incomeBreakdown": {"base": 0, "interest": 0, "streak": 0, "other": 0},
                              "eliminatedPlayerIds": []},
        "battleEvents": [],
    }


def make_command_result_schema():
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "tread://schemas/m1-command-result-v1",
        "title": "TREAD M1 Command Result",
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "bAccepted": {"type": "boolean"},
            "reasonCode": {"type": "string", "enum": list(REJECT_REASONS)},
            "requestId": {"type": "string"},
        },
        "required": ["bAccepted", "reasonCode", "requestId"],
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "M1_DataContract.schema.json").write_text(json.dumps(make_schema(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "M1_DataContract.sample.json").write_text(json.dumps(make_sample(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "M1_CommandResult.schema.json").write_text(json.dumps(make_command_result_schema(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUT / "M1_CommandResult.sample.json").write_text(json.dumps({
        "bAccepted": False, "reasonCode": "BenchFull", "requestId": "req-m1-sample-0001"
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"M1_DATA_CONTRACT_SCHEMA={OUT / 'M1_DataContract.schema.json'}")
    print(f"M1_DATA_CONTRACT_SAMPLE={OUT / 'M1_DataContract.sample.json'}")
    print(f"M1_COMMAND_RESULT_SCHEMA={OUT / 'M1_CommandResult.schema.json'}")
    print(f"M1_COMMAND_RESULT_SAMPLE={OUT / 'M1_CommandResult.sample.json'}")


if __name__ == "__main__":
    main()
