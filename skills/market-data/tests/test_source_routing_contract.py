from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILL = (ROOT / "SKILL.md").read_text(encoding="utf-8")
ROUTING = (ROOT / "references/source-routing.md").read_text(encoding="utf-8")
CONTRACT = (ROOT / "references/data-contract.md").read_text(encoding="utf-8")


class SourceRoutingContractTest(unittest.TestCase):
    def test_script_first_stateless_architecture(self):
        self.assertIn("只负责取得可靠、可复用的行情事实", SKILL)
        self.assertIn("scripts/market_data.py", SKILL)
        self.assertIn("不做本地文件缓存", SKILL)
        self.assertNotIn("不得调用 `market_data.py", SKILL)
        self.assertFalse((ROOT / "references/intraday-incremental.md").exists())

    def test_dual_window_policy_documented(self):
        for term in ("fetch_bars", "analysis_bars", "detail_bars", "min_bars", "120 根", "80 根", "96 根"):
            self.assertIn(term, SKILL)
        self.assertIn("cache_enabled", CONTRACT)
        self.assertIn("forming_bars", CONTRACT)

    def test_multi_market_routing_documented(self):
        for term in ("腾讯", "新浪", "Yahoo Chart API", "Binance", "$spot"):
            self.assertIn(term, ROUTING)
        self.assertIn("intraday_unadjusted_mismatch_with_1d_qfq", ROUTING)


if __name__ == "__main__":
    unittest.main()
