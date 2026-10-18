#!/usr/bin/env python3
"""Validate the M1 100-row character mapping and its special pool rules."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# The M1 100-row graybox map, frozen in Content/Data/Source on 2026-10-14; the M4 112-row map and its audit are
# Tools/m4/build_roster_map.py (Saved/Reports/M4_CharacterRosterMap_Audit.json).
MAP = ROOT / "Content" / "Data" / "Source" / "Roster100_Models.json"
REPORT = ROOT / "Saved" / "Reports" / "M1_CharacterRosterMap_Audit.json"

def main() -> int:
    data = json.loads(MAP.read_text(encoding="utf-8"))
    rows = data.get("characters", [])
    ids = [row.get("characterId") for row in rows]
    modernia = [row for row in rows if row.get("ueModelCharacterId") == "modernia"]
    checks = {
        "exactly_100_rows": len(rows) == 100,
        "unique_character_ids": len(ids) == len(set(ids)),
        "required_external_keys": all(row.get("modelAssetPath") and row.get("portraitKey") and row.get("voiceKey") for row in rows),
        "operator_tier_not_derived_from_cost": all(row.get("operatorTier") in {None, "I", "II", "III", "IV", "V", "VI"} for row in rows),
        "muresis_is_modernia": len(modernia) == 1 and modernia[0].get("originalOperatorName") == "缪尔赛思",
        "muresis_not_four_shared_cards": len(modernia) == 1 and not modernia[0].get("poolRule", {}).get("isSharedPool", True),
        "clone_never_consumes_pool": all(row.get("poolRule", {}).get("cloneConsumesPool") is False for row in rows),
    }
    report = {
        "schema": "Tread.M4.CharacterRosterMap.Validator.v1",
        "ok": all(checks.values()),
        "checks": checks,
        "rowCount": len(rows),
        "source": str(MAP.relative_to(ROOT)).replace("\\", "/"),
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
