import pandas as pd
from typing import Any, Tuple

from src.indicators.calc import ema, rsi, atr, add_all_indicators
from src.pipeline.strategy import list_strategies, get_conditions, get_stop_loss_atr, get_targets


def _match_playbook(
    market_state: str,
    rsi_val: float,
    hist: float,
    close: float,
) -> tuple[str, str]:
    """
    遍历所有已注册策略，寻找第一个满足条件的 playbook。

    匹配逻辑：
    - 依次检查 long / short 两个方向的条件
    - 条件字段：market_state、rsi_min、rsi_max、macd_hist_min、macd_hist_max
    - macd_hist_min / macd_hist_max 为价格归一化阈值（乘以 max(abs(close), 1.0)）
    - 返回 (action, playbook_name)；若无匹配返回 ("watch", "none")
    """
    close_ref = max(abs(close), 1.0)
    for strategy_name in list_strategies():
        for direction in ("long", "short"):
            conds = get_conditions(strategy_name, direction)
            if not conds:
                continue
            # 检查 market_state
            if conds.get("market_state") and market_state != conds["market_state"]:
                continue
            # 检查 RSI 下界
            if "rsi_min" in conds and rsi_val < conds["rsi_min"]:
                continue
            # 检查 RSI 上界
            if "rsi_max" in conds and rsi_val > conds["rsi_max"]:
                continue
            # 检查 MACD hist 下界（归一化）
            if "macd_hist_min" in conds and hist < conds["macd_hist_min"] * close_ref:
                continue
            # 检查 MACD hist 上界（归一化）
            if "macd_hist_max" in conds and hist > conds["macd_hist_max"] * close_ref:
                continue
            # 所有条件满足
            return direction, strategy_name
    return "watch", "none"


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
    df["rsi14"] = rsi(df["close"], 14)
    df["atr14"] = atr(df, 14)
    df["ema12"] = ema(df["close"], 12)
    df["ema26"] = ema(df["close"], 26)
    df["macd"] = df["ema12"] - df["ema26"]
    df["signal"] = ema(df["macd"], 9)
    df["hist"] = df["macd"] - df["signal"]

    last = df.iloc[-1]
    ts = str(analysis_rows[-1]["timestamp"])
    close = float(last["close"])
    ma20 = float(last["ma20"]) if pd.notna(last["ma20"]) else close
    has_ma60 = pd.notna(last["ma60"])
    ma60 = float(last["ma60"]) if has_ma60 else None
    rsi_val = float(last["rsi14"]) if pd.notna(last["rsi14"]) else 50.0
    atr_val = float(last["atr14"]) if pd.notna(last["atr14"]) and float(last["atr14"]) > 0 else max(close * 0.01, 1e-6)
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

    # 使用策略配置匹配 playbook，替代原先硬编码的判断逻辑
    action, playbook = _match_playbook(market_state, rsi_val, hist, close)

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
        # 从策略配置读取 ATR 倍数
        sl_mult = get_stop_loss_atr(playbook) if playbook != "none" else 1.0
        t1_mult, t2_mult = get_targets(playbook) if playbook != "none" else (1.6, 3.0)
        entry = close
        stop = close - sl_mult * atr_val
        t1, t2 = close + t1_mult * atr_val, close + t2_mult * atr_val
        rr = (t1 - entry) / max(entry - stop, 1e-6)
        trigger_type, invalidation = "close_above", "跌破止损"
    elif action == "short":
        sl_mult = get_stop_loss_atr(playbook) if playbook != "none" else 1.0
        t1_mult, t2_mult = get_targets(playbook) if playbook != "none" else (1.6, 3.0)
        entry = close
        stop = close + sl_mult * atr_val
        t1, t2 = close - t1_mult * atr_val, close - t2_mult * atr_val
        rr = (entry - t1) / max(stop - entry, 1e-6)
        trigger_type, invalidation = "close_below", "升破止损"
    else:
        entry = stop = t1 = t2 = rr = trigger_type = invalidation = None

    sample = {
        "meta": {
            "schema_version": "backtest_sample_v1",
            "symbol": symbol, "interval": interval, "case_id": case_id,
            "analysis_time": ts, "lookback_bars": lookback_bars, "forward_bars": forward_bars,
            "data_source": "ohlc",
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
        "close": close, "ma20": ma20, "ma60": ma60, "rsi14": rsi_val, "macd_hist": hist, "atr14": atr_val,
        "swing_high": float(df["high"].tail(20).max()) if len(df) else close,
        "swing_low": float(df["low"].tail(20).min()) if len(df) else close,
        "recent_open": float(df.iloc[-1]["open"]) if len(df) else close,
        "recent_high": float(df.iloc[-1]["high"]) if len(df) else close,
        "recent_low": float(df.iloc[-1]["low"]) if len(df) else close,
        "recent_close": float(df.iloc[-1]["close"]) if len(df) else close,
    }
    return sample, context
