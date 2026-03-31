"""
signal_writer.py — 信号归档工具

将分析结果写入 outputs/signals/{symbol}/{signal_id}/ 并更新 index.jsonl。
signal_id 自动从 time_utc 派生（格式：YYYYMMDD_HHMMSS）。

典型用法（从分析脚本调用）:
    from src.pipeline.signal_writer import write_signal

    write_signal(
        symbol="BTCUSDT",
        snapshot={
            "time_utc": "2026-03-31T09:00:00Z",
            "price_now": 66504.0,
            "decision": "short",
            "bias": "bearish",
            "confidence": "high",
            "playbook": "trend-pullback",
            "4h": {...},
            "1h": {...},
            "trade": {"entry_price": 66500, "stop_loss": 67100, "t1": 65000, "t2": 63000},
        },
    )
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SIGNALS_ROOT = REPO_ROOT / "outputs" / "signals"

# Required top-level fields in snapshot for a valid signal
_REQUIRED = ("time_utc", "price_now", "decision", "bias", "confidence")


def _signal_id_from_ts(time_utc: str) -> str:
    """Convert ISO timestamp to signal_id (YYYYMMDD_HHMMSS)."""
    try:
        dt = datetime.fromisoformat(time_utc.replace("Z", "+00:00"))
        return dt.strftime("%Y%m%d_%H%M%S")
    except Exception:
        return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _render_report(symbol: str, snapshot: dict[str, Any]) -> str:
    """Generate a minimal markdown report from snapshot fields."""
    price = snapshot.get("price_now", "-")
    decision = snapshot.get("decision", "-")
    bias = snapshot.get("bias", "-")
    confidence = snapshot.get("confidence", "-")
    playbook = snapshot.get("playbook", "-")
    time_utc = snapshot.get("time_utc", "-")
    trade = snapshot.get("trade") or {}

    h4 = snapshot.get("4h") or {}
    h1 = snapshot.get("1h") or {}

    verdict = snapshot.get("verdict") or {}
    signal_strength = verdict.get("signal_strength", "-")
    mtf = verdict.get("mtf_alignment", "-")

    structure = snapshot.get("structure") or {}
    market_state = structure.get("market_state") or h4.get("state", "-")
    notes = structure.get("notes", "")

    levels = snapshot.get("levels") or {}
    resistances = levels.get("resistances") or h4.get("resistance_top3") or []
    supports = levels.get("supports") or h4.get("support_top3") or []
    position = levels.get("position", "-")

    checklist = snapshot.get("checklist") or {}
    checklist_result = snapshot.get("checklist_result", "-")

    counter_reasons = snapshot.get("counter_reasons") or []

    lines = [
        f"# {symbol} 分析报告（{time_utc}）",
        "",
        "## 基础信息",
        f"- 品种: {symbol}",
        f"- 数据来源: Binance API OHLCV",
        f"- 当前价格: {price}",
        "",
        "## 市场结构",
        f"- 市场状态: **{market_state}**",
    ]
    if notes:
        lines.append(f"- 备注: {notes}")

    if resistances or supports:
        lines += [
            "",
            "## 关键价位",
            f"- 阻力: {', '.join(str(r) for r in resistances[:3])}",
            f"- 支撑: {', '.join(str(s) for s in supports[:3])}",
            f"- 当前位置: {position}",
        ]

    lines += [
        "",
        "## 综合研判",
        f"- 偏向: **{bias}**",
        f"- 信心: **{confidence}**",
        f"- 信号强度: {signal_strength}",
        f"- 多周期一致性: {mtf}",
        "",
        "---",
        "",
        "## 交易决策卡",
        "",
        "### 决策结论",
        f"- 方向: **{decision}**",
        f"- Playbook: {playbook}",
    ]

    if checklist:
        icon = {"pass": "✅", "fail": "❌", "degraded": "⚠️"}
        lines += ["", "### 入场前检查"]
        for k, v in checklist.items():
            lines.append(f"- {k}: {icon.get(str(v), str(v))}")
        lines.append(f"- **结论: {checklist_result}**")

    entry = trade.get("entry_price")
    sl = trade.get("stop_loss")
    t1 = trade.get("t1")
    t2 = trade.get("t2")
    rr = trade.get("risk_reward")
    invalidation = trade.get("invalidation")

    if any(v is not None for v in [entry, sl, t1]):
        lines += ["", "### 交易方案"]
        if entry is not None:
            lines.append(f"- 入场: {entry}")
        if sl is not None:
            lines.append(f"- 止损: {sl}")
        if t1 is not None:
            rr_str = f"（R:R ≈ {rr:.1f}:1）" if rr else ""
            lines.append(f"- 目标1: {t1} {rr_str}")
        if t2 is not None:
            lines.append(f"- 目标2: {t2}")
        if invalidation:
            lines.append(f"- 失效条件: {invalidation}")

    if counter_reasons:
        lines += ["", "### 风险提示"]
        for r in counter_reasons:
            lines.append(f"- {r}")

    lines += [
        "",
        "> 以上分析仅供学习和参考，不构成投资建议。"
        "交易有风险，请基于自身判断做出决策，并自行承担所有风险。",
    ]
    return "\n".join(lines)


def _build_index_entry(symbol: str, signal_id: str, snapshot: dict[str, Any]) -> dict[str, Any]:
    """Build a compact index.jsonl entry from snapshot."""
    trade = snapshot.get("trade") or {}
    plan_a = trade.get("plan_a") or {}
    verdict = snapshot.get("verdict") or {}

    entry_price = (
        trade.get("entry_price")
        or plan_a.get("entry_price")
        or snapshot.get("conditional_entry")
    )
    stop_loss = trade.get("stop_loss") or plan_a.get("stop_loss") or snapshot.get("stop_loss")
    t1 = trade.get("t1") or plan_a.get("t1") or snapshot.get("t1")
    t2 = trade.get("t2") or plan_a.get("t2") or snapshot.get("t2")

    h4 = snapshot.get("4h") or {}
    h1 = snapshot.get("1h") or {}

    return {
        "signal_id": signal_id,
        "symbol": symbol,
        "timestamp_utc": snapshot.get("time_utc"),
        "price_at_signal": snapshot.get("price_now"),
        "market_state_4h": h4.get("state"),
        "market_state_1h": h1.get("state"),
        "decision": snapshot.get("decision"),
        "bias": snapshot.get("bias") or verdict.get("bias"),
        "confidence": snapshot.get("confidence") or verdict.get("confidence"),
        "playbook": snapshot.get("playbook"),
        "conditional_entry": entry_price,
        "stop_loss": stop_loss,
        "t1": t1,
        "t2": t2,
        "path": f"{signal_id}/",
    }


def write_signal(
    symbol: str,
    snapshot: dict[str, Any],
    *,
    signal_id: str | None = None,
    overwrite: bool = False,
) -> str:
    """
    Write signal files and update index.jsonl.

    Returns the signal_id that was written.
    Raises ValueError if required snapshot fields are missing.
    """
    missing = [f for f in _REQUIRED if f not in snapshot]
    if missing:
        raise ValueError(f"snapshot 缺少必需字段: {missing}")

    sid = signal_id or _signal_id_from_ts(snapshot["time_utc"])
    sym_dir = SIGNALS_ROOT / symbol
    sig_dir = sym_dir / sid

    if sig_dir.exists() and not overwrite:
        raise FileExistsError(
            f"信号已存在: {sig_dir}。传入 overwrite=True 覆盖。"
        )

    sig_dir.mkdir(parents=True, exist_ok=True)

    # Write snapshot.json
    (sig_dir / "snapshot.json").write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Write report.md
    (sig_dir / "report.md").write_text(
        _render_report(symbol, snapshot), encoding="utf-8"
    )

    # Append to index.jsonl (skip if already present)
    index_path = sym_dir / "index.jsonl"
    existing_ids: set[str] = set()
    if index_path.exists():
        for line in index_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                existing_ids.add(json.loads(line).get("signal_id", ""))
            except Exception:
                pass

    if sid not in existing_ids:
        entry = _build_index_entry(symbol, sid, snapshot)
        with index_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return sid
