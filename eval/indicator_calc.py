"""
数据模式指标计算工具（MACD / RSI）。

用途：
1) 在 eval 数据模式 prompt 中补充指标上下文；
2) 供脚本复用，避免重复实现。
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def ema(series: pd.Series, n: int) -> pd.Series:
    return series.ewm(span=n, adjust=False).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    ma_up = up.ewm(alpha=1 / period, adjust=False).mean()
    ma_down = down.ewm(alpha=1 / period, adjust=False).mean()
    rs = ma_up / ma_down.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def add_macd_rsi(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in ("open", "high", "low", "close", "volume"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out.dropna(subset=["close"]).reset_index(drop=True)
    out["ema12"] = ema(out["close"], 12)
    out["ema26"] = ema(out["close"], 26)
    out["macd"] = out["ema12"] - out["ema26"]
    out["signal"] = ema(out["macd"], 9)
    out["hist"] = out["macd"] - out["signal"]
    out["rsi14"] = rsi(out["close"], 14)
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


def indicator_snapshot_from_rows(rows: list[dict[str, Any]], tail: int = 5) -> dict[str, Any]:
    if not rows:
        return {}
    df = pd.DataFrame(rows).copy()
    if "timestamp" not in df.columns and "time" in df.columns:
        df = df.rename(columns={"time": "timestamp"})
    if "timestamp" not in df.columns:
        return {}
    df = df.sort_values("timestamp").reset_index(drop=True)
    out = add_macd_rsi(df)
    if out.empty:
        return {}

    last = out.iloc[-1]
    rsi_val = _maybe_float(last.get("rsi14"), 2)
    if rsi_val is None:
        rsi_state = "na"
    elif rsi_val >= 70:
        rsi_state = "overbought"
    elif rsi_val <= 30:
        rsi_state = "oversold"
    else:
        rsi_state = "neutral"

    macd_val = _maybe_float(last.get("macd"), 4)
    signal_val = _maybe_float(last.get("signal"), 4)
    hist_val = _maybe_float(last.get("hist"), 4)
    if macd_val is None:
        macd_side = "na"
    else:
        macd_side = "above_zero" if macd_val >= 0 else "below_zero"

    tail_cols = [c for c in ("timestamp", "close", "rsi14", "macd", "signal", "hist") if c in out.columns]
    tail_rows = out[tail_cols].tail(max(1, tail)).copy()
    for c in ("close", "rsi14", "macd", "signal", "hist"):
        if c in tail_rows.columns:
            tail_rows[c] = tail_rows[c].map(lambda x: _maybe_float(x, 4))

    return {
        "latest_time": str(last.get("timestamp")),
        "rsi14": rsi_val,
        "rsi_state": rsi_state,
        "macd": macd_val,
        "macd_signal": signal_val,
        "macd_hist": hist_val,
        "macd_side": macd_side,
        "tail": tail_rows.to_dict("records"),
    }
