# src/scoring/signal_scorer.py
"""信号事后验证 — 用后续 K 线检查 entry/SL/T1/T2 是否触达。"""
from __future__ import annotations
from typing import Any


def score_signal(signal: dict[str, Any], forward_bars: list[dict[str, Any]]) -> dict[str, Any]:
    """
    对单个信号做事后验证。

    Args:
        signal: 信号字典，需包含 decision, conditional_entry/entry_price, stop_loss, t1, t2
        forward_bars: 信号发出后的 K 线列表（OHLCV dict, 需有 high/low/close）

    Returns:
        {outcome, entry_triggered, bars_to_entry, bars_to_outcome}
        outcome: "t1_hit" | "sl_hit" | "not_triggered" | "neither" | "no_levels"
    """
    decision = signal.get("decision", "watch")
    entry = _to_float(signal.get("conditional_entry") or signal.get("entry_price"))
    sl = _to_float(signal.get("stop_loss"))
    t1 = _to_float(signal.get("t1"))
    t2 = _to_float(signal.get("t2"))

    if entry is None or sl is None:
        return {"outcome": "no_levels", "entry_triggered": False}

    # 判断方向：long 入场价 < 止损说明方向错了，用 entry vs sl 关系判断
    is_long = entry > sl if decision == "watch" else decision == "long"

    entry_triggered = False
    entry_bar = None

    for i, bar in enumerate(forward_bars):
        h, l = float(bar["high"]), float(bar["low"])

        if not entry_triggered:
            # 检查价格是否触达入场价
            if l <= entry <= h:
                entry_triggered = True
                entry_bar = i
                # 同一根 bar 也可能触达 SL 或 T1，继续检查
            else:
                continue

        # 入场后逐 bar 检查
        if is_long:
            if l <= sl:
                return _result("sl_hit", True, entry_bar, i)
            if t1 and h >= t1:
                return _result("t1_hit", True, entry_bar, i)
        else:
            if h >= sl:
                return _result("sl_hit", True, entry_bar, i)
            if t1 and l <= t1:
                return _result("t1_hit", True, entry_bar, i)

    if not entry_triggered:
        return {"outcome": "not_triggered", "entry_triggered": False}

    return _result("neither", True, entry_bar, len(forward_bars) - 1)


def _result(outcome: str, triggered: bool, entry_bar: int | None, outcome_bar: int | None) -> dict:
    return {
        "outcome": outcome,
        "entry_triggered": triggered,
        "bars_to_entry": entry_bar,
        "bars_to_outcome": outcome_bar - entry_bar if entry_bar is not None and outcome_bar is not None else None,
    }


def _to_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None
