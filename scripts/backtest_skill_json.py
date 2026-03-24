#!/usr/bin/env python3
"""
回测「技术分析 Skill 输出 JSON」的一键脚本。

流程：
1. 读取本地缓存的 K 线（默认 1H 清洗数据）
2. 转换为 eval 需要的 CSV 格式
3. 调用 eval.run_eval 生成模型 JSON 预测
4. 调用 eval.score_eval 进行事后评分
5. 调用 eval.report 输出统计报告
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import subprocess
import shutil
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_FILE = "kline_1h_clean.csv"

# 确保可导入仓库内 eval 包
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.run_eval import make_cases, validate_backtest_sample


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="回测 Skill JSON 输出（基于本地缓存数据）")
    parser.add_argument(
        "--symbols",
        nargs="+",
        required=True,
        help="标的列表，例如 SH.600410 SZ.300033 SH.601899",
    )
    parser.add_argument(
        "--interval",
        default="1h",
        help="回测主周期标记（仅用于传给 eval 提示词），默认 1h",
    )
    parser.add_argument("--repeat", type=int, default=1, help="每个 case 重复调用次数")
    parser.add_argument("--sample", type=int, default=20, help="每个标的采样 case 数")
    parser.add_argument("--step", type=int, default=10, help="滑窗步长")
    parser.add_argument("--lookback", type=int, default=160, help="分析窗口根数")
    parser.add_argument("--forward", type=int, default=40, help="事后评估窗口根数")
    parser.add_argument(
        "--cache-file",
        default=DEFAULT_CACHE_FILE,
        help=f"缓存文件名（默认 {DEFAULT_CACHE_FILE}）",
    )
    parser.add_argument(
        "--output-root",
        default=None,
        help="输出根目录（默认语义化目录：eval/results/skill_backtest__<symbols>__...）",
    )
    parser.add_argument(
        "--no-clean-output",
        action="store_true",
        help="不清理已有输出目录（默认会清理，避免 results 下重复目录/重复文件）",
    )
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="只做数据准备，不调用 LLM 运行回测",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="可选，覆盖 EVAL_MODEL（如 gpt-4o / gpt-4o-mini）",
    )
    parser.add_argument(
        "--engine",
        choices=["auto", "openai", "local"],
        default="auto",
        help="样本生成引擎：auto(有Key用openai，否则local)，openai，local",
    )
    parser.add_argument(
        "--hide-analysis",
        action="store_true",
        help="不在控制台打印每个 case 的分析过程（默认打印）",
    )
    return parser.parse_args()


def normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper()


def _slugify(text: str) -> str:
    s = re.sub(r"[^A-Za-z0-9._-]+", "-", text.strip())
    s = s.strip("-")
    return s.lower() or "na"


def build_semantic_run_name(
    symbols: list[str],
    interval: str,
    lookback: int = 0,
    forward: int = 0,
    sample: int = 0,
    step: int = 0,
    repeat: int = 1,
    engine: str = "",
) -> str:
    """生成可读的 run 目录名。格式: {symbol}_{interval}
    
    参数细节（lookback/forward等）保存在 config.json，不编入目录名。
    """
    symbol_tag = "+".join(s.replace(".", "_") for s in symbols)
    return f"{symbol_tag}_{interval}"


def convert_cached_csv_to_eval_csv(src: Path, dst: Path) -> dict[str, Any]:
    """
    将缓存 K 线 CSV 转换为 eval 所需字段：
    timestamp,open,high,low,close,volume
    """
    df = pd.read_csv(src)
    if "time" not in df.columns:
        raise ValueError(f"缺少 time 列: {src}")
    required = {"open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"缺少列 {missing}: {src}")

    out = df.copy()
    out["timestamp"] = pd.to_datetime(out["time"], errors="coerce")
    out = out.dropna(subset=["timestamp"])
    # 统一输出为 UTC 字符串格式；时间序列相对先后关系不受时区转换影响
    out["timestamp"] = out["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    out = out[["timestamp", "open", "high", "low", "close", "volume"]]
    out = out.sort_values("timestamp").reset_index(drop=True)

    dst.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(dst, index=False)
    return {
        "rows": int(len(out)),
        "start": out["timestamp"].iloc[0] if len(out) else None,
        "end": out["timestamp"].iloc[-1] if len(out) else None,
        "path": str(dst),
    }


def run_cmd(cmd: list[str], cwd: Path, env: dict[str, str]) -> None:
    subprocess.run(cmd, cwd=str(cwd), env=env, check=True)


def score_summary(scored_path: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    with scored_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    if not rows:
        return {"runs": 0}

    trade_rows = [r for r in rows if r.get("outcome") in ("t1_hit", "sl_hit", "neither")]
    t1 = sum(1 for r in trade_rows if r.get("outcome") == "t1_hit")
    sl = sum(1 for r in trade_rows if r.get("outcome") == "sl_hit")
    watch = sum(1 for r in rows if r.get("action") == "watch" or r.get("outcome") == "no_trade")
    parse_error = sum(1 for r in rows if r.get("outcome") == "parse_error")
    win_rate = round((t1 / len(trade_rows) * 100), 2) if trade_rows else None

    return {
        "runs": len(rows),
        "trade_cases": len(trade_rows),
        "t1_hit": t1,
        "sl_hit": sl,
        "watch_or_no_trade": watch,
        "parse_error": parse_error,
        "win_rate_pct": win_rate,
    }


def append_template_alignment_summary(
    symbol_out_dir: Path,
    artifact_index_file: Path | None,
    template_file: Path,
) -> None:
    """
    在 summary.md 追加“与 output-templates.md 的对应关系”说明，
    让结果文件可直接看出模板映射链路。
    """
    summary_path = symbol_out_dir / "summary.md"
    if not summary_path.exists():
        return

    first_report = None
    first_sample = None
    case_count = 0

    if artifact_index_file and artifact_index_file.exists():
        try:
            items = json.loads(artifact_index_file.read_text(encoding="utf-8"))
            if isinstance(items, list):
                case_count = len(items)
                if items:
                    first = items[0]
                    report_path = Path(str(first.get("analysis_report", "")))
                    sample_path = Path(str(first.get("sample_json", "")))
                    if report_path.exists():
                        first_report = report_path
                    if sample_path.exists():
                        first_sample = sample_path
        except Exception:
            pass

    section_lines = [
        "",
        "## 与 output-templates.md 的对应关系",
        "",
        f"- 模板文件: `{template_file}`",
        "- 可读分析模板: `标准输出模板（完整模式） + 交易决策卡 + 免责声明`",
        "- 机器回测模板: `历史回测样本 JSON（backtest_sample_v1）`",
        f"- 本次 case 数（analysis artifacts）: {case_count}",
    ]
    if first_report is not None:
        section_lines.append(f"- 样例可读分析: `{first_report}`")
    if first_sample is not None:
        section_lines.append(f"- 样例结构化 JSON: `{first_sample}`")
    section_lines.extend(
        [
            "- 映射关系: `analysis_report.md` 对应模板中的“基础信息/市场结构/关键价位/价格行为/形态识别/指标信号/综合研判/交易决策卡”。",
            "- 映射关系: `backtest_sample_v1.json` 对应模板中的“meta/decision/trade”等可评分字段，由 `runs.jsonl.parsed_json` 进入评分器。",
        ]
    )

    old = summary_path.read_text(encoding="utf-8")
    if "## 与 output-templates.md 的对应关系" in old:
        return
    summary_path.write_text(old.rstrip() + "\n" + "\n".join(section_lines) + "\n", encoding="utf-8")


def _ema(series: pd.Series, n: int) -> pd.Series:
    return series.ewm(span=n, adjust=False).mean()


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    ma_up = up.ewm(alpha=1 / period, adjust=False).mean()
    ma_down = down.ewm(alpha=1 / period, adjust=False).mean()
    rs = ma_up / ma_down.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / n, adjust=False).mean()


def _build_local_backtest_sample(
    analysis_rows: list[dict[str, Any]],
    symbol: str,
    interval: str,
    case_id: str,
    lookback_bars: int,
    forward_bars: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    本地“技术分析 skill”近似规则引擎（无 API key 时使用）：
    - 依据趋势/均线/RSI/ATR 生成 decision + trade
    - 输出 backtest_sample_v1 结构
    """
    df = pd.DataFrame(analysis_rows).copy()
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)

    df["ma20"] = df["close"].rolling(20).mean()
    df["ma60"] = df["close"].rolling(60).mean()
    df["rsi14"] = _rsi(df["close"], 14)
    df["atr14"] = _atr(df, 14)
    df["ema12"] = _ema(df["close"], 12)
    df["ema26"] = _ema(df["close"], 26)
    df["macd"] = df["ema12"] - df["ema26"]
    df["signal"] = _ema(df["macd"], 9)
    df["hist"] = df["macd"] - df["signal"]

    last = df.iloc[-1]
    ts = str(analysis_rows[-1]["timestamp"])
    close = float(last["close"])
    ma20 = float(last["ma20"]) if pd.notna(last["ma20"]) else close
    has_ma60 = pd.notna(last["ma60"])
    ma60 = float(last["ma60"]) if has_ma60 else None
    rsi = float(last["rsi14"]) if pd.notna(last["rsi14"]) else 50.0
    atr = float(last["atr14"]) if pd.notna(last["atr14"]) and float(last["atr14"]) > 0 else max(close * 0.01, 1e-6)
    hist = float(last["hist"]) if pd.notna(last["hist"]) else 0.0

    # 市场状态
    if has_ma60:
        if close > ma20 > ma60:
            market_state = "uptrend"
        elif close < ma20 < ma60:
            market_state = "downtrend"
        elif abs(close - ma20) / max(abs(close), 1e-6) < 0.01:
            market_state = "range"
        else:
            market_state = "chaotic"
    else:
        # 样本窗口不足 60 根时，降级为 MA20 + 价格位置判断，避免全部落入 watch
        if close > ma20:
            market_state = "uptrend"
        elif close < ma20:
            market_state = "downtrend"
        else:
            market_state = "range"

    # 决策
    action = "watch"
    playbook = "none"
    if market_state == "uptrend" and rsi >= 52 and hist >= -0.02 * max(abs(close), 1.0):
        action = "long"
        playbook = "trend-pullback"
    elif market_state == "downtrend" and rsi <= 48 and hist <= 0.02 * max(abs(close), 1.0):
        action = "short"
        playbook = "trend-pullback"

    checklist = {
        "htf_direction": "pass" if action != "watch" else "degraded",
        "position": "pass" if action != "watch" else "fail",
        "setup_match": "pass" if action != "watch" else "fail",
        "trigger": "pass" if action != "watch" else "fail",
        "risk_reward": "pass" if action != "watch" else "fail",
        "events": "pass",
        "counter_reason": "degraded" if action != "watch" else "pass",
    }
    checklist_result = "pass_degraded" if action != "watch" else "fail"
    position_size_pct = 50.0 if action != "watch" else 0.0

    if action == "long":
        entry = close
        stop = close - atr
        t1 = close + 1.6 * atr
        t2 = close + 3.0 * atr
        rr = (t1 - entry) / max(entry - stop, 1e-6)
        trigger_type = "close_above"
        invalidation = "价格跌破止损位"
    elif action == "short":
        entry = close
        stop = close + atr
        t1 = close - 1.6 * atr
        t2 = close - 3.0 * atr
        rr = (entry - t1) / max(stop - entry, 1e-6)
        trigger_type = "close_below"
        invalidation = "价格升破止损位"
    else:
        entry = stop = t1 = t2 = rr = None
        trigger_type = None
        invalidation = None

    confidence = "low" if action == "watch" else ("medium" if abs(close - ma20) / max(close, 1e-6) < 0.03 else "high")
    bias = "watch" if action == "watch" else ("bullish" if action == "long" else "bearish")
    signal_strength = "weak" if action == "watch" else "medium"

    sample = {
        "meta": {
            "schema_version": "backtest_sample_v1",
            "symbol": symbol,
            "interval": interval,
            "case_id": case_id,
            "analysis_time": ts,
            "lookback_bars": int(lookback_bars),
            "forward_bars": int(forward_bars),
            "data_source": "ohlc",
        },
        "decision": {
            "action": action,
            "playbook": playbook,
            "checklist": checklist,
            "checklist_result": checklist_result,
            "position_size_pct": position_size_pct,
        },
        "trade": {
            "entry_price": round(float(entry), 6) if entry is not None else None,
            "stop_loss": round(float(stop), 6) if stop is not None else None,
            "t1": round(float(t1), 6) if t1 is not None else None,
            "t2": round(float(t2), 6) if t2 is not None else None,
            "risk_reward": round(float(rr), 6) if rr is not None else None,
            "trigger_type": trigger_type,
            "invalidation": invalidation,
        },
        "verdict": {
            "bias": bias,
            "confidence": confidence,
            "signal_strength": signal_strength,
        },
        "structure": {
            "market_state": market_state,
        },
    }
    context = {
        "close": close,
        "ma20": ma20,
        "ma60": ma60,
        "rsi14": rsi,
        "macd_hist": hist,
        "atr14": atr,
        "swing_high": float(df["high"].tail(20).max()) if len(df) else close,
        "swing_low": float(df["low"].tail(20).min()) if len(df) else close,
        "recent_open": float(df.iloc[-1]["open"]) if len(df) else close,
        "recent_high": float(df.iloc[-1]["high"]) if len(df) else close,
        "recent_low": float(df.iloc[-1]["low"]) if len(df) else close,
        "recent_close": float(df.iloc[-1]["close"]) if len(df) else close,
    }
    return sample, context


def _format_num(value: Any, ndigits: int = 3) -> str:
    if value is None:
        return "null"
    return str(round(float(value), ndigits))


def _build_analysis_report(
    sample: dict[str, Any],
    context: dict[str, Any],
) -> str:
    """
    生成可读分析过程（Markdown），对应 workflows/output-templates.md 的完整模式。
    """
    meta = sample["meta"]
    decision = sample["decision"]
    trade = sample["trade"]
    verdict = sample.get("verdict", {})
    structure = sample.get("structure", {})

    action_map = {"long": "做多", "short": "做空", "watch": "观望"}
    momentum = "犹豫不决"
    if context["recent_close"] > context["recent_open"]:
        momentum = "多头主导"
    elif context["recent_close"] < context["recent_open"]:
        momentum = "空头主导"

    report = f"""#### 基础信息
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
- 阻力: {_format_num(context['swing_high'])}
- 支撑: {_format_num(context['swing_low'])}
- 当前位置: {'中间' if decision['action'] == 'watch' else ('阻力附近' if decision['action'] == 'short' else '支撑附近')}

#### 价格行为
- 近期动量: {momentum}
- 关键K线: O={_format_num(context['recent_open'])}, H={_format_num(context['recent_high'])}, L={_format_num(context['recent_low'])}, C={_format_num(context['recent_close'])}

#### 形态识别
- K线形态: 无明显形态
- 图表形态: 无明显形态
- 信号强度: {verdict.get('signal_strength', 'weak')}

#### 指标信号（如可见）
- RSI: {_format_num(context['rsi14'], 2)}
- MACD: hist={_format_num(context['macd_hist'], 4)}

#### 综合研判
- 偏向: {verdict.get('bias', 'watch')}
- 信心: {verdict.get('confidence', 'low')}
- 多周期一致性: single_tf
- 核心逻辑: 以 MA20/MA60 与 MACD、RSI、ATR 进行结构判定；先定市场状态，再匹配 playbook 与条件触发。

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

### 交易方案（如通过检查）
- 入场: {_format_num(trade.get('entry_price'), 6)}
- 止损: {_format_num(trade.get('stop_loss'), 6)}
- 目标1: {_format_num(trade.get('t1'), 6)}（R:R = {_format_num(trade.get('risk_reward'), 3)}:1）
- 目标2: {_format_num(trade.get('t2'), 6)}
- 仓位: {_format_num(decision.get('position_size_pct'), 2)}%
- 失效条件: {trade.get('invalidation') or 'null'}
- 持仓管理: 到达 T1 后可分批止盈并将止损上移到成本附近。

> 以上分析仅供学习和参考，不构成任何投资建议。交易有风险，请基于自身判断做出决策，并自行承担所有风险。
"""
    return report


def _write_case_artifacts(
    out_root: Path,
    case_id: str,
    run_id: int,
    sample: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, str]:
    case_dir = out_root / "cases" / case_id / f"run_{run_id:02d}"
    case_dir.mkdir(parents=True, exist_ok=True)

    sample_file = case_dir / "backtest_sample_v1.json"
    report_file = case_dir / "analysis_report.md"

    sample_file.write_text(
        json.dumps(sample, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    report_file.write_text(
        _build_analysis_report(sample, context),
        encoding="utf-8",
    )
    return {
        "sample_json": str(sample_file),
        "analysis_report": str(report_file),
    }


def _print_case_reports(artifact_index_file: Path) -> None:
    """
    在终端打印分析过程，便于对话中直接查看，不必手动打开文件。
    """
    if not artifact_index_file.exists():
        return
    try:
        rows = json.loads(artifact_index_file.read_text(encoding="utf-8"))
    except Exception:
        return
    if not isinstance(rows, list) or not rows:
        return

    print("\n" + "=" * 70)
    print("🧠 技术分析过程（逐 case 输出）")
    print("=" * 70)

    for item in rows:
        case_id = item.get("case_id", "unknown_case")
        run_id = item.get("run_id", "unknown_run")
        report_path = Path(str(item.get("analysis_report", "")))
        sample_path = Path(str(item.get("sample_json", "")))

        print(f"\n--- Case: {case_id} | Run: {run_id} ---")
        if report_path.exists():
            report_text = report_path.read_text(encoding="utf-8").strip()
            print(report_text)
        else:
            print(f"⚠️ 未找到分析报告: {report_path}")

        if sample_path.exists():
            try:
                sample = json.loads(sample_path.read_text(encoding="utf-8"))
                decision = sample.get("decision", {})
                trade = sample.get("trade", {})
                print(
                    "\n[点位摘要] "
                    f"action={decision.get('action')} "
                    f"entry={trade.get('entry_price')} "
                    f"sl={trade.get('stop_loss')} "
                    f"t1={trade.get('t1')} "
                    f"t2={trade.get('t2')}"
                )
            except Exception:
                pass


def generate_local_runs(
    eval_csv: Path,
    symbol: str,
    interval: str,
    repeat: int,
    sample: int,
    step: int,
    lookback: int,
    forward: int,
    out_runs_file: Path,
) -> dict[str, Any]:
    """
    基于本地规则引擎生成 runs.jsonl，格式兼容 eval.score_eval。
    """
    df = pd.read_csv(eval_csv)
    required_cols = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"eval 输入 CSV 缺少列: {missing}")

    cases = make_cases(df, lookback, forward, sample, step)
    out_runs_file.parent.mkdir(parents=True, exist_ok=True)

    total_runs = 0
    parse_errors = 0
    artifact_rows: list[dict[str, Any]] = []
    with out_runs_file.open("w", encoding="utf-8") as f:
        for case in cases:
            for run_id in range(repeat):
                payload, context = _build_local_backtest_sample(
                    case["analysis_rows"],
                    symbol,
                    interval,
                    case["case_id"],
                    lookback,
                    forward,
                )
                ok, err, normalized = validate_backtest_sample(payload, case["case_id"])
                parse_error = not ok
                if parse_error:
                    parse_errors += 1
                artifacts = _write_case_artifacts(
                    out_runs_file.parent,
                    case["case_id"],
                    run_id,
                    normalized if normalized is not None else payload,
                    context,
                )
                # 兼容新旧 make_cases 契约：
                # 新版仅返回 analysis_start；旧版可能直接带 forward_rows。
                analysis_start = int(case.get("analysis_start", -1))
                if "forward_rows" in case and case["forward_rows"] is not None:
                    forward_rows = case["forward_rows"]
                elif analysis_start >= 0:
                    forward_start = analysis_start + lookback
                    forward_end = forward_start + forward
                    forward_rows = df.iloc[forward_start:forward_end].to_dict("records")
                else:
                    forward_rows = []

                run = {
                    "run_id": run_id,
                    "case_id": case["case_id"],
                    "analysis_start": analysis_start,
                    "symbol": symbol,
                    "interval": interval,
                    "temperature": 0.0,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "parse_error": parse_error,
                    "validation_error": err,
                    "parsed_json": normalized if normalized is not None else payload,
                    "forward_rows": forward_rows,
                    "raw_response_preview": "generated_by_local_skill_engine",
                    "artifacts": artifacts,
                }
                f.write(json.dumps(run, ensure_ascii=False, default=str) + "\n")
                total_runs += 1
                artifact_rows.append(
                    {
                        "case_id": case["case_id"],
                        "run_id": run_id,
                        **artifacts,
                    }
                )

    artifact_index = out_runs_file.parent / "analysis_artifacts.json"
    artifact_index.write_text(
        json.dumps(artifact_rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "cases": len(cases),
        "runs": total_runs,
        "parse_errors": parse_errors,
        "artifact_index": str(artifact_index),
    }


def main() -> None:
    args = parse_args()
    symbols = [normalize_symbol(s) for s in args.symbols]

    run_ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%SZ")

    env = os.environ.copy()
    if args.model:
        env["EVAL_MODEL"] = args.model

    engine = args.engine
    has_api_key = bool(env.get("OPENAI_API_KEY"))
    if engine == "auto":
        engine = "openai" if has_api_key else "local"
    if engine == "openai" and not has_api_key and not args.prepare_only:
        # 自动降级到 local，避免因未配置 key 中断
        engine = "local"

    semantic_name = build_semantic_run_name(
        symbols=symbols,
        interval=args.interval,
        lookback=args.lookback,
        forward=args.forward,
        sample=args.sample,
        step=args.step,
        repeat=args.repeat,
        engine=engine,
    )
    output_root = (
        Path(args.output_root).resolve()
        if args.output_root
        else (REPO_ROOT / "eval" / "results" / semantic_name)
    )
    # 默认清理旧结果，避免 results 下堆积重复目录与重复文件
    if output_root.exists() and not args.no_clean_output:
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    index: dict[str, Any] = {
        "run_id": run_ts,
        "semantic_name": semantic_name,
        "symbols": symbols,
        "config": {
            "interval": args.interval,
            "repeat": args.repeat,
            "sample": args.sample,
            "step": args.step,
            "lookback": args.lookback,
            "forward": args.forward,
            "cache_file": args.cache_file,
            "prepare_only": args.prepare_only,
            "model": env.get("EVAL_MODEL"),
            "engine": engine,
            "clean_output": (not args.no_clean_output),
        },
        "items": [],
    }

    for symbol in symbols:
        item: dict[str, Any] = {"symbol": symbol}
        symbol_dir = REPO_ROOT / "data" / "opend_kline" / symbol
        src_csv = symbol_dir / args.cache_file
        if not src_csv.exists():
            item["status"] = "missing_cache"
            item["error"] = f"未找到缓存文件: {src_csv}"
            index["items"].append(item)
            continue

        out_dir = output_root / symbol
        out_dir.mkdir(parents=True, exist_ok=True)
        eval_csv = out_dir / "eval_input.csv"

        try:
            item["input"] = convert_cached_csv_to_eval_csv(src_csv, eval_csv)
        except Exception as exc:
            item["status"] = "prepare_failed"
            item["error"] = str(exc)
            index["items"].append(item)
            continue

        if args.prepare_only:
            item["status"] = "prepared"
            index["items"].append(item)
            continue

        try:
            artifact_index_path: Path | None = None
            if engine == "openai":
                run_cmd(
                    [
                        "python3",
                        "-m",
                        "eval.run_eval",
                        "--csv",
                        str(eval_csv),
                        "--symbol",
                        symbol,
                        "--interval",
                        args.interval,
                        "--repeat",
                        str(args.repeat),
                        "--sample",
                        str(args.sample),
                        "--step",
                        str(args.step),
                        "--lookback",
                        str(args.lookback),
                        "--forward",
                        str(args.forward),
                        "--output",
                        str(out_dir),
                    ],
                    cwd=REPO_ROOT,
                    env=env,
                )
            else:
                local_meta = generate_local_runs(
                    eval_csv=eval_csv,
                    symbol=symbol,
                    interval=args.interval,
                    repeat=args.repeat,
                    sample=args.sample,
                    step=args.step,
                    lookback=args.lookback,
                    forward=args.forward,
                    out_runs_file=out_dir / "runs.jsonl",
                )
                item["local_generation"] = local_meta
                artifact_index_path = Path(str(local_meta.get("artifact_index", "")))
                if not args.hide_analysis:
                    _print_case_reports(artifact_index_path)

            run_cmd(
                [
                    "python3",
                    "-m",
                    "eval.score_eval",
                    "--results",
                    str(out_dir / "runs.jsonl"),
                    "--output",
                    str(out_dir / "scored.jsonl"),
                ],
                cwd=REPO_ROOT,
                env=env,
            )
            run_cmd(
                [
                    "python3",
                    "-m",
                    "eval.report",
                    "--dir",
                    str(out_dir),
                    "--save",
                ],
                cwd=REPO_ROOT,
                env=env,
            )
            append_template_alignment_summary(
                symbol_out_dir=out_dir,
                artifact_index_file=artifact_index_path,
                template_file=REPO_ROOT / "workflows" / "output-templates.md",
            )
            item["status"] = "done"
            item["results"] = {
                "runs": str(out_dir / "runs.jsonl"),
                "scored": str(out_dir / "scored.jsonl"),
                "summary": str(out_dir / "summary.md"),
            }
            item["summary"] = score_summary(out_dir / "scored.jsonl")
        except subprocess.CalledProcessError as exc:
            item["status"] = "run_failed"
            item["error"] = f"命令失败: {exc}"

        index["items"].append(item)

    index_file = output_root / "index.json"
    index_file.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(index, ensure_ascii=False, indent=2))
    print(f"\n已输出索引: {index_file}")


if __name__ == "__main__":
    main()
