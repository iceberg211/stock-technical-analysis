import unittest
import tempfile
from pathlib import Path


class TestLayout(unittest.TestCase):
    def test_symbol_layout_flat_paths(self):
        from src.pipeline.layout import SymbolLayout
        sl = SymbolLayout(Path("/tmp/test_run/BTCUSDT"))
        # All files should be directly under base_dir — no human/machine/data subdirs
        self.assertEqual(sl.config_json, Path("/tmp/test_run/BTCUSDT/config.json"))
        self.assertEqual(sl.runs_jsonl, Path("/tmp/test_run/BTCUSDT/runs.jsonl"))
        self.assertEqual(sl.scored_jsonl, Path("/tmp/test_run/BTCUSDT/scored.jsonl"))
        self.assertEqual(sl.metrics_json, Path("/tmp/test_run/BTCUSDT/metrics.json"))
        self.assertEqual(sl.summary_md, Path("/tmp/test_run/BTCUSDT/summary.md"))
        self.assertEqual(sl.details_md, Path("/tmp/test_run/BTCUSDT/details.md"))
        self.assertEqual(sl.input_parquet, Path("/tmp/test_run/BTCUSDT/input.parquet"))

    def test_run_layout_relative_manifest(self):
        from src.pipeline.layout import RunLayout
        rl = RunLayout("20260327_120000_btcusdt")
        sl = rl.get_symbol_layout("BTCUSDT")
        self.assertTrue(str(sl.base_dir).endswith("BTCUSDT"))

    def test_symbol_layout_setup_creates_dir(self):
        from src.pipeline.layout import SymbolLayout
        with tempfile.TemporaryDirectory() as td:
            sl = SymbolLayout(Path(td) / "BTCUSDT")
            sl.setup()
            self.assertTrue(sl.base_dir.exists())


if __name__ == "__main__":
    unittest.main()
