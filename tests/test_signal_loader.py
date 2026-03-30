from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from src.pipeline.signal_loader import import_legacy_signals, load_signal_index, load_signal_snapshot


class TestSignalLoader(unittest.TestCase):
    def test_load_signal_index_and_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            sig_dir = root / "outputs" / "signals" / "BTCUSDT" / "20260327_120000"
            sig_dir.mkdir(parents=True, exist_ok=True)
            (sig_dir / "snapshot.json").write_text(
                json.dumps({"time_utc": "2026-03-27T12:00:00Z", "price_now": 70000}),
                encoding="utf-8",
            )
            idx = root / "outputs" / "signals" / "BTCUSDT" / "index.jsonl"
            idx.parent.mkdir(parents=True, exist_ok=True)
            idx.write_text(
                json.dumps(
                    {
                        "signal_id": "20260327_120000",
                        "symbol": "BTCUSDT",
                        "timestamp_utc": "2026-03-27T12:00:00Z",
                        "path": "20260327_120000/",
                    },
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            rows = load_signal_index("BTCUSDT", outputs_root=root / "outputs")
            self.assertEqual(len(rows), 1)
            snap = load_signal_snapshot("BTCUSDT", rows[0], outputs_root=root / "outputs")
            self.assertEqual(snap["price_now"], 70000)

    def test_import_legacy_signals(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            old = root / "data" / "binance_kline" / "BTCUSDT"
            old.mkdir(parents=True, exist_ok=True)
            (old / "analysis_skill_snapshot.json").write_text(
                json.dumps(
                    {
                        "time_utc": "2026-03-27T12:00:00Z",
                        "price_now": 70000,
                        "decision": "watch",
                        "bias": "bearish",
                        "confidence": "medium",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            (old / "analysis_skill_report.md").write_text("legacy report", encoding="utf-8")

            result = import_legacy_signals(root=root, symbol="BTCUSDT")
            self.assertEqual(result["imported"], 1)
            idx = root / "outputs" / "signals" / "BTCUSDT" / "index.jsonl"
            self.assertTrue(idx.exists())
            lines = [ln for ln in idx.read_text(encoding="utf-8").splitlines() if ln.strip()]
            self.assertEqual(len(lines), 1)


if __name__ == "__main__":
    unittest.main()
