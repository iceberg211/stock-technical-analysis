# src/scoring/regression.py
"""Prompt 回归测试 — 对比新旧版本信号质量。"""
from __future__ import annotations
from typing import Any

REGRESSION_THRESHOLD = 0.05


def compare_versions(
    old_scored: list[dict[str, Any]],
    new_scored: list[dict[str, Any]],
) -> dict[str, Any]:
    old_wr = _win_rate(old_scored)
    new_wr = _win_rate(new_scored)
    diff = new_wr - old_wr

    if diff > REGRESSION_THRESHOLD:
        verdict = "improved"
    elif diff < -REGRESSION_THRESHOLD:
        verdict = "regressed"
    else:
        verdict = "no_change"

    return {
        "old_win_rate": old_wr,
        "new_win_rate": new_wr,
        "diff": round(diff, 4),
        "verdict": verdict,
    }


def _win_rate(scored: list[dict]) -> float:
    tradable = [s for s in scored if s.get("outcome") in ("t1_hit", "sl_hit", "neither")]
    if not tradable:
        return 0.0
    wins = [s for s in tradable if s["outcome"] == "t1_hit"]
    return len(wins) / len(tradable)
