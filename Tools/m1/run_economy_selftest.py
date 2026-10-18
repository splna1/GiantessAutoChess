"""M1-04 economy regression for the authoritative shop/economy rules."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "Saved" / "Reports" / "M1_Economy_SelfTest.json"


LEVEL_XP = [2, 2, 6, 10, 20, 36, 56, 80, 0]


@dataclass
class Player:
    funds: int = 5
    level: int = 3
    experience: int = 0
    exp_to_next: int = 6
    population_used: int = 0
    population_limit: int = 3
    win_streak: int = 0
    loss_streak: int = 0
    bench: list[dict] = field(default_factory=list)
    shop: list[dict] = field(default_factory=list)
    locked: bool = False
    refresh_index: int = 0


class Economy:
    def __init__(self, seed: int = 20260926):
        self.rng = random.Random(seed)
        self.player = Player()
        self.timer = 30.0
        self.phase = "Preparation"
        self.build_shop()

    def build_shop(self):
        self.player.shop = [
            {"slotIndex": i, "characterId": f"char_{self.rng.randrange(1, 33):03d}", "cost": self.rng.randrange(1, 6), "sold": False}
            for i in range(5)
        ]

    def income(self):
        streak = max(self.player.win_streak, self.player.loss_streak)
        return {
            "base": 5,
            "interest": min(5, self.player.funds // 10),
            "streak": 3 if streak >= 6 else (2 if streak >= 4 else (1 if streak >= 2 else 0)),
            "other": 0,
        }

    def purchase(self, slot: int):
        item = self.player.shop[slot]
        if item["sold"] or len(self.player.bench) >= 8 or self.player.funds < item["cost"]:
            return False
        self.player.funds -= item["cost"]
        self.player.bench.append({"id": f"unit_{len(self.player.bench) + 1}", "cost": item["cost"]})
        item["sold"] = True
        return True

    def refresh(self):
        if self.player.funds < 2:
            return False
        self.player.funds -= 2
        self.player.refresh_index += 1
        self.build_shop()
        return True

    def auto_next_round(self):
        old = self.player.refresh_index
        if not self.player.locked:
            self.player.refresh_index += 1
            self.build_shop()
        return old, self.player.refresh_index

    def sell(self):
        unit = self.player.bench.pop()
        self.player.funds += unit["cost"]
        return unit

    def buy_xp(self):
        if self.player.level >= 9 or self.player.funds < 4:
            return False
        self.player.funds -= 4
        self.player.experience += 4
        while self.player.level < 9 and self.player.experience >= self.player.exp_to_next:
            self.player.experience -= self.player.exp_to_next
            self.player.level += 1
            self.player.population_limit = self.player.level
            self.player.exp_to_next = LEVEL_XP[self.player.level - 1]
        return True

    def advance(self, seconds: float):
        self.timer = max(0.0, self.timer - seconds)
        if self.timer == 0.0:
            self.phase = "Battle"


def main() -> int:
    checks: list[dict] = []

    def check(name: str, passed: bool, detail: str = ""):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    economy = Economy()
    check("five_shop_slots", len(economy.player.shop) == 5)
    initial_funds = economy.player.funds
    cost = economy.player.shop[0]["cost"]
    check("purchase", economy.purchase(0) and len(economy.player.bench) == 1 and economy.player.funds == initial_funds - cost)
    check("duplicate_purchase_rejected", not economy.purchase(0))
    economy.player.funds = 100
    economy.player.locked = True
    before_manual = [slot["characterId"] for slot in economy.player.shop]
    check("manual_refresh_while_locked", economy.refresh() and economy.player.locked)
    check("manual_refresh_changes_shop", before_manual != [slot["characterId"] for slot in economy.player.shop])
    old_index, new_index = economy.auto_next_round()
    check("locked_auto_refresh_preserved", old_index == new_index)
    economy.player.locked = False
    old_index, new_index = economy.auto_next_round()
    check("unlocked_auto_refresh", new_index == old_index + 1)
    funds_before_sell = economy.player.funds
    sold = economy.sell()
    check("sell_returns_cost", economy.player.funds == funds_before_sell + sold["cost"] and not economy.player.bench)
    economy.player.funds = 20
    level_before = economy.player.level
    check("buy_experience", economy.buy_xp() and economy.player.funds == 16)
    check("experience_level_progression", economy.buy_xp() and economy.player.level == level_before + 1 and economy.player.population_limit == economy.player.level)
    economy.player.funds = 59
    economy.player.win_streak = 6
    income = economy.income()
    check("interest_cap", income["interest"] == 5)
    check("streak_246", income["streak"] == 3)
    check("thirty_second_preparation", economy.timer == 30.0)
    economy.advance(29.5)
    check("preparation_countdown", economy.phase == "Preparation" and economy.timer == 0.5)
    economy.advance(0.5)
    check("countdown_starts_battle", economy.phase == "Battle" and economy.timer == 0.0)
    hud = {"funds": economy.player.funds, "level": economy.player.level, "populationUsed": economy.player.population_used,
           "populationLimit": economy.player.population_limit, "nextRoundIncome": economy.income()}
    check("economy_hud_fields", set(hud) == {"funds", "level", "populationUsed", "populationLimit", "nextRoundIncome"})

    result = {
        "schema": "Tread.M1.EconomySelfTest.v1",
        "ok": all(item["passed"] for item in checks),
        "rules": {"shopSlots": 5, "refreshCost": 2, "baseIncome": 5, "interestStep": 10, "interestCap": 5,
                  "experienceCost": 4, "experienceAmount": 4, "preparationSeconds": 30},
        "checks": checks,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("M1_ECONOMY_SELFTEST=" + ("PASS" if result["ok"] else "FAIL"))
    print("M1_ECONOMY_SELFTEST_REPORT=" + str(REPORT))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
