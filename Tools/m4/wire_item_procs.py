"""Wire per-item combat procs into ItemCatalog.json (document/175).

The catalogue already carries flat `combat` stats and the ten on-equip ops.  The remaining forty rows
were either "partial" (stats run, the conditional/proc half did not) or "deferred" (nothing reached the
battle simulation).  This stage adds a data-driven `proc` array to every row whose effect can be
expressed as a trigger inside the abstract exchange simulation, and re-runs the support triage:

    python Tools/m4/wire_item_procs.py [--check]

Proc rows are explicit per base item (never guessed from parameter names), so every wired effect can be
audited against the Stronghold-Protocol description in `effectText`.
"""
import io
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CATALOG = os.path.join(ROOT, "Content", "Data", "Generated", "ItemCatalog.json")
REPORT = os.path.join(ROOT, "Saved", "Reports", "Item_Procs.json")

# Per base item: the procs the exchange simulation understands, and which source parameters still have
# no runtime meaning (they keep the row "partial", or "deferred" when no stat/proc runs at all).
#
# Ops:
#   DamageScale       value, window(seg), decay(per seg), condition(Ranged), partner(item id)
#   DamageTakenScale  value
#   Stun              chance, duration(seg), window(seg), condition(Ground)
#   Lifesteal         value (fraction of own max HP per attack)
#   Regen             value (fraction of own max HP per exchange), partner
#   Revive            count, health (fraction of max HP)
#   Undying           duration(seg) -- first lethal hit inside the window leaves 1 HP
#   SpInitial         value, perPactMember
#   SpRegen           value (points per exchange)
#   AmmoRefund        chance, percent, max
#   ExtraHit          chance, value(scale), valuePartner, condition(Pact:<name>), partner
#   Reflect           value (scale of incoming damage), condition(Pact:<name>)
#   AttackStack       value (attack-speed points per attack), max
#   AttackPerSkill    value (attack multiplier per skill), max
#   Burn              value (fraction of the attacker's damage per exchange for 3 exchanges)
#   Taunt             --
#   StatusImmune      hpRatio
#   HealthConditional value, condition(FrontEmpty)
#   Silence           duration(seg)
PROCS = {
    "chess_item_1_05_e": [{"op": "SelfDot", "value": 0.02}],  # 60 HP/s on a ~3000 HP operator
    "chess_item_2_01_e": [{"op": "Redeploy", "count": 1, "value": 0.4}],
    "chess_item_2_03_e": [{"op": "Stun", "chance": 0.1, "duration": 2, "condition": "Ground"}],
    "chess_item_3_01_e": [{"op": "NeighborAttackSpeed", "value": 10}],
    "chess_item_3_02_e": [{"op": "DamageScale", "value": 1.3, "condition": "Ranged"}],
    "chess_item_3_03_e": [{"op": "Penetrate", "value": 0.25}],
    "chess_item_3_04_e": [{"op": "AttackPerSkill", "value": 0.05, "max": 10}],
    "chess_item_3_05_e": [{"op": "SpInitial", "value": 3, "perPactMember": 3}],
    "chess_item_3_06_e": [{"op": "HealthConditional", "value": 0.15, "condition": "FrontEmpty"}],
    "chess_item_3_08_e": [{"op": "Silence", "duration": 5}],
    "chess_item_3_09_e": [{"op": "Undying", "duration": 8}],
    "chess_item_3_11_e": [{"op": "Stun", "chance": 1.0, "duration": 2, "window": 10}],
    "chess_item_4_01_e": [{"op": "RecruitPactUnit", "count": 1}],
    "chess_item_4_02_e": [{"op": "Taunt"}],
    "chess_item_4_03_e": [{"op": "AttackStack", "value": 1, "max": 60}],
    "chess_item_4_04_e": [{"op": "StealthAfterHit", "duration": 15}],
    "chess_item_4_05_e": [{"op": "DamageTakenScale", "value": 0.6}],
    "chess_item_4_06_e": [{"op": "Lifesteal", "value": 0.02}],
    "chess_item_4_07_e": [{"op": "DamageScale", "value": 1.35, "window": 15, "decay": 0.08}],
    "chess_item_4_08_e": [{"op": "AmmoRefund", "chance": 0.5, "percent": 0.4, "max": 3}],
    "chess_item_4_09_e": [{"op": "Burn", "value": 0.1}],
    "chess_item_4_10_e": [{"op": "StatusImmune", "hpRatio": 0.7}],
    "chess_item_4_11_e": [{"op": "ShieldOnHeal", "chance": 0.1, "max": 1}],
    "chess_item_4_12_e": [{"op": "Revive", "count": 1, "value": 0.5}],
    "chess_item_5_01_e": [{"op": "Stun", "chance": 0.03, "duration": 1}],
    "chess_item_5_02_e": [{"op": "Stun", "chance": 0.12, "duration": 1.5}],
    "chess_item_5_04_e": [{"op": "RecruitSameTierUnit", "count": 1}],
    "chess_item_5_07_e": [{"op": "SellCounterRecruit", "count": 8}],
    "chess_item_5_08_e": [{"op": "PostBattleTransform"}],
    "chess_item_5_09_e": [{"op": "Regen", "value": 0.08, "partner": "chess_item_6_01_e"}],
    "chess_item_6_01_e": [{"op": "DamageScale", "value": 1.3, "partner": "chess_item_5_09_e"}],
    "chess_item_6_02_e": [{"op": "ExtraHit", "chance": 0.35, "value": 1.5, "valuePartner": 3.0,
                           "condition": "Pact:拉特兰", "partner": "chess_item_4_08_e"}],
    "chess_item_6_03_e": [{"op": "AttackSpeedPerAcquire", "value": 25, "max": 3},
                          {"op": "FundsPerAcquire", "value": 2, "max": 3}],
    "chess_item_6_04_e": [{"op": "DamageTakenScale", "value": 0.7},
                          {"op": "Reflect", "value": 0.5, "condition": "Pact:阿戈尔"}],
    "chess_item_6_05_e": [{"op": "AttackSpeedFlat", "value": 30}, {"op": "Stun", "chance": 0.1, "duration": 2},
                          {"op": "Undying", "duration": 8}, {"op": "Burn", "value": 0.1}],
    "chess_item_6_06_e": [{"op": "Burn", "value": 0.3, "condition": "Stunned"}],
    "chess_item_6_07_e": [{"op": "SpInitial", "value": 30}],
    "chess_item_6_09_e": [{"op": "BondGrant"}],
    "chess_item_6_10_e": [{"op": "SkillWindowBuff", "value": 1.0, "duration": 20}],
    "chess_item_6_11_e": [{"op": "SpRegen", "value": 0.2}, {"op": "AtkRamp", "value": 0.02, "max": 1.0}],
}

# Source keys that still have no runtime consumer after the procs above.
REMAINING = {}


def load(path):
    with io.open(path, encoding="utf-8") as handle:
        return json.load(handle)


def main():
    check_only = "--check" in sys.argv[1:]
    catalog = load(CATALOG)
    rows = catalog["items"]

    wired, missing = [], []
    for row in rows:
        base_id = row.get("baseId") or row["itemId"]
        if base_id not in PROCS:
            missing.append(base_id)
            continue
        procs = PROCS[base_id]
        remaining = REMAINING.get(base_id, [])
        row["proc"] = procs
        has_combat = bool(row.get("combat")) or bool(row.get("eliteCombat"))
        if (has_combat or procs) and not remaining:
            row["runtimeSupport"] = "applied"
            row["supportNote"] = "combat stats + %d proc(s)" % len(procs) if procs else "combat stats"
        elif has_combat or procs:
            row["runtimeSupport"] = "partial"
            row["supportNote"] = "combat stats/procs applied; still deferred: %s" % ", ".join(remaining)
        else:
            row["runtimeSupport"] = "deferred"
            row["supportNote"] = "not modelled yet: %s" % ", ".join(remaining or ["unknown"])
        if procs:
            wired.append(base_id)

    support = {}
    for row in rows:
        support[row["runtimeSupport"]] = support.get(row["runtimeSupport"], 0) + 1
    ops = {}
    for row in rows:
        for proc in row.get("proc") or []:
            ops[proc["op"]] = ops.get(proc["op"], 0) + 1

    summary = {
        "items": len(rows),
        "withProcs": len(wired),
        "support": support,
        "byOp": ops,
        "unmapped": missing,
    }
    print("items %d, with procs %d" % (len(rows), len(wired)))
    print("support:", json.dumps(support, ensure_ascii=False, sort_keys=True))
    print("ops:", json.dumps(ops, ensure_ascii=False, sort_keys=True))
    if missing:
        print("unmapped base ids:", missing)
    if check_only:
        return
    with io.open(CATALOG, "w", encoding="utf-8") as handle:
        json.dump(catalog, handle, ensure_ascii=False, indent=1)
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with io.open(REPORT, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=1)
    print("wrote", CATALOG, "+", REPORT)


if __name__ == "__main__":
    main()
