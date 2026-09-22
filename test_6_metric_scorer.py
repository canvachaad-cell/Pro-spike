"""Unit tests for ConvictionScorer and the 5-Metric Vikram fundamental architecture."""
import unittest
from conviction_scorer import ConvictionScorer, classify, METRIC_WEIGHTS_VIKRAM


class TestVikramScorer(unittest.TestCase):
    def test_market_cap_classification(self):
        self.assertEqual(classify(500.0), "S")
        self.assertEqual(classify(6999.0), "S")
        self.assertEqual(classify(7000.0), "M")
        self.assertEqual(classify(15861.0), "M")
        self.assertEqual(classify(19999.0), "M")
        self.assertEqual(classify(20000.0), "L")
        self.assertEqual(classify(50000.0), "L")
        self.assertEqual(classify(None), "U")

    def test_weights_sum_to_one(self):
        self.assertAlmostEqual(sum(METRIC_WEIGHTS_VIKRAM.values()), 1.0, places=4)
        self.assertEqual(METRIC_WEIGHTS_VIKRAM["op_leverage"], 0.30)
        self.assertEqual(METRIC_WEIGHTS_VIKRAM["pledge_trend"], 0.25)
        self.assertEqual(METRIC_WEIGHTS_VIKRAM["fcf_quality"], 0.20)
        self.assertEqual(METRIC_WEIGHTS_VIKRAM["interest_coverage"], 0.20)
        self.assertEqual(METRIC_WEIGHTS_VIKRAM["roice"], 0.05)

    def test_missing_pledge_triggers_unverified_veto(self):
        scorer = ConvictionScorer()
        fund = {
            "market_cap_cr": 8000.0,
            "op_lev_ratio": 2.5,
            "pledge_trend": [0.0],
            "pledge_direction": None,  # Missing pledge veto metric
            "interest_coverage_trend": "improving",
            "roice_pct": 22.0,
            "fcf_pat_ratio": 1.1,
        }

        res = scorer.score(fund)
        self.assertEqual(res["stock_class"], "M")
        self.assertTrue(res["unverified_veto"])
        self.assertEqual(res["rating"], "UNVERIFIED_VETO")
        self.assertIn("Unverified", res["display_badge"])
        self.assertIsNotNone(res["score"])

    def test_pledge_over_25_hard_veto(self):
        scorer = ConvictionScorer()
        fund = {
            "market_cap_cr": 8000.0,
            "op_lev_ratio": 2.5,
            "pledge_trend": [30.0],
            "pledge_direction": "flat",
            "interest_coverage_trend": "improving",
            "roice_pct": 22.0,
            "fcf_pat_ratio": 1.1,
        }

        res = scorer.score(fund)
        self.assertTrue(res["veto"])
        self.assertEqual(res["rating"], "VETO")
        self.assertEqual(res["score"], 0)
        self.assertIn("exceeds 25% threshold", res["veto_reasons"][0])

    def test_fcf_divergence_hard_veto(self):
        scorer = ConvictionScorer()
        fund = {
            "market_cap_cr": 8000.0,
            "op_lev_ratio": 2.5,
            "pledge_trend": [0.0],
            "pledge_direction": "flat",
            "interest_coverage_trend": "improving",
            "roice_pct": 22.0,
            "fcf_pat_ratio": 4.5,  # Divergence > 3.0x
        }

        res = scorer.score(fund)
        self.assertTrue(res["veto"])
        self.assertEqual(res["rating"], "VETO")
        self.assertEqual(res["score"], 0)
        self.assertIn("FCF/PAT 3yr cumulative divergence", res["veto_reasons"][0])

    def test_clean_pass_5_metric_mode(self):
        scorer = ConvictionScorer()
        fund = {
            "market_cap_cr": 12000.0,  # Mid-Cap
            "op_lev_ratio": 3.5,
            "op_lev_inflecting": True,
            "pledge_trend": [0.0],
            "pledge_direction": "falling",
            "interest_coverage_trend": "improving",
            "roice_pct": 25.0,
            "fcf_pat_ratio": 1.2,
        }

        res = scorer.score(fund)
        self.assertEqual(res["stock_class"], "M")
        self.assertFalse(res["veto"])
        self.assertFalse(res["unverified_veto"])
        self.assertEqual(res["rating"], "HIGH_CONVICTION")
        self.assertEqual(res["data_completeness"]["resolved_count"], 5)
        self.assertEqual(res["data_completeness"]["total_count"], 5)
        self.assertIn("5-Metric Vikram", res["data_completeness"]["label"])


if __name__ == "__main__":
    unittest.main()

