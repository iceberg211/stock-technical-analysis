from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.pipeline.layout import REPO_ROOT
from src.pipeline.signals import append_signal


def _parse_utc(value: str | None) -> pd.Timestamp | None:
    if not value:
        return None
    ts = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(ts):
        return None
    return ts


def _extract_signal_meta(snapshot: dict[str, Any]) -> dict[str, Any]:
    decision = snapshot.get("decision")
    if isinstance(decision, dict):
        action = decision.get("action")
        playbook = decision.get("playbook")
        confidence = snapshot.get("confidence") or snapshot.get("verdict", {}).get("confidence")
        bias = snapshot.get("bias") or snapshot.get("verdict", {}).get("bias")
    else:
        action = snapshot.get("decision")
        playbook = snapshot.get("playbook")
        confidence = snapshot.get("confidence")
        bias = snapshot.get("bias")

    trade = snapshot.get("trade") if isinstance(snapshot.get("trade"), dict) else {}

    meta = {
        "decision": action,
        "bias": bias,
        "confidence": confidence,
        "playbook": playbook,
        "conditional_entry": snapshot.get("conditional_entry") or snapshot.get("entry_price") or trade.get("entry_price"),
        "stop_loss": snapshot.get("stop_loss") or trade.get("stop_loss"),
        "t1": snapshot.get("t1") or trade.get("t1"),
        "t2": snapshot.get("t2") or trade.get("t2"),
    }
    return meta


def load_signal_index(
    symbol: str,
    outputs_root: Path | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int = 0,
) -> list[dict[str, Any]]:
    """读取某 symbol 的信号索引并按时间过滤。"""
    outputs_root = outputs_root or (REPO_ROOT / "outputs")
    idx_file = outputs_root / "signals" / symbol.upper() / "index.jsonl"
    if not idx_file.exists():
        return []

    since_ts = _parse_utc(since)
    until_ts = _parse_utc(until)

    items: list[dict[str, Any]] = []
    with idx_file.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = _parse_utc(row.get("timestamp_utc"))
            if since_ts is not None and (ts is None or ts < since_ts):
                continue
            if until_ts is not None and (ts is None or ts > until_ts):
                continue
            items.append(row)

    def _sort_key(row: dict[str, Any]) -> tuple[str, str]:
        ts = str(row.get("timestamp_utc") or "")
        sid = str(row.get("signal_id") or "")
        return ts, sid

    items.sort(key=_sort_key)
    if limit and limit > 0:
        items = items[:limit]
    return items


def load_signal_snapshot(symbol: str, signal_entry: dict[str, Any], outputs_root: Path | None = None) -> dict[str, Any]:
    """按 index 条目加载 snapshot.json。"""
    outputs_root = outputs_root or (REPO_ROOT / "outputs")
    symbol_u = symbol.upper()
    rel_path = signal_entry.get("path") or ""
    rel_path = str(rel_path).strip("/")
    if rel_path:
        path = outputs_root / "signals" / symbol_u / rel_path / "snapshot.json"
    else:
        signal_id = str(signal_entry.get("signal_id") or "")
        path = outputs_root / "signals" / symbol_u / signal_id / "snapshot.json"

    if not path.exists():
        raise FileNotFoundError(f"信号快照不存在: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def import_legacy_signals(
    root: Path | None = None,
    symbol: str | None = None,
) -> dict[str, Any]:
    """从旧目录扫描 analysis_skill_snapshot.json 并导入 outputs/signals。"""
    root = root or REPO_ROOT
    symbol_filter = symbol.upper() if symbol else None

    old_roots = [
        root / "data" / "binance_kline",
        root / "data" / "mcp_kline",
        root / "data" / "opend_kline",
    ]

    imported = 0
    skipped = 0
    errors: list[str] = []
    details: list[dict[str, Any]] = []

    # 建立已有 fingerprint 索引，避免重复导入
    existing_fp: dict[str, set[str]] = {}
    signals_root = root / "outputs" / "signals"
    if signals_root.exists():
        for idx in signals_root.glob("*/index.jsonl"):
            sym = idx.parent.name.upper()
            fp_set = existing_fp.setdefault(sym, set())
            with idx.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except Exception:
                        continue
                    fp = row.get("fingerprint")
                    if isinstance(fp, str) and fp:
                        fp_set.add(fp)

    for base in old_roots:
        if not base.exists():
            continue
        for snap_path in base.glob("*/analysis_skill_snapshot.json"):
            sym = snap_path.parent.name.upper()
            if symbol_filter and sym != symbol_filter:
                continue

            report_path = snap_path.parent / "analysis_skill_report.md"
            try:
                snapshot = json.loads(snap_path.read_text(encoding="utf-8"))
            except Exception as e:
                errors.append(f"{snap_path}: {e}")
                continue

            fp = hashlib.sha1(
                json.dumps(snapshot, ensure_ascii=False, sort_keys=True).encode("utf-8")
            ).hexdigest()

            fp_set = existing_fp.setdefault(sym, set())
            if fp in fp_set:
                skipped += 1
                continue

            report_md = report_path.read_text(encoding="utf-8") if report_path.exists() else ""
            meta = _extract_signal_meta(snapshot)
            meta["fingerprint"] = fp

            try:
                result = append_signal(
                    symbol=sym,
                    snapshot=snapshot,
                    report_md=report_md,
                    signal_meta=meta,
                    outputs_root=root / "outputs",
                )
                imported += 1
                fp_set.add(fp)
                details.append(
                    {
                        "symbol": sym,
                        "signal_id": result["signal_id"],
                        "from": str(snap_path),
                    }
                )
            except Exception as e:
                errors.append(f"{snap_path}: {e}")

    return {
        "imported": imported,
        "skipped": skipped,
        "errors": errors,
        "details": details,
        "time_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
