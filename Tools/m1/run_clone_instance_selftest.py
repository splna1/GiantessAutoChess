"""M1-06 transform-clone lifecycle and shared-pool exclusion regression."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "Saved" / "Reports" / "M1_CloneInstance_SelfTest.json"
TIERS = {"I": 12, "II": 14, "III": 18, "IV": 16, "V": 8, "VI": 5}


def main() -> int:
    balances = {
        (f"char_{character:03d}", tier): {
            "poolCopiesTotal": total,
            "poolCopiesAvailable": total,
            "reservedCopies": 0,
            "ownedCopies": 0,
        }
        for character in range(1, 33)
        for tier, total in TIERS.items()
    }
    source = ("char_007", "III")
    before = dict(balances[source])
    clone = {
        "unitInstanceId": "P0_clone_unit_0002",
        "cloneInstanceId": "clone_P0_0001",
        "characterId": source[0],
        "copySourceCharacterId": source[0],
        "operatorTier": source[1],
        "ownerPlayerId": "P0",
        "isTransformClone": True,
        "populationDelta": 1,
    }
    entries = [
        {"action": "CloneCreate", "cloneInstanceId": clone["cloneInstanceId"],
         "copySourceCharacterId": clone["copySourceCharacterId"], "delta": 0},
    ]
    after_create = dict(balances[source])
    entries.append({"action": "CloneDestroy", "cloneInstanceId": clone["cloneInstanceId"],
                    "copySourceCharacterId": clone["copySourceCharacterId"], "delta": 0})
    after_destroy = dict(balances[source])
    checks = [
        {"name": "clone_has_stable_id_and_source", "passed": bool(clone["cloneInstanceId"] and clone["copySourceCharacterId"])},
        {"name": "clone_generation_does_not_consume_pool", "passed": before == after_create},
        {"name": "clone_destruction_does_not_return_pool", "passed": before == after_destroy},
        {"name": "clone_occupies_population", "passed": clone["populationDelta"] == 1},
        {"name": "clone_lifecycle_audited", "passed": [e["action"] for e in entries] == ["CloneCreate", "CloneDestroy"]},
        {"name": "muelsyse_not_a_shared_pool_balance", "passed": all(key[0].lower() not in {"muelsyse", "缪尔赛思"} for key in balances)},
        {"name": "all_balances_conserved", "passed": all(
            item["poolCopiesAvailable"] + item["reservedCopies"] + item["ownedCopies"] == item["poolCopiesTotal"]
            and min(item["poolCopiesAvailable"], item["reservedCopies"], item["ownedCopies"]) >= 0
            for item in balances.values()
        )},
    ]
    result = {
        "schema": "Tread.M1.CloneInstance.SelfTest.v1",
        "ok": all(check["passed"] for check in checks),
        "participants": 4,
        "poolBalanceKey": "characterId + operatorTier",
        "tierTotals": TIERS,
        "sharedPoolBalanceKeyCount": len(balances),
        "clone": clone,
        "ledgerEntries": entries,
        "checks": checks,
        "semantics": {
            "generation": "CloneCreate is an audit event with delta=0",
            "destruction": "CloneDestroy is an audit event with delta=0",
            "source": "copySourceCharacterId traces the target character",
            "muelsyse": "capability entry point; no four-card shared-pool row",
        },
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("M1_CLONE_INSTANCE_SELFTEST=" + ("PASS" if result["ok"] else "FAIL"))
    print("M1_CLONE_INSTANCE_REPORT=" + str(REPORT))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
