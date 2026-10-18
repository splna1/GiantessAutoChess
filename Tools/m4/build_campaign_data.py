#!/usr/bin/env python3
"""M4-D/E (host-side): 16-stage campaign data and the scripted PvE / leader opponents (LeaderRounds.json).

Input:
  <legacy>/MyProject/Assets/Resources/Tread/campaign_16.json   16 stages: country, landmark, rule text, modifiers
                                                               (old Unity project, read-only)
  Content/Data/Generated/CharacterRosterMap.json              the 112 cards, for the opponent lineups
Output:
  Content/Data/Generated/Campaign16.json     stages with the modifiers mapped onto Tread's rules (see MODIFIERS)
  Content/Data/Generated/LeaderRounds.json   R1-R2 garrisons (PvE) and the R12 leader of every stage
  Saved/Reports/M4_Campaign_Data_Validation.json

    python Tools/m4/build_campaign_data.py

Document 06: R1-R2 are PvE, R12 is the leader round, and the leader's lineup, health, behaviour, timeout and
settlement come from data, never from C++.  The lineups here are placeholders (plan risk table: "先以占位领袖完成流程,
再替换最终演出"): deterministic picks from the roster, harder with each stage's aiLevel.
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LEGACY = Path("F:/AI/workbuddy/GiantessAutoChess/MyProject/Assets/Resources/Tread/campaign_16.json")
ROSTER = ROOT / "Content/Data/Generated/CharacterRosterMap.json"
CAMPAIGN = ROOT / "Content/Data/Generated/Campaign16.json"
LEADERS = ROOT / "Content/Data/Generated/LeaderRounds.json"
REPORT = ROOT / "Saved/Reports/M4_Campaign_Data_Validation.json"
TIERS = ["I", "II", "III", "IV", "V", "VI"]

# How each campaign_16 modifier lands in Tread (N1 rules, doc 149: no building materials economy).
MODIFIERS = {
    "aiLevel": "AI players: +(aiLevel-1) base income per settlement; leader lineup size/stars grow with it",
    "garrisonBonus": "R1-R2 garrisons field this many extra units",
    "enemyHpBonus": "the three AI players start with this much extra base health (原文: 七名AI地标耐久)",
    "startGoldBonus": "player starting funds (round 1), floored at 0",
    "incomeBonus": "player base income per settlement",
    "damageTakenPercent": "player base-health loss after a lost battle, in percent",
    "prepareSecondsDelta": "preparation timer seconds (30 + delta)",
    "pveMaterialPercent": "not applicable: N1 has no building-material economy (doc 149); shown as text only",
    "buildingRewardPercent": "not applicable: N1 has no building-material economy (doc 149); shown as text only",
}


def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def main():
    raw = LEGACY.read_bytes()
    source = json.loads(raw.decode("utf-8-sig"))
    roster = json.loads(ROSTER.read_text(encoding="utf-8"))["characters"]
    by_tier = {t: sorted(r["characterId"] for r in roster if r["operatorTier"] == t) for t in TIERS}

    def pick(tier, n, offset):
        pool = by_tier[tier]
        return [pool[(offset + i * 7) % len(pool)] for i in range(n)]

    garrisons = []
    for rnd, (tier, count) in ((1, ("I", 2)), (2, ("II", 3))):
        garrisons.append({"round": rnd, "opponentId": "garrison_r%d" % rnd, "kind": "Garrison",
                          "displayName": "城市守军（第 %d 回合）" % rnd,
                          "lineup": [{"characterId": c, "star": 1} for c in pick(tier, count, rnd)],
                          "extraUnitCharacterId": pick("I", 1, 11)[0],
                          "health": 0, "behavior": "HoldPosition", "timeoutSec": 30,
                          "settlement": {"lossBase": 1, "lossPerSurvivor": 1, "winFunds": 1,
                                         "winDamageBase": 0, "winDamagePerSurvivor": 0}})

    stages, leaders = [], []
    for s in source["stages"]:
        i, ai = s["index"], s["aiLevel"]
        size = 4 + ai
        star = 1 if ai <= 2 else 2
        lineup = [{"characterId": c, "star": star} for c in pick("VI", 2, i) + pick("V", 2, i) + pick("IV", size - 4, i)]
        leader_id = "leader_stage_%02d" % i
        leaders.append({"round": 12, "opponentId": leader_id, "kind": "Leader",
                        "displayName": "%s守备领袖·%s（占位）" % (s["country"].split(" ")[0], s["landmark"]),
                        "lineup": lineup, "health": 60 + 10 * ai, "behavior": "FocusWeakest", "timeoutSec": 45,
                        "settlement": {"lossBase": 3 + ai, "lossPerSurvivor": 2, "winFunds": 0,
                                       "winDamageBase": 5, "winDamagePerSurvivor": 3}})
        stages.append({"index": i, "country": s["country"], "landmark": s["landmark"], "rule": s["rule"],
                       "effect": s["effect"], "aiLevel": ai, "garrisonBonus": s["garrisonBonus"],
                       "enemyHpBonus": s["enemyHpBonus"], "startGoldBonus": s["startGoldBonus"],
                       "incomeBonus": s["incomeBonus"], "damageTakenPercent": s["damageTakenPercent"],
                       "prepareSecondsDelta": s["prepareSecondsDelta"],
                       "pveMaterialPercent": s["pveMaterialPercent"], "buildingRewardPercent": s["buildingRewardPercent"],
                       "leaderId": leader_id, "board": "/Game/Tread/Maps/M3_Paris_Match",
                       "boardNote": "paris board for every stage until the stage's own city lands (plan M4: 可玩棋盘 + 地标标识)"})

    ids = {r["characterId"] for r in roster}
    used = [u["characterId"] for o in garrisons + leaders for u in o["lineup"]] + [g["extraUnitCharacterId"] for g in garrisons]
    checks = {
        "stages_16": len(stages) == 16,
        "stage_indices_1_to_16": [s["index"] for s in stages] == list(range(1, 17)),
        "stage1_is_paris": stages[0]["country"] == "法国" and stages[0]["landmark"] == "埃菲尔铁塔",
        "leader_per_stage": len({l["opponentId"] for l in leaders}) == 16,
        "lineup_ids_in_roster": all(c in ids for c in used),
        "garrisons_r1_r2": [g["round"] for g in garrisons] == [1, 2],
        "settlement_fields": all(set(o["settlement"]) == {"lossBase", "lossPerSurvivor", "winFunds", "winDamageBase",
                                                         "winDamagePerSurvivor"} for o in garrisons + leaders),
    }
    ok = all(checks.values())
    dump(REPORT, {"schema": "Tread.M4.CampaignDataValidation.v1", "ok": ok, "checks": checks,
                  "source": {"path": str(LEGACY), "sha256": hashlib.sha256(raw).hexdigest(), "version": source.get("version")},
                  "modifierMapping": MODIFIERS})
    if not ok:
        print("CAMPAIGN validation failed: %s" % [k for k, v in checks.items() if not v])
        return 1
    meta = {"source": str(LEGACY.name), "sourceSha256": hashlib.sha256(raw).hexdigest()}
    dump(CAMPAIGN, dict(schemaVersion="Tread.M4.Campaign16.v1", note=source.get("note"), modifierMapping=MODIFIERS,
                        stages=stages, **meta))
    dump(LEADERS, {"schemaVersion": "Tread.M4.LeaderRounds.v1",
                   "note": "Scripted opponents: R1-R2 garrisons (PvE) and one R12 leader per campaign stage; the free match "
                           "uses stage 1's leader. Placeholder lineups (M4), replaced by authored leaders later.",
                   "garrisons": garrisons, "leaders": leaders, "defaultLeaderId": leaders[0]["opponentId"]})
    print("CAMPAIGN ok stages=%d leaders=%d garrisons=%d" % (len(stages), len(leaders), len(garrisons)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
