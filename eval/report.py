"""
报告生成器：信心校准 + 一致性率 + Playbook 胜率。

用法:
    # 推荐：指定 run 目录
    python -m eval.report --dir eval/results/20260322_0939_BTCUSDT_4h

    # 兼容：手动指定 scored.jsonl
    python -m eval.report --scored eval/results/scored.jsonl

    # 保存 summary.md 到 run 目录
    python -m eval.report --dir eval/results/20260322_0939_BTCUSDT_4h --save
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


def load_scored(path: Path) -> list[dict]:
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


# ── 信心校准 ──────────────────────────────────────────

def confidence_calibration(rows: list[dict], lines: list[str] | None = None) -> dict[str, float]:
    """按 confidence 分组统计胜率。返回 {confidence: win_rate}。"""
    buckets: dict[str, dict] = defaultdict(lambda: {"total": 0, "t1": 0, "sl": 0, "neither": 0, "no_trade": 0})

    for r in rows:
        conf = r.get("confidence", "unknown")
        outcome = r.get("outcome", "")
        buckets[conf]["total"] += 1
        if outcome == "t1_hit":
            buckets[conf]["t1"] += 1
        elif outcome == "sl_hit":
            buckets[conf]["sl"] += 1
        elif outcome == "neither":
            buckets[conf]["neither"] += 1
        else:
            buckets[conf]["no_trade"] += 1

    def _out(s: str):
        print(s)
        if lines is not None:
            lines.append(s)

    _out("")
    _out("## 信心校准 (Confidence Calibration)")
    _out("")
    _out("| confidence | cases | t1_hit | sl_hit | neither | no_trade | win_rate |")
    _out("|------------|------:|-------:|-------:|--------:|---------:|--------:|")

    order = ["high", "medium", "low", "unknown"]
    win_rates = {}

    for conf in order:
        if conf not in buckets:
            continue
        b = buckets[conf]
        has_trade = b["t1"] + b["sl"] + b["neither"]
        wr = (b["t1"] / has_trade * 100) if has_trade > 0 else 0
        win_rates[conf] = wr
        wr_str = f"{wr:.1f}%" if has_trade > 0 else "N/A"
        _out(f"| {conf:<10} | {b['total']:>5} | {b['t1']:>6} | {b['sl']:>6} | {b['neither']:>7} | {b['no_trade']:>8} | {wr_str:>7} |")

    _out("")
    calibrated = True
    for a, b in [("high", "medium"), ("medium", "low")]:
        if a in win_rates and b in win_rates:
            if win_rates[a] <= win_rates[b]:
                _out(f"> ⚠️ 校准异常: {a} ({win_rates[a]:.1f}%) ≤ {b} ({win_rates[b]:.1f}%)")
                calibrated = False
    if calibrated and len(win_rates) >= 2:
        _out("> ✅ 信心校准正常: high > medium > low")

    return win_rates


# ── 一致性率 ──────────────────────────────────────────

def consistency_report(rows: list[dict], lines: list[str] | None = None) -> float:
    """按 case_id 分组计算一致性。返回平均综合一致性。"""
    by_case: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_case[r.get("case_id", "")].append(r)

    multi = {cid: runs for cid, runs in by_case.items() if len(runs) > 1}

    def _out(s: str):
        print(s)
        if lines is not None:
            lines.append(s)

    _out("")
    _out("## 一致性率 (Consistency)")
    _out("")

    if not multi:
        _out("> ℹ️ 没有多次 run 的 case（需要 `--repeat > 1`）")
        return 0.0

    _out("| case_id | runs | 方向 | 信心 | Playbook | 综合 |")
    _out("|---------|-----:|-----:|-----:|---------:|-----:|")

    total_overall = 0.0
    n = 0

    for cid, runs in sorted(multi.items()):
        cnt = len(runs)
        actions = [r.get("action", "?") for r in runs]
        confs = [r.get("confidence", "?") for r in runs]
        pbs = [r.get("playbook", "?") for r in runs]

        ac = max(actions.count(a) for a in set(actions)) / cnt
        cc = max(confs.count(c) for c in set(confs)) / cnt
        pc = max(pbs.count(p) for p in set(pbs)) / cnt
        ov = (ac + cc + pc) / 3

        total_overall += ov
        n += 1

        short_id = cid[:28] if len(cid) > 28 else cid
        _out(f"| {short_id:<27} | {cnt:>4} | {ac:>4.0%} | {cc:>4.0%} | {pc:>8.0%} | {ov:>4.0%} |")

    avg = total_overall / n if n > 0 else 0
    _out("")
    _out(f"> 平均综合一致性: **{avg:.0%}**")
    if avg < 0.7:
        _out("> ⚠️ 低于 70%，Skill 规则可能需要加强约束")

    return avg


# ── Playbook 胜率 ─────────────────────────────────────

def playbook_report(rows: list[dict], lines: list[str] | None = None):
    buckets: dict[str, dict] = defaultdict(lambda: {"total": 0, "t1": 0, "sl": 0, "neither": 0, "rr_sum": 0.0})

    for r in rows:
        pb = r.get("playbook")
        outcome = r.get("outcome", "")
        if not pb or pb == "none" or outcome in ("no_trade", "parse_error"):
            continue

        buckets[pb]["total"] += 1
        if outcome == "t1_hit":
            buckets[pb]["t1"] += 1
        elif outcome == "sl_hit":
            buckets[pb]["sl"] += 1
        elif outcome == "neither":
            buckets[pb]["neither"] += 1

        rr = r.get("risk_reward")
        if rr is not None:
            buckets[pb]["rr_sum"] += float(rr)

    def _out(s: str):
        print(s)
        if lines is not None:
            lines.append(s)

    _out("")
    _out("## Playbook 胜率")
    _out("")

    if not buckets:
        _out("> ℹ️ 没有匹配到 Playbook 的 case")
        return

    _out("| playbook | cases | t1_hit | sl_hit | neither | win_rate | avg_rr |")
    _out("|----------|------:|-------:|-------:|--------:|---------:|-------:|")

    for pb, b in sorted(buckets.items()):
        has_trade = b["t1"] + b["sl"] + b["neither"]
        wr = (b["t1"] / has_trade * 100) if has_trade > 0 else 0
        avg_rr = (b["rr_sum"] / b["total"]) if b["total"] > 0 else 0
        wr_str = f"{wr:.1f}%" if has_trade > 0 else "N/A"
        _out(f"| {pb:<24} | {b['total']:>5} | {b['t1']:>6} | {b['sl']:>6} | {b['neither']:>7} | {wr_str:>8} | {avg_rr:>5.1f}R |")


# ── 主入口 ────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Skill Eval 报告生成器")
    parser.add_argument("--dir", default=None, help="run 目录路径")
    parser.add_argument("--scored", default=None, help="scored.jsonl 路径")
    parser.add_argument("--save", action="store_true", help="保存 summary.md 到 run 目录")
    args = parser.parse_args()

    if args.dir:
        scored_path = Path(args.dir) / "scored.jsonl"
    elif args.scored:
        scored_path = Path(args.scored)
    else:
        print("❌ 必须指定 --dir 或 --scored", file=sys.stderr)
        sys.exit(1)

    if not scored_path.exists():
        print(f"❌ 文件不存在: {scored_path}", file=sys.stderr)
        sys.exit(1)

    rows = load_scored(scored_path)
    total = len(rows)

    # 如果要保存，收集所有输出行
    md_lines: list[str] | None = [] if args.save else None

    # 标题
    header = f"# Eval Report ({datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC)"
    print(header)
    if md_lines is not None:
        md_lines.append(header)

    overview = f"\n共 {total} 条记录，来源: `{scored_path.name}`"
    print(overview)
    if md_lines is not None:
        md_lines.append(overview)

    confidence_calibration(rows, md_lines)
    consistency_report(rows, md_lines)
    playbook_report(rows, md_lines)

    print()

    # 保存 summary.md
    if args.save and md_lines is not None:
        if args.dir:
            summary_path = Path(args.dir) / "summary.md"
        else:
            summary_path = scored_path.parent / "summary.md"
        summary_path.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
        print(f"📄 已保存: {summary_path}")


if __name__ == "__main__":
    main()
