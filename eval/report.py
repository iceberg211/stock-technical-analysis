"""
报告生成器：输出 summary.md（首屏结论）+ details.md（完整明细）+ metrics.json（机器消费）。

用法:
    # 推荐：指定 run 目录
    python -m eval.report --dir eval/results/20260322_0939_BTCUSDT_4h --save

    # 兼容：手动指定 scored.jsonl
    python -m eval.report --scored eval/results/scored.jsonl --save
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any


METRICS_SCHEMA_VERSION = "report_metrics_v2"


def load_scored(path: Path) -> list[dict]:
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _round_or_none(value: float | None, ndigits: int = 4) -> float | None:
    if value is None:
        return None
    return round(float(value), ndigits)


def _quantile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    v = sorted(values)
    if len(v) == 1:
        return v[0]
    pos = (len(v) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(v) - 1)
    frac = pos - lo
    return v[lo] * (1 - frac) + v[hi] * frac


def _safe_pct(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator * 100, 2)


def _safe_fraction(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _safe_ratio(numerator: float, denominator: float) -> float | None:
    if denominator == 0:
        return None
    return numerator / denominator


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


def _confidence_exec_stats(rows: list[dict]) -> dict[str, dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = defaultdict(lambda: {"total": 0, "wins": 0, "r_values": []})
    for r in rows:
        conf = str(r.get("confidence", "unknown"))
        outcome = r.get("outcome")
        if outcome not in ("t1_hit", "sl_hit", "neither"):
            continue
        buckets[conf]["total"] += 1
        if outcome == "t1_hit":
            buckets[conf]["wins"] += 1
        rr = r.get("realized_r")
        if isinstance(rr, (int, float)):
            buckets[conf]["r_values"].append(float(rr))
    return buckets


def build_metrics(rows: list[dict]) -> dict[str, Any]:
    total_runs = len(rows)
    parse_error_cases = sum(1 for r in rows if r.get("outcome") == "parse_error")

    tradable_signal_rows = [r for r in rows if r.get("action") in ("long", "short")]
    tradable_signal_cases = len(tradable_signal_rows)

    executed_rows = [r for r in rows if r.get("outcome") in ("t1_hit", "sl_hit", "neither")]
    executed_trade_cases = len(executed_rows)

    t1_hit = sum(1 for r in executed_rows if r.get("outcome") == "t1_hit")
    sl_hit = sum(1 for r in executed_rows if r.get("outcome") == "sl_hit")
    neither = sum(1 for r in executed_rows if r.get("outcome") == "neither")

    watch_cases = sum(1 for r in rows if r.get("action") == "watch" or r.get("outcome") == "no_trade")
    missed_entry_cases = sum(1 for r in rows if r.get("outcome") == "missed_entry")

    realized_r_values = [float(r["realized_r"]) for r in executed_rows if isinstance(r.get("realized_r"), (int, float))]
    positive_r = [x for x in realized_r_values if x > 0]
    negative_r = [x for x in realized_r_values if x < 0]

    risk_reward_values = [
        float(r["risk_reward"]) for r in tradable_signal_rows if isinstance(r.get("risk_reward"), (int, float))
    ]

    bars_to_outcome_values = [
        int(r["bars_to_outcome"]) for r in executed_rows if isinstance(r.get("bars_to_outcome"), (int, float))
    ]
    mfe_values = [float(r["mfe"]) for r in executed_rows if isinstance(r.get("mfe"), (int, float))]
    mae_values = [float(r["mae"]) for r in executed_rows if isinstance(r.get("mae"), (int, float))]

    win_rate = _round_or_none(_safe_fraction(t1_hit, executed_trade_cases), 4)
    entry_trigger_rate = _round_or_none(_safe_fraction(executed_trade_cases, tradable_signal_cases), 4)
    missed_entry_rate = _round_or_none(_safe_fraction(missed_entry_cases, tradable_signal_cases), 4)
    win_rate_pct = _round_or_none((win_rate * 100.0) if win_rate is not None else None, 2)
    entry_trigger_rate_pct = _round_or_none((entry_trigger_rate * 100.0) if entry_trigger_rate is not None else None, 2)
    missed_entry_rate_pct = _round_or_none((missed_entry_rate * 100.0) if missed_entry_rate is not None else None, 2)
    expectancy_r = _round_or_none(_mean(realized_r_values), 4)

    pf_den = abs(sum(negative_r))
    profit_factor_r = _round_or_none(
        _safe_ratio(sum(positive_r), pf_den) if pf_den > 0 else None,
        4,
    )

    avg_estimated_rr = _round_or_none(_mean(risk_reward_values), 4)
    median_bars_to_outcome = _round_or_none(float(median(bars_to_outcome_values)) if bars_to_outcome_values else None, 2)

    conf_stats = _confidence_exec_stats(rows)
    high_wr = _safe_pct(conf_stats.get("high", {}).get("wins", 0), conf_stats.get("high", {}).get("total", 0))
    medium_wr = _safe_pct(conf_stats.get("medium", {}).get("wins", 0), conf_stats.get("medium", {}).get("total", 0))
    low_wr = _safe_pct(conf_stats.get("low", {}).get("wins", 0), conf_stats.get("low", {}).get("total", 0))

    sample_sufficient = executed_trade_cases >= 30
    baseline_reasons: list[str] = []
    baseline_pass = True

    if not sample_sufficient:
        baseline_pass = False
        baseline_reasons.append("有效执行样本少于 30")

    if high_wr is not None and high_wr < 60:
        baseline_pass = False
        baseline_reasons.append(f"high 命中率 {high_wr:.2f}% < 60%")
    if medium_wr is not None and medium_wr < 50:
        baseline_pass = False
        baseline_reasons.append(f"medium 命中率 {medium_wr:.2f}% < 50%")
    if high_wr is not None and medium_wr is not None and high_wr <= medium_wr:
        baseline_pass = False
        baseline_reasons.append("high 命中率未高于 medium")
    if medium_wr is not None and low_wr is not None and medium_wr <= low_wr:
        baseline_pass = False
        baseline_reasons.append("medium 命中率未高于 low")

    playbook_r: dict[str, list[float]] = defaultdict(list)
    for r in executed_rows:
        pb = r.get("playbook")
        if not pb or pb == "none":
            continue
        rr = r.get("realized_r")
        if isinstance(rr, (int, float)):
            playbook_r[str(pb)].append(float(rr))
    avg_realized_r_by_playbook = {
        pb: _round_or_none(_mean(values), 4) for pb, values in sorted(playbook_r.items())
    }

    metrics = {
        "schema_version": METRICS_SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "total_runs": total_runs,
        "parse_error_cases": parse_error_cases,
        "tradable_signal_cases": tradable_signal_cases,
        "executed_trade_cases": executed_trade_cases,
        "watch_cases": watch_cases,
        "missed_entry_cases": missed_entry_cases,
        "t1_hit": t1_hit,
        "sl_hit": sl_hit,
        "neither": neither,
        # 锁定口径：主键使用比率（0~1）
        "win_rate": win_rate,
        "entry_trigger_rate": entry_trigger_rate,
        "missed_entry_rate": missed_entry_rate,
        # 向后兼容：保留历史百分比键
        "win_rate_pct": win_rate_pct,
        "entry_trigger_rate_pct": entry_trigger_rate_pct,
        "missed_entry_rate_pct": missed_entry_rate_pct,
        "expectancy_r": expectancy_r,
        "profit_factor_r": profit_factor_r,
        "avg_estimated_rr": avg_estimated_rr,
        "median_bars_to_outcome": median_bars_to_outcome,
        "mfe_quantiles": {
            "p50": _round_or_none(_quantile(mfe_values, 0.5), 4),
            "p75": _round_or_none(_quantile(mfe_values, 0.75), 4),
            "p90": _round_or_none(_quantile(mfe_values, 0.9), 4),
        },
        "mae_quantiles": {
            "p50": _round_or_none(_quantile(mae_values, 0.5), 4),
            "p75": _round_or_none(_quantile(mae_values, 0.75), 4),
            "p90": _round_or_none(_quantile(mae_values, 0.9), 4),
        },
        "avg_realized_r_by_playbook": avg_realized_r_by_playbook,
        "sample_sufficient": sample_sufficient,
        "baseline_pass": baseline_pass,
        "baseline_reasons": baseline_reasons,
    }
    return metrics


def build_playbook_breakdown(rows: list[dict]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"identified": 0, "executed": 0, "wins": 0, "rr_values": [], "realized_r_values": []}
    )

    for r in rows:
        pb = r.get("playbook")
        if not pb or pb == "none":
            continue

        buckets[pb]["identified"] += 1

        if isinstance(r.get("risk_reward"), (int, float)):
            buckets[pb]["rr_values"].append(float(r["risk_reward"]))

        outcome = r.get("outcome")
        if outcome in ("t1_hit", "sl_hit", "neither"):
            buckets[pb]["executed"] += 1
            if outcome == "t1_hit":
                buckets[pb]["wins"] += 1
            if isinstance(r.get("realized_r"), (int, float)):
                buckets[pb]["realized_r_values"].append(float(r["realized_r"]))

    rows_out: list[dict[str, Any]] = []
    for pb, b in sorted(buckets.items()):
        rows_out.append(
            {
                "playbook": pb,
                "identified_cases": b["identified"],
                "executed_cases": b["executed"],
                "win_rate_pct": _safe_pct(b["wins"], b["executed"]),
                "avg_estimated_rr": _round_or_none(_mean(b["rr_values"]), 4),
                "avg_realized_r": _round_or_none(_mean(b["realized_r_values"]), 4),
            }
        )
    return rows_out


def build_confidence_diagnostics(rows: list[dict]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"total": 0, "executed": 0, "wins": 0, "realized_r_values": []}
    )

    for r in rows:
        conf = str(r.get("confidence", "unknown"))
        buckets[conf]["total"] += 1
        outcome = r.get("outcome")
        if outcome in ("t1_hit", "sl_hit", "neither"):
            buckets[conf]["executed"] += 1
            if outcome == "t1_hit":
                buckets[conf]["wins"] += 1
            if isinstance(r.get("realized_r"), (int, float)):
                buckets[conf]["realized_r_values"].append(float(r["realized_r"]))

    order = ["high", "medium", "low", "unknown"]
    out: list[dict[str, Any]] = []
    for key in order:
        if key not in buckets:
            continue
        b = buckets[key]
        out.append(
            {
                "confidence": key,
                "total_cases": b["total"],
                "executed_cases": b["executed"],
                "win_rate_pct": _safe_pct(b["wins"], b["executed"]),
                "avg_realized_r": _round_or_none(_mean(b["realized_r_values"]), 4),
            }
        )
    return out


def build_market_state_breakdown(rows: list[dict]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"executed": 0, "wins": 0, "realized_r_values": []}
    )
    for r in rows:
        outcome = r.get("outcome")
        if outcome not in ("t1_hit", "sl_hit", "neither"):
            continue
        state = str(r.get("market_state", "unknown"))
        buckets[state]["executed"] += 1
        if outcome == "t1_hit":
            buckets[state]["wins"] += 1
        if isinstance(r.get("realized_r"), (int, float)):
            buckets[state]["realized_r_values"].append(float(r["realized_r"]))

    out: list[dict[str, Any]] = []
    for state, b in sorted(buckets.items()):
        out.append(
            {
                "market_state": state,
                "executed_cases": b["executed"],
                "win_rate_pct": _safe_pct(b["wins"], b["executed"]),
                "avg_realized_r": _round_or_none(_mean(b["realized_r_values"]), 4),
            }
        )
    return out


def build_consistency(rows: list[dict]) -> dict[str, Any]:
    by_case: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_case[str(r.get("case_id", ""))].append(r)

    multi = {cid: rs for cid, rs in by_case.items() if len(rs) > 1 and cid}
    if not multi:
        return {"has_multi_run": False, "avg_overall": None, "per_case": []}

    per_case = []
    acc = 0.0
    for cid, runs in sorted(multi.items()):
        cnt = len(runs)
        actions = [str(r.get("action", "?")) for r in runs]
        confs = [str(r.get("confidence", "?")) for r in runs]
        pbs = [str(r.get("playbook", "?")) for r in runs]

        action_cons = max(actions.count(a) for a in set(actions)) / cnt
        conf_cons = max(confs.count(c) for c in set(confs)) / cnt
        pb_cons = max(pbs.count(p) for p in set(pbs)) / cnt
        overall = (action_cons + conf_cons + pb_cons) / 3
        acc += overall

        per_case.append(
            {
                "case_id": cid,
                "runs": cnt,
                "action_consistency": round(action_cons, 4),
                "confidence_consistency": round(conf_cons, 4),
                "playbook_consistency": round(pb_cons, 4),
                "overall_consistency": round(overall, 4),
            }
        )

    avg_overall = round(acc / len(per_case), 4) if per_case else None
    return {"has_multi_run": True, "avg_overall": avg_overall, "per_case": per_case}


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


def _markdown_table(headers: list[str], rows: list[list[str]]) -> list[str]:
    head = "| " + " | ".join(headers) + " |"
    sep = "|" + "|".join(["---"] * len(headers)) + "|"
    body = ["| " + " | ".join(r) + " |" for r in rows]
    return [head, sep, *body]


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


def main():
    parser = argparse.ArgumentParser(description="Skill Eval 报告生成器")
    parser.add_argument("--dir", default=None, help="run 目录路径")
    parser.add_argument("--scored", default=None, help="scored.jsonl 路径")
    parser.add_argument("--save", action="store_true", help="保存 summary.md/details.md/metrics.json")
    args = parser.parse_args()

    if args.dir:
        run_dir = Path(args.dir)
        scored_path = run_dir / "scored.jsonl"
    elif args.scored:
        run_dir = Path(args.scored).resolve().parent
        scored_path = Path(args.scored)
    else:
        print("❌ 必须指定 --dir 或 --scored", file=sys.stderr)
        sys.exit(1)

    if not scored_path.exists():
        print(f"❌ 文件不存在: {scored_path}", file=sys.stderr)
        sys.exit(1)

    rows = load_scored(scored_path)
    metrics = build_metrics(rows)
    playbook_rows = build_playbook_breakdown(rows)
    confidence_rows = build_confidence_diagnostics(rows)
    market_state_rows = build_market_state_breakdown(rows)
    consistency = build_consistency(rows)

    summary_md = render_summary_markdown(scored_path.name, metrics)
    details_md = render_details_markdown(
        scored_name=scored_path.name,
        metrics=metrics,
        playbook_rows=playbook_rows,
        confidence_rows=confidence_rows,
        market_state_rows=market_state_rows,
        consistency=consistency,
    )

    print(summary_md)

    if args.save:
        summary_path = run_dir / "summary.md"
        details_path = run_dir / "details.md"
        metrics_path = run_dir / "metrics.json"

        summary_path.write_text(summary_md, encoding="utf-8")
        details_path.write_text(details_md, encoding="utf-8")
        metrics_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")

        print(f"📄 已保存: {summary_path}")
        print(f"📄 已保存: {details_path}")
        print(f"📄 已保存: {metrics_path}")


if __name__ == "__main__":
    main()
