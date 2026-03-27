"""Backtest sample validation and case generation utilities."""

from __future__ import annotations

import json
import re
import sys
from typing import Any

import pandas as pd


# ── JSON 提取 ─────────────────────────────────────────

_JSON_BLOCK_RE = re.compile(r"```json\s*\n(.*?)\n\s*```", re.DOTALL)

_ALLOWED_DATA_SOURCE = {"screenshot", "ohlc", "mixed"}
_ALLOWED_ACTION = {"long", "short", "watch"}
_ALLOWED_PLAYBOOK = {
    "trend-pullback",
    "breakout-retest",
    "range-reversal",
    "false-breakout-reversal",
    "flag-wedge-breakout",
    "none",
}
_ALLOWED_CHECKLIST_RESULT = {"pass", "pass_degraded", "fail"}
_ALLOWED_CHECKLIST = {
    "htf_direction": {"pass", "fail", "degraded"},
    "position": {"pass", "fail", "degraded"},
    "setup_match": {"pass", "fail"},
    "trigger": {"pass", "fail"},
    "risk_reward": {"pass", "fail"},
    "events": {"pass", "fail", "degraded"},
    "counter_reason": {"pass", "fail", "degraded"},
}
_ALLOWED_TRIGGER_TYPE = {"price_touch", "close_above", "close_below", None}

CASE_MODE_CHOICES = ("rolling", "non_overlap")


def extract_json(text: str) -> dict | None:
    """从 LLM 响应文本中提取 JSON 块并解析。"""
    m = _JSON_BLOCK_RE.search(text)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def _unwrap_backtest_payload(parsed: dict) -> dict:
    """
    兼容两种输出：
    1) 顶层直接是 backtest_sample_v1
    2) {"backtest_sample_v1": {...}} 包裹
    """
    if (
        isinstance(parsed, dict)
        and "backtest_sample_v1" in parsed
        and isinstance(parsed["backtest_sample_v1"], dict)
    ):
        return parsed["backtest_sample_v1"]
    return parsed


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def validate_backtest_sample(parsed: dict, case_id: str) -> tuple[bool, str | None, dict | None]:
    """校验 backtest_sample_v1 是否合规。"""
    if not isinstance(parsed, dict):
        return False, "parsed_json 不是对象", None

    payload = _unwrap_backtest_payload(parsed)
    if not isinstance(payload, dict):
        return False, "backtest payload 不是对象", None

    # 必要顶层
    for key in ("meta", "decision", "trade"):
        if key not in payload or not isinstance(payload[key], dict):
            return False, f"缺少或非法顶层字段: {key}", None

    meta = payload["meta"]
    decision = payload["decision"]
    trade = payload["trade"]

    required_meta = {
        "schema_version", "symbol", "interval", "case_id",
        "analysis_time", "lookback_bars", "forward_bars", "data_source",
    }
    miss_meta = required_meta - set(meta.keys())
    if miss_meta:
        return False, f"meta 缺少字段: {sorted(miss_meta)}", None

    if meta["schema_version"] != "backtest_sample_v1":
        return False, f"schema_version 非法: {meta['schema_version']}", None
    if not isinstance(meta["symbol"], str) or not meta["symbol"]:
        return False, "meta.symbol 非法", None
    if not isinstance(meta["interval"], str) or not meta["interval"]:
        return False, "meta.interval 非法", None
    if not isinstance(meta["case_id"], str) or not meta["case_id"]:
        return False, "meta.case_id 非法", None
    if meta["case_id"] != case_id:
        return False, f"meta.case_id 与输入不一致: {meta['case_id']} != {case_id}", None
    if not isinstance(meta["analysis_time"], str) or not meta["analysis_time"]:
        return False, "meta.analysis_time 非法", None
    if not isinstance(meta["lookback_bars"], int) or meta["lookback_bars"] <= 0:
        return False, "meta.lookback_bars 非法", None
    if not isinstance(meta["forward_bars"], int) or meta["forward_bars"] <= 0:
        return False, "meta.forward_bars 非法", None
    if meta["data_source"] not in _ALLOWED_DATA_SOURCE:
        return False, f"meta.data_source 非法: {meta['data_source']}", None

    required_decision = {"action", "playbook", "checklist", "checklist_result", "position_size_pct"}
    miss_decision = required_decision - set(decision.keys())
    if miss_decision:
        return False, f"decision 缺少字段: {sorted(miss_decision)}", None

    action = decision["action"]
    if action not in _ALLOWED_ACTION:
        return False, f"decision.action 非法: {action}", None
    if decision["playbook"] not in _ALLOWED_PLAYBOOK:
        return False, f"decision.playbook 非法: {decision['playbook']}", None
    if decision["checklist_result"] not in _ALLOWED_CHECKLIST_RESULT:
        return False, f"decision.checklist_result 非法: {decision['checklist_result']}", None
    if not _is_number(decision["position_size_pct"]):
        return False, "decision.position_size_pct 必须为数字", None

    checklist = decision["checklist"]
    if not isinstance(checklist, dict):
        return False, "decision.checklist 必须为对象", None
    for k, allowed in _ALLOWED_CHECKLIST.items():
        if k not in checklist:
            return False, f"decision.checklist 缺少字段: {k}", None
        if checklist[k] not in allowed:
            return False, f"decision.checklist.{k} 非法: {checklist[k]}", None

    required_trade = {
        "entry_price", "stop_loss", "t1", "t2",
        "risk_reward", "trigger_type", "invalidation",
    }
    miss_trade = required_trade - set(trade.keys())
    if miss_trade:
        return False, f"trade 缺少字段: {sorted(miss_trade)}", None

    if trade["trigger_type"] not in _ALLOWED_TRIGGER_TYPE:
        return False, f"trade.trigger_type 非法: {trade['trigger_type']}", None
    if trade["invalidation"] is not None and not isinstance(trade["invalidation"], str):
        return False, "trade.invalidation 必须是 string 或 null", None

    # 动作与交易字段一致性
    numeric_trade_fields = ("entry_price", "stop_loss", "t1", "t2", "risk_reward")
    if action == "watch":
        for f in numeric_trade_fields:
            if trade[f] is not None:
                return False, f"watch 模式下 trade.{f} 必须为 null", None
    else:
        for f in ("entry_price", "stop_loss", "t1"):
            if not _is_number(trade[f]):
                return False, f"{action} 模式下 trade.{f} 必须为数字", None
        for f in ("t2", "risk_reward"):
            if trade[f] is not None and not _is_number(trade[f]):
                return False, f"trade.{f} 必须是数字或 null", None

    return True, None, payload


# ── 滑动窗口切片 ──────────────────────────────────────

def make_cases(
    df: pd.DataFrame,
    lookback: int,
    forward: int,
    sample: int,
    step: int,
    case_mode: str = "non_overlap",
    warmup_bars: int = 120,
) -> list[dict]:
    """
    按滑动窗口从 DataFrame 中切出 case 列表。

    每个 case 包含:
        - case_id: 唯一标识
        - analysis_start: int  (分析窗口起始行号, 用于事后重建)
        - analysis_rows: list[dict]  (OHLCV, 发给 LLM)
    """
    total = len(df)
    min_required = lookback + forward
    if total < min_required:
        print(
            f"⚠️  数据不足: 需要至少 {min_required} 根 K 线, 实际 {total}",
            file=sys.stderr,
        )
        return []

    cases = []
    max_start = total - min_required
    start_from = max(0, int(warmup_bars))
    if start_from > max_start:
        print(
            f"⚠️  数据不足: warmup={start_from}, 可用最大起点={max_start}",
            file=sys.stderr,
        )
        return []

    if case_mode not in CASE_MODE_CHOICES:
        raise ValueError(f"不支持的 case_mode: {case_mode}")
    if case_mode == "rolling":
        stride = max(1, int(step))
    else:
        stride = max(1, int(lookback + forward))

    starts = list(range(start_from, max_start + 1, stride))
    if sample > 0:
        starts = starts[:sample]

    for i, start in enumerate(starts):
        end_analysis = start + lookback

        analysis_df = df.iloc[start:end_analysis]

        last_ts = str(analysis_df.iloc[-1]["timestamp"])
        case_id = f"case_{i:04d}_{last_ts.replace(':', '').replace('-', '').replace(' ', 'T')[:15]}"

        cases.append({
            "case_id": case_id,
            "analysis_start": start,
            "analysis_rows": analysis_df.to_dict("records"),
        })

    return cases
