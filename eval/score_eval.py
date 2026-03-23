"""
事后评分器：对比 Skill JSON 预测 vs 实际 K 线走势。

用法:
    # 推荐：指定 run 目录（自动读取 config.json + runs.jsonl + CSV）
    python -m eval.score_eval --dir eval/results/20260322_0939_BTCUSDT_4h

    # 兼容：手动指定 runs.jsonl + CSV
    python -m eval.score_eval --results runs.jsonl --csv data.csv --lookback 200 --forward 50 --step 10
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd


def _to_float_or_none(value):
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def normalize_parsed_payload(parsed: dict | None) -> dict | None:
    """兼容 legacy/new 两种 JSON 结构。"""
    if not isinstance(parsed, dict):
        return None
    if "backtest_sample_v1" in parsed and isinstance(parsed["backtest_sample_v1"], dict):
        return parsed["backtest_sample_v1"]
    return parsed


# ── 评分逻辑 ──────────────────────────────────────────

def score_trade(parsed: dict, forward_rows: list[dict]) -> dict:
    """
    对有 trade 方案的 case 评分。
    逐根遍历事后 K 线，判断 T1 和 SL 哪个先被触碰。
    """
    trade = parsed.get("trade", {})
    decision = parsed.get("decision", {})
    action = decision.get("action")

    entry = _to_float_or_none(trade.get("entry_price"))
    sl = _to_float_or_none(trade.get("stop_loss"))
    t1 = _to_float_or_none(trade.get("t1"))

    if entry is None or sl is None or t1 is None or action == "watch":
        return {"outcome": "no_trade", "mfe": None, "mae": None, "bars_to_outcome": None}

    is_long = action == "long"
    mfe = 0.0
    mae = 0.0
    outcome = "neither"
    bars_to_outcome = None

    for bar_idx, bar in enumerate(forward_rows):
        high = float(bar["high"])
        low = float(bar["low"])

        if is_long:
            favorable = high - entry
            adverse = entry - low
            t1_hit = high >= t1
            sl_hit = low <= sl
        else:
            favorable = entry - low
            adverse = high - entry
            t1_hit = low <= t1
            sl_hit = high >= sl

        mfe = max(mfe, favorable)
        mae = max(mae, adverse)

        # 同根同时触碰 → 保守假设 SL 先到
        if sl_hit and t1_hit:
            outcome = "sl_hit"
            bars_to_outcome = bar_idx + 1
            break
        elif sl_hit:
            outcome = "sl_hit"
            bars_to_outcome = bar_idx + 1
            break
        elif t1_hit:
            outcome = "t1_hit"
            bars_to_outcome = bar_idx + 1
            break

    return {
        "outcome": outcome,
        "mfe": round(mfe, 4),
        "mae": round(mae, 4),
        "bars_to_outcome": bars_to_outcome,
    }


def score_watch(forward_rows: list[dict]) -> dict:
    """对 watch 的 case 计算事后波动（检测漏单）。"""
    if not forward_rows:
        return {"outcome": "no_trade", "max_move_up_pct": None, "max_move_down_pct": None}

    first_close = float(forward_rows[0]["close"])
    max_high = max(float(b["high"]) for b in forward_rows)
    min_low = min(float(b["low"]) for b in forward_rows)

    return {
        "outcome": "no_trade",
        "max_move_up_pct": round((max_high - first_close) / first_close * 100, 2),
        "max_move_down_pct": round((first_close - min_low) / first_close * 100, 2),
    }


# ── Forward 窗口重建 ─────────────────────────────────

def rebuild_forward_map(
    csv_path: str,
    lookback: int,
    forward: int,
) -> dict[int, list[dict]]:
    """
    从 CSV 重建 forward 窗口。

    返回 {analysis_start: [forward_rows]} 的映射。
    """
    df = pd.read_csv(csv_path)
    forward_map = {}

    total = len(df)
    for start in range(0, total - lookback - forward + 1):
        fwd_start = start + lookback
        fwd_end = fwd_start + forward
        forward_map[start] = df.iloc[fwd_start:fwd_end].to_dict("records")

    return forward_map


# ── 评分主流程 ────────────────────────────────────────

def _extract_meta(run: dict) -> dict:
    return {
        "case_id": run.get("case_id", ""),
        "run_id": run.get("run_id", 0),
        "symbol": run.get("symbol", ""),
        "interval": run.get("interval", ""),
        "temperature": run.get("temperature", 0),
        "timestamp": run.get("timestamp", ""),
    }


def _extract_verdict(parsed: dict) -> dict:
    verdict = parsed.get("verdict", {})
    decision = parsed.get("decision", {})
    trade = parsed.get("trade", {})
    structure = parsed.get("structure", {})

    return {
        "action": decision.get("action"),
        "playbook": decision.get("playbook"),
        "confidence": verdict.get("confidence"),
        "bias": verdict.get("bias"),
        "signal_strength": verdict.get("signal_strength"),
        "market_state": structure.get("market_state"),
        "checklist_result": decision.get("checklist_result"),
        "entry_price": _to_float_or_none(trade.get("entry_price")),
        "stop_loss": _to_float_or_none(trade.get("stop_loss")),
        "t1": _to_float_or_none(trade.get("t1")),
        "risk_reward": _to_float_or_none(trade.get("risk_reward")),
    }


def score_runs(runs_file: Path, forward_map: dict[int, list[dict]]) -> list[dict]:
    """读取 runs.jsonl 并逐行评分。"""
    scored = []

    with open(runs_file, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue

            try:
                run = json.loads(line)
            except json.JSONDecodeError:
                print(f"⚠️  第 {line_num} 行 JSON 解析失败, 跳过", file=sys.stderr)
                continue

            parsed = normalize_parsed_payload(run.get("parsed_json"))

            if not parsed or run.get("parse_error"):
                scored.append({**_extract_meta(run), "outcome": "parse_error"})
                continue

            # 获取 forward 窗口
            analysis_start = run.get("analysis_start")
            forward_rows = []
            if analysis_start is not None and analysis_start in forward_map:
                forward_rows = forward_map[analysis_start]
            elif "forward_rows" in run:
                # 兼容旧格式（forward_rows 内联在 JSONL 中）
                forward_rows = run["forward_rows"]

            action = parsed.get("decision", {}).get("action", "watch")

            if action in ("long", "short"):
                score = score_trade(parsed, forward_rows)
            else:
                score = score_watch(forward_rows)

            scored.append({
                **_extract_meta(run),
                **_extract_verdict(parsed),
                **score,
            })

    return scored


def main():
    parser = argparse.ArgumentParser(description="Skill Eval 评分器")

    # 推荐用法：--dir
    parser.add_argument("--dir", default=None, help="run 目录路径 (自动读取 config.json + runs.jsonl)")

    # 兼容用法：手动指定
    parser.add_argument("--results", default=None, help="runs.jsonl 路径")
    parser.add_argument("--csv", default=None, help="原始 OHLCV CSV 路径")
    parser.add_argument("--lookback", type=int, default=200, help="分析窗口大小")
    parser.add_argument("--forward", type=int, default=50, help="事后窗口大小")

    parser.add_argument("--output", default=None, help="输出 scored.jsonl 路径")
    args = parser.parse_args()

    # 解析参数来源
    if args.dir:
        run_dir = Path(args.dir)
        config_file = run_dir / "config.json"
        if not config_file.exists():
            print(f"❌ config.json 不存在: {config_file}", file=sys.stderr)
            sys.exit(1)

        config = json.loads(config_file.read_text(encoding="utf-8"))
        runs_file = run_dir / "runs.jsonl"
        csv_path = config["csv"]
        lookback = config["lookback"]
        forward = config["forward"]
        out_file = Path(args.output) if args.output else run_dir / "scored.jsonl"
    elif args.results:
        runs_file = Path(args.results)
        csv_path = args.csv
        lookback = args.lookback
        forward = args.forward
        out_file = Path(args.output) if args.output else runs_file.parent / "scored.jsonl"
    else:
        print("❌ 必须指定 --dir 或 --results", file=sys.stderr)
        sys.exit(1)

    if not runs_file.exists():
        print(f"❌ 文件不存在: {runs_file}", file=sys.stderr)
        sys.exit(1)

    # 重建 forward 窗口
    forward_map: dict[int, list[dict]] = {}
    if csv_path and Path(csv_path).exists():
        print(f"📂 从 CSV 重建 forward 窗口: {csv_path}")
        forward_map = rebuild_forward_map(csv_path, lookback, forward)
        print(f"   可用窗口: {len(forward_map)} 个")
    else:
        print("ℹ️  无 CSV，尝试从 JSONL 内联 forward_rows 评分")

    # 评分
    print(f"📊 评分: {runs_file}")
    scored = score_runs(runs_file, forward_map)

    # 保存
    with open(out_file, "w", encoding="utf-8") as f:
        for s in scored:
            f.write(json.dumps(s, ensure_ascii=False, default=str) + "\n")

    # 统计
    total = len(scored)
    has_trade = [s for s in scored if s.get("outcome") in ("t1_hit", "sl_hit", "neither")]
    t1_hits = sum(1 for s in has_trade if s["outcome"] == "t1_hit")
    sl_hits = sum(1 for s in has_trade if s["outcome"] == "sl_hit")
    neither = sum(1 for s in has_trade if s["outcome"] == "neither")
    watch = sum(1 for s in scored if s.get("action") == "watch" or s.get("outcome") == "no_trade")
    errors = sum(1 for s in scored if s.get("outcome") == "parse_error")

    print(f"\n{'─'*40}")
    print(f"📈 评分统计")
    print(f"   总 runs: {total}")
    print(f"   有方案: {len(has_trade)}")
    if has_trade:
        print(f"     T1 命中: {t1_hits}  SL 命中: {sl_hits}  未触碰: {neither}")
        print(f"     胜率: {t1_hits / len(has_trade) * 100:.1f}%")
    print(f"   观望: {watch}  解析错误: {errors}")
    print(f"\n✅ 结果: {out_file}")


if __name__ == "__main__":
    main()
