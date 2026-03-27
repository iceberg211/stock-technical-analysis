from __future__ import annotations

import json
from pathlib import Path
from typing import Any

def _format_num(value: Any, ndigits: int = 3) -> str:
    if value is None:
        return "null"
    return str(round(float(value), ndigits))

def build_analysis_report(sample: dict[str, Any], context: dict[str, Any]) -> str:
    """生成可读分析过程（Markdown），对应 workflows/output-templates.md 的完整模式。"""
    meta = sample["meta"]
    decision = sample["decision"]
    trade = sample["trade"]
    verdict = sample.get("verdict", {})
    structure = sample.get("structure", {})

    action_map = {"long": "做多", "short": "做空", "watch": "观望"}
    momentum = "犹豫不决"
    if context.get("recent_close", 0) > context.get("recent_open", 0):
        momentum = "多头主导"
    elif context.get("recent_close", 0) < context.get("recent_open", 0):
        momentum = "空头主导"

    return f"""#### 基础信息
- 品种: {meta['symbol']}
- 数据来源: 数据模式（OHLC）
- 图表数量: 无截图
- 分析模式: 数据模式
- 时间框架: 单一周期={meta['interval']}

#### 市场结构
- 市场状态: {structure.get('market_state', 'unknown')}
- 关键 BOS/CHoCH: 无明确 CHoCH，按均线与动量做结构判定
- 趋势健康度: {'健康' if decision['action'] != 'watch' else '可能反转'}

#### 关键价位
- 阻力: {_format_num(context.get('swing_high'))}
- 支撑: {_format_num(context.get('swing_low'))}
- 当前位置: {'中间' if decision['action'] == 'watch' else ('阻力附近' if decision['action'] == 'short' else '支撑附近')}

#### 价格行为
- 近期动量: {momentum}
- 关键K线: O={_format_num(context.get('recent_open'))}, H={_format_num(context.get('recent_high'))}, L={_format_num(context.get('recent_low'))}, C={_format_num(context.get('recent_close'))}

#### 形态识别
- K线形态: 无明显形态
- 图表形态: 无明显形态
- 信号强度: {verdict.get('signal_strength', 'weak')}

#### 指标信号（如可见）
- RSI: {_format_num(context.get('rsi14'), 2)}
- MACD: hist={_format_num(context.get('macd_hist'), 4)}

#### 综合研判
- 偏向: {verdict.get('bias', 'watch')}
- 信心: {verdict.get('confidence', 'low')}
- 多周期一致性: single_tf
- 核心逻辑: 纯数据模式的规则引擎过滤，优先判断均线状态，叠加 RSI 与 MACD。

---

交易决策卡

### 决策结论
- 方向: {action_map.get(decision['action'], decision['action'])}
- 理由: 市场状态={structure.get('market_state', 'unknown')}，Playbook={decision.get('playbook', 'none')}，清单结果={decision.get('checklist_result', 'fail')}。

### Setup & Checklist
- Playbook: {decision.get('playbook', 'none')}
- 入场前检查:
  硬否决项: position / setup_match / trigger / risk_reward
  软降级项: htf_direction / events / counter_reason
  结论: {'通过' if decision['action'] != 'watch' else '不做'}

### 交易方案
- 入场: {_format_num(trade.get('entry_price'), 6)}
- 止损: {_format_num(trade.get('stop_loss'), 6)}
- 目标1: {_format_num(trade.get('t1'), 6)}（R:R = {_format_num(trade.get('risk_reward'), 3)}:1）
- 目标2: {_format_num(trade.get('t2'), 6)}
- 仓位: {_format_num(decision.get('position_size_pct'), 2)}%
- 失效条件: {trade.get('invalidation') or 'null'}
- 持仓管理: 到达 T1 后可分批止盈并将止损上移到成本附近。

> 以上分析由回测数据引擎 mock 生成，不代表真实大模型分析结论。
"""


def score_summary(scored_path: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    if not scored_path.exists():
        return {"runs": 0}

    with scored_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    if not rows:
        return {"runs": 0}

    trade_rows = [r for r in rows if r.get("outcome") in ("t1_hit", "sl_hit", "neither")]
    t1 = sum(1 for r in trade_rows if r.get("outcome") == "t1_hit")
    t2 = sum(1 for r in trade_rows if bool(r.get("t2_hit")))
    sl = sum(1 for r in trade_rows if r.get("outcome") == "sl_hit")
    missed_entry = sum(1 for r in rows if r.get("outcome") == "missed_entry")
    watch = sum(1 for r in rows if r.get("action") == "watch" or r.get("outcome") == "no_trade")
    parse_error = sum(1 for r in rows if r.get("outcome") == "parse_error")
    win_rate = round((t1 / len(trade_rows) * 100), 2) if trade_rows else None

    return {
        "runs": len(rows),
        "trade_cases": len(trade_rows),
        "t1_hit": t1,
        "t2_hit": t2,
        "sl_hit": sl,
        "missed_entry": missed_entry,
        "watch_or_no_trade": watch,
        "parse_error": parse_error,
        "win_rate_pct": win_rate,
    }


def append_template_alignment_details(details_path: Path, artifact_index_file: Path | None, template_file: Path) -> None:
    """追加写入 details.md"""
    if not details_path.exists():
        return

    first_report, first_sample = None, None
    case_count = 0

    if artifact_index_file and artifact_index_file.exists():
        try:
            items = json.loads(artifact_index_file.read_text(encoding="utf-8"))
            if isinstance(items, list):
                case_count = len(items)
                if items:
                    first = items[0]
                    first_report = first.get("analysis_report")
                    first_sample = first.get("sample_json")
        except Exception:
            pass

    lines = [
        "", "## 与 output-templates.md 的对应关系", "",
        f"- 模板文件: `{template_file}`",
        f"- 本次 case 数（analysis artifacts）: {case_count}",
    ]
    if first_report:
        lines.append(f"- 样例可读分析: `{first_report}`")
    if first_sample:
         lines.append(f"- 样例结构化 JSON: `{first_sample}`")

    old = details_path.read_text(encoding="utf-8")
    if "## 与 output-templates.md 的对应关系" in old:
        return
    details_path.write_text(old.rstrip() + "\n" + "\n".join(lines) + "\n", encoding="utf-8")
