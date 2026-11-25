from pathlib import Path
import json
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILL = (ROOT / "SKILL.md").read_text(encoding="utf-8")
DATA_BUDGET = (ROOT / "references/data-budget.md").read_text(encoding="utf-8")
INTRADAY = (ROOT / "references/intraday-mode.md").read_text(encoding="utf-8")
OUTPUT = (ROOT / "references/output-contract.md").read_text(encoding="utf-8")
STATE = (ROOT / "references/state-contract.md").read_text(encoding="utf-8")
REASONING = (ROOT / "references/decision-loop.md").read_text(encoding="utf-8")
ROUTER = (ROOT / "references/setup-router.md").read_text(encoding="utf-8")
SOURCE_MAP = (ROOT / "references/source-map.md").read_text(encoding="utf-8")
SESSION = (ROOT / "references/session-context.md").read_text(encoding="utf-8")
TRADE_STYLE = (ROOT / "references/trade-style.md").read_text(encoding="utf-8")
H1_H2 = (ROOT / "references/h2-l2.md").read_text(encoding="utf-8")
MANAGEMENT = (ROOT / "references/trade-management.md").read_text(encoding="utf-8")
MTR = (ROOT / "references/mtr.md").read_text(encoding="utf-8")
BROAD = (ROOT / "references/broad-channel.md").read_text(encoding="utf-8")
RANGE = (ROOT / "references/trading-range.md").read_text(encoding="utf-8")
CLIMAX = (ROOT / "references/climactic-reversal.md").read_text(encoding="utf-8")
LATE = (ROOT / "references/late-trend.md").read_text(encoding="utf-8")
BREAKOUT = (ROOT / "references/bo-ft.md").read_text(encoding="utf-8")
SCENARIOS = json.loads((ROOT / "tests/course_scenarios.json").read_text(encoding="utf-8"))


class SkillContractTest(unittest.TestCase):
    def test_direct_dependencies_are_separated(self):
        self.assertIn("$market-data", SKILL)
        self.assertIn("$trade-risk", SKILL)
        self.assertIn("不以 `$stock-technical-analysis` 作为前置依赖", SKILL)

    def test_runtime_routes_by_market_environment_not_chapter(self):
        self.assertIn("不按章节号匹配交易", SKILL)
        self.assertIn("按市场环境选择交易模式", SKILL)
        self.assertNotIn("Video 37", SKILL)
        self.assertNotIn("Video 38", SKILL)
        self.assertNotIn("路由到实战章节", SKILL)
        self.assertIn("运行时不要按章节号匹配交易", SOURCE_MAP)

    def test_reasoning_starts_from_price_and_includes_both_sides(self):
        for term in (
            "价格是真相",
            "同时理解多空双方",
            "区分方向判断与交易结构",
            "交易者方程",
            "持续更新而非守住观点",
        ):
            self.assertIn(term, REASONING)
        self.assertIn("多头在交易什么，空头在交易什么", SKILL)
        self.assertIn("交易者方程", SKILL)

    def test_router_covers_real_trading_environments(self):
        for term in (
            "强突破并有跟进",
            "窄幅通道",
            "宽幅通道",
            "交易区间下部",
            "交易区间上部",
            "MTR 候选",
            "高潮反转候选",
            "趋势后段参与",
            "BO+FT",
            "BLSHS",
        ):
            self.assertIn(term, ROUTER)
        self.assertNotIn("主要章节", ROUTER)
        self.assertNotIn("Video 37", ROUTER)

    def test_runtime_uses_progressive_reference_loading(self):
        self.assertIn("不得为了比较而一次加载全部环境卡", SKILL)
        self.assertIn("正常分析只加载环境卡和交易模式卡", SOURCE_MAP)

    def test_data_budget_bounds_snapshot_and_incremental_requests(self):
        for term in (
            "双层 K 线窗口规则",
            "`1d`",
            "`60m`",
            "`15m`",
            "`5m`",
            "120 根",
            "80 根",
            "96 根",
            "无缓存实时快照",
            "market_data.py snapshot",
        ):
            self.assertIn(term, DATA_BUDGET)
        self.assertIn("不得自行扩大周期数量或历史根数", SKILL)
        self.assertIn("不要把任何行情源的完整原始 JSON", DATA_BUDGET)
        self.assertIn("唯一脚本调用规范", DATA_BUDGET)

    def test_source_window_is_separate_from_analysis_handoff(self):
        for term in (
            "fetch_bars",
            "analysis_bars",
            "detail_bars",
            "market_data.py snapshot --mode pa",
        ):
            self.assertIn(term, SKILL)
        for term in (
            "250 根",
            "180 根",
            "200 根",
            "240 根",
            "prior_segments",
            "recent_detail_bars",
            "EMA20 / ATR14",
        ):
            self.assertIn(term, DATA_BUDGET)

    def test_multi_symbol_requests_are_sequenced_and_retry_only_failed_period(self):
        for term in (
            "一次只处理一个标的",
            "完成该标的的压缩摘要后再处理下一个",
            "不得一次并发发出所有标的的所有周期请求",
            "只允许重试该失败周期一次",
            "成功周期不得整组重拉",
        ):
            self.assertIn(term, SKILL)
        for term in (
            "一个标的的元信息 → 目标周期有限窗口 → 压缩摘要",
            "不要把多个标的的原始返回同时放进上下文",
            "逐标的顺序处理",
            "只重试该周期一次",
            "重试仍失败",
        ):
            self.assertIn(term, DATA_BUDGET)

    def test_runtime_does_not_scan_unrelated_history_for_market_or_course_context(self):
        self.assertIn("不得为了查找课程或历史测试而扫描 `/Users`", SKILL)
        self.assertIn("不要用 shell 搜索归档会话、记忆原文或其他目录", DATA_BUDGET)
        self.assertIn("工具返回原始结果后立即压缩", SKILL)

    def test_data_handoff_keeps_quality_and_forming_bar_boundaries(self):
        for term in (
            "实际数",
            "覆盖起止",
            "最后完整 K 线",
            "forming K 线",
            "最近 `6～12` 根完整 K 线",
            "H=L=C",
            "不单独用来确认突破、反转或 Always In 切换",
        ):
            self.assertIn(term, DATA_BUDGET)
        for term in ("有限窗口", "数据质量", "去重、排序", "完整K线过滤"):
            self.assertIn(term, SKILL)

    def test_full_test_report_preserves_auditable_summary_without_raw_json(self):
        for term in (
            "测试”“完整分析”“复核",
            "紧凑数据表",
            "实际K线数量",
            "覆盖范围",
            "最后完整K线",
            "forming或剔除记录",
            "最近必要的 6～12 根事实摘要",
            "多标的完整报告必须逐标的",
        ):
            self.assertIn(term, OUTPUT)
        self.assertIn("完整原始 JSON", SKILL)

    def test_h1_h2_l1_l2_are_contextual_entries(self):
        for term in ("H1", "H2", "L1", "L2", "共同前提", "不是独立市场环境"):
            self.assertIn(term, H1_H2)

    def test_session_context_covers_the_trading_day(self):
        for term in ("开盘阶段", "盘中阶段", "尾盘阶段", "剩余时间"):
            self.assertIn(term, SESSION)
        self.assertIn("不是市场状态", SESSION)

    def test_trade_style_values_and_boundaries_are_defined(self):
        for term in ("scalp", "swing", "mixed", "no_trade"):
            self.assertIn(term, TRADE_STYLE)
            self.assertIn(term, STATE)
        self.assertIn("被动改成波段", TRADE_STYLE)

    def test_management_distinguishes_bad_trade_from_good_trade_gone_bad(self):
        self.assertIn("一开始就是错误交易", MANAGEMENT)
        self.assertIn("好交易变坏", MANAGEMENT)
        self.assertIn("固定计时器", MANAGEMENT)

    def test_source_map_covers_part_two_without_runtime_routing(self):
        for video in ("37", "38～39", "40", "41", "42", "43～44", "45～46", "47", "48", "49～50", "51～52"):
            self.assertIn(video, SOURCE_MAP)
        self.assertIn("运行时不要按章节号匹配交易", SOURCE_MAP)

    def test_intraday_timeframes_are_defined(self):
        for timeframe in ("60m", "15m", "5m"):
            self.assertIn(timeframe, INTRADAY)
        self.assertIn("未完成K线", INTRADAY)

    def test_setup_lifecycle_is_defined(self):
        for status in (
            "none",
            "candidate",
            "armed",
            "triggered",
            "managing",
            "invalidated",
            "closed",
        ):
            self.assertIn(status, STATE)

    def test_state_tracks_competing_explanations_and_trade_structure(self):
        for term in (
            "alternate_state",
            "switch_condition",
            "trade_style",
            "order_type",
            "initial_risk",
            "logical_risk",
            "target_space",
        ):
            self.assertIn(term, STATE)

    def test_intraday_output_is_delta_only(self):
        self.assertIn("盘中精简模式", OUTPUT)
        self.assertIn("不要重复完整报告", OUTPUT)
        self.assertIn("新K线做了什么", OUTPUT)
        self.assertIn("当前动作", OUTPUT)
        self.assertIn("下一触发", OUTPUT)
        self.assertIn("没改变什么", OUTPUT)

    def test_full_output_requires_readable_report_contract(self):
        for term in (
            "先给结论",
            "基础信息",
            "市场结构",
            "关键价位",
            "价格行为",
            "交易决策卡",
            "多头在交易什么",
            "空头在交易什么",
            "不要默认输出",
            "作者式二元决策",
        ):
            self.assertIn(term, OUTPUT)
        self.assertIn("先给自然结论", SKILL)
        self.assertIn("禁止单独输出", SKILL)
        self.assertNotIn("Video 37", OUTPUT)
        self.assertNotIn("Video xx", OUTPUT)
        self.assertIn("课程章节编号", OUTPUT)

    def test_state_and_setup_are_separate(self):
        # keep soft separation language if present; otherwise ensure router separates env and entry
        self.assertIn("H2/L2 是趋势或旗形里的入场结构，不是市场环境", ROUTER)
        self.assertIn("Bailout 不参与入场模式竞争", ROUTER)

    def test_course_consistency_scenarios_are_complete(self):
        self.assertEqual(8, len(SCENARIOS))
        ids = {scenario["id"] for scenario in SCENARIOS}
        self.assertEqual(8, len(ids))
        expected_fields = {
            "price_facts",
            "environment",
            "always_in",
            "bull_case",
            "bear_case",
            "primary",
            "alternate",
            "switch_condition",
            "trade_style",
            "order_type",
            "stop_logic",
            "target",
            "invalidation",
        }
        for scenario in SCENARIOS:
            self.assertTrue(scenario["facts"])
            self.assertTrue(scenario["must_not_conclude"])
            self.assertEqual(expected_fields, set(scenario["expected"]))
            self.assertIn(
                scenario["expected"]["trade_style"],
                {"scalp", "swing", "mixed", "no_trade"},
            )
            self.assertIn(
                scenario["expected"]["order_type"],
                {"market", "close", "stop", "limit", "wait"},
            )

    def test_course_scenario_rules_are_backed_by_references(self):
        checks = (
            (MTR, "强趋势中的第一次反向运动通常先按旗形"),
            (BROAD, "逆势通常 `scalp`"),
            (RANGE, "不能仅凭动量追空"),
            (CLIMAX, "交易区间或原趋势恢复"),
            (LATE, "正的交易者方程"),
            (SESSION, "逆势限价、宽止损和加仓"),
            (MANAGEMENT, "证据明确时可市价退出"),
            (BREAKOUT, "价格重新进入旧区间并停留"),
        )
        for reference, rule in checks:
            self.assertIn(rule, reference)


if __name__ == "__main__":
    unittest.main()
