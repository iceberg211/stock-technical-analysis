"""
事后评分器：对比 Skill JSON 预测 vs 实际 K 线走势。

用法:
    # 推荐：指定 run 目录（自动读取 config.json + runs.jsonl + CSV）
    python -m eval.score_eval --dir eval/results/20260322_0939_BTCUSDT_4h

    # 兼容：手动指定 runs.jsonl + CSV
    python -m eval.score_eval --results runs.jsonl --csv data.csv --lookback 200 --forward 50
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

SCORE_SCHEMA_VERSION = "score_v2"
RUN_SCHEMA_VERSION = "run_v2"


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

def _entry_triggered(
    _action: str,
    trigger_type: str | None,
    trigger_price: float,
    bar: dict,
) -> tuple[bool, float | None]:
    """
    判断是否在当前 bar 触发入场，并返回执行价。

    规则：
    - price_touch: 价位被触碰则入场，执行价按 trigger_price
    - close_above / close_below: 收盘确认，执行价按 bar.close
    - 未知 trigger_type: 回退为 price_touch
    """
    high = _to_float_or_none(bar.get("high"))
    low = _to_float_or_none(bar.get("low"))
    close = _to_float_or_none(bar.get("close"))
    if high is None or low is None or close is None:
        return False, None

    tt = trigger_type or "price_touch"
    if tt == "price_touch":
        hit = low <= trigger_price <= high
        return (hit, trigger_price if hit else None)
    if tt == "close_above":
        hit = close >= trigger_price
        return (hit, close if hit else None)
    if tt == "close_below":
        hit = close <= trigger_price
        return (hit, close if hit else None)

    # 未知类型，回退触价逻辑
    hit = low <= trigger_price <= high
    return (hit, trigger_price if hit else None)


def _risk_denominator(action: str, entry_price: float, stop_loss: float) -> float:
    if action == "long":
        return entry_price - stop_loss
    return stop_loss - entry_price


def score_trade(
    parsed: dict,
    forward_rows: list[dict],
    slippage_pct: float = 0.0,
    fee_pct: float = 0.0,
) -> dict:
    """
    对有 trade 方案的 case 评分。

    Parameters
    ----------
    slippage_pct : float
        滑点比例（如 0.0005 = 0.05%），对入场价做不利方向偏移。
    fee_pct : float
        单边手续费比例（如 0.001 = 0.1%），入场和出场各收一次。

    逻辑：
    1) 先检查是否触发入场（支持 trigger_type）；
    2) 入场后再评估 SL / T1 / T2；
    3) 到 T1 后按规则将剩余仓位止损抬到保本（entry）。
    """
    trade = parsed.get("trade", {})
    decision = parsed.get("decision", {})
    action = decision.get("action")

    entry = _to_float_or_none(trade.get("entry_price"))
    sl = _to_float_or_none(trade.get("stop_loss"))
    t1 = _to_float_or_none(trade.get("t1"))
    t2 = _to_float_or_none(trade.get("t2"))
    trigger_type = trade.get("trigger_type")
    trigger_price = _to_float_or_none(trade.get("trigger_price"))
    if trigger_price is None:
        trigger_price = entry

    if entry is None or sl is None or t1 is None or action == "watch":
        return {
            "outcome": "no_trade",
            "entry_triggered": False,
            "entry_exec_price": None,
            "bars_to_entry": None,
            "bars_to_outcome": None,
            "bars_to_t1": None,
            "bars_to_t2": None,
            "bars_to_sl": None,
            "t1_hit": False,
            "t2_hit": False,
            "mfe": None,
            "mae": None,
            "realized_r": None,
        }

    is_long = action == "long"
    entry_triggered = False
    entry_exec_price = None
    bars_to_entry = None
    mfe = 0.0
    mae = 0.0
    outcome = "missed_entry"
    bars_to_outcome = None
    bars_to_t1 = None
    bars_to_t2 = None
    bars_to_sl = None
    t1_hit = False
    t2_hit = False

    for bar_idx, bar in enumerate(forward_rows, start=1):
        high = float(bar["high"])
        low = float(bar["low"])

        # 1) 入场触发检查
        if not entry_triggered:
            triggered, exec_px = _entry_triggered(action, trigger_type, float(trigger_price), bar)
            if not triggered:
                continue

            entry_triggered = True
            raw_exec = float(exec_px) if exec_px is not None else float(entry)
            # 滑点：对入场价做不利方向偏移
            if is_long:
                entry_exec_price = raw_exec * (1 + slippage_pct + fee_pct)
            else:
                entry_exec_price = raw_exec * (1 - slippage_pct - fee_pct)
            bars_to_entry = bar_idx
            outcome = "neither"
            # close_* 触发后按收盘入场，不在同一根继续判定出场，避免同根前后顺序歧义
            if trigger_type in ("close_above", "close_below"):
                continue

        if is_long:
            favorable = high - entry_exec_price
            adverse = entry_exec_price - low
        else:
            favorable = entry_exec_price - low
            adverse = high - entry_exec_price

        mfe = max(mfe, favorable)
        mae = max(mae, adverse)

        # 2) 出场评分状态机
        if is_long:
            active_sl = entry_exec_price if t1_hit else sl
            sl_now = low <= active_sl
            t1_now = (not t1_hit) and (high >= t1)
            t2_now = t1_hit and (t2 is not None) and (high >= t2)
        else:
            active_sl = entry_exec_price if t1_hit else sl
            sl_now = high >= active_sl
            t1_now = (not t1_hit) and (low <= t1)
            t2_now = t1_hit and (t2 is not None) and (low <= t2)

        # 还没到 T1 之前：SL 与 T1 同根冲突按保守规则记 SL
        if not t1_hit:
            if sl_now and t1_now:
                outcome = "sl_hit"
                bars_to_sl = bar_idx
                bars_to_outcome = bar_idx
                break
            if sl_now:
                outcome = "sl_hit"
                bars_to_sl = bar_idx
                bars_to_outcome = bar_idx
                break
            if t1_now:
                t1_hit = True
                bars_to_t1 = bar_idx
                # 无 T2 时，默认 T1 全平
                if t2 is None:
                    outcome = "t1_hit"
                    bars_to_outcome = bar_idx
                    break
                continue
        else:
            # 到达 T1 后：先看 T2，再看保本止损
            if t2_now:
                t2_hit = True
                bars_to_t2 = bar_idx
                outcome = "t1_hit"
                bars_to_outcome = bar_idx
                break
            if sl_now:
                # 这里是“保本止损被打”，仍记为已完成 T1 的正向交易
                outcome = "t1_hit"
                bars_to_sl = bar_idx
                bars_to_outcome = bar_idx
                break

    if not entry_triggered:
        return {
            "outcome": "missed_entry",
            "entry_triggered": False,
            "entry_exec_price": None,
            "bars_to_entry": None,
            "bars_to_outcome": None,
            "bars_to_t1": None,
            "bars_to_t2": None,
            "bars_to_sl": None,
            "t1_hit": False,
            "t2_hit": False,
            "mfe": None,
            "mae": None,
            "realized_r": None,
        }

    if bars_to_outcome is None:
        if t1_hit:
            outcome = "t1_hit"
        else:
            outcome = "neither"

    # 3) R 结果：-1R（先止损）、+0.5R（到T1后其余保本）、到T2按半仓扩展
    #    出场手续费在 R 计算中扣除（入场费已计入 entry_exec_price）
    realized_r = None
    den = _risk_denominator(action, entry_exec_price, sl)
    exit_fee_abs = entry_exec_price * fee_pct  # 出场手续费绝对值

    if den > 0:
        if outcome == "sl_hit" and not t1_hit:
            realized_r = -1.0 - (exit_fee_abs / den) if den > 0 else -1.0
        elif t1_hit:
            if is_long:
                r1 = (t1 - entry_exec_price - exit_fee_abs) / den
            else:
                r1 = (entry_exec_price - t1 - exit_fee_abs) / den

            if t2_hit and t2 is not None:
                if is_long:
                    r2 = (t2 - entry_exec_price - exit_fee_abs) / den
                else:
                    r2 = (entry_exec_price - t2 - exit_fee_abs) / den
                realized_r = 0.5 * r1 + 0.5 * r2
            else:
                realized_r = 0.5 * r1
        elif outcome == "neither":
            # 窗口结束仍未触发出场，给出按最后收盘的浮动 R 参考
            last_close = _to_float_or_none(forward_rows[-1].get("close")) if forward_rows else None
            if last_close is not None:
                if is_long:
                    realized_r = (last_close - entry_exec_price - exit_fee_abs) / den
                else:
                    realized_r = (entry_exec_price - last_close - exit_fee_abs) / den

    return {
        "outcome": outcome,
        "entry_triggered": True,
        "entry_exec_price": round(entry_exec_price, 6),
        "bars_to_entry": bars_to_entry,
        "mfe": round(mfe, 4),
        "mae": round(mae, 4),
        "bars_to_outcome": bars_to_outcome,
        "bars_to_t1": bars_to_t1,
        "bars_to_t2": bars_to_t2,
        "bars_to_sl": bars_to_sl,
        "t1_hit": t1_hit,
        "t2_hit": t2_hit,
        "realized_r": round(realized_r, 4) if realized_r is not None else None,
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


# ── Forward 窗口重建/兼容读取 ─────────────────────────

def _load_csv_df(csv_path: str | None) -> pd.DataFrame | None:
    if not csv_path:
        return None
    p = Path(csv_path)
    if not p.exists():
        return None
    df = pd.read_csv(p)
    required_cols = {"timestamp", "open", "high", "low", "close", "volume"}
    if not required_cols.issubset(set(df.columns)):
        return None
    return df.reset_index(drop=True)


def _infer_window(parsed: dict, default_lookback: int, default_forward: int) -> tuple[int, int]:
    meta = parsed.get("meta", {}) if isinstance(parsed, dict) else {}
    lb = meta.get("lookback_bars", default_lookback)
    fw = meta.get("forward_bars", default_forward)
    try:
        lb_i = max(1, int(lb))
    except Exception:
        lb_i = max(1, int(default_lookback))
    try:
        fw_i = max(1, int(fw))
    except Exception:
        fw_i = max(1, int(default_forward))
    return lb_i, fw_i


def _slice_forward_rows(
    df: pd.DataFrame | None,
    analysis_start: int | None,
    lookback: int,
    forward: int,
) -> list[dict]:
    if df is None or analysis_start is None:
        return []
    if analysis_start < 0:
        return []
    total = len(df)
    fwd_start = analysis_start + lookback
    fwd_end = fwd_start + forward
    if fwd_start < 0 or fwd_end > total:
        return []
    return df.iloc[fwd_start:fwd_end].to_dict("records")


# ── 评分主流程 ────────────────────────────────────────

def _extract_meta(run: dict) -> dict:
    return {
        "score_schema_version": SCORE_SCHEMA_VERSION,
        "run_schema_version": run.get("run_schema_version", "run_v1"),
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
        "t2": _to_float_or_none(trade.get("t2")),
        "trigger_type": trade.get("trigger_type"),
        "risk_reward": _to_float_or_none(trade.get("risk_reward")),
    }


def score_runs(
    runs_file: Path,
    primary_df: pd.DataFrame | None,
    fallback_df: pd.DataFrame | None,
    default_lookback: int,
    default_forward: int,
    slippage_pct: float = 0.0,
    fee_pct: float = 0.0,
) -> tuple[list[dict], dict[str, int]]:
    """读取 runs.jsonl 并逐行评分。"""
    scored: list[dict] = []
    source_stats = {
        "config_csv": 0,
        "inline_forward_rows": 0,
        "eval_input_csv": 0,
        "none": 0,
    }

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

            analysis_start = run.get("analysis_start")
            try:
                analysis_start = int(analysis_start) if analysis_start is not None else None
            except Exception:
                analysis_start = None

            lookback, forward = _infer_window(parsed, default_lookback, default_forward)
            forward_rows: list[dict] = []
            forward_source = "none"

            # 1) config + csv 重建
            forward_rows = _slice_forward_rows(primary_df, analysis_start, lookback, forward)
            if forward_rows:
                forward_source = "config_csv"
            # 2) run.forward_rows 兼容
            elif "forward_rows" in run and isinstance(run["forward_rows"], list) and run["forward_rows"]:
                forward_rows = run["forward_rows"]
                forward_source = "inline_forward_rows"
            # 3) 同目录 eval_input.csv 回退
            else:
                forward_rows = _slice_forward_rows(fallback_df, analysis_start, lookback, forward)
                if forward_rows:
                    forward_source = "eval_input_csv"

            source_stats[forward_source] = source_stats.get(forward_source, 0) + 1

            action = parsed.get("decision", {}).get("action", "watch")
            if action in ("long", "short"):
                score = score_trade(parsed, forward_rows, slippage_pct=slippage_pct, fee_pct=fee_pct)
            else:
                score = score_watch(forward_rows)

            scored.append(
                {
                    **_extract_meta(run),
                    "forward_source": forward_source,
                    **_extract_verdict(parsed),
                    **score,
                }
            )

    return scored, source_stats


def _write_compat_manifest(
    run_dir: Path,
    config_exists: bool,
    primary_csv_path: str | None,
    fallback_csv_path: str | None,
    legacy_run_schema_detected: bool,
    source_stats: dict[str, int],
) -> None:
    manifest_path = run_dir / "compat_manifest.json"
    if manifest_path.exists():
        return
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "score_schema_version": SCORE_SCHEMA_VERSION,
        "config_exists": config_exists,
        "primary_csv_path": primary_csv_path,
        "fallback_eval_input_csv": fallback_csv_path,
        "legacy_run_schema_detected": legacy_run_schema_detected,
        "forward_source_stats": source_stats,
        "note": "懒迁移兼容标记：仅记录识别结果，不改写旧数据。",
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def _detect_legacy_run_schema(runs_file: Path) -> bool:
    with open(runs_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                run = json.loads(line)
            except json.JSONDecodeError:
                continue
            if run.get("run_schema_version") != RUN_SCHEMA_VERSION:
                return True
    return False


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
    parser.add_argument("--slippage", type=float, default=0.0005, help="滑点比例（默认 0.05%%）")
    parser.add_argument("--fee", type=float, default=0.001, help="单边手续费比例（默认 0.1%%）")
    args = parser.parse_args()

    run_dir: Path | None = None
    config_exists = False
    primary_csv_path: str | None = None
    fallback_csv_path: str | None = None

    # 解析参数来源
    if args.dir:
        run_dir = Path(args.dir)
        runs_file = run_dir / "runs.jsonl"
        config_file = run_dir / "config.json"

        config: dict[str, Any] = {}
        if config_file.exists():
            config_exists = True
            config = json.loads(config_file.read_text(encoding="utf-8"))

        primary_csv_path = args.csv or config.get("csv")
        lookback = int(config.get("lookback", args.lookback))
        forward = int(config.get("forward", args.forward))
        out_file = Path(args.output) if args.output else run_dir / "scored.jsonl"

        fallback_eval_input = run_dir / "eval_input.csv"
        if fallback_eval_input.exists():
            fallback_csv_path = str(fallback_eval_input)
    elif args.results:
        runs_file = Path(args.results)
        primary_csv_path = args.csv
        lookback = args.lookback
        forward = args.forward
        out_file = Path(args.output) if args.output else runs_file.parent / "scored.jsonl"
    else:
        print("❌ 必须指定 --dir 或 --results", file=sys.stderr)
        sys.exit(1)

    if not runs_file.exists():
        print(f"❌ 文件不存在: {runs_file}", file=sys.stderr)
        sys.exit(1)

    legacy_run_schema_detected = _detect_legacy_run_schema(runs_file)

    primary_df = _load_csv_df(primary_csv_path)
    fallback_df = None
    if fallback_csv_path:
        # 如果 fallback 与 primary 相同路径，避免重复读取
        if not primary_csv_path or Path(fallback_csv_path).resolve() != Path(primary_csv_path).resolve():
            fallback_df = _load_csv_df(fallback_csv_path)

    if primary_df is not None:
        print(f"📂 从 CSV 重建 forward 优先路径: {primary_csv_path}")
    else:
        print("ℹ️  主 CSV 不可用，优先走 JSONL 内联 forward_rows")

    if fallback_df is not None:
        print(f"📂 启用回退 CSV: {fallback_csv_path}")

    # 评分
    print(f"📊 评分: {runs_file} (slippage={args.slippage:.4%}, fee={args.fee:.4%})")
    scored, source_stats = score_runs(
        runs_file=runs_file,
        primary_df=primary_df,
        fallback_df=fallback_df,
        default_lookback=lookback,
        default_forward=forward,
        slippage_pct=args.slippage,
        fee_pct=args.fee,
    )

    # 保存
    with open(out_file, "w", encoding="utf-8") as f:
        for s in scored:
            f.write(json.dumps(s, ensure_ascii=False, default=str) + "\n")

    # dir 模式：仅在旧目录兼容分支被触发时写懒迁移标记
    needs_compat_manifest = (
        (not config_exists)
        or legacy_run_schema_detected
        or source_stats.get("inline_forward_rows", 0) > 0
        or source_stats.get("eval_input_csv", 0) > 0
    )
    if run_dir is not None and needs_compat_manifest:
        _write_compat_manifest(
            run_dir=run_dir,
                config_exists=config_exists,
                primary_csv_path=primary_csv_path,
                fallback_csv_path=fallback_csv_path,
                legacy_run_schema_detected=legacy_run_schema_detected,
                source_stats=source_stats,
            )

    # 统计
    total = len(scored)
    has_trade = [s for s in scored if s.get("outcome") in ("t1_hit", "sl_hit", "neither")]
    t1_hits = sum(1 for s in has_trade if s["outcome"] == "t1_hit")
    t2_hits = sum(1 for s in has_trade if bool(s.get("t2_hit")))
    sl_hits = sum(1 for s in has_trade if s["outcome"] == "sl_hit")
    neither = sum(1 for s in has_trade if s["outcome"] == "neither")
    missed_entry = sum(1 for s in scored if s.get("outcome") == "missed_entry")
    watch = sum(1 for s in scored if s.get("action") == "watch" or s.get("outcome") == "no_trade")
    errors = sum(1 for s in scored if s.get("outcome") == "parse_error")

    print(f"\n{'─'*40}")
    print("📈 评分统计")
    print(f"   总 runs: {total}")
    print(f"   有方案: {len(has_trade)}")
    if has_trade:
        print(f"     T1 命中: {t1_hits}  (其中 T2 命中: {t2_hits})")
        print(f"     SL 命中: {sl_hits}  未触碰: {neither}")
        print(f"     胜率: {t1_hits / len(has_trade) * 100:.1f}%")
    print(f"   未触发入场: {missed_entry}")
    print(f"   观望: {watch}  解析错误: {errors}")
    print(
        "   forward 来源: "
        f"config_csv={source_stats.get('config_csv', 0)}, "
        f"inline={source_stats.get('inline_forward_rows', 0)}, "
        f"eval_input={source_stats.get('eval_input_csv', 0)}, "
        f"none={source_stats.get('none', 0)}"
    )
    print(f"\n✅ 结果: {out_file}")


if __name__ == "__main__":
    main()
