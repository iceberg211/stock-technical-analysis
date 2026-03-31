# src/pipeline/price_monitor.py
"""价格监控 — 检查活跃信号的条件是否满足。"""
from __future__ import annotations
from typing import Any


def check_signals(
    signals: list[dict[str, Any]],
    current_prices: dict[str, float],
) -> list[dict[str, Any]]:
    """
    检查信号列表，返回触发的事件。

    Args:
        signals: 活跃信号列表
        current_prices: {symbol: price} 当前价格

    Returns:
        触发的事件列表 [{event, signal, current_price}]
    """
    events = []

    for sig in signals:
        symbol = sig.get("symbol", "")
        price = current_prices.get(symbol)
        if price is None:
            continue

        decision = sig.get("decision")
        entry = _to_float(sig.get("conditional_entry") or sig.get("entry_price"))
        sl = _to_float(sig.get("stop_loss"))
        t1 = _to_float(sig.get("t1"))
        status = sig.get("status", "pending")

        # 判断方向
        is_long = decision == "long" or (decision == "watch" and entry is not None and sl is not None and entry > sl)

        if status == "pending" and entry is not None:
            if is_long and price <= entry:
                events.append({"event": "entry_triggered", "signal": sig, "current_price": price})
            elif not is_long and price >= entry:
                events.append({"event": "entry_triggered", "signal": sig, "current_price": price})

        if status == "active" and sl is not None:
            distance_pct = abs(price - sl) / max(price, 1) * 100
            if distance_pct < 1.0:
                events.append({"event": "sl_warning", "signal": sig, "current_price": price})

        if status == "active" and t1 is not None:
            if is_long and price >= t1:
                events.append({"event": "t1_reached", "signal": sig, "current_price": price})
            elif not is_long and price <= t1:
                events.append({"event": "t1_reached", "signal": sig, "current_price": price})

    return events


def _to_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None
