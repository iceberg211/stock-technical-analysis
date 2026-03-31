# src/pipeline/notifier.py
"""通知发送器 — 支持 stdout / 飞书 / Telegram。"""
from __future__ import annotations
from typing import Any, Protocol
import json


class Notifier(Protocol):
    def send(self, message: str) -> dict[str, Any]: ...


class StdoutNotifier:
    """开发调试用 — 输出到控制台。"""
    def send(self, message: str) -> dict[str, Any]:
        print(f"[NOTIFY] {message}")
        return {"sent": True, "channel": "stdout"}


class FeishuNotifier:
    """飞书机器人通知 — 通过 webhook 发送。"""
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send(self, message: str) -> dict[str, Any]:
        import urllib.request
        payload = json.dumps({"msg_type": "text", "content": {"text": message}}).encode()
        req = urllib.request.Request(self.webhook_url, data=payload, headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=10)
            return {"sent": True, "channel": "feishu"}
        except Exception as e:
            return {"sent": False, "channel": "feishu", "error": str(e)}


_DECISION_LABEL = {"long": "做多", "short": "做空", "watch": "观望"}


def format_notification(event: str, signal: dict[str, Any], current_price: float | None = None) -> str:
    sym = signal.get("symbol", "?")
    decision = _DECISION_LABEL.get(signal.get("decision", ""), signal.get("decision", "?"))
    entry = signal.get("conditional_entry", "?")
    sl = signal.get("stop_loss", "?")
    t1 = signal.get("t1", "?")
    ts = (signal.get("timestamp_utc") or "?")[:16]

    if event == "entry_triggered":
        return f"📍 {sym} 条件单触发\n方向: {decision} | 入场: {entry}\n止损: {sl} | 目标: {t1}\n信号时间: {ts}\n当前价: {current_price}"
    elif event == "sl_warning":
        return f"⚠️ {sym} 接近止损\n止损位: {sl} | 当前价: {current_price}\n方向: {decision} | 信号时间: {ts}"
    elif event == "t1_reached":
        return f"🎯 {sym} 到达目标 1\nT1: {t1} | 当前价: {current_price}\n方向: {decision} | 可考虑部分止盈"
    else:
        return f"📊 {sym} {event}\n{decision} | {entry} → {t1}"
