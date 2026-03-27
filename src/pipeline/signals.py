# src/pipeline/signals.py
"""
信号追加机制 — 每次分析后自动归档信号，绝不覆盖。

输出结构:
    outputs/signals/{SYMBOL}/{signal_id}/
        snapshot.json   — 模型输出的完整信号快照
        report.md       — 人可读分析报告
    outputs/signals/{SYMBOL}/index.jsonl — 所有信号的追加索引
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config import REPO_ROOT


def _generate_signal_id(timestamp_utc: str | None) -> str:
    """从 UTC 时间戳生成 signal_id，格式 YYYYMMDD_HHMMSS。"""
    if timestamp_utc:
        try:
            dt = datetime.fromisoformat(timestamp_utc.replace("Z", "+00:00"))
            return dt.strftime("%Y%m%d_%H%M%S")
        except Exception:
            pass
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _unique_signal_dir(signals_dir: Path, signal_id: str) -> Path:
    """确保 signal 目录唯一 — 如果已存在，追加序号。"""
    candidate = signals_dir / signal_id
    if not candidate.exists():
        return candidate
    counter = 1
    while True:
        candidate = signals_dir / f"{signal_id}_{counter:03d}"
        if not candidate.exists():
            return candidate
        counter += 1


def append_signal(
    symbol: str,
    snapshot: dict[str, Any],
    report_md: str,
    signal_meta: dict[str, Any],
    outputs_root: Path | None = None,
) -> dict[str, Path]:
    """
    归档一次分析信号。

    Parameters
    ----------
    symbol : str
        标的代码，如 "BTCUSDT"
    snapshot : dict
        模型输出的完整信号快照 (analysis_skill_snapshot.json)
    report_md : str
        人可读分析报告文本
    signal_meta : dict
        交易决策元数据 (decision, bias, confidence, playbook, entry, stop, targets)
    outputs_root : Path
        输出根目录，默认 REPO_ROOT / "outputs"

    Returns
    -------
    dict with keys: signal_id, signal_dir, snapshot_path, report_path, index_path
    """
    outputs_root = outputs_root or (REPO_ROOT / "outputs")
    signals_dir = outputs_root / "signals" / symbol.upper()
    signals_dir.mkdir(parents=True, exist_ok=True)

    timestamp_utc = snapshot.get("time_utc")
    signal_id = _generate_signal_id(timestamp_utc)
    signal_dir = _unique_signal_dir(signals_dir, signal_id)
    signal_dir.mkdir(parents=True, exist_ok=True)

    # Write snapshot
    snapshot_path = signal_dir / "snapshot.json"
    snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

    # Write report
    report_path = signal_dir / "report.md"
    report_path.write_text(report_md, encoding="utf-8")

    # Build index entry
    index_entry = {
        "signal_id": signal_dir.name,  # Use actual dir name (may have suffix)
        "symbol": symbol.upper(),
        "timestamp_utc": timestamp_utc,
        "price_at_signal": snapshot.get("price_now"),
        "market_state_4h": snapshot.get("4h", {}).get("state"),
        "market_state_1h": snapshot.get("1h", {}).get("state"),
        **signal_meta,
        "path": signal_dir.name + "/",
    }

    # Append to index.jsonl (never overwrite)
    index_path = signals_dir / "index.jsonl"
    with index_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(index_entry, ensure_ascii=False) + "\n")

    return {
        "signal_id": signal_dir.name,
        "signal_dir": signal_dir,
        "snapshot_path": snapshot_path,
        "report_path": report_path,
        "index_path": index_path,
    }
