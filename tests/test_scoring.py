from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.reporting.metrics import build_metrics
from src.scoring.validator import make_cases
from src.scoring.engine import score_runs


class TestEvalV2(unittest.TestCase):
    def _build_df(self, n: int) -> pd.DataFrame:
        rows = []
        for i in range(n):
            rows.append(
                {
                    "timestamp": f"2026-01-01T{i:02d}:00:00Z",
                    "open": 100 + i,
                    "high": 101 + i,
                    "low": 99 + i,
                    "close": 100 + i,
                    "volume": 1.0,
                }
            )
        return pd.DataFrame(rows)

    def test_make_cases_non_overlap_with_warmup(self):
        df = self._build_df(300)
        cases = make_cases(
            df=df,
            lookback=50,
            forward=10,
            sample=10,
            step=5,
            case_mode="non_overlap",
            warmup_bars=120,
        )
        starts = [c["analysis_start"] for c in cases]
        self.assertEqual(starts, [120, 180, 240])

    def test_make_cases_rolling_with_warmup(self):
        df = self._build_df(300)
        cases = make_cases(
            df=df,
            lookback=50,
            forward=10,
            sample=3,
            step=10,
            case_mode="rolling",
            warmup_bars=120,
        )
        starts = [c["analysis_start"] for c in cases]
        self.assertEqual(starts, [120, 130, 140])

    def test_build_metrics_formula(self):
        rows = [
            {"action": "long", "playbook": "trend-pullback", "outcome": "t1_hit", "realized_r": 1.0, "risk_reward": 2.0},
            {"action": "short", "playbook": "trend-pullback", "outcome": "sl_hit", "realized_r": -1.0, "risk_reward": 1.5},
            {"action": "long", "playbook": "breakout-retest", "outcome": "neither", "realized_r": 0.5, "risk_reward": 2.0},
            {"action": "short", "playbook": "breakout-retest", "outcome": "missed_entry", "realized_r": None, "risk_reward": 1.0},
            {"action": "watch", "playbook": "none", "outcome": "no_trade", "realized_r": None, "risk_reward": None},
        ]
        m = build_metrics(rows)
        self.assertEqual(m["tradable_signal_cases"], 4)
        self.assertEqual(m["executed_trade_cases"], 3)
        self.assertEqual(m["t1_hit"], 1)
        self.assertEqual(m["sl_hit"], 1)
        self.assertEqual(m["neither"], 1)
        self.assertAlmostEqual(m["win_rate"], 1 / 3, places=4)
        self.assertAlmostEqual(m["entry_trigger_rate"], 0.75, places=4)
        self.assertAlmostEqual(m["missed_entry_rate"], 0.25, places=4)
        self.assertAlmostEqual(m["win_rate_pct"], 33.33, places=2)
        self.assertAlmostEqual(m["entry_trigger_rate_pct"], 75.0, places=2)
        self.assertAlmostEqual(m["missed_entry_rate_pct"], 25.0, places=2)
        self.assertAlmostEqual(m["expectancy_r"], 0.1667, places=4)
        self.assertAlmostEqual(m["profit_factor_r"], 1.5, places=4)

    def test_score_runs_forward_source_priority(self):
        primary_df = self._build_df(4)
        fallback_df = self._build_df(8)

        parsed_template = {
            "meta": {
                "schema_version": "backtest_sample_v1",
                "symbol": "TEST",
                "interval": "1h",
                "case_id": "case_x",
                "analysis_time": "2026-01-01T00:00:00Z",
                "lookback_bars": 2,
                "forward_bars": 2,
                "data_source": "ohlc",
            },
            "decision": {
                "action": "watch",
                "playbook": "none",
                "checklist": {
                    "htf_direction": "degraded",
                    "position": "fail",
                    "setup_match": "fail",
                    "trigger": "fail",
                    "risk_reward": "fail",
                    "events": "pass",
                    "counter_reason": "pass",
                },
                "checklist_result": "fail",
                "position_size_pct": 0.0,
            },
            "trade": {
                "entry_price": None,
                "stop_loss": None,
                "t1": None,
                "t2": None,
                "risk_reward": None,
                "trigger_type": None,
                "invalidation": None,
            },
        }

        run1 = {
            "run_id": 0,
            "case_id": "c1",
            "analysis_start": 0,
            "symbol": "TEST",
            "interval": "1h",
            "parse_error": False,
            "parsed_json": {**parsed_template, "meta": {**parsed_template["meta"], "case_id": "c1"}},
        }
        run2 = {
            "run_id": 0,
            "case_id": "c2",
            "analysis_start": 10,
            "symbol": "TEST",
            "interval": "1h",
            "parse_error": False,
            "forward_rows": [
                {
                    "timestamp": "2026-01-01T00:00:00Z",
                    "open": 1,
                    "high": 2,
                    "low": 0.5,
                    "close": 1.5,
                    "volume": 1,
                }
            ],
            "parsed_json": {**parsed_template, "meta": {**parsed_template["meta"], "case_id": "c2"}},
        }
        run3 = {
            "run_id": 0,
            "case_id": "c3",
            "analysis_start": 2,
            "symbol": "TEST",
            "interval": "1h",
            "parse_error": False,
            "parsed_json": {**parsed_template, "meta": {**parsed_template["meta"], "case_id": "c3"}},
        }

        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "runs.jsonl"
            with p.open("w", encoding="utf-8") as f:
                for run in (run1, run2, run3):
                    f.write(json.dumps(run, ensure_ascii=False) + "\n")

            scored, source_stats = score_runs(
                runs_file=p,
                primary_df=primary_df,
                fallback_df=fallback_df,
                default_lookback=2,
                default_forward=2,
            )

        sources = [r["forward_source"] for r in scored if r.get("case_id") in ("c1", "c2", "c3")]
        self.assertEqual(sources, ["config_csv", "inline_forward_rows", "eval_input_csv"])
        self.assertEqual(source_stats["config_csv"], 1)
        self.assertEqual(source_stats["inline_forward_rows"], 1)
        self.assertEqual(source_stats["eval_input_csv"], 1)


if __name__ == "__main__":
    unittest.main()
