#!/usr/bin/env python3
"""Validate the N1/N2 generated data (import_stronghold_data.py) -> Saved/Reports/N1_Data_Validation.json.

Checks: 112 unique model<->operator bindings; every card has >= 1 trait with a known trigger and ops; pact names used
by cards/items/traits exist; thresholds ascending; pool copies / prices match Economy.json; 40 strategies with
start health > 0; deterministic regeneration (sha256 of outputs before/after a second run).
Exit code 0 = ok."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GEN = ROOT / "Content/Data/Generated"
OUT = ROOT / "Saved/Reports/N1_Data_Validation.json"
FILES = ["Roster112.json", "Economy.json", "Pacts.json", "Traits.json", "M2_ItemSeeds.json", "StrategyEffects.json", "Strategies40.json"]
TRIGGERS = {"Acquire", "RoundStart", "RoundEnd", "Battle", "Sell", "Passive", "ShopRefresh"}
KNOWN_OPS = {"AddStacks", "GainFundsNextRound", "GainFunds", "GrantItem", "GrantUnit", "TriggerTraits", "PurchaseCostOverride",
             "CombineCopies", "StackScaledStat", "FlatStat", "AmplifyFrontStackGain", "FreeRefresh", "Deferred"}


def load(name):
    return json.loads((GEN / name).read_text(encoding="utf-8"))


def digest():
    return {f: hashlib.sha256((GEN / f).read_bytes()).hexdigest() for f in FILES}


def main():
    errors, warnings = [], []
    before = digest()
    subprocess.run([sys.executable, str(ROOT / "Tools/m4/import_stronghold_data.py")], check=True, capture_output=True)
    after = digest()
    if before != after:
        errors.append("regeneration is not byte-identical: %s" % [f for f in FILES if before[f] != after[f]])
    roster, econ, pacts, traits = load("Roster112.json"), load("Economy.json"), load("Pacts.json"), load("Traits.json")
    items, strategies = load("M2_ItemSeeds.json"), load("Strategies40.json")
    chars = roster["characters"]
    if len(chars) != 112:
        errors.append("roster has %d characters" % len(chars))
    for key in ("characterId", "operatorChessId"):
        values = [c[key] for c in chars]
        if len(set(values)) != len(values):
            errors.append("duplicate %s in roster" % key)
    mmd = [c for c in chars if c["modelSource"].startswith("mmd:")]
    if len(mmd) != 12:
        errors.append("expected 12 MMD models, found %d" % len(mmd))
    pact_ids = {p["pactId"] for p in pacts["pacts"]}
    if len(pact_ids) != 23:
        errors.append("expected 23 pacts, found %d" % len(pact_ids))
    for p in pacts["pacts"]:
        if p["thresholds"] != sorted(p["thresholds"]) or not p["thresholds"]:
            errors.append("pact %s thresholds %s" % (p["pactId"], p["thresholds"]))
    copies = econ["poolCopiesByTier"]
    support = {}
    for card, c in zip(traits["cards"], chars):
        if card["characterId"] != c["characterId"]:
            errors.append("card/roster order mismatch at %s" % card["characterId"])
        for pact in card["corePacts"] + card["adjunctPacts"]:
            if pact not in pact_ids:
                errors.append("%s unknown pact %s" % (card["characterId"], pact))
        if card["price"] != econ["priceByTier"][card["operatorTier"]]:
            errors.append("%s price %s != tier price" % (card["characterId"], card["price"]))
        expected = econ["poolCopiesOverrides"].get(c["operatorChessId"], copies[card["operatorTier"]])
        if card["poolCopies"] != expected:
            errors.append("%s pool copies %s != %s" % (card["characterId"], card["poolCopies"], expected))
        if not card["traits"]:
            errors.append("%s has no trait" % card["characterId"])
        for t in card["traits"]:
            support[t["runtimeSupport"]] = support.get(t["runtimeSupport"], 0) + 1
            if t["trigger"] not in TRIGGERS:
                errors.append("%s unknown trigger %s" % (t["id"], t["trigger"]))
            for e in t["effects"]:
                if e["op"] not in KNOWN_OPS:
                    errors.append("%s unknown op %s" % (t["id"], e["op"]))
                for pact in e.get("pacts", []):
                    if pact not in pact_ids:
                        errors.append("%s effect names unknown pact %s" % (t["id"], pact))
            if t["runtimeSupport"] != "applied":
                warnings.append("%s %s: %s" % (t["id"], t["runtimeSupport"], t["displayText"][:60]))
    for it in items["items"]:
        for pact in it["providesPacts"]:
            if pact not in pact_ids:
                errors.append("item %s unknown pact %s" % (it["displayName"], pact))
    if len(strategies["strategies"]) != 40:
        errors.append("expected 40 strategies, found %d" % len(strategies["strategies"]))
    for s in strategies["strategies"]:
        if s["startHealth"] <= 0:
            errors.append("%s start health %s" % (s["strategyId"], s["startHealth"]))
    report = {"schema": "Tread.N1.DataValidation.v1", "ok": not errors, "errors": errors, "warnings": warnings,
              "counts": {"characters": len(chars), "mmdModels": len(mmd), "pacts": len(pact_ids), "items": len(items["items"]),
                         "strategies": len(strategies["strategies"]), "traits": sum(len(c["traits"]) for c in traits["cards"]),
                         "runtimeSupport": support},
              "deterministic": before == after, "sha256": after, "provenance": roster["provenance"]}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("N1_DATA_VALIDATION=%s errors=%d warnings=%d" % ("PASS" if not errors else "FAIL", len(errors), len(warnings)))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
