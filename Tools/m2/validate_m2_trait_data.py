#!/usr/bin/env python3
"""Validate M2 pact/trait data and write Saved/Reports/M2_Trait_Data_Validation.json.

Fails (exit 1) on schema/foreign-key problems; reference-sheet differences are reported, never patched.
Run after generate_m2_pact_trait_data.py:  python Tools/m2/validate_m2_trait_data.py
"""
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GEN = ROOT / "Content/Data/Generated"
OUT = ROOT / "Saved/Reports/M2_Trait_Data_Validation.json"

CORE = ["炎", "萨尔贡", "维多利亚", "谢拉格", "拉特兰", "阿戈尔", "叙拉古", "卡西米尔"]
ADJUNCT = ["精准", "迅捷", "灵巧", "奥术", "坚守", "助力", "远见", "奇迹", "投资人", "突袭", "不屈", "调和", "协防", "独行", "绝技"]
REQUIRED_TRIGGERS = ["Acquire", "RoundStart", "RoundEnd", "Battle", "Sell"]
TRAIT_FIELDS = ["id", "cardId", "rarity", "corePacts", "adjunctPacts", "trigger", "triggerCondition", "stackMode", "targets",
                "baseValue", "eliteValue", "scalePerStack", "stackCap", "activationRequired", "repeatCount", "sourcePattern",
                "effects", "displayText", "valueText", "runtimeSupport"]
KNOWN_OPS = {"AddStacks", "GainFundsNextRound", "GainFunds", "GrantItem", "GrantUnit", "TriggerTraits", "PurchaseCostOverride",
             "CombineCopies", "StackScaledStat", "FlatStat", "EnemyTagAttack", "WeaknessDamage", "HealPercent",
             "AmplifyFrontStackGain", "AcquireRepeat", "HarmonyCountsAsActiveCore", "CombatFlat", "PactThresholdDelta",
             "PactCountsBench"}


def load(name):
    return json.loads((GEN / name).read_text(encoding="utf-8"))


def norm(text):
    """Collapse formatting-only differences ("+2[+4]" vs "+2/+4", brackets, filler words) between the two workbooks."""
    t = (text or "").replace("阿格尔", "阿戈尔").replace("回合开始", "进入休整期").replace("回合结束", "休整期结束")
    t = re.sub(r"[\s（）()“”\"'，,。.\[\]【】<>/+%×、：:]", "", t)
    for filler in ("无需激活盟约", "无需激活", "已激活的", "已激活", "所属", "的", "使", "盟约", "干员", "层数", "时"):
        t = t.replace(filler, "")
    return t


def numbers(text):
    """Sorted numeric tokens of a trait text; percentages and multipliers normalised (100% == 1)."""
    values = []
    for raw, pct in re.findall(r"(\d+(?:\.\d+)?)(%?)", text or ""):
        v = float(raw) / (100 if pct and float(raw) >= 100 else 1)
        values.append(v)
    return sorted(values)


def main():
    errors, warnings = [], []
    pacts = load("Pacts.json")
    traits = load("Traits.json")
    items = load("M2_ItemSeeds.json")
    strategies = load("StrategyEffects.json")
    roster = load("CharacterRosterMap.json")
    snapshot = json.loads((ROOT / "Content/Data/Source/M2_PactReference_Snapshot.json").read_text(encoding="utf-8"))

    # ---- pacts
    pact_ids = [p["pactId"] for p in pacts["pacts"]]
    core = [p["pactId"] for p in pacts["pacts"] if p["kind"] == "Core"]
    adjunct = [p["pactId"] for p in pacts["pacts"] if p["kind"] == "Adjunct"]
    if core != CORE:
        errors.append("core pacts %s != canonical %s" % (core, CORE))
    if adjunct != ADJUNCT:
        errors.append("adjunct pacts %s != canonical %s" % (adjunct, ADJUNCT))
    threshold_table = []
    for p in pacts["pacts"]:
        t = p["thresholds"]
        if not t or any(x <= 0 for x in t) or t != sorted(set(t)):
            errors.append("pact %s thresholds not strictly ascending positive: %s" % (p["pactId"], t))
        default = [3, 6] if p["kind"] == "Core" else [2, 3]
        threshold_table.append({"pactId": p["pactId"], "kind": p["kind"], "thresholds": t,
                                "special": t != default, "source": p["thresholdSource"], "sourceStatus": p["sourceStatus"],
                                "countsBench": p["countsBench"]})
    missing_pacts = [p["pactId"] for p in pacts["pacts"] if p["sourceStatus"] != "reference"]

    # ---- cards / traits
    roster_ids = [c["characterId"] for c in roster["characters"]]
    cards = traits["cards"]
    card_ids = [c["characterId"] for c in cards]
    if card_ids != roster_ids:
        errors.append("Traits.json card ids do not match CharacterRosterMap order/set")
    trait_ids, trigger_cover, support = set(), {}, {}
    ops_used = {}
    item_names = {i["displayName"] for i in items["items"]}
    value_text_ok = 0
    for c in cards:
        if not c["traits"]:
            errors.append("%s has no trait" % c["characterId"])
        for p in c["corePacts"] + c["adjunctPacts"]:
            if p not in pact_ids:
                errors.append("%s references unknown pact %s" % (c["characterId"], p))
        for p in c["corePacts"]:
            if p not in CORE:
                errors.append("%s core pact %s is not a core pact" % (c["characterId"], p))
        for p in c["adjunctPacts"]:
            if p not in ADJUNCT:
                errors.append("%s adjunct pact %s is not an adjunct pact" % (c["characterId"], p))
        for t in c["traits"]:
            missing = [f for f in TRAIT_FIELDS if f not in t]
            if missing:
                errors.append("%s missing fields %s" % (t.get("id"), missing))
            if t["id"] in trait_ids:
                errors.append("duplicate trait id %s" % t["id"])
            trait_ids.add(t["id"])
            trigger_cover.setdefault(t["trigger"], []).append(c["characterId"])
            support.setdefault(t["runtimeSupport"], []).append(c["characterId"])
            if t["valueText"] and re.fullmatch(r"-?[\d.]+/-?[\d.]+", t["valueText"]):
                value_text_ok += 1
            for e in t["effects"]:
                ops_used[e["op"]] = ops_used.get(e["op"], 0) + 1
                if e["op"] not in KNOWN_OPS:
                    errors.append("%s uses op %s unknown to the C++ interpreter" % (t["id"], e["op"]))
                for p in e.get("pacts", []):
                    if p not in pact_ids:
                        errors.append("%s effect references unknown pact %s" % (t["id"], p))
                for name in [e.get("item")] + e.get("itemChoices", []) + [e.get("rareItem")]:
                    if name and name not in item_names:
                        errors.append("%s grants unknown item %s" % (t["id"], name))
                if "baseValue" not in e or "eliteValue" not in e:
                    errors.append("%s effect %s lacks baseValue/eliteValue" % (t["id"], e["op"]))
    for trig in REQUIRED_TRIGGERS:
        if trig not in trigger_cover:
            errors.append("no trait with trigger %s" % trig)

    # stacking modes required by the M2 acceptance list
    def any_trait(pred):
        return [c["characterId"] for c in cards for t in c["traits"] if pred(t)]
    stack_modes = {
        "acquire": any_trait(lambda t: t["trigger"] == "Acquire" and any(e["op"] == "AddStacks" for e in t["effects"])),
        "roundEnd": any_trait(lambda t: t["trigger"] == "RoundEnd" and any(e["op"] == "AddStacks" for e in t["effects"])),
        "kill": any_trait(lambda t: t["triggerCondition"].get("event") == "Kill"),
        "ammoOrSkill": any_trait(lambda t: t["triggerCondition"].get("event") in ("AmmoConsumed", "SkillActivated")),
        "sameRowOrNeighbour": any_trait(lambda t: t["triggerCondition"].get("sameRowAtLeast") or t["targets"] in ("SelfAndBehind1", "SelfAndFront1", "Front1", "Front2", "FrontColumn")),
        "equipment": [i["displayName"] for i in items["items"] if i["providesPacts"]],
        "sell": any_trait(lambda t: t["trigger"] == "Sell"),
        "noActivationRequired": any_trait(lambda t: not t["activationRequired"]),
    }
    for mode, hits in stack_modes.items():
        if not hits:
            errors.append("no data for stacking mode %s" % mode)

    # ---- strategies
    if len(strategies["strategies"]) != 32:
        errors.append("StrategyEffects.json has %d strategies, expected 32" % len(strategies["strategies"]))
    strategy_applied = [s["strategyId"] for s in strategies["strategies"] if any(e["op"] for e in s["effects"])]
    strategy_deferred = [s["strategyId"] for s in strategies["strategies"] if not any(e["op"] for e in s["effects"])]
    dispatched = {"MatchStart", "RoundStart", "RoundEnd", "BattleStart", "BattleEnd", "Settlement", "Sell", "Combine", "ShopRefresh", "BuyExperience"}
    not_dispatched = sorted({s["trigger"] for s in strategies["strategies"]} - dispatched)

    # ---- reference diff (95 rows vs 100 cards)
    ops = snapshot["operators"]
    by_assign = {}
    for c in cards:
        by_assign.setdefault(c["assignment"], []).append(c["characterId"])
    used_refs = {c["referenceOperatorName"] for c in cards if c["referenceOperatorName"]}
    unused_refs = [o["operatorName"] for o in ops if o["operatorName"] not in used_refs]
    # The notes workbook paraphrases every row, so only numeric disagreement is a real data difference.
    alt_diff = [{"operator": o["operatorName"], "quickTable": o["traitText"], "notesTable": o["alternateTraitText"],
                 "quickNumbers": numbers(o["traitText"]), "notesNumbers": numbers(o["alternateTraitText"])}
                for o in ops if o["alternateTraitText"] and numbers(o["alternateTraitText"]) != numbers(o["traitText"])]
    no_alt = [o["operatorName"] for o in ops if not o["alternateTraitText"]]
    reference_diff = {
        "referenceRowsQuickTable": len(ops),
        "quickTableTitleClaims": "96 名（表头）; 实际有效干员行 95",
        "cards": len(cards),
        "nameMatched": [{"characterId": c["characterId"], "operator": c["referenceOperatorName"]} for c in cards if c["assignment"] == "name-match"],
        "provisionalOrderCount": len(by_assign.get("provisional-order", [])),
        "supplementCards": [{"characterId": c["characterId"], "corePacts": c["corePacts"], "adjunctPacts": c["adjunctPacts"],
                             "trait": c["traits"][0]["displayText"]} for c in cards if c["assignment"] == "supplement"],
        "unusedReferenceRows": unused_refs,
        "missingPactsInBothWorkbooks": missing_pacts,
        "planThresholdClaimsNotInSheet": ["施工计划称炎/阿戈尔等有 5/9、1/2、2/5 档；资料整理表实际为 炎 3/6、阿戈尔 3/5、调和 1、协防/投资人 3、迅捷/灵巧/远见/奇迹/突袭 2；运行时以表为准"],
        "numericDifferencesBetweenWorkbooks": len(alt_diff),
        "numericDifferences": alt_diff,
        "operatorsWithoutAlternateWording": no_alt,
        "note": "100 卡为运行时全集；95 条参考行按 provenance 绑定（1 同名、94 暂定顺序），5 张补位卡承载两表缺失的 5 个盟约；均待 M4 权威名册闭合",
    }

    report = {
        "schema": "Tread.M2.TraitDataValidation.v1",
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "inputs": {name: hashlib.sha256((GEN / name).read_bytes()).hexdigest()
                   for name in ("Pacts.json", "Traits.json", "M2_ItemSeeds.json", "StrategyEffects.json")},
        "pacts": {"core": len(core), "adjunct": len(adjunct), "table": threshold_table, "missingInReference": missing_pacts},
        "cards": {"total": len(cards), "withTrait": sum(1 for c in cards if c["traits"]), "traits": len(trait_ids),
                  "valueTextXY": value_text_ok,
                  "triggerCoverage": {k: len(v) for k, v in sorted(trigger_cover.items())},
                  "requiredTriggersPresent": all(t in trigger_cover for t in REQUIRED_TRIGGERS),
                  "runtimeSupport": {k: {"count": len(v), "cards": v if k != "applied" else None} for k, v in sorted(support.items())},
                  "opsUsed": dict(sorted(ops_used.items()))},
        "stackModes": {k: v[:8] for k, v in stack_modes.items()},
        "strategyBus": {"strategies": len(strategies["strategies"]), "withRuntimeOp": strategy_applied,
                        "loggedDeferredM4": strategy_deferred, "triggersNotDispatchedInM2": not_dispatched},
        "items": [{"displayName": i["displayName"], "providesPacts": i["providesPacts"], "effectStatus": i["effectStatus"]} for i in items["items"]],
        "referenceDiff": reference_diff,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("M2_TRAIT_DATA_VALIDATION=%s errors=%d -> %s" % ("PASS" if not errors else "FAIL", len(errors), OUT))
    for e in errors[:20]:
        print("  ERROR", e)
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
