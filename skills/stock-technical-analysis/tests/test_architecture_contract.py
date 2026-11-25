from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT.parent
AGENTS_SKILLS = Path.home() / ".agents" / "skills"
CODEX_SKILLS = Path.home() / ".codex" / "skills"


def _resolve_peer_skill(name: str) -> Path:
    for base in (STAGE, AGENTS_SKILLS, CODEX_SKILLS):
        candidate = base / name
        if (candidate / "SKILL.md").exists():
            return candidate
    raise FileNotFoundError(f"无法定位协作 Skill: {name}")


SKILL = (ROOT / "SKILL.md").read_text(encoding="utf-8")
DATA_COMPAT = (ROOT / "workflows/data-acquisition-workflow.md").read_text(
    encoding="utf-8"
)
CHART = (ROOT / "workflows/chart-analysis-workflow.md").read_text(encoding="utf-8")
TRADING = (ROOT / "workflows/trading-decision.md").read_text(encoding="utf-8")
OUTPUT = (ROOT / "workflows/output-templates.md").read_text(encoding="utf-8")
DAILY = (ROOT / "workflows/daily-review.md").read_text(encoding="utf-8")
CHECKLIST = (ROOT / "references/checklists/pre-trade-checklist.md").read_text(
    encoding="utf-8"
)
MARKET_DATA = (_resolve_peer_skill("market-data") / "SKILL.md").read_text(
    encoding="utf-8"
)
PRICE_ACTION = (_resolve_peer_skill("price-action-decision") / "SKILL.md").read_text(
    encoding="utf-8"
)


class ArchitectureContractTest(unittest.TestCase):
    def test_market_data_owns_data_acquisition(self):
        self.assertIn("$market-data", SKILL)
        self.assertIn("不拥有行情接口", SKILL)
        self.assertIn("只负责取得可靠、可复用的行情事实", MARKET_DATA)
        self.assertIn("旧调用路径", DATA_COMPAT)
        self.assertNotIn("Yahoo Finance chart API interval=1d", DATA_COMPAT)

    def test_price_action_does_not_depend_on_full_technical_analysis(self):
        self.assertIn("不以 `$stock-technical-analysis` 作为前置依赖", PRICE_ACTION)
        self.assertIn("$market-data", PRICE_ACTION)
        self.assertIn("平级分析器", PRICE_ACTION)

    def test_risk_is_delegated(self):
        self.assertIn("$trade-risk", SKILL)
        self.assertIn("$trade-risk", TRADING)
        self.assertNotIn("正常单笔风险：总资金", TRADING)
        self.assertNotIn("到 T1 至少 `1.5:1`", TRADING)

    def test_indicator_requirements_are_mode_scoped(self):
        self.assertIn("`structure` 模式跳过本步骤", CHART)
        self.assertIn("`indicator` 或 `complete`", CHART)

    def test_multitimeframe_conflict_is_not_universal_veto(self):
        self.assertIn("区间或反转 Playbook 降低信心", CHART)
        self.assertNotIn("三层同向才执行", CHART)

    def test_output_templates_aligned_with_market_data_and_no_stale_yahoo_rule(self):
        self.assertIn("fetched_complete_bars", OUTPUT)
        self.assertIn("analysis_bars_count", OUTPUT)
        self.assertIn("degraded_quality", OUTPUT)
        self.assertNotIn("必须先请求 Yahoo Finance", OUTPUT)

    def test_daily_review_has_no_deleted_pipeline_commands(self):
        self.assertIn("编排型工作流", DAILY)
        self.assertIn("Phase 能力归属表", DAILY)
        self.assertIn("$market-data", DAILY)
        self.assertNotIn("python3 -m src", DAILY)
        self.assertNotIn("opend/mcp", DAILY)

    def test_four_state_divergence_and_quality_degradation_protocol(self):
        for doc_name, text in (
            ("SKILL.md", SKILL),
            ("chart-analysis-workflow.md", CHART),
            ("output-templates.md", OUTPUT),
        ):
            with self.subTest(doc=doc_name):
                self.assertIn("无背离 / 候选 / 已确认 / 无法判断", text)
                self.assertIn("degraded_quality", text)
        self.assertIn("divergence_status", OUTPUT)
        self.assertNotIn("若无法给出成对锚点，结论必须写 `无背离`", CHART)

    def test_normalized_signal_strength_scoring(self):
        self.assertIn("score_ratio = hits / applicable_items", CHART)
        self.assertIn("applicable_items < 3", CHART)
        self.assertNotIn("| **强信号** | >= 4 分 |", CHART)

    def test_pre_trade_checklist_hybrid_classification_is_consistent(self):
        self.assertIn("**混合项**", CHECKLIST)
        self.assertIn("### ① HTF 方向（🟡 混合项）", CHECKLIST)
        self.assertIn("### ② 位置（🟡 混合项）", CHECKLIST)
        self.assertIn("$trade-risk", CHECKLIST)
        self.assertNotIn("每个 ⚠️ 独立让仓位 × 50%", CHECKLIST)


if __name__ == "__main__":
    unittest.main()
