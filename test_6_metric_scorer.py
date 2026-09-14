"""Unit tests for ConvictionScorer and the 6-Metric Small/Mid-Cap fundamental architecture."""
import unittest
from conviction_scorer import ConvictionScorer, classify


class Test6MetricScorer(unittest.TestCase):
    def test_market_cap_classification(self):
        self.assertEqual(classify(500.0), "S")
        self.assertEqual(classify(6999.0), "S")
        self.assertEqual(classify(7000.0), "M")
        self.assertEqual(classify(15861.0), "M")  # EMAMILTD is now Mid-Cap!
        self.assertEqual(classify(19999.0), "M")
        self.assertEqual(classify(20000.0), "L")
        self.assertEqual(classify(50000.0), "L")
        self.assertEqual(classify(None), "U")

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
            "rpt_status": "OK",
            "rpt_pct": 4.5,
        }

        res = scorer.score(fund)
        self.assertEqual(res["stock_class"], "M")
        self.assertTrue(res["unverified_veto"])
        self.assertEqual(res["rating"], "UNVERIFIED_VETO")
        self.assertIn("Unverified", res["display_badge"])
        self.assertIsNotNone(res["score"])

    def test_missing_rpt_gracefully_excludes(self):
        scorer = ConvictionScorer()
        fund = {
            "market_cap_cr": 8000.0,
            "op_lev_ratio": 2.5,
            "pledge_trend": [0.0],
            "pledge_direction": "flat",
            "interest_coverage_trend": "improving",
            "roice_pct": 22.0,
            "fcf_pat_ratio": 1.1,
            "rpt_status": "NOT_FOUND",  # Missing RPT metric
            "rpt_pct": None,
        }

        res = scorer.score(fund)
        self.assertEqual(res["stock_class"], "M")
        self.assertFalse(res.get("unverified_veto", False))
        self.assertNotEqual(res["rating"], "UNVERIFIED_VETO")
        self.assertIn("rpt_pct", res["not_applicable_metrics"])
        self.assertTrue(res["rpt_data_missing"])
        self.assertEqual(res["data_completeness"]["resolved_count"], 5)

    def test_rpt_veto_trigger(self):
        scorer = ConvictionScorer()
        fund = {
            "market_cap_cr": 8000.0,
            "op_lev_ratio": 2.5,
            "pledge_trend": [0.0],
            "pledge_direction": "flat",
            "interest_coverage_trend": "improving",
            "roice_pct": 22.0,
            "fcf_pat_ratio": 1.1,
            "rpt_status": "OK",
            "rpt_pct": 25.0,  # > 20% Veto threshold
        }

        res = scorer.score(fund)
        self.assertTrue(res["veto"])
        self.assertEqual(res["rating"], "VETO")
        self.assertEqual(res["score"], 0)
        self.assertIn("exceeds veto threshold", res["veto_reasons"][0])

    def test_clean_pass_with_data_completeness(self):
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
            "rpt_status": "OK",
            "rpt_pct": 4.5,  # Clean RPT < 10%
        }

        res = scorer.score(fund)
        self.assertEqual(res["stock_class"], "M")
        self.assertFalse(res["veto"])
        self.assertFalse(res["unverified_veto"])
        self.assertEqual(res["rating"], "HIGH_CONVICTION")
        self.assertEqual(res["data_completeness"]["resolved_count"], 6)
        self.assertIn("6-Metric Mode (6/6 metrics resolved)", res["data_completeness"]["label"])


if __name__ == "__main__":
    unittest.main()

