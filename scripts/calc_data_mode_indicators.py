#!/usr/bin/env python3
"""
数据模式指标计算脚本（MACD / RSI14）。

用法：
  python3 scripts/calc_data_mode_indicators.py \
    --csv data/opend_kline/BTCUSDT/kline_1h_clean.csv
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.indicator_calc import add_macd_rsi, indicator_snapshot_from_rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="计算数据模式指标（MACD/RSI14）")
    parser.add_argument("--csv", required=True, help="输入 CSV（需含 time 或 timestamp, open,high,low,close,volume）")
    parser.add_argument("--out-csv", default=None, help="输出带指标的 CSV（默认同目录 *_indicators.csv）")
    parser.add_argument("--out-json", default=None, help="输出指标摘要 JSON（默认同目录 *_indicators_summary.json）")
    return parser.parse_args()


def _normalize_input(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "timestamp" not in out.columns and "time" in out.columns:
        out["timestamp"] = out["time"]
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = required - set(out.columns)
    if missing:
        raise ValueError(f"输入 CSV 缺少字段: {sorted(missing)}")
    out = out[["timestamp", "open", "high", "low", "close", "volume"]].copy()
    out["timestamp"] = pd.to_datetime(out["timestamp"], errors="coerce")
    out = out.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)
    for col in ("open", "high", "low", "close", "volume"):
        out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)
    out["timestamp"] = out["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return out


def _maybe_float(v: Any, ndigits: int = 4) -> float | None:
    if v is None:
        return None
    try:
        x = float(v)
    except Exception:
        return None
    if np.isnan(x):
        return None
    return round(x, ndigits)


def main() -> None:
    args = parse_args()
    src = Path(args.csv).resolve()
    if not src.exists():
        raise FileNotFoundError(f"未找到输入 CSV: {src}")

    out_csv = Path(args.out_csv).resolve() if args.out_csv else src.with_name(f"{src.stem}_indicators.csv")
    out_json = Path(args.out_json).resolve() if args.out_json else src.with_name(f"{src.stem}_indicators_summary.json")

    raw = pd.read_csv(src)
    norm = _normalize_input(raw)
    with_ind = add_macd_rsi(norm)
    with_ind.to_csv(out_csv, index=False)

    snap = indicator_snapshot_from_rows(norm.to_dict("records"), tail=5)
    latest = with_ind.iloc[-1].to_dict() if not with_ind.empty else {}
    summary = {
        "input_csv": str(src),
        "output_csv": str(out_csv),
        "rows": int(len(with_ind)),
        "latest": {
            "timestamp": str(latest.get("timestamp")),
            "close": _maybe_float(latest.get("close")),
            "rsi14": _maybe_float(latest.get("rsi14"), 2),
            "macd": _maybe_float(latest.get("macd")),
            "signal": _maybe_float(latest.get("signal")),
            "hist": _maybe_float(latest.get("hist")),
        },
        "snapshot": snap,
    }
    out_json.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\n已输出指标 CSV: {out_csv}")
    print(f"已输出指标摘要: {out_json}")


if __name__ == "__main__":
    main()
