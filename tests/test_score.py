import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from residual_desk.__main__ import main
from residual_desk.score import POLICIES, score_path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "fixtures" / "calls.jsonl"


def _write(records: list[dict]) -> Path:
    directory = Path(tempfile.mkdtemp())
    path = directory / "calls.jsonl"
    path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
    return path


PRICES = {"type": "prices", "rules": "0.002", "small": "0.012", "big": "0.080", "note": "illustrative"}


class ScoreTests(unittest.TestCase):
    def test_fixture_cost_against_close_rate(self) -> None:
        report = score_path(FIXTURE)
        self.assertEqual(tuple(summary.policy for summary in report.summaries), POLICIES)
        by_policy = {summary.policy: summary for summary in report.summaries}
        self.assertEqual(by_policy["always-big"].closed, 11)
        self.assertEqual(by_policy["always-big"].total, 12)
        self.assertEqual(by_policy["always-big"].cost, Decimal("0.960"))
        self.assertEqual(by_policy["rules-then-big"].closed, 11)
        self.assertEqual(by_policy["rules-then-big"].cost, Decimal("0.664"))
        self.assertEqual(by_policy["small-judge-then-big"].closed, 10)
        self.assertEqual(by_policy["small-judge-then-big"].cost, Decimal("0.384"))

    def test_small_false_close_does_not_escalate(self) -> None:
        path = _write(
            [
                PRICES,
                {
                    "type": "call",
                    "id": "billing-dispute",
                    "title": "Partial refund outside the published window",
                    "rules": "pass",
                    "small": "close",
                    "big": "close",
                    "can_close": ["big"],
                },
            ]
        )
        report = score_path(path)
        routes = {route.policy: route for route in report.routes}
        self.assertFalse(routes["small-judge-then-big"].closed)
        self.assertEqual(routes["small-judge-then-big"].reason, "false close")
        self.assertEqual(routes["small-judge-then-big"].cost, Decimal("0.012"))
        self.assertTrue(routes["rules-then-big"].closed)
        self.assertEqual(routes["rules-then-big"].cost, Decimal("0.082"))
        self.assertTrue(routes["always-big"].closed)
        self.assertEqual(routes["always-big"].cost, Decimal("0.080"))

    def test_rules_keep_does_not_pay_the_big_model(self) -> None:
        path = _write(
            [
                PRICES,
                {
                    "type": "call",
                    "id": "store-hours",
                    "title": "Store hours",
                    "rules": "close",
                    "small": "close",
                    "big": "close",
                    "can_close": ["rules", "small", "big"],
                },
            ]
        )
        report = score_path(path)
        routes = {route.policy: route for route in report.routes}
        self.assertEqual(routes["rules-then-big"].tier, "rules")
        self.assertEqual(routes["rules-then-big"].cost, Decimal("0.002"))
        self.assertEqual(routes["small-judge-then-big"].tier, "small")
        self.assertEqual(routes["small-judge-then-big"].cost, Decimal("0.012"))
        self.assertEqual(routes["always-big"].cost, Decimal("0.080"))

    def test_nobody_can_close(self) -> None:
        path = _write(
            [
                PRICES,
                {
                    "type": "call",
                    "id": "legal-threat",
                    "title": "Caller wants a lawyer",
                    "rules": "pass",
                    "small": "pass",
                    "big": "pass",
                    "can_close": [],
                },
            ]
        )
        report = score_path(path)
        self.assertTrue(all(summary.closed == 0 for summary in report.summaries))
        costs = {summary.policy: summary.cost for summary in report.summaries}
        self.assertEqual(costs["always-big"], Decimal("0.080"))
        self.assertEqual(costs["rules-then-big"], Decimal("0.082"))
        self.assertEqual(costs["small-judge-then-big"], Decimal("0.092"))

    def test_prices_must_be_marked_illustrative(self) -> None:
        path = _write(
            [
                {"type": "prices", "rules": "0.002", "small": "0.012", "big": "0.080"},
                {
                    "type": "call",
                    "id": "store-hours",
                    "title": "Store hours",
                    "rules": "close",
                    "small": "close",
                    "big": "close",
                    "can_close": ["rules"],
                },
            ]
        )
        with self.assertRaises(ValueError):
            score_path(path)

    def test_cli(self) -> None:
        from io import StringIO
        from contextlib import redirect_stdout

        buf = StringIO()
        with redirect_stdout(buf):
            code = main([str(FIXTURE)])
        self.assertEqual(code, 0)
        text = buf.getvalue()
        self.assertIn("small-judge-then-big   10/12       83.3%     0.384", text)
        self.assertIn("rules-then-big         11/12       91.7%     0.664", text)
        self.assertIn("always-big             11/12       91.7%     0.960", text)
        self.assertIn("Prices are illustrative", text)


if __name__ == "__main__":
    unittest.main()
