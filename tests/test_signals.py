import unittest
import tempfile
import json
from pathlib import Path


class TestSignals(unittest.TestCase):
    def setUp(self):
        # 为每个测试方法创建独立的临时目录，测试结束后自动清理
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp_dir.name) / "outputs"

    def tearDown(self):
        self._tmp_dir.cleanup()

    def test_append_signal_creates_directory_and_index(self):
        from src.pipeline.signals import append_signal
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            snapshot = {
                "time_utc": "2026-03-27T12:00:00Z",
                "price_now": 70000,
                "1h": {"state": "downtrend"},
                "4h": {"state": "downtrend"},
            }
            report_md = "# Test Report\nBTC is bearish."
            signal_meta = {
                "decision": "watch",
                "bias": "bearish",
                "confidence": "medium",
                "playbook": "trend-pullback",
                "conditional_entry": 70050,
                "stop_loss": 70680,
                "t1": 68150,
                "t2": 67450,
            }

            result = append_signal(
                symbol="BTCUSDT",
                snapshot=snapshot,
                report_md=report_md,
                signal_meta=signal_meta,
                outputs_root=root / "outputs",
            )

            # Verify files created
            self.assertTrue(result["snapshot_path"].exists())
            self.assertTrue(result["report_path"].exists())
            self.assertTrue(result["index_path"].exists())

            # Verify index.jsonl has one line
            lines = result["index_path"].read_text().strip().split("\n")
            self.assertEqual(len(lines), 1)
            entry = json.loads(lines[0])
            self.assertEqual(entry["symbol"], "BTCUSDT")
            self.assertEqual(entry["decision"], "watch")
            self.assertEqual(entry["stop_loss"], 70680)

    def test_append_signal_never_overwrites(self):
        from src.pipeline.signals import append_signal
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            kwargs = dict(
                symbol="BTCUSDT",
                snapshot={"time_utc": "2026-03-27T12:00:00Z", "price_now": 70000},
                report_md="Report 1",
                signal_meta={"decision": "watch"},
                outputs_root=root / "outputs",
            )

            r1 = append_signal(**kwargs)
            # Call again with same timestamp — should create a new unique dir, not overwrite
            r2 = append_signal(**kwargs)

            self.assertNotEqual(r1["signal_dir"], r2["signal_dir"])

            # Index should have 2 lines
            lines = r1["index_path"].read_text().strip().split("\n")
            self.assertEqual(len(lines), 2)


    def test_append_signal_preserves_meta(self):
        """验证 snapshot 中的 meta 字段（含 prompt_version / model / data_range）被完整保存，
        确保信号的可复现性元数据不丢失。"""
        from src.pipeline.signals import append_signal

        meta = {
            "prompt_version": "analysis-v1.0",
            "model": "claude-sonnet-4-6",
            "data_range": {"symbol": "BTCUSDT", "intervals": ["4h", "1h"], "bar_count": 200},
            "schema_version": "1.0",
        }
        result = append_signal(
            symbol="BTCUSDT",
            snapshot={"test": True, "meta": meta},
            report_md="# Test with meta",
            signal_meta={"decision": "long", "bias": "bullish", "confidence": "high"},
            outputs_root=self.tmp,
        )
        snapshot = json.loads(result["snapshot_path"].read_text())
        self.assertEqual(snapshot["meta"]["prompt_version"], "analysis-v1.0")
        self.assertEqual(snapshot["meta"]["model"], "claude-sonnet-4-6")
        self.assertIn("data_range", snapshot["meta"])


if __name__ == "__main__":
    unittest.main()
