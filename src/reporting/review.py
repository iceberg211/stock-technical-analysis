# src/reporting/review.py
"""复盘统计 — 按 decision/playbook/market_state 分组计算胜率。"""
from __future__ import annotations
from collections import defaultdict
from typing import Any


def compute_review(scored_signals: list[dict[str, Any]]) -> dict[str, Any]:
    if not scored_signals:
        return {"total": 0, "by_decision": {}, "by_playbook": {}, "by_market_state": {}}
    return {
        "total": len(scored_signals),
        "by_decision": _group_stats(scored_signals, "decision"),
        "by_playbook": _group_stats(scored_signals, "playbook"),
        "by_market_state": _group_stats(scored_signals, "market_state"),
    }


def _group_stats(items: list[dict], key: str) -> dict[str, dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        groups[item.get(key, "unknown")].append(item)

    result = {}
    for name, group in sorted(groups.items()):
        tradable = [g for g in group if g.get("decision") in ("long", "short")]
        wins = [g for g in tradable if g.get("outcome") == "t1_hit"]
        result[name] = {
            "total": len(group),
            "tradable": len(tradable),
            "wins": len(wins),
            "win_rate": len(wins) / len(tradable) if tradable else 0.0,
            "watch_count": len(group) - len(tradable),
        }
    return result
