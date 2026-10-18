"""Regression checks for the strategy-to-roster foreign-key gate."""

import unittest

from validate_m1_contract import validate_strategy_issuer_foreign_keys


class StrategyIssuerForeignKeyTests(unittest.TestCase):
    def setUp(self):
        self.source = {"strategies": [
            {"strategyId": f"strategy_{index:03d}", "issuerCharacterId": f"char_{index:03d}"}
            for index in range(1, 33)
        ]}
        self.roster = {"characters": [
            {"characterId": f"char_{index:03d}"} for index in range(1, 101)
        ]}

    def test_valid_references_pass(self):
        self.assertEqual(validate_strategy_issuer_foreign_keys(self.source, self.roster), [])

    def test_missing_issuer_fails(self):
        self.source["strategies"][4]["issuerCharacterId"] = "char_999"
        self.assertTrue(any("strategy_005" in error for error in
                            validate_strategy_issuer_foreign_keys(self.source, self.roster)))

    def test_duplicate_roster_id_fails(self):
        self.roster["characters"][99]["characterId"] = "char_001"
        self.assertTrue(any("unique" in error for error in
                            validate_strategy_issuer_foreign_keys(self.source, self.roster)))

    def test_malformed_roster_id_fails_cleanly(self):
        self.roster["characters"][99]["characterId"] = ["char_100"]
        self.assertTrue(any("unique" in error for error in
                            validate_strategy_issuer_foreign_keys(self.source, self.roster)))

    def test_missing_roster_rows_fails(self):
        self.roster["characters"].pop()
        self.assertTrue(any("exactly 100" in error for error in
                            validate_strategy_issuer_foreign_keys(self.source, self.roster)))


if __name__ == "__main__":
    unittest.main()
