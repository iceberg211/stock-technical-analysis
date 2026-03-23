"""
Prompt 组装器。

读取 Skill markdown 文件，拼接为 system prompt；
将 OHLCV 数据格式化为 user message。
"""

from __future__ import annotations

from eval.config import SKILL_FILES


def build_system_prompt() -> str:
    """拼接所有 Skill 文件为一份完整的 system prompt。"""
    parts: list[str] = []
    for path in SKILL_FILES:
        content = path.read_text(encoding="utf-8").strip()
        # 用文件名做分隔标记，方便调试
        parts.append(f"<!-- {path.name} -->\n{content}")
    return "\n\n---\n\n".join(parts)


def build_user_message(
    ohlcv_text: str,
    symbol: str,
    interval: str,
    case_id: str,
    lookback_bars: int,
    forward_bars: int,
) -> str:
    """
    构建 user message。

    Parameters
    ----------
    ohlcv_text : str
        已格式化的 OHLCV 数据文本（CSV 或表格）
    symbol : str
        标的代码，如 "BTCUSDT"
    interval : str
        K 线周期，如 "4h"
    """
    return (
        f"请对以下 {symbol} {interval} K 线数据进行技术分析并输出回测样本。--json\n\n"
        f"品种: {symbol}\n"
        f"周期: {interval}\n"
        f"case_id: {case_id}\n"
        f"lookback_bars: {lookback_bars}\n"
        f"forward_bars: {forward_bars}\n"
        f"数据格式: timestamp,open,high,low,close,volume\n\n"
        "输出要求（必须严格遵守）:\n"
        "1) 只输出一个 ```json 代码块，且仅包含 backtest_sample_v1 结构化 JSON。\n"
        "2) 不要输出额外解释文字，不要输出多个 JSON 代码块。\n"
        "3) 若 decision.action=watch，则 trade 数值字段必须为 null。\n"
        "4) 若 decision.action=long/short，则 trade.entry_price、trade.stop_loss、trade.t1 必须是数字。\n\n"
        f"```csv\n{ohlcv_text}\n```"
    )


def format_ohlcv_csv(rows: list[dict]) -> str:
    """
    将 OHLCV 行列表格式化为 CSV 文本。

    每行 dict 需包含: timestamp, open, high, low, close, volume
    """
    header = "timestamp,open,high,low,close,volume"
    lines = [header]
    for r in rows:
        lines.append(
            f"{r['timestamp']},{r['open']},{r['high']},"
            f"{r['low']},{r['close']},{r['volume']}"
        )
    return "\n".join(lines)
