#!/usr/bin/env python3
"""纯确定性技术指标、价格行为微结构特征与窗口压缩摘要计算。"""

from __future__ import annotations

from typing import Any


def _round_opt(value: float | None, digits: int = 4) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def calc_sma(values: list[float | None], period: int) -> list[float | None]:
    """计算简单移动平均线，支持前导 None。"""
    if period <= 0:
        raise ValueError("period 必须大于 0")
    out: list[float | None] = [None] * len(values)
    for i in range(period - 1, len(values)):
        window = values[i - period + 1 : i + 1]
        if any(v is None for v in window):
            continue
        out[i] = sum(float(v) for v in window if v is not None) / period
    return out


def calc_ema(values: list[float | None], period: int) -> list[float | None]:
    """计算指数移动平均线（首值取前 period 个非空样本均值）。"""
    if period <= 0:
        raise ValueError("period 必须大于 0")
    out: list[float | None] = [None] * len(values)
    first_valid = next((idx for idx, v in enumerate(values) if v is not None), None)
    if first_valid is None or first_valid + period > len(values):
        return out

    seed_slice = values[first_valid : first_valid + period]
    if any(v is None for v in seed_slice):
        return out

    ema_val = sum(float(v) for v in seed_slice if v is not None) / period
    start_idx = first_valid + period - 1
    out[start_idx] = ema_val

    k = 2.0 / (period + 1)
    for i in range(start_idx + 1, len(values)):
        val = values[i]
        if val is None:
            continue
        ema_val = float(val) * k + ema_val * (1.0 - k)
        out[i] = ema_val
    return out


def calc_rsi(closes: list[float], period: int = 14) -> list[float | None]:
    """计算 Wilder RSI(14)。"""
    n = len(closes)
    out: list[float | None] = [None] * n
    if n <= period:
        return out

    gains: list[float] = []
    losses: list[float] = []
    for i in range(1, period + 1):
        delta = closes[i] - closes[i - 1]
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    def _to_rsi(ag: float, al: float) -> float:
        if al == 0.0:
            return 100.0 if ag > 0 else 50.0
        rs = ag / al
        return 100.0 - (100.0 / (1.0 + rs))

    out[period] = _to_rsi(avg_gain, avg_loss)
    for i in range(period + 1, n):
        delta = closes[i] - closes[i - 1]
        gain = max(delta, 0.0)
        loss = max(-delta, 0.0)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        out[i] = _to_rsi(avg_gain, avg_loss)
    return out


def calc_macd(
    closes: list[float], fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """计算 MACD(12, 26, 9)，hist = dif - dea。"""
    n = len(closes)
    close_opt: list[float | None] = [float(c) for c in closes]
    ema_fast = calc_ema(close_opt, fast)
    ema_slow = calc_ema(close_opt, slow)

    dif: list[float | None] = [
        (ef - es) if (ef is not None and es is not None) else None
        for ef, es in zip(ema_fast, ema_slow)
    ]
    dea = calc_ema(dif, signal)
    hist: list[float | None] = [
        (d - s) if (d is not None and s is not None) else None
        for d, s in zip(dif, dea)
    ]
    return dif, dea, hist


def calc_atr(bars: list[dict[str, Any]], period: int = 14) -> list[float | None]:
    """计算 Wilder ATR(14)。"""
    n = len(bars)
    out: list[float | None] = [None] * n
    if n < period:
        return out

    trs: list[float] = []
    for i, bar in enumerate(bars):
        h = float(bar["high"])
        l = float(bar["low"])
        if i == 0:
            trs.append(h - l)
        else:
            prev_c = float(bars[i - 1]["close"])
            trs.append(max(h - l, abs(h - prev_c), abs(l - prev_c)))

    atr = sum(trs[:period]) / period
    out[period - 1] = atr
    for i in range(period, n):
        atr = (atr * (period - 1) + trs[i]) / period
        out[i] = atr
    return out


def extract_swings(
    bars: list[dict[str, Any]],
    rsi_vals: list[float | None],
    dif_vals: list[float | None],
    hist_vals: list[float | None],
    *,
    left: int = 3,
    right: int = 3,
    max_points: int = 6,
) -> dict[str, Any]:
    """提取分析窗口内主要 Swing 高低点及当时对应指标值（供结构与背离锚点识别）。"""
    n = len(bars)
    if n == 0:
        return {"highs": [], "lows": [], "window_extreme": None}

    swing_highs: list[dict[str, Any]] = []
    swing_lows: list[dict[str, Any]] = []

    for i in range(left, max(left, n - right)):
        hi = float(bars[i]["high"])
        lo = float(bars[i]["low"])

        is_sh = all(hi > float(bars[j]["high"]) for j in range(i - left, i)) and all(
            hi >= float(bars[j]["high"]) for j in range(i + 1, i + right + 1)
        )
        if is_sh:
            swing_highs.append(
                {
                    "index": i,
                    "local_time": bars[i].get("local_time") or bars[i]["timestamp"],
                    "price": _round_opt(hi, 4),
                    "rsi14": _round_opt(rsi_vals[i], 2),
                    "macd_dif": _round_opt(dif_vals[i], 4),
                    "macd_hist": _round_opt(hist_vals[i], 4),
                }
            )

        is_sl = all(lo < float(bars[j]["low"]) for j in range(i - left, i)) and all(
            lo <= float(bars[j]["low"]) for j in range(i + 1, i + right + 1)
        )
        if is_sl:
            swing_lows.append(
                {
                    "index": i,
                    "local_time": bars[i].get("local_time") or bars[i]["timestamp"],
                    "price": _round_opt(lo, 4),
                    "rsi14": _round_opt(rsi_vals[i], 2),
                    "macd_dif": _round_opt(dif_vals[i], 4),
                    "macd_hist": _round_opt(hist_vals[i], 4),
                }
            )

    max_idx = max(range(n), key=lambda k: float(bars[k]["high"]))
    min_idx = min(range(n), key=lambda k: float(bars[k]["low"]))

    return {
        "swing_highs": swing_highs[-max_points:],
        "swing_lows": swing_lows[-max_points:],
        "window_high": {
            "index": max_idx,
            "local_time": bars[max_idx].get("local_time") or bars[max_idx]["timestamp"],
            "price": _round_opt(float(bars[max_idx]["high"]), 4),
            "rsi14": _round_opt(rsi_vals[max_idx], 2),
            "macd_dif": _round_opt(dif_vals[max_idx], 4),
        },
        "window_low": {
            "index": min_idx,
            "local_time": bars[min_idx].get("local_time") or bars[min_idx]["timestamp"],
            "price": _round_opt(float(bars[min_idx]["low"]), 4),
            "rsi14": _round_opt(rsi_vals[min_idx], 2),
            "macd_dif": _round_opt(dif_vals[min_idx], 4),
        },
    }


def summarize_bar_microstructure(
    bar: dict[str, Any],
    prev_bar: dict[str, Any] | None,
    ema20: float | None,
    vma20: float | None,
    *,
    include_tech: bool = True,
) -> dict[str, Any]:
    """生成单根 K 线的紧凑微结构摘要。"""
    o = float(bar["open"])
    h = float(bar["high"])
    l = float(bar["low"])
    c = float(bar["close"])
    rng = h - l
    body = c - o

    if rng > 0:
        body_pct = round(abs(body) / rng, 2)
        upper_wick_pct = round((h - max(o, c)) / rng, 2)
        lower_wick_pct = round((min(o, c) - l) / rng, 2)
        close_pos = round((c - l) / rng, 2)
    else:
        body_pct = 0.0
        upper_wick_pct = 0.0
        lower_wick_pct = 0.0
        close_pos = 0.5

    direction = "bull" if body > 0 else ("bear" if body < 0 else "flat")
    is_doji = body_pct <= 0.15

    entry: dict[str, Any] = {
        "local_time": bar.get("local_time") or bar["timestamp"],
        "o": round(o, 4),
        "h": round(h, 4),
        "l": round(l, 4),
        "c": round(c, 4),
        "dir": direction,
        "doji": is_doji,
        "body_pct": body_pct,
        "u_wick": upper_wick_pct,
        "l_wick": lower_wick_pct,
        "close_pos": close_pos,
    }
    if bar.get("volume") is not None:
        entry["v"] = round(float(bar["volume"]), 2)
        if include_tech and vma20 and vma20 > 0:
            entry["vol_ratio"] = round(float(bar["volume"]) / vma20, 2)

    if prev_bar is not None:
        ph = float(prev_bar["high"])
        pl = float(prev_bar["low"])
        if h <= ph and l >= pl:
            entry["pattern"] = "IB"
        elif h >= ph and l <= pl and (h > ph or l < pl):
            entry["pattern"] = "OB"
        if l > ph:
            entry["gap"] = f"+{round(l - ph, 4)}"
        elif h < pl:
            entry["gap"] = f"-{round(pl - h, 4)}"

    if ema20 is not None:
        entry["ema20"] = round(ema20, 4)

    return entry


def compress_history_segments(
    bars: list[dict[str, Any]], segment_count: int = 4
) -> list[dict[str, Any]]:
    """将细节窗口之前的历史 K 线按时间等分压缩为宏观波段摘要。"""
    n = len(bars)
    if n == 0:
        return []
    count = min(segment_count, n)
    chunk_size = max(1, (n + count - 1) // count)
    segments: list[dict[str, Any]] = []
    for start in range(0, n, chunk_size):
        chunk = bars[start : start + chunk_size]
        o = float(chunk[0]["open"])
        c = float(chunk[-1]["close"])
        hi = max(float(b["high"]) for b in chunk)
        lo = min(float(b["low"]) for b in chunk)
        bull_count = sum(1 for b in chunk if float(b["close"]) > float(b["open"]))
        bear_count = sum(1 for b in chunk if float(b["close"]) < float(b["open"]))
        net_pct = round(((c - o) / o) * 100, 2) if o > 0 else 0.0
        segments.append(
            {
                "coverage": f"{chunk[0].get('local_time') or chunk[0]['timestamp']} ~ {chunk[-1].get('local_time') or chunk[-1]['timestamp']}",
                "bars": len(chunk),
                "open": round(o, 4),
                "high": round(hi, 4),
                "low": round(lo, 4),
                "close": round(c, 4),
                "bull_bars": bull_count,
                "bear_bars": bear_count,
                "net_pct": net_pct,
            }
        )
    return segments


def build_timeframe_package(
    complete_bars: list[dict[str, Any]],
    forming_bars: list[dict[str, Any]],
    *,
    analysis_limit: int,
    detail_limit: int,
    min_bars: int,
    mode: str = "full",
    include_bars: bool = False,
) -> dict[str, Any]:
    """基于全量预热计算所有指标，并裁剪为受控上下文窗口交付分析层。"""
    n = len(complete_bars)
    if n == 0:
        return {
            "timeframe_status": "unavailable",
            "fetched_bars": 0,
            "analysis_bars_count": 0,
            "forming_bars": forming_bars,
        }

    closes = [float(b["close"]) for b in complete_bars]
    close_opt: list[float | None] = [float(c) for c in closes]
    volumes: list[float | None] = [
        float(b["volume"]) if b.get("volume") is not None else None
        for b in complete_bars
    ]

    ema20_all = calc_ema(close_opt, 20)
    ma20_all = calc_sma(close_opt, 20)
    ma50_all = calc_sma(close_opt, 50)
    vma20_all = calc_sma(volumes, 20)
    rsi14_all = calc_rsi(closes, 14)
    dif_all, dea_all, hist_all = calc_macd(closes, 12, 26, 9)
    atr14_all = calc_atr(complete_bars, 14)

    # 裁剪至分析窗口
    slice_start = max(0, n - analysis_limit)
    win_bars = complete_bars[slice_start:]
    win_ema20 = ema20_all[slice_start:]
    win_ma20 = ma20_all[slice_start:]
    win_ma50 = ma50_all[slice_start:]
    win_vma20 = vma20_all[slice_start:]
    win_rsi14 = rsi14_all[slice_start:]
    win_dif = dif_all[slice_start:]
    win_dea = dea_all[slice_start:]
    win_hist = hist_all[slice_start:]
    win_atr14 = atr14_all[slice_start:]

    wn = len(win_bars)
    w_high = max(float(b["high"]) for b in win_bars)
    w_low = min(float(b["low"]) for b in win_bars)
    last_bar = win_bars[-1]
    last_close = float(last_bar["close"])
    range_pos_pct = (
        round(((last_close - w_low) / (w_high - w_low)) * 100, 1)
        if w_high > w_low
        else 50.0
    )

    detail_start = max(0, wn - detail_limit)
    detail_bars = [
        summarize_bar_microstructure(
            win_bars[i],
            win_bars[i - 1] if i > 0 else None,
            win_ema20[i],
            win_vma20[i],
            include_tech=(mode in {"full", "tech"}),
        )
        for i in range(detail_start, wn)
    ]
    prior_segments = compress_history_segments(win_bars[:detail_start], segment_count=4)

    # 统计近期连续同侧与 EMA20 状态
    last_ema20 = win_ema20[-1]
    ema20_prev5 = win_ema20[-6] if wn >= 6 else None
    ema20_slope = None
    if last_ema20 is not None and ema20_prev5 is not None:
        diff = last_ema20 - ema20_prev5
        ema20_slope = "up" if diff > 0 else ("down" if diff < 0 else "flat")

    streak_above_ema20 = 0
    for i in range(wn - 1, -1, -1):
        e = win_ema20[i]
        if e is None:
            break
        c_val = float(win_bars[i]["close"])
        if i == wn - 1:
            side = c_val >= e
        elif (c_val >= e) != side:
            break
        streak_above_ema20 += 1

    # 量能评级
    last_vol = volumes[-1]
    last_vma20 = win_vma20[-1]
    vol_ratio = (
        round(last_vol / last_vma20, 2)
        if (last_vol is not None and last_vma20 is not None and last_vma20 > 0)
        else None
    )
    vol_grade = None
    if vol_ratio is not None:
        vol_grade = (
            "放量(>=1.5x)"
            if vol_ratio >= 1.5
            else ("缩量(<=0.7x)" if vol_ratio <= 0.7 else "常态")
        )

    indicators: dict[str, Any] = {
        "ema20": _round_opt(last_ema20, 4),
        "ema20_slope_5bar": ema20_slope,
        "close_vs_ema20_streak": (
            f"{'above' if (last_ema20 is not None and last_close >= last_ema20) else 'below'}:{streak_above_ema20}"
            if last_ema20 is not None
            else None
        ),
        "atr14": _round_opt(win_atr14[-1], 4),
    }

    if mode in {"full", "tech"}:
        indicators.update(
            {
                "ma20": _round_opt(win_ma20[-1], 4),
                "ma50": _round_opt(win_ma50[-1], 4),
                "vma20": _round_opt(last_vma20, 2),
                "vol_ratio_vma20": vol_ratio,
                "vol_grade": vol_grade,
                "rsi14": _round_opt(win_rsi14[-1], 2),
                "macd": {
                    "dif": _round_opt(win_dif[-1], 4),
                    "dea": _round_opt(win_dea[-1], 4),
                    "hist": _round_opt(win_hist[-1], 4),
                    "formula": "hist=dif-dea",
                },
            }
        )

    status = "complete" if wn >= min_bars else "degraded_recent_only"

    payload: dict[str, Any] = {
        "timeframe_status": status,
        "fetched_complete_bars": n,
        "analysis_bars_count": wn,
        "coverage_start": win_bars[0].get("local_time") or win_bars[0]["timestamp"],
        "coverage_end": last_bar.get("local_time") or last_bar["timestamp"],
        "last_complete_bar": {
            "local_time": last_bar.get("local_time") or last_bar["timestamp"],
            "timestamp": last_bar["timestamp"],
            "open": round(float(last_bar["open"]), 4),
            "high": round(float(last_bar["high"]), 4),
            "low": round(float(last_bar["low"]), 4),
            "close": round(last_close, 4),
            "volume": round(float(last_bar["volume"]), 2)
            if last_bar.get("volume") is not None
            else None,
        },
        "window_range": {
            "high": round(w_high, 4),
            "low": round(w_low, 4),
            "last_pos_pct": range_pos_pct,
        },
        "indicators": indicators,
        "prior_segments": prior_segments,
        "recent_detail_bars": detail_bars,
        "forming_bars": forming_bars,
    }

    if mode in {"full", "tech"}:
        payload["swings"] = extract_swings(
            win_bars, win_rsi14, win_dif, win_hist, left=3, right=3, max_points=6
        )

    if include_bars:
        payload["bars"] = win_bars

    return payload
