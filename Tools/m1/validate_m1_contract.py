"""Deterministic, dependency-free validation for the generated M1 sample state."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SAMPLE = ROOT / "Content" / "Data" / "Generated" / "M1_DataContract.sample.json"
STRATEGIES = ROOT / "Content" / "Data" / "Strategies.json"
ROSTER_MAP = ROOT / "Content" / "Data" / "Generated" / "CharacterRosterMap.json"
COMMAND_SCHEMA = ROOT / "Content" / "Data" / "Generated" / "M1_CommandResult.schema.json"
COMMAND_SAMPLE = ROOT / "Content" / "Data" / "Generated" / "M1_CommandResult.sample.json"
REPORT = ROOT / "Saved" / "Reports" / "M1_DataContract_Validation.json"
POOL_TOTALS = {"I": 12, "II": 14, "III": 18, "IV": 16, "V": 8, "VI": 5}


def fail(errors, message):
    errors.append(message)


def validate_strategy_issuer_foreign_keys(source, roster):
    errors = []
    strategies = source.get("strategies") if isinstance(source, dict) else None
    characters = roster.get("characters") if isinstance(roster, dict) else None
    if not isinstance(strategies, list) or len(strategies) != 32 or not all(isinstance(row, dict) for row in strategies):
        fail(errors, "Strategies.json must contain exactly 32 strategy objects")
        return errors
    if not isinstance(characters, list) or len(characters) != 100 or not all(isinstance(row, dict) for row in characters):
        fail(errors, "CharacterRosterMap.json must contain exactly 100 character objects")
        return errors

    character_ids = [row.get("characterId") for row in characters]
    roster_ids = {value for value in character_ids if isinstance(value, str) and value.strip()}
    if len(roster_ids) != 100:
        fail(errors, "CharacterRosterMap.json characterId values must be nonempty and unique")
    for strategy in strategies:
        issuer = strategy.get("issuerCharacterId")
        if not isinstance(issuer, str) or not issuer.strip() or issuer not in roster_ids:
            fail(errors, f"{strategy.get('strategyId', '<missing strategyId>')}: issuerCharacterId must reference a roster characterId")
    return errors


def validate(data):
    errors = []
    if data.get("schemaVersion") != "Tread.M1.DataContract.v1":
        fail(errors, "schemaVersion must be Tread.M1.DataContract.v1")
    if data.get("randomStreamAlgorithm") != "UE.FRandomStream.v1":
        fail(errors, "randomStreamAlgorithm must be UE.FRandomStream.v1")
    if not isinstance(data.get("randomStreamState"), int):
        fail(errors, "randomStreamState must be an integer")
    if data.get("mode") != "FreeCompetition":
        fail(errors, "mode must be FreeCompetition")
    if not isinstance(data.get("seed"), int) or data["seed"] < 0:
        fail(errors, "seed must be a non-negative integer")
    if data.get("bp", {}).get("seed") != data.get("seed"):
        fail(errors, "bp.seed must equal match seed for replay determinism")
    rules = data.get("rules", {})
    if rules.get("benchPurchasePolicy") != "RejectWhenFull":
        fail(errors, "bench purchase policy must reject purchases when the bench is full")
    if rules.get("shopLockMode") != "AutoRefreshOnly":
        fail(errors, "shop lock mode must preserve slots only across automatic refresh")
    if rules.get("bpHasCountdown") is not False:
        fail(errors, "BP must not have a countdown")
    if rules.get("aiSelectionStartsAfterPlayerPick") is not True:
        fail(errors, "AI selection must start after the player picks")
    if rules.get("deployCompletesPreparation") is not True or rules.get("autoBattleMode") != "AlwaysOn":
        fail(errors, "Deploy completes preparation and battle is always automatic")
    if rules.get("playerEliminationFlow") != "DirectSettlement":
        fail(errors, "player elimination must go directly to settlement")
    economy_rules = {
        "preparationDurationSec": 30,
        "baseIncome": 5,
        "interestFundsStep": 10,
        "maxInterest": 5,
        "experiencePurchaseCost": 4,
        "experiencePurchaseAmount": 4,
        "shopSlotCount": 5,
        "shopRefreshCost": 2,
        "maxBenchSlots": 8,
    }
    for key, expected in economy_rules.items():
        if rules.get(key) != expected:
            fail(errors, f"rules.{key} must be {expected}")
    level_rules = rules.get("levelExperienceTable", [])
    if len(level_rules) != 9 or [item.get("level") for item in level_rules] != list(range(1, 10)):
        fail(errors, "levelExperienceTable must contain levels 1..9 in order")
    players = data.get("players", [])
    if len(players) != 4:
        fail(errors, "players must contain exactly 4 participants")
    player_ids = [p.get("playerId") for p in players]
    if len(set(player_ids)) != len(player_ids):
        fail(errors, "playerId values must be unique")
    for player in players:
        if len(player.get("shop", {}).get("slots", [])) != 5:
            fail(errors, f"{player.get('playerId')}: shop must contain exactly 5 slots")
        if player.get("shop", {}).get("lockMode") != "AutoRefreshOnly":
            fail(errors, f"{player.get('playerId')}: shop lock mode mismatch")
        if len(player.get("benchUnitInstanceIds", [])) != 8:
            fail(errors, f"{player.get('playerId')}: bench must contain exactly 8 slots")
        if len(player.get("benchUnits", [])) > 8:
            fail(errors, f"{player.get('playerId')}: benchUnits exceeds 8 units")
        if player.get("level", 0) < 1 or player.get("level", 0) > 9:
            fail(errors, f"{player.get('playerId')}: level outside 1..9")
        if player.get("populationUsed", 0) > player.get("populationLimit", 0):
            fail(errors, f"{player.get('playerId')}: population exceeds limit")
        income = player.get("nextRoundIncome", {})
        if income.get("base") != 5 or income.get("interest", 0) > 5:
            fail(errors, f"{player.get('playerId')}: nextRoundIncome base/interest mismatch")
        if set(income) != {"base", "interest", "streak", "other"}:
            fail(errors, f"{player.get('playerId')}: nextRoundIncome must be a full breakdown")
        for unit in player.get("boardUnits", []):
            if unit.get("unitStar") not in (1, 2, 3):
                fail(errors, f"{player.get('playerId')}: unitStar must be 1..3")
            if unit.get("operatorTier") not in ("I", "II", "III", "IV", "V", "VI"):
                fail(errors, f"{player.get('playerId')}: operatorTier must be I..VI")
            if unit.get("isTransformClone") and not unit.get("cloneInstanceId"):
                fail(errors, f"{player.get('playerId')}: clone needs cloneInstanceId")
            if unit.get("isTransformClone") and not unit.get("copySourceCharacterId"):
                fail(errors, f"{player.get('playerId')}: clone needs copySourceCharacterId")
    bp = data.get("bp", {})
    strategies = {s.get("strategyId") for s in data.get("strategies", [])}
    banned = bp.get("bannedStrategyIds", [])
    available = bp.get("availableStrategyIds", [])
    if len(strategies) != 32:
        fail(errors, "strategies must contain exactly 32 unique IDs")
    for strategy in data.get("strategies", []):
        if not strategy.get("offerText") or "placeholder" in strategy.get("offerText", "").lower():
            fail(errors, f"{strategy.get('strategyId')}: formal strategy text is missing")
        if not strategy.get("effects") or strategy.get("uniqueScope") != "StrategyId":
            fail(errors, f"{strategy.get('strategyId')}: formal strategy effects or unique scope is missing")
    try:
        source = json.loads(STRATEGIES.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        fail(errors, f"Strategies.json is missing or invalid: {exc}")
    else:
        source_rows = source.get("strategies") if isinstance(source, dict) else None
        source_ids = {item.get("strategyId") for item in source_rows if isinstance(item.get("strategyId"), str)} if isinstance(source_rows, list) and all(isinstance(item, dict) for item in source_rows) else set()
        if len(source_ids) != 32 or source_ids != strategies:
            fail(errors, "Strategies.json must contain the same 32 strategy IDs as the snapshot")
        try:
            roster = json.loads(ROSTER_MAP.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            fail(errors, f"CharacterRosterMap.json is missing or invalid: {exc}")
        else:
            errors.extend(validate_strategy_issuer_foreign_keys(source, roster))
    if len(banned) != 4 or len(set(banned)) != 4:
        fail(errors, "BP must contain exactly 4 unique BAN IDs")
    if len(available) != 28 or len(set(available)) != 28:
        fail(errors, "BP must contain exactly 28 unique available IDs")
    if set(banned) & set(available):
        fail(errors, "BP banned and available IDs must be disjoint")
    if set(banned) | set(available) != strategies:
        fail(errors, "BP IDs must partition the 32 strategy IDs")
    chosen = [bp.get("playerStrategyId")] + bp.get("aiStrategyIds", [])
    chosen = [value for value in chosen if value is not None]
    if len(chosen) != len(set(chosen)):
        fail(errors, "BP chosen strategy IDs must be unique")
    if set(chosen) - set(available):
        fail(errors, "BP chosen strategies must come from available IDs")
    if len(bp.get("aiPickStates", [])) != 3 or any(state not in ("Waiting", "Thinking", "Selected", "Confirmed") for state in bp.get("aiPickStates", [])):
        fail(errors, "BP must expose one valid AI pick state per AI")
    snapshots = data.get("scoutSnapshots", [])
    if len(snapshots) != 4 or {s.get("playerId") for s in snapshots} != set(player_ids):
        fail(errors, "ScoutSnapshot must contain one read-only snapshot per participant")
    for snapshot in snapshots:
        if snapshot.get("readOnly") is not True:
            fail(errors, f"{snapshot.get('playerId')}: ScoutSnapshot must be read-only")
        if "shop" in snapshot or "hiddenState" in snapshot or "unpublishedStrategyIds" in snapshot:
            fail(errors, f"{snapshot.get('playerId')}: ScoutSnapshot leaks hidden state")
        if not {"populationUsed", "populationLimit", "nextRoundIncome"}.issubset(snapshot):
            fail(errors, f"{snapshot.get('playerId')}: ScoutSnapshot economy HUD fields missing")
    entries = data.get("poolLedger", {}).get("entries", [])
    if not isinstance(data.get("poolLedger"), dict):
        fail(errors, "poolLedger must be an object with revision and entries")
    if not isinstance(entries, list):
        fail(errors, "poolLedger.entries must be an array")
        entries = []
    ledger = data.get("poolLedger", {})
    if ledger.get("revision", -1) < 0:
        fail(errors, "PoolLedger revision must be non-negative")
    balances = ledger.get("balances", [])
    if len(balances) != 32 * 6:
        fail(errors, "PoolLedger must contain 32 characterId x 6 operatorTier balances")
    keys = set()
    for balance in balances:
        key = (balance.get("characterId"), balance.get("operatorTier"))
        if key in keys:
            fail(errors, f"PoolLedger duplicate balance key: {key[0]}+{key[1]}")
        keys.add(key)
        tier = balance.get("operatorTier")
        expected = POOL_TOTALS.get(tier)
        if expected is None or balance.get("poolCopiesTotal") != expected:
            fail(errors, f"PoolLedger {key[0]}+{tier}: total must be {expected}")
        available = balance.get("poolCopiesAvailable", -1)
        reserved = balance.get("reservedCopies", -1)
        owned = balance.get("ownedCopies", -1)
        if min(available, reserved, owned) < 0 or available + reserved + owned != balance.get("poolCopiesTotal"):
            fail(errors, f"PoolLedger {key[0]}+{tier}: available + reserved + owned must equal total")
    for entry in entries:
        if entry.get("poolCopiesAvailable", 0) > entry.get("poolCopiesTotal", 0):
            fail(errors, f"{entry.get('entryId')}: PoolLedger available copies exceed total")
        if min(entry.get("reservedCopies", 0), entry.get("ownedCopies", 0)) < 0:
            fail(errors, f"{entry.get('entryId')}: PoolLedger bucket cannot be negative")
        if entry.get("poolCopiesAvailable", 0) + entry.get("reservedCopies", 0) + entry.get("ownedCopies", 0) != entry.get("poolCopiesTotal", 0):
            fail(errors, f"{entry.get('entryId')}: PoolLedger buckets do not conserve total")
        if entry.get("action") in ("CloneCreate", "CloneDestroy"):
            if not entry.get("cloneInstanceId"):
                fail(errors, f"{entry.get('entryId')}: clone ledger entries need cloneInstanceId")
            if not entry.get("copySourceCharacterId"):
                fail(errors, f"{entry.get('entryId')}: clone ledger entries need copySourceCharacterId")
            if entry.get("delta") != 0:
                fail(errors, f"{entry.get('entryId')}: clone ledger entries must have zero pool delta")
    result = data.get("lastBattleResult", {})
    if not isinstance(result.get("pairings", []), list) or not isinstance(result.get("outcomes", []), list):
        fail(errors, "lastBattleResult pairings and outcomes must be arrays")
    for event in data.get("battleEvents", []):
        if event.get("eventType") not in ("UnitDamaged", "UnitDied", "UnitTargetChanged"):
            fail(errors, f"{event.get('eventId')}: invalid battle event type")
    return errors


def validate_command_contract():
    errors = []
    schema = json.loads(COMMAND_SCHEMA.read_text(encoding="utf-8"))
    sample = json.loads(COMMAND_SAMPLE.read_text(encoding="utf-8"))
    reasons = schema.get("properties", {}).get("reasonCode", {}).get("enum", [])
    if len(reasons) != len(set(reasons)) or "None" not in reasons or "Unknown" not in reasons:
        fail(errors, "command result reason codes must be unique and include None/Unknown")
    if set(sample) != {"bAccepted", "reasonCode", "requestId"}:
        fail(errors, "command result sample must include acceptance, reason code and request id")
    if sample.get("reasonCode") not in reasons:
        fail(errors, "command result sample uses an unknown reason code")
    if sample.get("bAccepted") is not False and sample.get("reasonCode") != "None":
        fail(errors, "accepted command results must use reasonCode=None")
    if sample.get("bAccepted") is False and sample.get("reasonCode") == "None":
        fail(errors, "rejected command results must provide a reason code")
    return errors


def main():
    data = json.loads(SAMPLE.read_text(encoding="utf-8"))
    errors = validate(data) + validate_command_contract()
    result = {
        "schema": "Tread.M1.DataContract.Validation.v1",
        "ok": not errors,
        "sample": str(SAMPLE),
        "errors": errors,
        "checks": [
            "four participants",
            "five shop slots and eight bench slots",
            "operatorTier separated from unitStar",
            "32 strategy BP partition with four bans",
            "formal Strategies.json source and per-AI pick states",
            "32 strategy issuerCharacterId keys reference 100 unique roster characterId values",
            "level experience, bench purchase, shop lock, deployment and elimination rules",
            "BattleResult, BattleEvent and command rejection contract",
            "standalone command-result schema and rejection sample",
            "read-only ScoutSnapshot without hidden state",
            "PoolLedger copy bounds",
            "PoolLedger 32x6 shared balances and conservation buckets",
            "UE.FRandomStream algorithm and state",
        ],
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("M1_DATA_CONTRACT_VALIDATION=" + ("PASS" if result["ok"] else "FAIL"))
    print("M1_DATA_CONTRACT_REPORT=" + str(REPORT))
    if errors:
        for error in errors:
            print("ERROR:", error)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
