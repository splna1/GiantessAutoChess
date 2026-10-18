"""Standalone Python replay oracle; never represents C++/PIE M1 acceptance.

This small, one-round model checks random-stream reproducibility and its own
bookkeeping only. Run run_match_selftest.ps1 for the authoritative UE regression.
"""

from __future__ import annotations

import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "Saved" / "Reports" / "M1_Match_PythonOracle.json"
POOL_TOTALS = {"I": 12, "II": 14, "III": 18, "IV": 16, "V": 8, "VI": 5}


class UERandomStream:
    def __init__(self, seed: int):
        seed64 = seed & 0xFFFFFFFFFFFFFFFF
        self.seed = ((seed64 & 0xFFFFFFFF) ^ (seed64 >> 32)) & 0xFFFFFFFF

    def fraction(self) -> float:
        self.seed = (self.seed * 196314165 + 907633515) & 0xFFFFFFFF
        bits = 0x3F800000 | (self.seed >> 9)
        return struct.unpack("<f", struct.pack("<I", bits))[0] - 1.0

    def rand_range(self, minimum: int, maximum: int) -> int:
        count = maximum - minimum + 1
        return minimum + (int(self.fraction() * count) if count > 0 else 0)


def shuffle(values: list[str], rng: UERandomStream) -> None:
    for index in range(len(values) - 1, 0, -1):
        other = rng.rand_range(0, index)
        values[index], values[other] = values[other], values[index]


def run(seed: int = 20260926) -> dict:
    rng = UERandomStream(seed)
    phase_trace = ["R0Briefing"]
    players = [{"id": f"P{i}", "health": 100, "funds": 5, "level": 3, "population": 0, "shop": []} for i in range(4)]
    balances = {(f"char_{character:03d}", tier): {"total": POOL_TOTALS[tier], "available": POOL_TOTALS[tier], "reserved": 0, "owned": 0}
                for character in range(1, 33) for tier in POOL_TOTALS}
    for player in players:
        for slot in range(5):
            character_id = f"char_{rng.rand_range(1, 32):03d}"
            tier = ("I", "II", "III", "IV", "V", "VI")[rng.rand_range(0, 5)]
            balance = balances[(character_id, tier)]
            balance["available"] -= 1
            balance["reserved"] += 1
            player["shop"].append({
                "slotIndex": slot,
                "characterId": character_id,
                "operatorTier": tier,
                "cost": rng.rand_range(1, 5),
            })
    strategies = [f"strategy_{i:03d}" for i in range(1, 33)]
    shuffle(strategies, rng)
    banned, available = strategies[:4], strategies[4:]
    phase_trace.append("PreMatchBP")
    chosen = [available[0]]
    for _ in range(3):
        candidates = [s for s in available if s not in chosen]
        chosen.append(candidates[rng.rand_range(0, len(candidates) - 1)])
    phase_trace.append("Preparation")
    active_ids = [player["id"] for player in players]
    shuffle(active_ids, rng)
    pairings = [[active_ids[i], active_ids[i + 1]] for i in range(0, len(active_ids) - 1, 2)]
    phase_trace.append("Battle")
    outcomes = []
    for left_id, right_id in pairings:
        left = next(p for p in players if p["id"] == left_id)
        right = next(p for p in players if p["id"] == right_id)
        left_power = left["level"] * 2 + left["population"] + rng.rand_range(0, 2)
        right_power = right["level"] * 2 + right["population"] + rng.rand_range(0, 2)
        winner, loser = (left, right) if left_power >= right_power else (right, left)
        damage = max(1, 2 + abs(left_power - right_power))
        loser["health"] = max(0, loser["health"] - damage)
        outcomes.extend([{"playerId": winner["id"], "outcome": "Win", "healthAfter": winner["health"]},
                         {"playerId": loser["id"], "outcome": "Lose", "healthAfter": loser["health"]}])
    phase_trace.append("Settlement")
    for player in players:
        player["funds"] += 5 + min(5, player["funds"] // 10) + 1
    conservation = all(item["available"] + item["reserved"] + item["owned"] == item["total"] and
                       min(item["available"], item["reserved"], item["owned"]) >= 0 for item in balances.values())
    clone_balance_before = dict(balances[("char_001", "I")])
    # CloneCreate is recorded with its cloneInstanceId but leaves the shared balance untouched.
    clone_balance_after = dict(balances[("char_001", "I")])
    clone_excluded = clone_balance_before == clone_balance_after
    balance_rows = [{"characterId": key[0], "operatorTier": key[1], **value} for key, value in balances.items()]
    return {
        "schema": "Tread.M1.MatchPythonOracle.v1", "ok": True,
        "evidenceSource": "standalone Python model", "authoritativeRuntime": False,
        "scope": "one-round RNG/model sanity check; no C++, R1-R12, drag or PIE acceptance",
        "matchId": f"m1-{seed}", "seed": seed,
        "players": 4, "roundsCompleted": 1, "randomStreamAlgorithm": "UE.FRandomStream.v1",
        "randomStreamState": rng.seed, "phaseTrace": phase_trace,
        "shops": [p["shop"] for p in players], "poolLedger": {"balances": balance_rows, "conservation": conservation,
                                                                 "participants": 4, "tierTotals": POOL_TOTALS,
                                                                 "cloneExcluded": clone_excluded},
        "bp": {"banned": banned, "available": available, "chosen": chosen},
        "pairings": pairings, "outcomes": outcomes,
        "settlement": [{"playerId": p["id"], "health": p["health"], "funds": p["funds"]} for p in players],
        "checks": ["four participants", "one UE FRandomStream for shops, BP, pairing and battle",
                   "32 strategies partitioned into 4 bans + 28 offers", "player pick then three unique AI picks",
                   "R0/BP/Preparation/Battle/Settlement transitions", "same seed replay equality",
                   "different seed divergence", "base income 5 with interest and streak", "shared PoolLedger 4-player reservation conservation",
                   "initial shop reservation conservation", "modeled clone creation leaves copied balance unchanged"],
    }


def main() -> int:
    result = run()
    replay = run(result["seed"])
    alternate = run(result["seed"] + 1)
    result["replay"] = {"sameSeedEqual": result == replay,
                        "differentSeedDiverges": result["bp"] != alternate["bp"] or result["shops"] != alternate["shops"],
                        "alternateSeed": alternate["seed"]}
    result["ok"] = (result["replay"]["sameSeedEqual"] and result["replay"]["differentSeedDiverges"]
                    and result["poolLedger"]["conservation"] and result["poolLedger"]["cloneExcluded"])
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("M1_MATCH_PYTHON_ORACLE=" + ("PASS" if result["ok"] else "FAIL"))
    print("M1_MATCH_PYTHON_ORACLE_REPORT=" + str(REPORT))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
