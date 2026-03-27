import pandas as pd
import numpy as np
from typing import Any, Tuple

def _ema(series: pd.Series, n: int) -> pd.Series:
    return series.ewm(span=n, adjust=False).mean()

def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    ma_up = up.ewm(alpha=1 / period, adjust=False).mean()
    ma_down = down.ewm(alpha=1 / period, adjust=False).mean()
    rs = ma_up / ma_down.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()

def build_local_backtest_sample(
    analysis_rows: list[dict[str, Any]],
    symbol: str,
    interval: str,
    case_id: str,
    lookback_bars: int,
    forward_bars: int,
) -> Tuple[dict[str, Any], dict[str, Any]]:
    """本地规则引擎，仅在离线兜底或者测试 pipeline 连通性时调用"""
    df = pd.DataFrame(analysis_rows).copy()
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)

    df["ma20"] = df["close"].rolling(20).mean()
    df["ma60"] = df["close"].rolling(60).mean()
    df["rsi14"] = _rsi(df["close"], 14)
    df["atr14"] = _atr(df, 14)
    df["ema12"] = _ema(df["close"], 12)
    df["ema26"] = _ema(df["close"], 26)
    df["macd"] = df["ema12"] - df["ema26"]
    df["signal"] = _ema(df["macd"], 9)
    df["hist"] = df["macd"] - df["signal"]

    last = df.iloc[-1]
    ts = str(analysis_rows[-1]["timestamp"])
    close = float(last["close"])
    ma20 = float(last["ma20"]) if pd.notna(last["ma20"]) else close
    has_ma60 = pd.notna(last["ma60"])
    ma60 = float(last["ma60"]) if has_ma60 else None
    rsi = float(last["rsi14"]) if pd.notna(last["rsi14"]) else 50.0
    atr = float(last["atr14"]) if pd.notna(last["atr14"]) and float(last["atr14"]) > 0 else max(close * 0.01, 1e-6)
    hist = float(last["hist"]) if pd.notna(last["hist"]) else 0.0

    # 判断状态
    if has_ma60:
        if close > ma20 > ma60: market_state = "uptrend"
        elif close < ma20 < ma60: market_state = "downtrend"
        elif abs(close - ma20) / max(abs(close), 1e-6) < 0.01: market_state = "range"
        else: market_state = "chaotic"
    else:
        if close > ma20: market_state = "uptrend"
        elif close < ma20: market_state = "downtrend"
        else: market_state = "range"

    action = "watch"
    playbook = "none"
    if market_state == "uptrend" and rsi >= 52 and hist >= -0.02 * max(abs(close), 1.0):
        action, playbook = "long", "trend-pullback"
    elif market_state == "downtrend" and rsi <= 48 and hist <= 0.02 * max(abs(close), 1.0):
        action, playbook = "short", "trend-pullback"

    checklist = {
        "htf_direction": "pass" if action != "watch" else "degraded",
        "position": "pass" if action != "watch" else "fail",
        "setup_match": "pass" if action != "watch" else "fail",
        "trigger": "pass" if action != "watch" else "fail",
        "risk_reward": "pass" if action != "watch" else "fail",
        "events": "pass",
        "counter_reason": "degraded" if action != "watch" else "pass",
    }

    if action == "long":
        entry = close
        stop = close - atr
        t1, t2 = close + 1.6 * atr, close + 3.0 * atr
        rr = (t1 - entry) / max(entry - stop, 1e-6)
        trigger_type, invalidation = "close_above", "跌破止损"
    elif action == "short":
        entry = close
        stop = close + atr
        t1, t2 = close - 1.6 * atr, close - 3.0 * atr
        rr = (entry - t1) / max(stop - entry, 1e-6)
        trigger_type, invalidation = "close_below", "升破止损"
    else:
        entry = stop = t1 = t2 = rr = trigger_type = invalidation = None

    sample = {
        "meta": {
            "schema_version": "backtest_sample_v1",
            "symbol": symbol, "interval": interval, "case_id": case_id,
            "analysis_time": ts, "lookback_bars": lookback_bars, "forward_bars": forward_bars,
        },
        "decision": {
            "action": action, "playbook": playbook, "checklist": checklist,
            "checklist_result": "pass_degraded" if action != "watch" else "fail",
            "position_size_pct": 50.0 if action != "watch" else 0.0,
        },
        "trade": {
            "entry_price": round(float(entry), 6) if entry is not None else None,
            "stop_loss": round(float(stop), 6) if stop is not None else None,
            "t1": round(float(t1), 6) if t1 is not None else None,
            "t2": round(float(t2), 6) if t2 is not None else None,
            "risk_reward": round(float(rr), 6) if rr is not None else None,
            "trigger_type": trigger_type,
            "invalidation": invalidation,
        },
        "verdict": {
            "bias": "bullish" if action == "long" else ("bearish" if action == "short" else "watch"),
            "confidence": "low" if action == "watch" else ("high" if abs(close-ma20)/max(close, 1e-6)>0.03 else "medium"),
            "signal_strength": "medium" if action != "watch" else "weak",
        },
        "structure": {"market_state": market_state},
    }
    context = {
        "close": close, "ma20": ma20, "ma60": ma60, "rsi14": rsi, "macd_hist": hist, "atr14": atr,
        "swing_high": float(df["high"].tail(20).max()) if len(df) else close,
        "swing_low": float(df["low"].tail(20).min()) if len(df) else close,
        "recent_open": float(df.iloc[-1]["open"]) if len(df) else close,
        "recent_high": float(df.iloc[-1]["high"]) if len(df) else close,
        "recent_low": float(df.iloc[-1]["low"]) if len(df) else close,
        "recent_close": float(df.iloc[-1]["close"]) if len(df) else close,
    }
    return sample, context
