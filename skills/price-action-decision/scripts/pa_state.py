#!/usr/bin/env python3
"""Price Action 战法生命周期校验与差量生成。"""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any


ALLOWED_TRANSITIONS = {
    "none": {"candidate"},
    "candidate": {"armed", "invalidated", "none"},
    "armed": {"triggered", "invalidated", "candidate"},
    "triggered": {"managing", "invalidated", "closed"},
    "managing": {"invalidated", "closed"},
    "invalidated": {"none", "candidate"},
    "closed": {"none", "candidate"},
}

VALID_TRADE_STYLES = {"scalp", "swing", "mixed", "no_trade"}
VALID_ORDER_TYPES = {"market", "close", "stop", "limit", "wait"}

MATERIAL_PATHS = (
    ("market_context", "primary_state"),
    ("market_context", "alternate_state"),
    ("market_context", "switch_condition"),
    ("market_context", "always_in"),
    ("market_context", "location"),
    ("market_context", "transition"),
    ("market_context", "confidence"),
    ("setup", "type"),
    ("setup", "status"),
    ("setup", "trade_style"),
    ("setup", "order_type"),
    ("setup", "trigger"),
    ("setup", "initial_risk"),
    ("setup", "logical_stop"),
    ("setup", "logical_risk"),
    ("setup", "target_space"),
    ("setup", "targets"),
    ("setup", "invalidation"),
    ("position", "premise_status"),
    ("data_quality_warning",),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def get_path(payload: dict[str, Any], path: tuple[str, ...]) -> Any:
    value: Any = payload
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def validate_state(state: dict[str, Any]) -> None:
    """校验新增的交易方式字段；缺失字段保持向后兼容。"""
    setup = state.get("setup", {})
    trade_style = setup.get("trade_style")
    order_type = setup.get("order_type")
    if trade_style is not None and trade_style not in VALID_TRADE_STYLES:
        raise ValueError(f"非法持仓方式: {trade_style}")
    if order_type is not None and order_type not in VALID_ORDER_TYPES:
        raise ValueError(f"非法订单方式: {order_type}")


def transition_setup(
    state: dict[str, Any], target: str, event_time: str, reason: str
) -> dict[str, Any]:
    """执行合法的战法生命周期转换。"""
    validate_state(state)
    current = state.get("setup", {}).get("status", "none")
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        raise ValueError(f"非法战法状态转换: {current} -> {target}")
    updated = deepcopy(state)
    updated.setdefault("setup", {})["status"] = target
    updated["setup"]["last_transition_time"] = event_time
    updated["setup"]["last_transition_reason"] = reason
    updated["version"] = int(updated.get("version", 0)) + 1
    return updated


def material_delta(
    previous: dict[str, Any], current: dict[str, Any]
) -> dict[str, Any]:
    """只返回需要向用户报告的实质变化。"""
    validate_state(previous)
    validate_state(current)
    changes = []
    for path in MATERIAL_PATHS:
        before = get_path(previous, path)
        after = get_path(current, path)
        if before != after:
            changes.append({"field": ".".join(path), "before": before, "after": after})
    return {
        "material_change": bool(changes),
        "changes": changes,
        "last_complete_bar_time": current.get("last_complete_bar_time"),
    }


def event_id(state: dict[str, Any]) -> str:
    """为可推送状态生成稳定事件标识，避免重复通知。"""
    validate_state(state)
    material = {
        "symbol": state.get("symbol"),
        "values": {".".join(path): get_path(state, path) for path in MATERIAL_PATHS},
        "last_transition_time": state.get("setup", {}).get("last_transition_time"),
    }
    encoded = json.dumps(material, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:20]


def should_emit(state: dict[str, Any]) -> bool:
    """只有当前事件尚未推送时才返回真。"""
    return event_id(state) != state.get("last_emitted_event_id")


def mark_emitted(state: dict[str, Any]) -> dict[str, Any]:
    """记录当前事件已经推送。"""
    updated = deepcopy(state)
    updated["last_emitted_event_id"] = event_id(state)
    return updated


def read_json(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    delta = subparsers.add_parser("delta")
    delta.add_argument("--previous", required=True)
    delta.add_argument("--current", required=True)

    transition = subparsers.add_parser("transition")
    transition.add_argument("--state", required=True)
    transition.add_argument("--target", required=True, choices=ALLOWED_TRANSITIONS)
    transition.add_argument("--event-time", default=None)
    transition.add_argument("--reason", required=True)

    mark = subparsers.add_parser("mark-emitted")
    mark.add_argument("--state", required=True)

    args = parser.parse_args()
    if args.command == "delta":
        result = material_delta(read_json(args.previous), read_json(args.current))
    elif args.command == "transition":
        result = transition_setup(
            read_json(args.state), args.target, args.event_time or utc_now(), args.reason
        )
        result["event_id"] = event_id(result)
    else:
        result = mark_emitted(read_json(args.state))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
