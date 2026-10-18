"""Emit the item on-equip ops the runtime already understands (document/165 P0-2).

The M4 importer (Tools/m4/import_stronghold_data.py) already decided, per item, which runtime op carries the effect and
wrote it into `supportNote` ("on-equip op GainFundsRandom" etc.). The M2 seed generator never emitted that `onEquip`
object, so every item loaded with an empty op and equipping did nothing but pact membership.

This step copies the decision into Content/Data/Generated/M2_ItemSeeds.json (read by TreadM2PactData.cpp) and refreshes
`runtimeSupport` in ItemCatalog.json:

    python Tools/m4/wire_item_ops.py [--check]
"""
import io
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CATALOG = os.path.join(ROOT, "Content", "Data", "Generated", "ItemCatalog.json")
SEEDS = os.path.join(ROOT, "Content", "Data", "Generated", "M2_ItemSeeds.json")
REPORT = os.path.join(ROOT, "Saved", "Reports", "Item_Effects.json")

OP_PATTERN = re.compile(r"on-equip op ([A-Za-z]+)")

# Which parameter feeds each op, base first then elite.
OP_VALUE_KEYS = {
    "GainFundsRandom": ("min", "max"),
    "GainFundsNextRound": ("count", "funds"),
    "GainFundsEachRound": ("count", "funds"),
    "AddOwnPactStacks": ("layer",),
    "SetPopulationLimit": ("count", "pop"),
    "PromoteElite": ("count",),
    "RecruitFromShop": ("count",),
    "RecruitSamePact": ("count",),
    "RecruitSameOperator": ("count",),
}


def load(path):
    with io.open(path, encoding="utf-8") as handle:
        return json.load(handle)


def pick(params, names, fallback):
    for name in names:
        if name in params and isinstance(params[name], (int, float)):
            return int(round(params[name]))
    return fallback


def main():
    check_only = "--check" in sys.argv[1:]
    catalog = load(CATALOG)
    seeds = load(SEEDS)

    by_id = {}
    for item in catalog.get("items", []):
        by_id[item["itemId"]] = item
        if item.get("eliteItemId"):
            by_id[item["eliteItemId"]] = item

    wired = []
    skipped = []
    for row in seeds.get("items", []):
        item = by_id.get(row.get("itemId"))
        if not item:
            skipped.append((row.get("itemId"), "not in catalog"))
            continue
        note = item.get("supportNote", "")
        match = OP_PATTERN.search(note)
        if not match:
            continue
        op = match.group(1)
        names = OP_VALUE_KEYS.get(op)
        if not names:
            skipped.append((row["itemId"], "op %s has no value rule" % op))
            continue
        base_params = item.get("params") or {}
        elite_params = item.get("eliteParams") or base_params
        base_value = pick(base_params, names, 1)
        elite_value = pick(elite_params, names, base_value)
        row["onEquip"] = {"op": op, "baseValue": base_value, "eliteValue": elite_value}
        if names[0] in ("min", "max") and "max" in base_params:
            row["onEquip"]["baseMax"] = int(round(base_params.get("max", base_value)))
            row["onEquip"]["eliteMax"] = int(round(elite_params.get("max", elite_value)))
        wired.append((row["itemId"], op, base_value, elite_value))

    # Refresh the support flags from what actually reaches the runtime now: an item is "applied" when its whole
    # effect is a combat stat map or a wired op, "partial" when only the stat/op half runs and a proc part does not,
    # and "deferred" when nothing reaches the simulation.
    for item in catalog.get("items", []):
        has_combat = bool(item.get("combat"))
        has_op = any(entry[0] in (item["itemId"], item.get("eliteItemId")) for entry in wired)
        note = item.get("supportNote", "")
        deferred = "parts deferred" in note
        if (has_op or has_combat) and not deferred:
            item["runtimeSupport"] = "applied"
        elif has_op or has_combat:
            item["runtimeSupport"] = "partial"
        else:
            item["runtimeSupport"] = "deferred"

    summary = {
        "seeds": len(seeds.get("items", [])),
        "wired": len(wired),
        "skipped": skipped,
        "byOp": {},
        "support": {},
    }
    for entry in wired:
        summary["byOp"][entry[1]] = summary["byOp"].get(entry[1], 0) + 1
    for item in catalog.get("items", []):
        key = item["runtimeSupport"]
        summary["support"][key] = summary["support"].get(key, 0) + 1

    print("wired %d item rows / %d seeds" % (len(wired), summary["seeds"]))
    print("by op:", json.dumps(summary["byOp"], ensure_ascii=False))
    print("support:", json.dumps(summary["support"], ensure_ascii=False))
    if skipped:
        print("skipped:", skipped[:6])
    if check_only:
        print("--check: no files written")
        return
    with io.open(SEEDS, "w", encoding="utf-8") as handle:
        json.dump(seeds, handle, ensure_ascii=False, indent=1)
    with io.open(CATALOG, "w", encoding="utf-8") as handle:
        json.dump(catalog, handle, ensure_ascii=False, indent=1)
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with io.open(REPORT, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=1)
    print("wrote", SEEDS, "+", CATALOG)


if __name__ == "__main__":
    main()
