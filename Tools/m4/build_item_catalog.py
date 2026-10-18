#!/usr/bin/env python3
"""M4-C (host-side): item/strategy source snapshot, ItemCatalog.json, StrategyItems.json and their validation.

Source of record (owner decision 2026-10-08, doc 143/149: N1 numbers come from Stronghold-Protocol, the web replica
of 卫戍协议 that transcribes the game's PRTS pages): Saved/Staging/ref/Stronghold-Protocol-HEAD/data/{items,bands}.json
at commit SP_COMMIT.  The M4 plan's "PRTS snapshot" is therefore this repository snapshot: URL, retrieval time,
content hash, section and version per input, plus the trimmed rows, so a later re-download can be diffed.

Output:
  Content/Data/Source/ItemStrategy_Snapshot.json       sourceUrl, retrievedAt, contentHash, section, version, rows
  Content/Data/Generated/ItemCatalog.json              56 equipment items, base (Ⅰ) / elite (Ⅱ) values side by side,
                                                       combat stats for the battle sim, on-equip ops, support status
  Content/Data/Generated/StrategyItems.json            the 3 special spell items (MAGIC) with support status
  Saved/Reports/M4_ItemCatalog_Source_And_Validation.json

    python Tools/m4/build_item_catalog.py

A row whose source or required field is missing fails the validation and stops the script before it writes
the catalog (the runtime keeps the previous one).  Effects the abstract battle cannot express yet are kept with
runtimeSupport "deferred" and a reason, never dropped.
"""
import datetime
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SP = ROOT / "Saved/Staging/ref/Stronghold-Protocol-HEAD/data"
SP_ZIP = ROOT / "Saved/Staging/ref/sp.zip"
SP_COMMIT = "3eced7bdba5aae11a325bd3dbe66cdf01361d2bd"
SP_RAW = "https://raw.githubusercontent.com/sganggs/Stronghold-Protocol/%s/data/%%s.json" % SP_COMMIT
SNAPSHOT = ROOT / "Content/Data/Source/ItemStrategy_Snapshot.json"
CATALOG = ROOT / "Content/Data/Generated/ItemCatalog.json"
STRATEGY_ITEMS = ROOT / "Content/Data/Generated/StrategyItems.json"
REPORT = ROOT / "Saved/Reports/M4_ItemCatalog_Source_And_Validation.json"
BONDS_ZH = {}

# Unconditional numeric parts -> the battle sim's stat keys (TreadM2PactRuntime ComputeUnitCombat).  Attack speed
# is in points on a base of 100; magic resistance counts half because roughly half the incoming damage is arts.
STAT_MAP = {"atk": ("Attack", 1.0), "def": ("Defense", 1.0), "max_hp": ("Health", 1.0), "init_max_hp": ("Health", 1.0),
            "attack_speed": ("AttackSpeed", 0.01), "sp_recovery_per_sec": ("SkillRegen", 1.0),
            "magic_resistance": ("DamageReduction", 0.005)}
# Keys that only matter together with a condition, a proc or a timer: their item stays partly deferred.
CONDITIONAL = {"prob", "disarmed_duration", "damage", "radius", "damage_scale", "at_root", "undeadable_duration",
               "silence", "stun", "duration", "interval", "ex_interval", "damage_scale_minus", "ammo_percent",
               "max_trigger_cnt", "cold", "atk_buff_cnt", "max_buff_cnt", "taunt_level", "hp_ratio", "ex_max_hp",
               "respawn_time", "magic_resist_penetrate", "sp_each_person", "max_stack_cnt", "max_respawn_cnt",
               "hp_recovery_per_sec_by_max_hp_ratio", "atk_scale", "atk_scale_1", "atk_scale_2", "lock_duration",
               "value", "sp", "addition_sp", "init_sp", "move_speed", "atk_per_sec", "max_atk", "max_cnt"}
IGNORED = {"key", "big_hammer", "equip_chess_id", "other_equip", "bond", "hammer_1", "hammer_2", "hammer_3",
           "hammer_4", "count", "max", "min", "layer", "refresh_cnt", "choice_cnt"}
# Stat keys that look unconditional but only apply under a condition the description states (pact holder, per
# skill / per attack stacks): kept out of the flat combat bonus.
CONDITIONAL_STATS = {
    "chess_item_3_04_e": {"atk"},                          # 炎国短刀: +5% per skill use, up to 10
    "chess_item_4_03_e": {"atk", "attack_speed"},          # 有限加速器: +1 per attack, up to 60
    "chess_item_6_03_e": {"attack_speed"},                 # 天师古鼎: only on a 炎 holder
    "chess_item_6_10_e": {"atk", "attack_speed", "max_hp"},  # 骑士戒律: only on a 卡西米尔 holder, after a skill
}
# consume_on_equip items the runtime executes (EquipItem): op name and which param carries the amount.
ON_EQUIP = {
    "chess_item_1_03_e": ("GainFundsRandom", "min", "max"),     # 盟约之币
    "chess_item_3_12_e": ("GainFundsRandom", "min", "max"),     # 骑士储蓄罐
    "chess_item_2_07_e": ("GainFundsNextRound", "count", None),  # 见钱眼开玩偶
    "chess_item_2_05_e": ("GainFundsEachRound", "count", None),  # 精打细算玩偶
    "chess_item_1_04_e": ("AddOwnPactStacks", "layer", None),   # 随身身份牌
    "chess_item_2_02_e": ("RecruitFromShop", "count", None),    # 紧急调度券
    "chess_item_2_06_e": ("RecruitSamePact", "count", None),    # 简易通讯机
    "chess_item_5_05_e": ("RecruitSameOperator", None, None),   # 拟态物质
    "chess_item_5_06_e": ("PromoteElite", None, None),          # 博士投影
    "chess_item_6_08_e": ("SetPopulationLimit", "count", None),  # 人事部文档
}


def load(name):
    return json.loads((SP / ("%s.json" % name)).read_text(encoding="utf-8"))


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def combat_of(params, skip=()):
    out = {}
    for key, value in (params or {}).items():
        if key in STAT_MAP and key not in skip and isinstance(value, (int, float)):
            stat, scale = STAT_MAP[key]
            out[stat] = round(out.get(stat, 0.0) + value * scale, 4)
    return out


def main():
    bonds = load("bonds")
    bond_zh = {k: ("协防" if v["name"] == "协防干员" else v["name"]) for k, v in bonds.items()}
    items = load("items")
    bands = load("bands")
    retrieved = datetime.datetime.fromtimestamp(SP_ZIP.stat().st_mtime, datetime.timezone.utc).isoformat()
    sources = {}
    for name in ("items", "bands", "bonds"):
        raw = (SP / ("%s.json" % name)).read_bytes()
        sources[name] = {"sourceUrl": SP_RAW % name, "retrievedAt": retrieved, "contentHash": "sha256:" + sha256(raw),
                         "section": "data/%s.json" % name, "version": SP_COMMIT}

    errors, rows = [], []
    for item in items.values():
        if item["isGolden"] or item["itemType"] != "EQUIP":
            continue
        elite = items.get(item.get("goldenId") or "")
        for field in ("id", "name", "tier", "price", "desc", "category", "kind"):
            if item.get(field) in (None, ""):
                errors.append("%s: missing %s" % (item.get("id"), field))
        if elite is None:
            errors.append("%s: missing elite (Ⅱ) version %s" % (item["id"], item.get("goldenId")))
            continue
        base_id = item["id"][:-2]  # chess_item_1_01_e_a -> chess_item_1_01_e
        skip = CONDITIONAL_STATS.get(base_id, set())
        combat, elite_combat = combat_of(item["params"], skip), combat_of(elite["params"], skip)
        keys = set(item["params"] or {}) | set(elite["params"] or {})
        unhandled = sorted(k for k in keys if (k not in STAT_MAP or k in skip) and k not in IGNORED)
        on_equip = ON_EQUIP.get(base_id)
        if on_equip:
            support, reason = "applied", "on-equip op %s" % on_equip[0]
        elif combat and not unhandled:
            support, reason = "applied", "combat stats"
        elif combat:
            support, reason = "partial", "combat stats applied; conditional/proc parts deferred: %s" % ", ".join(unhandled)
        elif item["category"] == "BOND_GRANT":
            support, reason = "applied", "transform clone (变形同构体) handled by the clone runtime"
        elif item["category"] in ("RECRUIT", "ECONOMY"):
            support, reason = "deferred", "%s effect (%s) not implemented yet" % (item["category"], item["kind"])
        else:
            support, reason = "deferred", "needs per-tick battle simulation (%s)" % (", ".join(unhandled) or item["category"])
        op = None
        if on_equip:
            name, amount_key, max_key = on_equip
            op = {"op": name,
                  "baseValue": (item["params"] or {}).get(amount_key, 1) if amount_key else 1,
                  "eliteValue": (elite["params"] or {}).get(amount_key, 1) if amount_key else 1}
            if max_key:
                op["baseMax"] = item["params"][max_key]
                op["eliteMax"] = elite["params"][max_key]
        row = {
            "itemId": item["id"], "eliteItemId": elite["id"], "baseId": base_id, "displayName": item["name"],
            "tier": item["tier"], "price": item["price"], "category": item["category"], "kind": item["kind"],
            "mergeCopies": item.get("upgradeNum") or 2,
            "providesPacts": [bond_zh[item["giveBondId"]]] if item.get("giveBondId") in bond_zh else [],
            "effectText": item["desc"], "eliteEffectText": elite["desc"],
            "params": item["params"], "eliteParams": elite["params"],
            "combat": combat, "eliteCombat": elite_combat, "onEquip": op,
            "consumedOnEquip": item["kind"].startswith("consume_on_equip"),
            "runtimeSupport": support, "supportNote": reason,
            "contentHash": "sha256:" + sha256(json.dumps([item, elite], ensure_ascii=False, sort_keys=True).encode("utf-8")),
        }
        rows.append(row)
    rows.sort(key=lambda r: r["itemId"])

    magic = []
    for item in items.values():
        if item["itemType"] != "MAGIC":
            continue
        support = {"chess_item_6_02_m": ("applied", "copy of a board operator as a transform clone (no pool cost)")}.get(
            item["id"], ("deferred", "needs the bounty (悬赏) system, not in Tread's 4-player rules; disabled"))
        magic.append({"itemId": item["id"], "displayName": item["name"], "tier": item["tier"], "price": item["price"],
                      "effectText": item["desc"], "implementationNote": item.get("implFormula"),
                      "runtimeSupport": support[0], "supportNote": support[1], "enabled": support[0] == "applied",
                      "contentHash": "sha256:" + sha256(json.dumps(item, ensure_ascii=False, sort_keys=True).encode("utf-8"))})
    magic.sort(key=lambda r: r["itemId"])

    ids = [r["itemId"] for r in rows]
    names = [r["displayName"] for r in rows]
    checks = {
        "source_hashes_present": all(s["contentHash"] for s in sources.values()),
        "equipment_56": len(rows) == 56,
        "each_has_base_and_elite": all(r["eliteItemId"] for r in rows),
        "ids_unique": len(set(ids)) == len(ids),
        "names_unique": len(set(names)) == len(names),
        "required_fields": not errors,
        "magic_3": len(magic) == 3,
        "every_row_has_support_status": all(r["runtimeSupport"] in ("applied", "partial", "deferred") for r in rows + magic),
        "strategies_40": len([b for b in bands.values() if not b.get("isHidden")]) >= 40 or len(bands) >= 40,
    }
    ok = all(checks.values())
    support_counts = {}
    for r in rows + magic:
        support_counts[r["runtimeSupport"]] = support_counts.get(r["runtimeSupport"], 0) + 1
    report = {"schema": "Tread.M4.ItemCatalogValidation.v1", "ok": ok, "checks": checks, "errors": errors,
              "sources": sources, "equipment": len(rows), "magic": len(magic), "support": support_counts,
              "deferred": [{"itemId": r["itemId"], "displayName": r["displayName"], "why": r["supportNote"]}
                           for r in rows + magic if r["runtimeSupport"] != "applied"]}
    dump(REPORT, report)
    if not ok:
        print("ITEMS validation failed, catalog not written: %s %s" % ([k for k, v in checks.items() if not v], errors[:5]))
        return 1
    dump(SNAPSHOT, {"schemaVersion": "Tread.M4.ItemStrategySnapshot.v1",
                    "note": "M4 item/strategy source snapshot. Stronghold-Protocol transcribes the 卫戍协议 PRTS pages; N1 takes "
                            "its numbers (doc 143/149). Re-download and compare contentHash to detect upstream changes.",
                    "sources": sources,
                    "rows": {"items": [{k: i.get(k) for k in ("id", "name", "itemType", "tier", "price", "desc", "category",
                                                              "kind", "params", "goldenId", "giveBondId")}
                                       for i in sorted(items.values(), key=lambda i: i["id"])],
                             "bands": [{k: b.get(k) for k in ("id", "name", "desc")} for b in
                                       sorted(bands.values(), key=lambda b: b.get("id", ""))]}})
    dump(CATALOG, {"schemaVersion": "Tread.M4.ItemCatalog.v1", "source": sources["items"], "items": rows})
    dump(STRATEGY_ITEMS, {"schemaVersion": "Tread.M4.StrategyItems.v1", "source": sources["items"], "items": magic})
    print("ITEMS ok equipment=%d magic=%d support=%s" % (len(rows), len(magic), support_counts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
