#!/usr/bin/env python3
"""N1/N2 data import: Stronghold-Protocol (网页《卫戍协议：盟约》复刻) numbers -> Tread runtime data.

Owner decision 2026-10-08 (doc 143 §4): take its operators, pacts, numbers, equipment and strategies; keep Tread's
match structure (4-player free competition, 12 rounds, PvP, 8 bench slots, 100 base health). Non-commercial fan
project. Only the DATA is used (Hypergryph-derived, non-commercial); none of its GPL-3.0 code is copied.

Input (read-only, staged by hand from codeload.github.com, see doc 143 §1):
  Saved/Staging/ref/Stronghold-Protocol-HEAD/data/{chess,bonds,bands,items,garrisons,choices,config}.json
  Content/Data/Source/Roster100_Models.json           the 100 existing character models (char_001..char_100)
  Content/Data/Source/Roster112_Models.json           the 12 MMD models (char_101..char_112), written by this script
                                                      when missing; owner-editable
  Content/Data/Source/Roster112_Overrides.json         optional {"char_007": "chess_char_3_05_a", ...} pinning a
                                                      model to an operator; the rest are paired deterministically.
                                                      2026-10-14: char_070 (the Muelsyse/Modernia model) <-> char_103
                                                      swapped so the 缪尔赛思 model plays operator 缪尔赛思 (M4 checklist)
Output:
  Content/Data/Source/StrongholdProtocol/Snapshot.json  provenance (commit, sha256 of every input) + trimmed records
  Content/Data/Generated/Roster112.json                 112 model <-> operator bindings (tier, price, copies, stats)
  Content/Data/Generated/Economy.json                   income / upgrade / shop / pool numbers (mode_multi_normal)
  Content/Data/Generated/Pacts.json                     23 pacts (same schema as M2, real thresholds and per-stack numbers)
  Content/Data/Generated/Traits.json                    112 cards with garrison traits as event-bus ops (M2 schema)
  Content/Data/Generated/M2_ItemSeeds.json              56 equipment items (+ pact membership)
  Content/Data/Generated/StrategyEffects.json           40 strategies (bands) -> event-bus ops
  Content/Data/Generated/Strategies40.json              40 strategies for BP (M1 strategy schema)
Deterministic: re-running with unchanged inputs gives byte-identical outputs.

    python Tools/m4/import_stronghold_data.py
"""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SP_DIR = ROOT / "Saved/Staging/ref/Stronghold-Protocol-HEAD"
SP = SP_DIR / "data"
SP_COMMIT = "3eced7bdba5aae11a325bd3dbe66cdf01361d2bd"
SP_ZIP = ROOT / "Saved/Staging/ref/sp.zip"
# Frozen copy of the M1 graybox map; Generated/CharacterRosterMap.json is now the M4 roster map built from this
# script's output by Tools/m4/build_roster_map.py (2026-10-14).
ROSTER100 = ROOT / "Content/Data/Source/Roster100_Models.json"
MMD_MODELS = ROOT / "Content/Data/Source/Roster112_Models.json"
OVERRIDES = ROOT / "Content/Data/Source/Roster112_Overrides.json"
OUT_SRC = ROOT / "Content/Data/Source/StrongholdProtocol"
OUT_GEN = ROOT / "Content/Data/Generated"
MODE = "mode_multi_normal"  # 险境模拟, the 4-player multi mode
TIER_ROMAN = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI"}
PROFESSION_ZH = {"PIONEER": "先锋", "WARRIOR": "近卫", "TANK": "重装", "SNIPER": "狙击", "CASTER": "术士",
                 "MEDIC": "医疗", "SUPPORT": "辅助", "SPECIAL": "特种"}
# The 12 MMD models added by the owner (mmd_12/, 2026-10-08). Archive names are the source of record.
MMD_DEFAULT = [
    ("OTs-14", "少女前线2：追放", "OTs14原皮"), ("代理人", "少女前线2：追放", "_Agent_代理人原皮"),
    ("克莱妲·濯浪焦点", "少女前线2：追放", "克莱妲衣装濯浪焦点"), ("莱娅·女仆", "少女前线2：追放", "莱娅女仆"),
    ("伊洛伊", "异环", "【异环】伊洛伊"), ("明音凛", "异环", "【异环】明音凛"), ("真红", "异环", "【异环】真红"),
    ("黑羽", "异环", "【异环】黑羽"), ("哈索尔", "异环", "哈索尔"), ("小吱", "异环", "小吱"), ("残虹", "异环", "残虹"),
    ("浔", "异环", "【异环】浔"),
]


def load(name):
    return json.loads((SP / (name + ".json")).read_text(encoding="utf-8"))


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clean(text):
    return re.sub(r"<@[^>]*>|</>", "", text or "").strip()


def num(v):
    return int(v) if isinstance(v, float) and v.is_integer() else v


def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")


# --------------------------------------------------------------------------------------------- roster
def roster(chess, models):
    ops = [c for c in chess.values() if not c["isGolden"] and c["visible"] and not c["isHidden"]]
    ops.sort(key=lambda c: (c["tier"], c["shopSortId"], c["chessId"]))
    assert len(ops) == 112, len(ops)
    overrides = json.loads(OVERRIDES.read_text(encoding="utf-8")) if OVERRIDES.exists() else {}
    taken = set(overrides.values())
    free_ops = [o for o in ops if o["chessId"] not in taken]
    # Deterministic pairing: models in (legacy cost, id) order, the 12 new MMD models last, onto operators in
    # (tier, shop order). Cheap legacy models land on low tiers, the new models on the top tiers.
    free_models = [m for m in models if m["characterId"] not in overrides]
    free_models.sort(key=lambda m: (m.get("legacyCost") or 99, m["characterId"]))
    pairing = dict(overrides)
    for m, o in zip(free_models, free_ops):
        pairing[m["characterId"]] = o["chessId"]
    by_id = {o["chessId"]: o for o in ops}
    out = []
    for m in sorted(models, key=lambda m: m["characterId"]):
        o = by_id[pairing[m["characterId"]]]
        out.append((m, o, "override" if m["characterId"] in overrides else "auto-cost-order"))
    return out


# --------------------------------------------------------------------------------------------- traits
TRIGGER = {"SERVER_GAIN": "Acquire", "SERVER_PREP_FIN": "RoundEnd", "SERVER_PREP_START": "RoundStart",
           "SERVER_CHESS_SOLD": "Sell", "SERVER_REFRESH_SHOP": "ShopRefresh", "SERVER_PRICE": "Passive"}
STAT_KEYS = {"atk": "Attack", "def": "Defense", "max_hp": "Health", "attack_speed": "AttackSpeed",
             "respawn_time": "RedeployTime", "sp_recovery_per_sec": "SkillRegen"}


def eff(op, **kw):
    e = {"op": op}
    e.update(kw)
    for k in ("baseValue", "eliteValue"):
        if k in e:
            e[k] = num(e[k])
    return e


def trait_from_garrison(ga, gb, bond_name, item_name, pools, op_name, garrisons):
    """Structured (bb) garrison record -> M2 trait fields. Unknown keys become logged-deferred traits."""
    desc = clean(ga["desc"])
    bb, bbs, bbb = ga["bb"], ga["bbStr"], gb["bb"] if gb else ga["bb"]
    et, key = ga["effectType"], ga["effectKey"]
    bonds = [bond_name[b] for b in (bbs.get("bond") or bbs.get("bond_id") or "").split(",") if b in bond_name]
    trig = TRIGGER.get(ga["eventType"], "Battle")
    res = {"trigger": trig, "triggerCondition": {}, "targets": "Self", "activationRequired": "无需激活" not in desc,
           "worksOnBench": "整备区时也有效" in desc or "整备区也有效" in desc, "repeatCount": 1, "effects": [],
           "runtimeSupport": "applied", "rule": key}
    stacks = lambda sel, b, e, **kw: eff("AddStacks", pactSelector=sel, baseValue=b, eliteValue=e,
                                          amountScale=kw.pop("scale", "Fixed"), **kw)
    cnt = lambda k="count": (bb.get(k, 0), bbb.get(k, 0))
    if bbs.get("conditionkey") == "character_same_row" and "check_count" in bb:
        res["triggerCondition"]["sameRowAtLeast"] = bb["check_count"]
        if "check_count" not in bbb:
            res["triggerCondition"]["eliteIgnoresCondition"] = True
    # ---- server-side (preparation phase) effects
    if et == "SERVER_ADD_BOND_CHESS_ALL":
        res["effects"] = [stacks("OwnPacts" if "自身所属盟约" in desc else "OwnActivePacts", *cnt())]
    elif et == "SERVER_ADD_BOND":
        res["effects"] = [stacks("Pacts", *cnt(), pacts=bonds)]
    elif et == "SERVER_ADD_MULTIPLE_BOND":
        amounts = [int(x) for x in str(bbs.get("count", "")).split(",")]
        res["effects"] = [stacks("Pacts", a, a * 2, pacts=[p]) for p, a in zip(bonds, amounts)]
    elif et == "SERVER_ADD_BOND_METHOD":
        scale = {"round_gain_char": "AcquiredThisRound", "shoplv": "ShopLevel", "hand_count": "BenchCount", "same_bond_diff_lv": "DistinctTiersInPact", "same_row": "SameRowCount"}[bbs["add_method"]]
        res["effects"] = [stacks("Pacts", *cnt("multi"), pacts=bonds, scale=scale)]
    elif et == "SERVER_ADD_BOND_POSITION":
        res["targets"] = "SelfAndBehind1" if bbs.get("dir") == "behind" else "SelfAndFront1"
        res["effects"] = [stacks("TargetActivePacts", *cnt())]
    elif et == "SERVER_ADD_BOND_ACTIVATED_MOST_LAYER":
        res["effects"] = [stacks("HighestActivePact", *cnt())]
    elif et == "SERVER_ADD_ACT_BOND_DIFF_LV_MOST_LAYER":
        res["effects"] = [stacks("HighestActivePact", *cnt("multi"), scale="DistinctTiersInPact")]
    elif et == "SERVER_ADD_BOND_IN_HAND":
        res["targets"] = "Bench"
        res["effects"] = [stacks("TargetActivePacts", *cnt())]
    elif et in ("SERVER_ONCE_GOLD", "SERVER_ONCE_GOLD_WITH_BOND_CONDITION"):
        res["effects"] = [eff("GainFundsNextRound", baseValue=bb["count"], eliteValue=bbb["count"])]
        if bonds:
            res["triggerCondition"]["benchIfAnyActive"] = bonds
    elif et == "SERVER_GAIN_EQUIP":
        res["effects"] = [eff("GrantItem", item=item_name(bbs["chess"]), baseValue=bb["count"], eliteValue=bbb["count"])]
    elif et in ("SERVER_POOL_EQUIP", "SERVER_GAIN_RANDOM_EQUIP_CHESS_IN_POOL"):
        pool = pools[bbs["pool"]]
        names = [item_name(i) for i, _ in pool.get("weighted", [])] or [item_name(i) for i in pool.get("items", [])]
        res["effects"] = [eff("GrantItem", item=names[0] if len(names) == 1 else "随机装备", itemChoices=names,
                              baseValue=bb["count"], eliteValue=bbb["count"])]
        if "round_list" in bbs:
            res["triggerCondition"]["oddRoundsOnly"] = True
    elif et == "SERVER_POOL_CHAR":
        res["effects"] = [eff("GrantUnit", unitSelector="NamedOperators", operators=[op_name(i) for i in pools[bbs["pool"]]["items"]]
                              if "items" in pools[bbs["pool"]] else [op_name(i) for i, _ in pools[bbs["pool"]]["weighted"]],
                              baseValue=bb["count"], eliteValue=bbb.get("count", bb["count"]))]
    elif et == "SERVER_MOST_BOND":
        res["effects"] = [eff("GrantUnit", unitSelector="MostPopulatedPact", baseValue=1, eliteValue=1)]
    elif et == "SERVER_TRIGGER_ANOTHER":
        if bbs.get("scope") == "front":
            res["targets"] = "Front1"
            res["effects"] = [eff("TriggerTraits", triggerFilter="Acquire", baseValue=1, eliteValue=bbb.get("count", 1))]
        else:
            res["targets"] = "TopRightBoardUnit"
            res["effects"] = [eff("TriggerTraits", triggerFilter="RoundEnd", baseValue=1, eliteValue=1)]
    elif et in ("SERVER_FRONT_SAME_EFFECT_PREP_START", "SERVER_FRONT_SAME_EFFECT_PREP_FIN"):
        res["trigger"] = "RoundStart" if et.endswith("START") else "RoundEnd"
        res["targets"] = "Front1"
        res["effects"] = [eff("TriggerTraits", triggerFilter=res["trigger"], anchor="Self", baseValue=1, eliteValue=1)]
    elif et == "SERVER_CHESS_PRICE":
        res["effects"] = [eff("PurchaseCostOverride", baseValue=bb["price"], eliteValue=bbb["price"])]
    elif et == "SERVER_GAIN_FREE_REFRESH_COUNT":
        res["effects"] = [eff("FreeRefresh", baseValue=bb["count"], eliteValue=bbb["count"])]
    elif et == "SERVER_ADD_REFRESH_CNT_MULTIPLIER_BOND_LAYER":
        res["effects"] = [stacks("Pacts", bb["multiplier"], bbb["multiplier"], pacts=bonds, scale="RefreshesThisRound",
                                 capBase=bb["max_layer"], capElite=bbb["max_layer"])]
    elif et == "SERVER_ADD_BOND_ROUND_COIN_COST":
        res["effects"] = [stacks("Pacts", bb["layer"], bbb["layer"], pacts=bonds, scale="FundsSpentThisRound",
                                 scaleDivisor=bb["count"])]
    elif et == "SERVER_GAIN_BOND_LAYER_BY_REFRESH_CNT":
        res["triggerCondition"]["firstOnly"] = True
        res["effects"] = [stacks("Pacts", bb["layer"], bbb["layer"], pacts=bonds)]
    elif et == "SERVER_SELL_CHESS_GAIN_SPECIAL_GOODS":
        res["effects"] = [eff("GrantUnit", unitSelector="TierPool", tierBase=1, tierElite=5, baseValue=1, eliteValue=1)]
    elif et == "NONE" and "只需2个" in desc:
        res["trigger"] = "Passive"
        res["effects"] = [eff("CombineCopies", baseValue=2, eliteValue=2)]
    # ---- in-battle effects
    elif key == "act1autochess_gar_event_addition_cnt":
        res["triggerCondition"].update(event="FrontTraitStackGain", source="Front1")
        res["effects"] = [eff("AmplifyFrontStackGain", baseValue=bb["extra_cnt"], eliteValue=bbb["extra_cnt"])]
    elif et == "GAIN_BUFF":
        res["trigger"] = "Passive"
        stat_b = {k: v for k, v in bb.items() if k in STAT_KEYS}
        stat_e = {k: v for k, v in bbb.items() if k in STAT_KEYS}
        if key == "act1autochess_gar_eff_attrByBond" or key == "act1autochess_gar_eff_respawnTimeByBond":
            res["effects"] = [eff("StackScaledStat", pacts=bonds, perStacks=bb["divide_num"], stat=STAT_KEYS[k],
                                  baseValue=round(abs(v) * (1 if k == "attack_speed" else 100), 4),
                                  eliteValue=round(abs(stat_e.get(k, v)) * (1 if k == "attack_speed" else 100), 4))
                              for k, v in stat_b.items()]
        elif key == "GAIN_BUFF" and {"atk", "max_hp"} <= set(bb):
            res["effects"] = [eff("FlatStat", stat="AttackHealth", baseValue=round((bb["atk"] - 1) * 100, 4),
                                  eliteValue=round((bbb["atk"] - 1) * 100, 4))]
        elif key == "attr_common_global_buff":
            res["effects"] = [eff("FlatStat", stat="SkillRegen", baseValue=bb["sp_recovery_per_sec"], eliteValue=bbb["sp_recovery_per_sec"])]
        else:
            res["runtimeSupport"] = "logged-deferred-M4"
            res["effects"] = [eff("Deferred", key=key, baseValue=0, eliteValue=0)]
    elif et == "ADD_BOND":
        cond = res["triggerCondition"]
        sel = "OwnActivePacts" if bbs.get("bond_type") == "bond_self" else "Pacts"
        amt = lambda: stacks(sel, bb.get("bond_add_count", 1), bbb.get("bond_add_count", 1), **({"pacts": bonds} if sel == "Pacts" else {}))
        cap = bb.get("max_add_count_per_battle")
        if cap:
            cond["perBattleCap"] = cap
        if key.endswith("selfkillenemy"):
            cond.update(event="Kill", source="Self", every=bb.get("check_cnt", 1))
            if "前3次" in desc:
                cond["maxTimes"] = 3
            res["effects"] = [amt()]
        elif key.endswith("useskill"):
            cond.update(event="SkillActivated", source="Self")
            if "首次" in desc:
                cond["firstOnly"] = True
            if "同一行每有" in desc:
                res["effects"] = [stacks("HighestActivePact", bb.get("bond_add_count", 1), bbb.get("bond_add_count", 1), scale="SameRowCount")]
            else:
                res["effects"] = [amt()]
        elif key.endswith("onstart"):
            cond.update(event="BattleStart", source="Self")
            res["effects"] = [amt()]
        elif key.endswith("consume_ammo"):
            cond.update(event="AmmoConsumed", source="Around4" if bbs.get("range_id") == "x-5" else "Self",
                        every=bb["consume_count"])
            res["effects"] = [amt()]
        elif key.endswith("abflag_inrange"):
            cond.update(event="EnemyFrozen", source="Self", chanceBase=int(bb["prob"] * 100), chanceElite=int(bbb.get("prob", bb["prob"]) * 100))
            res["effects"] = [amt()]
        elif key.endswith("selfdead"):
            cond.update(event="SelfKnockedOut", source="Self")
            m = re.findall(r"【([^】]+)】层数\+(\d+)", desc)
            res["effects"] = [stacks("Pacts", int(a), int(a) * 2, pacts=[p if p != "协防干员" else p]) for p, a in m] or [amt()]
            if "<部署时>" in desc:
                res["runtimeSupport"] = "partial"  # the deploy half of garrison_75 needs a Deploy battle event
        elif key == "ADD_BOND" and "give_garrison_id" in bbs:
            given = garrisons[bbs["give_garrison_id"]]
            gbb, gbs = given["bb"], given["bbStr"]
            given_b = garrisons.get(bbs["give_garrison_id"][:-1] + "b", given)["bb"]
            cond.update(event="SkillActivated", source="Front1", perBattleCap=gbb.get("max_add_count_per_battle", 0))
            if gbs.get("bond_type") == "bond_self":
                res["effects"] = [stacks("SourceUnitActivePacts", gbb.get("bond_add_count", 1), given_b.get("bond_add_count", 1))]
            else:
                res["effects"] = [stacks("Pacts", gbb.get("bond_add_count", 1), given_b.get("bond_add_count", 1),
                                         pacts=[bond_name[b] for b in gbs.get("bond_id", "").split(",") if b in bond_name])]
        else:
            res["runtimeSupport"] = "logged-deferred-M4"
            res["effects"] = [eff("Deferred", key=key, baseValue=0, eliteValue=0)]
    else:
        res["runtimeSupport"] = "logged-deferred-M4"
        res["effects"] = [eff("Deferred", key=key or et, baseValue=0, eliteValue=0)]
    if res["trigger"] == "Battle":
        res["stackMode"] = "Battle"
    else:
        res["stackMode"] = {"Acquire": "Single", "Passive": "Passive"}.get(res["trigger"], "Persistent")
    return desc, res


def value_text(effects):
    e = next((x for x in effects if "baseValue" in x and x["op"] != "Deferred"), None)
    return "%s/%s" % (num(e["baseValue"]), num(e["eliteValue"])) if e else ""


# --------------------------------------------------------------------------------------------- pacts
PER_STACK_STAT = {"atk_per_stack": ("Attack", 1), "damage_scale_per_stack": ("Damage", 1), "max_hp_per_stack": ("Health", 1),
                  "def_per_stack": ("Defense", 1), "attack_speed_per_stack": ("AttackSpeed", 0.01)}
# "ex_*" keys (谢拉格 ex_damage_scale) are conditional extras (storm / special state), not an always-on bonus.
BASE_STAT = {"base_atk": "Attack", "base_damage_scale": "Damage", "base_max_hp": "Health", "base_def": "Defense",
             "base_attack_speed": "AttackSpeed"}



def sp_block(name, bb):
    """技力 numbers from bonds.json `bb` (document/167). Empty for the pacts that do not touch SP."""
    if name == "迅捷":
        return {"perAttack": int(round(bb.get("normal_sp", 0))), "chance": round(float(bb.get("base_prob", 0.0)), 4),
                "elitePerAttack": int(round(bb.get("power_sp", 0)))}
    if name == "绝技":
        # sp_ratio 0.7 = the skill costs 70 % of the usual SP (tier 2, five elite units).
        return {"costRatio": round(float(bb.get("sp_ratio", 1.0)), 4)}
    if name == "独行":
        return {"initial": int(round(bb.get("sp", 0)))}
    return {}


def ammo_block(name, bb):
    """拉特兰 ammunition numbers from bonds.json `bb` (document/168)."""
    if name != "拉特兰":
        return {}
    return {"perSkill": 3, "grantBonus": round(float(bb.get("base_ammo_percent", 0.0)), 4),
            "atkPerRound": round(float(bb.get("atk_per_consume", 0.0)), 4),
            "maxAtkMul": round(float(bb.get("max_atk_for_consume", 1.0)), 4)}


def pact_record(b):
    name = "协防" if b["name"] == "协防干员" else b["name"]
    lines = [clean(l) for l in (b["desc"] or "").split("\n") if clean(l)]
    tiers = []
    for i, count in enumerate(b["thresholds"]):
        text = next((l for l in lines if ("在场%d名" % count) in l), lines[0] if i == 0 and lines else (lines[i] if i < len(lines) else ""))
        tiers.append({"count": count, "text": text, "ops": []})
    if name == "助力":
        tiers[0]["ops"].append(eff("AddStacks", trigger="RoundEnd", pactSelector="AllActivePacts", baseValue=b["bb"]["layer"],
                                   eliteValue=b["bb"]["layer"], amountScale="Fixed"))
        if len(tiers) > 1:
            tiers[1]["ops"].append(eff("AddStacks", trigger="RoundEnd", pactSelector="AllActivePacts", baseValue=b["bb"]["more_layer"],
                                       eliteValue=b["bb"]["more_layer"], amountScale="Fixed"))
    if name == "投资人":
        tiers[0]["ops"].append(eff("AcquireRepeat", trigger="Passive", baseValue=b["bb"]["count"], eliteValue=b["bb"]["count"]))
    if name == "协防":
        tiers[0]["ops"].append(eff("CombatFlat", trigger="Passive", stat="DamageReduction", baseValue=b["bb"]["damage_resistance"],
                                   eliteValue=b["bb"]["damage_resistance"]))
    if name == "调和":
        tiers[0]["ops"].append(eff("HarmonyCountsAsActiveCore", trigger="Passive", baseValue=1, eliteValue=1))
    if name == "独行":
        tiers[0]["ops"].append(eff("CombatFlat", trigger="Passive", stat="AttackHealth", baseValue=b["bb"]["atk"], eliteValue=b["bb"]["atk"]))
    if name == "绝技":
        tiers[0]["ops"].append(eff("CombatFlat", trigger="Passive", stat="Attack", baseValue=b["bb"]["power_atk"], eliteValue=b["bb"]["power_atk"]))
    combat = []
    for k, v in b["bb"].items():
        if k in PER_STACK_STAT:
            stat, mul = PER_STACK_STAT[k]
            combat.append({"stat": stat, "perStack": round(v * mul, 6)})
    # base_*damage_scale values are multipliers (1.25 = +25 %); attack speed is flat aspd points (25 = +25 %)
    base = [{"stat": BASE_STAT[k], "value": round(v / 100.0 if k == "base_attack_speed" else (v - 1.0 if "damage_scale" in k and v >= 1.0 else v), 6)}
            for k, v in b["bb"].items() if k in BASE_STAT]
    milestones = []
    for m in b.get("layerMilestones") or []:
        op = {"bond_layer_gain_coin": "GainFundsNextRound", "bond_layer_added_reward_equip": "GrantItem"}.get(m["effect"], "Deferred")
        rec = {("every" if m["mode"] == "every" else "atLeast"): m["layer"], "op": op, "effect": m["effect"]}
        if m["mode"] != "every":
            rec["once"] = True
        if op == "GainFundsNextRound":
            rec["amount"] = 2 if name == "远见" else 10 if name == "奇迹" else 1
        if op == "GrantItem":
            rec["item"] = "维式重锤"
        milestones.append(rec)
    return {
        "pactId": name, "kind": "Core" if b["isCore"] else "Adjunct", "displayName": name, "sourceBondId": b["bondId"],
        "thresholds": b["thresholds"], "tiers": tiers, "thresholdSource": "StrongholdProtocol/bonds.json",
        "sourceStatus": "stronghold-protocol", "countsBench": b["countMode"] == "BOARD_AND_DECK",
        "countsEliteAll": b["countMode"] == "BOARD_ALL_CHESS", "isHarmony": name == "调和",
        # 独行 soloShip is the only bond with a cap: 1 member activates it, 2 or more switches it off.
        "maxCount": b.get("maxCount") or 0,
        "skillAppliesFreeze": name == "谢拉格", "baseStats": base, "combatPerStack": combat,
        "combatScope": "AllUnits" if name in ("坚守", "助力", "协防") else "PactMembers",
        "sp": sp_block(name, b["bb"]),
        "ammo": ammo_block(name, b["bb"]),
        "params": {k: round(float(v), 4) for k, v in b["bb"].items() if isinstance(v, (int, float))},
        "balanceStatus": "stronghold-protocol", "stackMilestones": milestones, "description": " / ".join(lines),
    }


# --------------------------------------------------------------------------------------------- strategies
def strategy_ops(band, item_name, bond_name):
    """Band buffs -> event-bus ops. Ones Tread cannot run yet are kept as logged-deferred entries."""
    out = []
    p = band["params"]
    for bf in band["buffs"]:
        k, bb = bf["key"], bf.get("bb", {})
        op = None
        if k == "prep_finish_char_bond_add_layer":
            op = eff("AddStacks", pactSelector="RandomUnitPerTierPacts", baseValue=bb["layer"], eliteValue=bb["layer"], amountScale="Fixed")
        elif k == "preparation_start_gain_chess_from_round" and bb.get("type") == "equip":
            op = eff("GrantItem", item=item_name(bb.get("chess", p.get("chess"))), baseValue=bb.get("count", 1), eliteValue=bb.get("count", 1),
                     onRound=bb.get("round"))
        elif k == "round_start_bond_check_gain_layer":
            op = eff("AddStacks", pactSelector="AllActivePacts", baseValue=bb["count2"], eliteValue=bb["count2"], amountScale="Fixed",
                     onRound=bb["round"], singleActiveAmount=bb["count1"])
        elif k == "coin_carry_over":
            op = eff("CarryOverFunds", baseValue=bb.get("interest", 1), eliteValue=bb.get("interest", 1), capital=bb.get("capital", 5))
        elif k == "give_coin_in_round":
            op = eff("GainFunds", baseValue=bb.get("coin", 0), eliteValue=bb.get("coin", 0), onRound=bb.get("round"))
        elif k == "first_buy_in_round_char_price_change":
            op = eff("FirstBuyPrice", pacts=[bond_name.get(bb.get("bond"), "")], baseValue=bb["price"], eliteValue=bb["price"])
        out.append({"raw": "%s %s" % (k, json.dumps(bb, ensure_ascii=False, sort_keys=True)), "op": op,
                    "runtimeSupport": "applied" if op else "logged-deferred-M4"})
    return out


# --------------------------------------------------------------------------------------------- main
def main():
    chess, bonds, bands, items = load("chess"), load("bonds"), load("bands"), load("items")
    garrisons, choices, config = load("garrisons"), load("choices"), load("config")
    bond_name = {k: ("协防" if v["name"] == "协防干员" else v["name"]) for k, v in bonds.items()}
    item_name = lambda iid: items[iid]["name"] if iid in items else iid
    op_name = lambda cid: chess[cid]["name"] if cid in chess else cid

    roster100 = json.loads(ROSTER100.read_text(encoding="utf-8-sig"))["characters"]
    if not MMD_MODELS.exists():
        dump(MMD_MODELS, {"schemaVersion": "Tread.N2.MmdModels.v1", "note": "owner-editable; archives under mmd_12/ (read-only)",
                          "models": [{"characterId": "char_%03d" % (101 + i), "modelName": n, "sourceGame": g, "archivePrefix": a,
                                      "format": "PMX", "license": "non-commercial fan use only; no redistribution of the model files"}
                                     for i, (n, g, a) in enumerate(MMD_DEFAULT)]})
    mmd = json.loads(MMD_MODELS.read_text(encoding="utf-8"))["models"]
    models = [{"characterId": c["characterId"], "modelName": c["originalOperatorName"], "modelSource": "legacy-vrm",
               "legacyCost": c["legacyCost"], "modelAssetPath": c["modelAssetPath"]} for c in roster100]
    models += [{"characterId": m["characterId"], "modelName": m["modelName"], "modelSource": "mmd:" + m["sourceGame"],
                "legacyCost": None, "modelAssetPath": "mmd_12/" + m["archivePrefix"]} for m in mmd]
    pairs = roster(chess, models)

    econ_cfg = config["economy"]
    mode = config["modes"][MODE]
    pool_copies = {int(k): v for k, v in econ_cfg["poolCopies"].items()}

    # ---- roster + cards
    roster_out, cards, rule_counts, support_counts, trig_counts = [], [], {}, {}, {}
    for m, o, how in pairs:
        cid = m["characterId"]
        tier = o["tier"]
        golden = chess.get(o["goldenId"], {})
        copies = econ_cfg["poolCopiesOverrides"].get(o["chessId"], pool_copies[tier])
        merge = econ_cfg["mergeCountOverrides"].get(o["chessId"], o.get("upgradeNum") or econ_cfg["mergeCount"])
        core = [bond_name[b] for b in o["bonds"] if bonds[b]["isCore"]]
        adj = [bond_name[b] for b in o["bonds"] if not bonds[b]["isCore"]]
        prof = PROFESSION_ZH.get(o["profession"], o["profession"])
        roster_out.append({
            "characterId": cid, "modelName": m["modelName"], "modelSource": m["modelSource"], "modelAssetPath": m["modelAssetPath"],
            "operatorChessId": o["chessId"], "operatorEliteChessId": o["goldenId"], "operatorCharId": o["charId"],
            "operatorName": o["name"], "operatorAppellation": o["appellation"], "operatorTier": TIER_ROMAN[tier], "tier": tier,
            "rarity": o["rarity"], "profession": prof, "subProfession": o["subProfessionName"], "position": o["position"],
            "corePacts": core, "adjunctPacts": adj, "price": o["price"], "sellPrice": o["sellPrice"], "poolCopies": copies,
            "combineCopies": merge, "stats": o["stats"], "eliteStats": golden.get("stats"), "attackKind": o["attackKind"],
            "dmgType": o["dmgType"], "skillName": (o.get("skill") or {}).get("name"), "binding": how,
        })
        traits = []
        for n, gid in enumerate(o["garrisonIds"]):
            ga = garrisons[gid]
            gb = garrisons.get(gid[:-1] + "b")
            desc, res = trait_from_garrison(ga, gb, bond_name, item_name, choices["pools"], op_name, garrisons)
            label = re.match(r"(<[^>]+>)", desc)
            trait = {"id": "trait_%s_%02d" % (cid, n + 1), "cardId": cid, "rarity": tier, "corePacts": core, "adjunctPacts": adj,
                     "trigger": res["trigger"], "triggerLabel": label.group(1) if label else "", "triggerCondition": res["triggerCondition"],
                     "stackMode": res["stackMode"], "targets": res["targets"], "activationRequired": res["activationRequired"],
                     "worksOnBench": res["worksOnBench"], "repeatCount": res["repeatCount"], "effects": res["effects"],
                     "stackCap": 999, "scalePerStack": 1, "displayText": desc, "eliteDisplayText": clean(gb["desc"]) if gb else desc,
                     "valueText": value_text(res["effects"]), "sourcePattern": "StrongholdProtocol/garrisons.json#" + gid,
                     "parseRule": res["rule"], "runtimeSupport": res["runtimeSupport"]}
            first = next((e for e in res["effects"] if "baseValue" in e), None)
            trait["baseValue"] = first["baseValue"] if first else 0
            trait["eliteValue"] = first["eliteValue"] if first else 0
            traits.append(trait)
            rule_counts[res["rule"]] = rule_counts.get(res["rule"], 0) + 1
            support_counts[res["runtimeSupport"]] = support_counts.get(res["runtimeSupport"], 0) + 1
            trig_counts[res["trigger"]] = trig_counts.get(res["trigger"], 0) + 1
        cards.append({
            "characterId": cid, "originalOperatorName": m["modelName"], "referenceOperatorName": o["name"],
            "referenceOperatorTier": TIER_ROMAN[tier], "assignment": how, "assignmentStatus": "N2 binding (Roster112.json)",
            "operatorTier": TIER_ROMAN[tier], "price": o["price"], "sellPrice": o["sellPrice"], "poolCopies": copies,
            "corePacts": core, "adjunctPacts": adj, "profession": prof,
            "consumesAmmo": (o.get("skill") or {}).get("durationType") == "AMMO", "combineCopies": merge, "traits": traits,
        })

    # ---- pacts
    pacts = [pact_record(b) for b in sorted(bonds.values(), key=lambda b: (not b["isCore"], b["bondOrder"], b["bondId"]))]

    # ---- items (base equipment only; golden variants are the merge result)
    item_out = []
    for iid, it in sorted(items.items()):
        if it["isGolden"] or it["itemType"] != "EQUIP":
            continue
        g = items.get(it["goldenId"], {})
        item_out.append({"itemId": iid, "displayName": it["name"], "tier": it["tier"], "price": it["price"],
                         "providesPacts": [bond_name[it["giveBondId"]]] if it.get("giveBondId") in bond_name else [],
                         "effectText": clean(it["desc"]), "eliteEffectText": clean(g.get("desc", "")), "category": it.get("category"),
                         "params": it.get("params"), "eliteParams": g.get("params"), "mergeCopies": it.get("upgradeNum"),
                         "effectStatus": "pact-membership-applied; stat effect pending ItemCatalog", "enabled": True})
    item_out.append({"itemId": "item_random_equip", "displayName": "随机装备", "providesPacts": [], "effectStatus": "placeholder",
                     "enabled": True, "note": "resolved to a random shop-eligible equipment at runtime"})

    # ---- strategies (bands): Tread base health is 100; the band's target life (default 28) scales it
    start_lp = econ_cfg["defaultStartLp"]
    strat40, strat_bus = [], []
    for i, (bid, band) in enumerate(sorted(bands.items(), key=lambda kv: kv[1]["sortId"])):
        sid = "strategy_%03d" % (i + 1)
        health = round(100 * band["totalHp"] / start_lp)
        strat40.append({"strategyId": sid, "bandId": bid, "issuerCharacterId": "", "issuerName": band["name"],
                        "effectName": band["effectName"], "offerText": clean(band["desc"]), "hpCost": 100 - health,
                        "startHealth": health, "effects": [b["key"] for b in band["buffs"]] or ["None"],
                        "trigger": "MatchStart", "unlockCondition": "Always", "initialOnly": True, "bpEligible": True,
                        "uniqueScope": "StrategyId"})
        # "开始作战时 ... 层数+2" (prep_finish_*) fires when preparation ends; everything else is set up at match start
        # and round-scheduled ops (onRound) fire at the RoundStart of their round.
        trigger = "RoundEnd" if any(b["key"].startswith("prep_finish") for b in band["buffs"]) else "MatchStart"
        strat_bus.append({"strategyId": sid, "bandId": bid, "trigger": trigger, "sourceTrigger": "band",
                          "effects": strategy_ops(band, item_name, bond_name)})

    economy = {
        "schemaVersion": "Tread.N1.Economy.v1", "mode": MODE, "modeName": mode["name"],
        "incomeByRound": econ_cfg["income"], "incomeFormula": econ_cfg["incomeFormula"], "incomeCap": econ_cfg["incomeCap"],
        "leftoverFundsLost": econ_cfg["leftoverFundsLost"], "interest": False, "streakIncome": False,
        "priceByTier": {TIER_ROMAN[int(k)]: v["normal"] for k, v in econ_cfg["chessPrice"].items()},
        "sellByTier": {TIER_ROMAN[int(k)]: v["normal"] for k, v in econ_cfg["chessSell"].items()},
        "refreshPrice": econ_cfg["refreshPrice"], "freeze": econ_cfg["freeze"],
        "poolCopiesByTier": {TIER_ROMAN[k]: v for k, v in pool_copies.items()}, "poolCopiesOverrides": econ_cfg["poolCopiesOverrides"],
        "mergeCount": econ_cfg["mergeCount"], "shopOddsModel": econ_cfg["shopOdds"]["model"],
        "shopLevel": {"start": 1, "max": mode["maxShopLevel"], "upgradePrices": mode["upgradePrices"],
                      "upgradeDiscountPerRound": 1, "chessSlotsByLevel": {k: v["chess"] for k, v in mode["shopSlots"].items()},
                      "itemSlotsByLevel": {k: v["item"] for k, v in mode["shopSlots"].items()}},
        "deployCap": econ_cfg["deployCap"], "equipPerUnit": econ_cfg["equipPerChess"],
        "kept_from_tread": {"players": 4, "rounds": 12, "pvp": True, "benchSlots": 8, "baseHealth": 100, "preparationSec": 30},
        "rewardOffer": econ_cfg["rewardOffer"],
    }

    provenance = {"repository": "https://github.com/sganggs/Stronghold-Protocol", "commit": SP_COMMIT,
                  "zipSha256": sha256(SP_ZIP) if SP_ZIP.exists() else None,
                  "files": {n: sha256(SP / (n + ".json")) for n in ("chess", "bonds", "bands", "items", "garrisons", "choices", "config")},
                  "license": "data derived from Hypergryph game data; non-commercial fan use only (repo NOTICE.md §2-3); no GPL code copied",
                  "generator": "Tools/m4/import_stronghold_data.py"}
    dump(OUT_SRC / "Snapshot.json", {"schemaVersion": "Tread.N1.StrongholdSnapshot.v1", "provenance": provenance,
                                     "mode": MODE, "bonds": {k: {x: v[x] for x in ("name", "isCore", "thresholds", "countMode", "bb", "desc")} for k, v in bonds.items()},
                                     "bands": {k: {x: v[x] for x in ("name", "totalHp", "effectName", "desc", "buffs", "params")} for k, v in bands.items()}})
    dump(OUT_GEN / "Roster112.json", {"schemaVersion": "Tread.N2.Roster112.v1", "provenance": provenance,
                                      "binding": "models sorted by (legacyCost, id), 12 MMD models last; operators by (tier, shopSortId); Roster112_Overrides.json wins",
                                      "characters": roster_out})
    dump(OUT_GEN / "Economy.json", dict(economy, provenance=provenance))
    dump(OUT_GEN / "Pacts.json", {"schemaVersion": "Tread.N1.Pacts.v1", "provenance": provenance,
                                  "rules": {"spRegenPerSecond": 2.0, "countDistinctCharacters": True, "boardCounts": True,
                                            "benchCountsForPacts": sorted(p["pactId"] for p in pacts if p["countsBench"]),
                                            "eliteStarAtLeast": 2, "stackCap": 999, "harmony": "调和: each active core pact counts +1",
                                            "professions": sorted(set(PROFESSION_ZH.values())), "professionIsPact": False,
                                            "battle": {"skillEveryAttacks": 3, "ammoPerAttack": 1, "frozenOnSkillForPact": "谢拉格"}},
                                  "pacts": pacts})
    dump(OUT_GEN / "Traits.json", {"schemaVersion": "Tread.N1.Traits.v1", "provenance": provenance,
                                   "summary": {"cards": len(cards), "traits": sum(len(c["traits"]) for c in cards),
                                               "triggers": dict(sorted(trig_counts.items())), "parseRules": dict(sorted(rule_counts.items())),
                                               "runtimeSupport": dict(sorted(support_counts.items()))},
                                   "cards": cards})
    dump(OUT_GEN / "M2_ItemSeeds.json", {"schemaVersion": "Tread.N1.Items.v1", "provenance": provenance, "items": item_out})
    dump(OUT_GEN / "StrategyEffects.json", {"schemaVersion": "Tread.N1.StrategyEffects.v1", "provenance": provenance, "strategies": strat_bus})
    dump(OUT_GEN / "Strategies40.json", {"schemaVersion": "Tread.N1.Strategies.v1", "provenance": provenance, "strategies": strat40})
    print("roster=%d cards=%d traits=%d pacts=%d items=%d strategies=%d" % (
        len(roster_out), len(cards), sum(len(c["traits"]) for c in cards), len(pacts), len(item_out), len(strat40)))
    print("support=%s" % support_counts)
    print("triggers=%s" % trig_counts)


if __name__ == "__main__":
    main()
