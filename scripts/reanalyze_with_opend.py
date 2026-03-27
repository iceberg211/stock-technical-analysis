#!/usr/bin/env python3
"""
使用 OpenAPI 原生 1D/1H K 线拉取并生成技术分析摘要。

功能：
1. 调用 openapi skill 的 get_kline.py 拉取最新 1D、1H 数据
2. 清洗原始 JSON（兼容 SDK 日志混入）
3. 计算基础指标（MA20/MA60、MACD、RSI14、ATR14）
4. 输出分析摘要 JSON 和清洗后 CSV
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.indicator_calc import ema, rsi, atr, add_all_indicators, maybe_float

DEFAULT_OPENAPI_KLINE_SCRIPT = Path.home() / ".codex/skills/openapi/scripts/quote/get_kline.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="拉取最新 OpenAPI K 线并生成分析摘要")
    parser.add_argument("--symbol", required=True, help="标的代码，例如 SH.601899 / HK.00700 / US.AAPL")
    parser.add_argument("--daily-days", type=int, default=200, help="日线回看天数（默认 200）")
    parser.add_argument("--hourly-days", type=int, default=120, help="1小时回看天数（默认 120）")
    parser.add_argument("--rehab", choices=["none", "forward", "backward"], default="forward", help="复权类型")
    parser.add_argument(
        "--kline-script",
        default=str(DEFAULT_OPENAPI_KLINE_SCRIPT),
        help="openapi get_kline.py 脚本路径",
    )
    parser.add_argument(
        "--out-dir",
        default=None,
        help="输出目录（默认 data/opend_kline/<symbol>）",
    )
    return parser.parse_args()


def run_kline_script(
    kline_script: Path,
    symbol: str,
    ktype: str,
    start_date: str,
    end_date: str,
    rehab: str,
    output_file: Path,
) -> None:
    cmd = [
        "python3",
        str(kline_script),
        symbol,
        "--ktype",
        ktype,
        "--start",
        start_date,
        "--end",
        end_date,
        "--rehab",
        rehab,
        "--json",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    # stdout/stderr 都可能有日志，统一写入，后续做 JSON 提取
    mixed_output = ""
    if result.stdout:
        mixed_output += result.stdout
    if result.stderr:
        mixed_output += ("\n" + result.stderr if mixed_output else result.stderr)
    output_file.write_text(mixed_output, encoding="utf-8")


def load_mixed_json(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end < 0 or end <= start:
        raise ValueError(f"无法从文件提取 JSON: {path}")
    return json.loads(text[start : end + 1])


def to_df(obj: dict[str, Any]) -> pd.DataFrame:
    data = obj.get("data", [])
    df = pd.DataFrame(data)
    if df.empty:
        return df
    df["time"] = pd.to_datetime(df["time"])
    for col in ["open", "high", "low", "close", "turnover"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype("int64")
    return df.sort_values("time").reset_index(drop=True)


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """为 OpenD 数据添加指标（基于 time 列而非 timestamp）。"""
    if df.empty:
        return df
    out = df.copy()
    out["ma20"] = out["close"].rolling(20).mean()
    out["ma60"] = out["close"].rolling(60).mean()
    out["ema12"] = ema(out["close"], 12)
    out["ema26"] = ema(out["close"], 26)
    out["macd"] = out["ema12"] - out["ema26"]
    out["signal"] = ema(out["macd"], 9)
    out["hist"] = out["macd"] - out["signal"]
    out["rsi14"] = rsi(out["close"], 14)
    out["atr14"] = atr(out, 14)
    return out


def pivot_levels(df: pd.DataFrame, n: int) -> dict[str, list[float]]:
    part = df.tail(n)
    if part.empty:
        return {"resistance": [], "support": []}
    hi = part["high"].nlargest(3).sort_values(ascending=False).round(3).tolist()
    lo = part["low"].nsmallest(3).sort_values(ascending=True).round(3).tolist()
    return {"resistance": hi, "support": lo}


def main() -> None:
    args = parse_args()
    symbol = args.symbol.strip().upper()
    kline_script = Path(args.kline_script).expanduser().resolve()
    if not kline_script.exists():
        raise FileNotFoundError(f"未找到 get_kline.py: {kline_script}")

    out_dir = Path(args.out_dir).resolve() if args.out_dir else (REPO_ROOT / "data" / "opend_kline" / symbol)
    out_dir.mkdir(parents=True, exist_ok=True)
    run_time_utc = datetime.now(timezone.utc)
    run_id = run_time_utc.strftime("%Y%m%d_%H%M%SZ")

    today = date.today()
    daily_start = (today - timedelta(days=args.daily_days)).isoformat()
    hourly_start = (today - timedelta(days=args.hourly_days)).isoformat()
    end_date = today.isoformat()

    raw_1d = out_dir / "kline_1d_raw.json"
    raw_1h = out_dir / "kline_1h_raw.json"

    run_kline_script(kline_script, symbol, "1d", daily_start, end_date, args.rehab, raw_1d)
    run_kline_script(kline_script, symbol, "60m", hourly_start, end_date, args.rehab, raw_1h)

    obj_1d = load_mixed_json(raw_1d)
    obj_1h = load_mixed_json(raw_1h)

    df_1d = add_indicators(to_df(obj_1d))
    df_1h = add_indicators(to_df(obj_1h))

    df_1d.to_csv(out_dir / "kline_1d_clean.csv", index=False)
    df_1h.to_csv(out_dir / "kline_1h_clean.csv", index=False)

    last_d = df_1d.iloc[-1].to_dict() if not df_1d.empty else {}
    last_h = df_1h.iloc[-1].to_dict() if not df_1h.empty else {}
    prev_d = df_1d.iloc[-2].to_dict() if len(df_1d) > 1 else {}

    daily_20_high = maybe_float(df_1d.tail(20)["high"].max()) if not df_1d.empty else None
    daily_20_low = maybe_float(df_1d.tail(20)["low"].min()) if not df_1d.empty else None
    hourly_10_high = maybe_float(df_1h.tail(10)["high"].max()) if not df_1h.empty else None
    hourly_10_low = maybe_float(df_1h.tail(10)["low"].min()) if not df_1h.empty else None

    summary = {
        "symbol": symbol,
        "run_id": run_id,
        "analysis_time_utc": run_time_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "analysis_date": today.isoformat(),
        "rehab": args.rehab,
        "rows": {
            "1d": int(len(df_1d)),
            "1h": int(len(df_1h)),
        },
        "range": {
            "1d": [str(df_1d["time"].min()) if not df_1d.empty else None, str(df_1d["time"].max()) if not df_1d.empty else None],
            "1h": [str(df_1h["time"].min()) if not df_1h.empty else None, str(df_1h["time"].max()) if not df_1h.empty else None],
        },
        "last_daily": {
            "time": str(last_d.get("time")),
            "open": maybe_float(last_d.get("open")),
            "high": maybe_float(last_d.get("high")),
            "low": maybe_float(last_d.get("low")),
            "close": maybe_float(last_d.get("close")),
            "prev_close": maybe_float(prev_d.get("close")),
            "ma20": maybe_float(last_d.get("ma20")),
            "ma60": maybe_float(last_d.get("ma60")),
            "macd": maybe_float(last_d.get("macd"), 4),
            "signal": maybe_float(last_d.get("signal"), 4),
            "hist": maybe_float(last_d.get("hist"), 4),
            "rsi14": maybe_float(last_d.get("rsi14"), 2),
            "atr14": maybe_float(last_d.get("atr14")),
        },
        "last_hourly": {
            "time": str(last_h.get("time")),
            "close": maybe_float(last_h.get("close")),
            "ma20": maybe_float(last_h.get("ma20")),
            "ma60": maybe_float(last_h.get("ma60")),
            "macd": maybe_float(last_h.get("macd"), 4),
            "signal": maybe_float(last_h.get("signal"), 4),
            "hist": maybe_float(last_h.get("hist"), 4),
            "rsi14": maybe_float(last_h.get("rsi14"), 2),
        },
        "daily_20d_high_low": [daily_20_high, daily_20_low],
        "hourly_10bar_high_low": [hourly_10_high, hourly_10_low],
        "levels_daily_60": pivot_levels(df_1d, 60),
        "levels_hourly_80": pivot_levels(df_1h, 80),
    }

    summary_file = out_dir / "analysis_summary.json"
    summary_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    # 历史归档：每次运行保留一份完整快照，便于回测与复盘
    run_dir = out_dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    archived_summary_file = run_dir / "analysis_summary.json"
    archived_summary_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    for src in [raw_1d, raw_1h, out_dir / "kline_1d_clean.csv", out_dir / "kline_1h_clean.csv"]:
        if src.exists():
            shutil.copy2(src, run_dir / src.name)

    # 追加日志：jsonl 便于程序化读取和批量统计
    logs_dir = out_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    run_log_file = logs_dir / "analysis_runs.jsonl"
    run_log = {
        "run_id": run_id,
        "analysis_time_utc": summary["analysis_time_utc"],
        "symbol": symbol,
        "summary_path": str(archived_summary_file),
        "last_daily_close": summary["last_daily"]["close"],
        "last_hourly_close": summary["last_hourly"]["close"],
        "rows_1d": summary["rows"]["1d"],
        "rows_1h": summary["rows"]["1h"],
    }
    with run_log_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(run_log, ensure_ascii=False) + "\n")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\n已输出: {summary_file}")
    print(f"已归档: {archived_summary_file}")
    print(f"已记录日志: {run_log_file}")


if __name__ == "__main__":
    main()
