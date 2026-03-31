from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.pipeline.layout import REPO_ROOT, RunLayout
from src.pipeline.manifest import GlobalRegistry, RunManifest
from src.pipeline.catalog import Catalog
from src.pipeline.retention import apply_artifact_retention
from src.pipeline.backtest import score_and_report
from src.pipeline.reporting import score_summary
from src.pipeline.signal_loader import (
    import_legacy_signals,
    load_signal_index,
    load_signal_snapshot,
)
from src.scoring.validator import validate_backtest_sample


_ALLOWED_PLAYBOOK = {
    "trend-pullback",
    "breakout-retest",
    "range-reversal",
    "false-breakout-reversal",
    "flag-wedge-breakout",
    "none",
}
_ALLOWED_CONFIDENCE = {"high", "medium", "low"}
_ALLOWED_TRIGGER_TYPE = {"price_touch", "close_above", "close_below"}


def _to_float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if text.startswith("$"):
            text = text[1:]
        try:
            return float(text)
        except ValueError:
            return None
    return None


def _normalize_action(raw_action: Any, bias: Any) -> str:
    action = str(raw_action or "").strip().lower()
    if action in ("long", "short", "watch"):
        return action

    b = str(bias or "").strip().lower()
    if b.startswith("bull"):
        return "long"
    if b.startswith("bear"):
        return "short"
    return "watch"


def _normalize_playbook(value: Any) -> str:
    pb = str(value or "none").strip()
    return pb if pb in _ALLOWED_PLAYBOOK else "none"


def _normalize_confidence(value: Any) -> str:
    c = str(value or "low").strip().lower()
    return c if c in _ALLOWED_CONFIDENCE else "low"


def _pick_market_state(snapshot: dict[str, Any], entry: dict[str, Any]) -> str:
    for key in ("market_state", "market_state_1h", "market_state_4h"):
        v = entry.get(key)
        if isinstance(v, str) and v:
            return v

    one_h = snapshot.get("1h") if isinstance(snapshot.get("1h"), dict) else {}
    four_h = snapshot.get("4h") if isinstance(snapshot.get("4h"), dict) else {}
    if isinstance(one_h.get("state"), str):
        return one_h["state"]
    if isinstance(four_h.get("state"), str):
        return four_h["state"]
    return "unknown"


def _build_payload_from_signal(
    symbol: str,
    interval: str,
    signal_id: str,
    signal_entry: dict[str, Any],
    snapshot: dict[str, Any],
    lookback: int,
    forward: int,
) -> dict[str, Any]:
    ts = signal_entry.get("timestamp_utc") or snapshot.get("time_utc")

    raw_action = signal_entry.get("decision")
    if raw_action is None:
        raw_action = snapshot.get("decision")
    bias = signal_entry.get("bias") or snapshot.get("bias") or snapshot.get("verdict", {}).get("bias")

    action = _normalize_action(raw_action, bias)
    playbook = _normalize_playbook(signal_entry.get("playbook") or snapshot.get("playbook"))
    confidence = _normalize_confidence(
        signal_entry.get("confidence") or snapshot.get("confidence") or snapshot.get("verdict", {}).get("confidence")
    )

    conditional_entry = _to_float_or_none(signal_entry.get("conditional_entry"))
    trade = snapshot.get("trade") if isinstance(snapshot.get("trade"), dict) else {}

    entry_price = conditional_entry
    if entry_price is None:
        entry_price = _to_float_or_none(signal_entry.get("entry_price"))
    if entry_price is None:
        entry_price = _to_float_or_none(snapshot.get("entry_price"))
    if entry_price is None:
        entry_price = _to_float_or_none(trade.get("entry_price"))

    stop_loss = _to_float_or_none(signal_entry.get("stop_loss"))
    if stop_loss is None:
        stop_loss = _to_float_or_none(snapshot.get("stop_loss"))
    if stop_loss is None:
        stop_loss = _to_float_or_none(trade.get("stop_loss"))

    t1 = _to_float_or_none(signal_entry.get("t1"))
    if t1 is None:
        t1 = _to_float_or_none(snapshot.get("t1"))
    if t1 is None:
        t1 = _to_float_or_none(trade.get("t1"))

    t2 = _to_float_or_none(signal_entry.get("t2"))
    if t2 is None:
        t2 = _to_float_or_none(snapshot.get("t2"))
    if t2 is None:
        t2 = _to_float_or_none(trade.get("t2"))

    trigger_type = signal_entry.get("trigger_type") or snapshot.get("trigger_type") or trade.get("trigger_type")
    trigger_type = str(trigger_type).strip() if trigger_type is not None else "price_touch"
    if trigger_type not in _ALLOWED_TRIGGER_TYPE:
        trigger_type = "price_touch"

    risk_reward = _to_float_or_none(signal_entry.get("risk_reward"))
    if risk_reward is None:
        risk_reward = _to_float_or_none(snapshot.get("risk_reward"))
    if risk_reward is None:
        risk_reward = _to_float_or_none(trade.get("risk_reward"))

    # 若缺关键字段，自动降级为 watch，避免脏数据污染评分
    if action in ("long", "short") and (entry_price is None or stop_loss is None or t1 is None):
        action = "watch"

    if risk_reward is None and action in ("long", "short") and entry_price is not None and stop_loss is not None and t1 is not None:
        den = (entry_price - stop_loss) if action == "long" else (stop_loss - entry_price)
        if den and den > 0:
            num = (t1 - entry_price) if action == "long" else (entry_price - t1)
            risk_reward = num / den

    if action == "watch":
        entry_price = None
        stop_loss = None
        t1 = None
        t2 = None
        risk_reward = None
        trigger_type = None
        checklist_result = "fail"
        position_size = 0.0
        bias = str(bias or "watch")
        signal_strength = "weak"
    else:
        checklist_result = "pass_degraded"
        position_size = 50.0
        bias = str(bias or ("bullish" if action == "long" else "bearish"))
        signal_strength = "medium"

    case_id = f"signal_{signal_id}"
    market_state = _pick_market_state(snapshot, signal_entry)

    payload = {
        "meta": {
            "schema_version": "backtest_sample_v1",
            "symbol": symbol,
            "interval": interval,
            "case_id": case_id,
            "analysis_time": ts,
            "lookback_bars": int(lookback),
            "forward_bars": int(forward),
            "data_source": "ohlc",
        },
        "decision": {
            "action": action,
            "playbook": playbook,
            "checklist": {
                "htf_direction": "pass" if action != "watch" else "degraded",
                "position": "pass" if action != "watch" else "fail",
                "setup_match": "pass" if action != "watch" else "fail",
                "trigger": "pass" if action != "watch" else "fail",
                "risk_reward": "pass" if action != "watch" else "fail",
                "events": "pass",
                "counter_reason": "degraded" if action != "watch" else "pass",
            },
            "checklist_result": checklist_result,
            "position_size_pct": position_size,
        },
        "trade": {
            "entry_price": round(entry_price, 6) if entry_price is not None else None,
            "stop_loss": round(stop_loss, 6) if stop_loss is not None else None,
            "t1": round(t1, 6) if t1 is not None else None,
            "t2": round(t2, 6) if t2 is not None else None,
            "risk_reward": round(risk_reward, 6) if risk_reward is not None else None,
            "trigger_type": trigger_type,
            "invalidation": signal_entry.get("invalidation") or snapshot.get("invalidation"),
        },
        "verdict": {
            "bias": bias,
            "confidence": confidence,
            "signal_strength": signal_strength,
        },
        "structure": {
            "market_state": market_state,
        },
    }
    return payload


def _find_analysis_start(df: pd.DataFrame, signal_ts: str | None, lookback: int, forward: int) -> int | None:
    if not signal_ts:
        return None
    ts = pd.to_datetime(signal_ts, errors="coerce", utc=True)
    if pd.isna(ts):
        return None

    timestamps = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
    if timestamps.isna().all():
        return None

    pos = int(timestamps.searchsorted(ts, side="right") - 1)
    if pos < 0:
        return None

    start = pos - int(lookback) + 1
    if start < 0:
        return None
    if start + int(lookback) + int(forward) > len(df):
        return None
    return int(start)


def _repo_rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except Exception:
        return str(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按 outputs/signals 逐信号回测")
    parser.add_argument("--symbols", nargs="+", required=True, help="标的列表，如 BTCUSDT ETHUSDT")
    parser.add_argument("--interval", default="1h", help="回测周期")
    parser.add_argument("--lookback", type=int, default=160, help="分析窗口")
    parser.add_argument("--forward", type=int, default=40, help="事后窗口")
    parser.add_argument("--since", default=None, help="仅回测该时间之后信号")
    parser.add_argument("--until", default=None, help="仅回测该时间之前信号")
    parser.add_argument("--limit", type=int, default=0, help="每个 symbol 最多取多少条信号，0=不限")
    parser.add_argument("--artifact-level", choices=["core", "standard", "full"], default="standard")
    parser.add_argument("--embed-forward-rows", action="store_true", help="内联 forward_rows 到 runs.jsonl")
    parser.add_argument("--import-legacy", action="store_true", help="先导入旧目录 analysis_skill_snapshot.json")
    parser.add_argument("--run-id", default=None, help="可选，指定 run_id")
    parser.add_argument("--slippage", type=float, default=0.0005, help="滑点比例")
    parser.add_argument("--fee", type=float, default=0.001, help="单边手续费")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    symbols = [s.strip().upper() for s in args.symbols]

    run_ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    if args.run_id:
        run_id = args.run_id
    else:
        tag = "_".join(s.lower().replace(".", "") for s in symbols)
        run_id = f"{run_ts}_signalbt_{tag}"

    layout = RunLayout(run_id)
    manifest = RunManifest(layout, symbols, vars(args))
    catalog = Catalog()

    for symbol in symbols:
        sym_layout = layout.get_symbol_layout(symbol)
        item: dict[str, Any] = {"symbol": symbol, "status": "unknown"}

        try:
            sym_layout.setup()

            if args.import_legacy:
                item["legacy_import"] = import_legacy_signals(root=REPO_ROOT, symbol=symbol)

            clean_path = catalog.clean_path(symbol, args.interval)
            item["input"] = catalog.prepare_eval_input(symbol, args.interval, sym_layout.input_parquet)
            df = catalog.read_clean(symbol, args.interval).reset_index(drop=True)
            df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)

            signal_entries = load_signal_index(
                symbol=symbol,
                outputs_root=REPO_ROOT / "outputs",
                since=args.since,
                until=args.until,
                limit=args.limit,
            )
            item["signal_candidates"] = len(signal_entries)

            runs_written = 0
            skipped = 0
            parse_errors = 0

            with sym_layout.runs_jsonl.open("w", encoding="utf-8") as f:
                for idx, entry in enumerate(signal_entries):
                    signal_id = str(entry.get("signal_id") or f"unknown_{idx:04d}")
                    signal_ts = entry.get("timestamp_utc")

                    analysis_start = _find_analysis_start(df, signal_ts, args.lookback, args.forward)
                    if analysis_start is None:
                        skipped += 1
                        continue

                    try:
                        snapshot = load_signal_snapshot(symbol, entry, outputs_root=REPO_ROOT / "outputs")
                    except Exception:
                        skipped += 1
                        continue

                    payload = _build_payload_from_signal(
                        symbol=symbol,
                        interval=args.interval,
                        signal_id=signal_id,
                        signal_entry=entry,
                        snapshot=snapshot,
                        lookback=args.lookback,
                        forward=args.forward,
                    )

                    case_id = payload.get("meta", {}).get("case_id", f"signal_{signal_id}")
                    ok, err, normalized = validate_backtest_sample(payload, case_id)
                    parse_error = not ok
                    if parse_error:
                        parse_errors += 1

                    run_record: dict[str, Any] = {
                        "run_schema_version": "run_v2",
                        "run_id": runs_written,
                        "case_id": case_id,
                        "signal_id": signal_id,
                        "analysis_start": analysis_start,
                        "symbol": symbol,
                        "interval": args.interval,
                        "temperature": 0.0,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "parse_error": parse_error,
                        "validation_error": err,
                        "parsed_json": normalized if normalized is not None else payload,
                        "raw_response_preview": "generated_from_signal_archive",
                    }

                    if args.embed_forward_rows:
                        f_start = analysis_start + int(args.lookback)
                        f_end = f_start + int(args.forward)
                        run_record["forward_rows"] = df.iloc[f_start:f_end].to_dict("records")

                    f.write(json.dumps(run_record, ensure_ascii=False, default=str) + "\n")
                    runs_written += 1

            config_record = {
                "run_id": run_id,
                "symbol": symbol,
                "interval": args.interval,
                "csv": _repo_rel(clean_path),
                "lookback": int(args.lookback),
                "forward": int(args.forward),
                "source": "signal_backtest",
                "signal_filters": {
                    "since": args.since,
                    "until": args.until,
                    "limit": args.limit,
                },
                "artifact_level": args.artifact_level,
                "embed_forward_rows": bool(args.embed_forward_rows),
                "run_schema_version": "run_v2",
            }
            sym_layout.config_json.write_text(json.dumps(config_record, ensure_ascii=False, indent=2), encoding="utf-8")

            score_and_report(sym_layout, slippage_pct=args.slippage, fee_pct=args.fee)
            apply_artifact_retention(sym_layout, args.artifact_level)

            item["status"] = "done"
            item["runs_written"] = runs_written
            item["skipped"] = skipped
            item["parse_errors"] = parse_errors
            item["summary"] = score_summary(sym_layout.scored_jsonl)

            GlobalRegistry.append_run(run_id, symbol, args.interval, "done", str(sym_layout.base_dir))

        except Exception as e:
            item["status"] = "failed"
            item["error"] = str(e)
            GlobalRegistry.append_run(run_id, symbol, args.interval, "failed", str(sym_layout.base_dir), error=str(e))

        manifest.add_symbol_item(item)

    manifest.save()
    print(f"✅ 信号回测完成: {run_id}")
    print(f"- manifest: {layout.manifest_path}")


if __name__ == "__main__":
    main()
