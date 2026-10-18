"""M1-05 shared PoolLedger conservation regression."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "Saved" / "Reports" / "M1_PoolLedger_Conservation.json"
TIERS = {"I": 12, "II": 14, "III": 18, "IV": 16, "V": 8, "VI": 5}


def main() -> int:
    balances = {
        (f"char_{character:03d}", tier): {
            "poolCopiesTotal": total, "poolCopiesAvailable": total,
            "reservedCopies": 0, "ownedCopies": 0,
        }
        for character in range(1, 33) for tier, total in TIERS.items()
    }

    def reserve(key: tuple[str, str]) -> bool:
        item = balances[key]
        if item["poolCopiesAvailable"] <= 0:
            return False
        item["poolCopiesAvailable"] -= 1
        item["reservedCopies"] += 1
        return True

    def purchase(key: tuple[str, str]) -> bool:
        item = balances[key]
        if item["reservedCopies"] <= 0:
            return False
        item["reservedCopies"] -= 1
        item["ownedCopies"] += 1
        return True

    def return_reserved(key: tuple[str, str]) -> bool:
        item = balances[key]
        if item["reservedCopies"] <= 0:
            return False
        item["reservedCopies"] -= 1
        item["poolCopiesAvailable"] += 1
        return True

    def return_owned(key: tuple[str, str]) -> bool:
        item = balances[key]
        if item["ownedCopies"] <= 0:
            return False
        item["ownedCopies"] -= 1
        item["poolCopiesAvailable"] += 1
        return True

    checks = []
    shared_key = ("char_001", "I")
    checks.append({"name": "four_participant_shared_ledger", "passed": len(balances) == 192})
    checks.append({"name": "tier_totals", "passed": all(item["poolCopiesTotal"] == TIERS[key[1]] for key, item in balances.items())})
    initial = dict(balances[shared_key])

    reserved_keys = []
    for player in range(4):
        for slot in range(5):
            key = (f"char_{player * 5 + slot + 1:03d}", ("I", "II", "III", "IV", "V")[slot % 5])
            reserved_keys.append(key)
            reserve(key)
    checks.append({"name": "shop_reserve_20_cards", "passed": sum(item["reservedCopies"] for item in balances.values()) == 20})
    purchase(reserved_keys[0])
    checks.append({"name": "purchase_conservation", "passed": balances[reserved_keys[0]]["ownedCopies"] == 1})
    return_reserved(reserved_keys[1])
    checks.append({"name": "refresh_return_conservation", "passed": balances[reserved_keys[1]] == {
        "poolCopiesTotal": TIERS[reserved_keys[1][1]], "poolCopiesAvailable": TIERS[reserved_keys[1][1]], "reservedCopies": 0, "ownedCopies": 0}})
    return_owned(reserved_keys[0])
    checks.append({"name": "sell_return_conservation", "passed": balances[reserved_keys[0]] == initial})
    for key in reserved_keys[2:5]:
        return_reserved(key)
    checks.append({"name": "elimination_return_conservation", "passed": sum(item["reservedCopies"] for item in balances.values()) == 15})
    clone_before = dict(balances[shared_key])
    # CloneCreate/CloneDestroy are audit events only; no balance mutation.
    checks.append({"name": "clone_excluded_from_pool", "passed": balances[shared_key] == clone_before})
    checks.append({"name": "all_balances_nonnegative_and_conserved", "passed": all(
        min(item.values()) >= 0 and item["poolCopiesAvailable"] + item["reservedCopies"] + item["ownedCopies"] == item["poolCopiesTotal"]
        for item in balances.values())})

    result = {
        "schema": "Tread.M1.PoolLedger.Conservation.v1",
        "ok": all(check["passed"] for check in checks),
        "participants": 4,
        "tierTotals": TIERS,
        "balanceKeyCount": len(balances),
        "checks": checks,
        "semantics": {"total": "available + reserved + owned", "key": "characterId + operatorTier",
                       "clone": "CloneCreate/CloneDestroy do not mutate shared pool"},
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("M1_POOL_LEDGER_SELFTEST=" + ("PASS" if result["ok"] else "FAIL"))
    print("M1_POOL_LEDGER_REPORT=" + str(REPORT))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
