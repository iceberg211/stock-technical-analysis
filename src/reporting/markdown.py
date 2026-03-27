"""
Markdown rendering functions for eval report generation.

Renders summary.md and details.md from pre-computed metrics dicts.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _fmt_num(value: float | int | None, ndigits: int = 2) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, int):
        return str(value)
    return f"{value:.{ndigits}f}"


def _fmt_pct(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2f}%"


def _markdown_table(headers: list[str], rows: list[list[str]]) -> list[str]:
    head = "| " + " | ".join(headers) + " |"
    sep = "|" + "|".join(["---"] * len(headers)) + "|"
    body = ["| " + " | ".join(r) + " |" for r in rows]
    return [head, sep, *body]


def render_summary_markdown(
    scored_name: str,
    metrics: dict[str, Any],
) -> str:
    baseline = "通过" if metrics.get("baseline_pass") else "未通过"
    baseline_reason = "；".join(metrics.get("baseline_reasons", [])) if metrics.get("baseline_reasons") else "无"

    lines = [
        f"# 回测执行总览 ({datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC)",
        "",
        f"来源: `{scored_name}`",
        "",
        "## 结论",
        f"- 样本覆盖: 总 runs={metrics['total_runs']}，可交易信号={metrics['tradable_signal_cases']}，实际执行={metrics['executed_trade_cases']}",
        f"- 胜率 (Win Rate): {_fmt_pct(metrics.get('win_rate_pct'))}",
        f"- 平均实现 R (Expectancy): {_fmt_num(metrics.get('expectancy_r'), 4)}",
        f"- 利润因子 (Profit Factor R): {_fmt_num(metrics.get('profit_factor_r'), 4)}",
        f"- 入场触发率: {_fmt_pct(metrics.get('entry_trigger_rate_pct'))}；漏触发率: {_fmt_pct(metrics.get('missed_entry_rate_pct'))}",
        f"- 基线判定: **{baseline}**（原因: {baseline_reason}）",
        "",
        "## 风险提示",
        f"- watch={metrics['watch_cases']}，missed_entry={metrics['missed_entry_cases']}，parse_error={metrics['parse_error_cases']}",
        f"- 样本充分性: {'满足（>=30）' if metrics.get('sample_sufficient') else '不足（<30）'}",
        "",
        "详见 `details.md`（策略明细与 AI 诊断）和 `metrics.json`（程序化消费）。",
        "",
    ]
    return "\n".join(lines)


def render_details_markdown(
    scored_name: str,
    metrics: dict[str, Any],
    playbook_rows: list[dict[str, Any]],
    confidence_rows: list[dict[str, Any]],
    market_state_rows: list[dict[str, Any]],
    consistency: dict[str, Any],
) -> str:
    lines: list[str] = [
        f"# 回测详细报告 ({datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC)",
        "",
        f"来源: `{scored_name}`",
        "",
        "## 核心 KPI",
    ]

    kpi_table = _markdown_table(
        ["指标", "数值"],
        [
            ["总 runs", _fmt_num(metrics.get("total_runs"), 0)],
            ["可交易信号", _fmt_num(metrics.get("tradable_signal_cases"), 0)],
            ["实际执行", _fmt_num(metrics.get("executed_trade_cases"), 0)],
            ["Win Rate", _fmt_pct(metrics.get("win_rate_pct"))],
            ["Expectancy R", _fmt_num(metrics.get("expectancy_r"), 4)],
            ["Profit Factor R", _fmt_num(metrics.get("profit_factor_r"), 4)],
            ["Avg Estimated RR", _fmt_num(metrics.get("avg_estimated_rr"), 4)],
            ["Median Bars To Outcome", _fmt_num(metrics.get("median_bars_to_outcome"), 2)],
        ],
    )
    lines.extend(kpi_table)
    lines.extend(["", "## 策略表现明细 (Playbook)"])

    if playbook_rows:
        pb_table_rows = [
            [
                str(r["playbook"]),
                _fmt_num(r.get("identified_cases"), 0),
                _fmt_num(r.get("executed_cases"), 0),
                _fmt_pct(r.get("win_rate_pct")),
                _fmt_num(r.get("avg_estimated_rr"), 4),
                _fmt_num(r.get("avg_realized_r"), 4),
            ]
            for r in playbook_rows
        ]
        lines.extend(
            _markdown_table(
                ["Playbook", "识别次数", "执行次数", "胜率", "Avg Estimated RR", "Avg Realized R"],
                pb_table_rows,
            )
        )
    else:
        lines.append("无有效 playbook 样本。")

    lines.extend(["", "## AI Diagnostics - Confidence"])
    if confidence_rows:
        conf_table_rows = [
            [
                str(r["confidence"]),
                _fmt_num(r.get("total_cases"), 0),
                _fmt_num(r.get("executed_cases"), 0),
                _fmt_pct(r.get("win_rate_pct")),
                _fmt_num(r.get("avg_realized_r"), 4),
            ]
            for r in confidence_rows
        ]
        lines.extend(
            _markdown_table(
                ["Confidence", "总样本", "执行次数", "胜率", "Avg Realized R"],
                conf_table_rows,
            )
        )
    else:
        lines.append("无 confidence 诊断样本。")

    lines.extend(["", "## AI Diagnostics - Market State"])
    if market_state_rows:
        ms_rows = [
            [
                str(r["market_state"]),
                _fmt_num(r.get("executed_cases"), 0),
                _fmt_pct(r.get("win_rate_pct")),
                _fmt_num(r.get("avg_realized_r"), 4),
            ]
            for r in market_state_rows
        ]
        lines.extend(
            _markdown_table(
                ["Market State", "执行次数", "胜率", "Avg Realized R"],
                ms_rows,
            )
        )
    else:
        lines.append("无 market_state 诊断样本。")

    lines.extend(["", "## 一致性率 (Consistency)"])
    if not consistency.get("has_multi_run"):
        lines.append("无多次重复运行样本（需要 repeat > 1）。")
    else:
        lines.append(f"平均综合一致性: **{_fmt_pct((consistency.get('avg_overall') or 0) * 100)}**")
        case_rows = [
            [
                str(r["case_id"]),
                _fmt_num(r.get("runs"), 0),
                _fmt_pct(float(r.get("action_consistency", 0.0)) * 100),
                _fmt_pct(float(r.get("confidence_consistency", 0.0)) * 100),
                _fmt_pct(float(r.get("playbook_consistency", 0.0)) * 100),
                _fmt_pct(float(r.get("overall_consistency", 0.0)) * 100),
            ]
            for r in consistency.get("per_case", [])
        ]
        lines.extend(
            _markdown_table(
                ["Case", "Runs", "方向一致", "信心一致", "Playbook一致", "综合一致"],
                case_rows,
            )
        )

    lines.append("")
    return "\n".join(lines)
