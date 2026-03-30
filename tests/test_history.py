import json
import tempfile
import unittest
from pathlib import Path

from src.pipeline.history import (
    archive_conversation,
    archive_signal_record,
    import_conversations,
    list_conversations,
)


class TestHistory(unittest.TestCase):
    def test_archive_conversation_and_signal(self):
        with tempfile.TemporaryDirectory() as td:
            outputs_root = Path(td) / "outputs"

            conv = archive_conversation(
                symbol="BTCUSDT",
                source="claude",
                title="BTC 复盘",
                transcript_md="# 对话\n内容",
                metadata={"model": "gpt-5"},
                timestamp_utc="2026-03-30T10:00:00Z",
                outputs_root=outputs_root,
            )
            self.assertTrue(conv["transcript_path"].exists())
            self.assertTrue(conv["metadata_path"].exists())

            signal = archive_signal_record(
                symbol="BTCUSDT",
                snapshot={
                    "time_utc": "2026-03-30T10:00:00Z",
                    "price_now": 68000,
                    "1h": {"state": "downtrend"},
                    "4h": {"state": "downtrend"},
                    "decision": "watch",
                    "bias": "bearish",
                    "confidence": "medium",
                },
                report_md="# 报告\n观望",
                outputs_root=outputs_root,
            )
            self.assertTrue(signal["snapshot_path"].exists())
            self.assertTrue(signal["report_path"].exists())

            rows = list_conversations(symbol="BTCUSDT", outputs_root=outputs_root)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["symbol"], "BTCUSDT")

    def test_import_conversations_jsonl(self):
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            outputs_root = base / "outputs"
            import_file = base / "import.jsonl"

            items = [
                {
                    "symbol": "BTCUSDT",
                    "source": "chatgpt",
                    "title": "第一次",
                    "timestamp_utc": "2026-03-30T11:00:00Z",
                    "transcript_md": "hello",
                },
                {
                    "symbol": "BTCUSDT",
                    "source": "gemini",
                    "title": "第二次",
                    "timestamp_utc": "2026-03-30T12:00:00Z",
                    "transcript_md": "world",
                    "signal_snapshot": {
                        "time_utc": "2026-03-30T12:00:00Z",
                        "price_now": 68100,
                        "1h": {"state": "uptrend"},
                        "4h": {"state": "downtrend"},
                        "decision": "watch",
                    },
                    "signal_report_md": "signal report",
                },
            ]
            import_file.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in items), encoding="utf-8")

            result = import_conversations(import_file=import_file, outputs_root=outputs_root)
            self.assertEqual(result["imported"], 2)
            self.assertEqual(result["failed"], 0)

            conv_rows = list_conversations(symbol="BTCUSDT", outputs_root=outputs_root)
            self.assertEqual(len(conv_rows), 2)

            signal_index = outputs_root / "signals" / "BTCUSDT" / "index.jsonl"
            self.assertTrue(signal_index.exists())
            lines = [ln for ln in signal_index.read_text(encoding="utf-8").splitlines() if ln.strip()]
            self.assertEqual(len(lines), 1)


if __name__ == "__main__":
    unittest.main()
