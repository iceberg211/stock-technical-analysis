"""
核心运行器：OHLCV CSV → Skill 调用 → JSON 提取。

用法:
    python -m eval.run_eval --csv data/btc_4h.csv --symbol BTCUSDT --interval 4h
    python -m eval.run_eval --csv data/btc_4h.csv --symbol BTCUSDT --interval 4h --repeat 3

输出目录结构（扁平化）:
    eval/results/{YYYYMMDD_HHMM}_{symbol}_{interval}/
        ├── config.json       ← 运行配置（可复现）
        ├── runs.jsonl        ← 核心数据：每行 = 一次 LLM 调用记录
        └── reports/          ← 可选：LLM 原始文本响应
              ├── case_0000_run00.txt
              └── ...
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from openai import OpenAI

from eval.config import (
    DEFAULT_REPEAT,
    DEFAULT_RESULTS_DIR,
    DEFAULT_SAMPLE,
    DEFAULT_STEP,
    FORWARD_BARS,
    LOOKBACK_BARS,
    MAX_TOKENS,
    MODEL,
    TEMPERATURE_CONSISTENCY,
    TEMPERATURE_EVAL,
)
from eval.prompt_builder import (
    build_system_prompt,
    build_user_message,
    format_ohlcv_csv,
    format_indicator_context,
)

RUN_SCHEMA_VERSION = "run_v2"
ARTIFACT_LEVEL_CHOICES = ("core", "standard", "full")
CASE_MODE_CHOICES = ("rolling", "non_overlap")


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


# ── LLM 调用 ──────────────────────────────────────────

def call_llm(
    client: OpenAI,
    system_prompt: str,
    user_message: str,
    temperature: float,
) -> str:
    """调用 OpenAI ChatCompletion，返回 assistant 文本。"""
    resp = client.chat.completions.create(
        model=MODEL,
        temperature=temperature,
        max_tokens=MAX_TOKENS,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    )
    return resp.choices[0].message.content or ""


# ── 单 case 运行 ──────────────────────────────────────

def run_single_case(
    client: OpenAI,
    system_prompt: str,
    case: dict,
    symbol: str,
    interval: str,
    repeat: int,
    lookback_bars: int,
    forward_bars: int,
    reports_dir: Path | None = None,
) -> list[dict]:
    """对单个 case 运行 repeat 次 LLM 调用。"""
    ohlcv_text = format_ohlcv_csv(case["analysis_rows"])
    indicator_text = format_indicator_context(case["analysis_rows"])
    user_msg = build_user_message(
        ohlcv_text, indicator_text, symbol, interval,
        case["case_id"], lookback_bars, forward_bars,
    )

    temp = TEMPERATURE_EVAL if repeat == 1 else TEMPERATURE_CONSISTENCY

    results = []
    for run_id in range(repeat):
        print(f"    run {run_id + 1}/{repeat} ...", end=" ", flush=True)
        validation_error = None
        try:
            raw = call_llm(client, system_prompt, user_msg, temp)
            parsed = extract_json(raw)
            parse_error = parsed is None
            if parse_error:
                print("⚠️  JSON 解析失败")
            else:
                ok, err, normalized = validate_backtest_sample(parsed, case["case_id"])
                if not ok:
                    parse_error = True
                    validation_error = err
                    parsed = normalized if normalized is not None else parsed
                    print(f"⚠️  JSON 校验失败: {validation_error}")
                else:
                    parsed = normalized
                    action = parsed.get("decision", {}).get("action", "?")
                    confidence = parsed.get("verdict", {}).get("confidence", "?")
                    print(f"✅ action={action} confidence={confidence}")
        except Exception as e:
            raw = str(e)
            parsed = None
            parse_error = True
            validation_error = str(e)
            print(f"❌ API 错误: {e}")

        # 可选：保存原始文本到 reports/
        if reports_dir:
            report_file = reports_dir / f"{case['case_id']}_run{run_id:02d}.txt"
            report_file.write_text(raw, encoding="utf-8")

        results.append({
            "run_id": run_id,
            "case_id": case["case_id"],
            "analysis_start": case["analysis_start"],
            "symbol": symbol,
            "interval": interval,
            "parsed_json": parsed,
            "parse_error": parse_error,
            "validation_error": validation_error,
            "temperature": temp,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        if run_id < repeat - 1:
            time.sleep(1)

    return results


# ── 输出 ──────────────────────────────────────────────

def _make_output_dir(base: Path, symbol: str, interval: str) -> Path:
    """在 base 下生成带时间戳的子目录: {YYYYMMDD_HHMM}_{symbol}_{interval}"""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    name = f"{ts}_{symbol}_{interval}"
    out = base / name
    out.mkdir(parents=True, exist_ok=True)
    return out


def _save_config(output_dir: Path, args: argparse.Namespace, num_cases: int):
    """保存运行配置，用于 score_eval 复现 forward 窗口。"""
    config = {
        "csv": str(Path(args.csv).resolve()),
        "symbol": args.symbol,
        "interval": args.interval,
        "lookback": args.lookback,
        "forward": args.forward,
        "sample": args.sample,
        "step": args.step,
        "repeat": args.repeat,
        "case_mode": args.case_mode,
        "warmup_bars": args.warmup_bars,
        "artifact_level": args.artifact_level,
        "embed_forward_rows": bool(args.embed_forward_rows),
        "run_schema_version": RUN_SCHEMA_VERSION,
        "model": MODEL,
        "temperature_eval": TEMPERATURE_EVAL,
        "temperature_consistency": TEMPERATURE_CONSISTENCY,
        "num_cases": num_cases,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    (output_dir / "config.json").write_text(
        json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _save_results(results: list[dict], output_dir: Path):
    """
    保存结果到 runs.jsonl。

    不保存 forward_rows（从 CSV + config 重建），
    不保存 raw_response（已存到 reports/ 目录）。
    """
    out_file = output_dir / "runs.jsonl"
    with open(out_file, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False, default=str) + "\n")


def _print_summary(results: list[dict]):
    """打印简要统计。"""
    total = len(results)
    if total == 0:
        return
    parse_ok = sum(1 for r in results if not r["parse_error"])
    parse_fail = total - parse_ok

    actions = {}
    confidences = {}
    for r in results:
        pj = r.get("parsed_json")
        if pj:
            a = pj.get("decision", {}).get("action", "?")
            c = pj.get("verdict", {}).get("confidence", "?")
            actions[a] = actions.get(a, 0) + 1
            confidences[c] = confidences.get(c, 0) + 1

    print(f"\n{'─'*40}")
    print(f"📈 运行统计")
    print(f"   总 runs: {total}")
    print(f"   JSON 合规: {parse_ok} ({parse_ok/total*100:.0f}%)")
    print(f"   JSON 失败: {parse_fail}")
    print(f"   action 分布: {actions}")
    print(f"   confidence 分布: {confidences}")


# ── 主流程 ────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Skill Eval 运行器")
    parser.add_argument("--csv", required=True, help="OHLCV CSV 文件路径")
    parser.add_argument("--symbol", required=True, help="标的代码, 如 BTCUSDT")
    parser.add_argument("--interval", required=True, help="K 线周期, 如 4h")
    parser.add_argument("--repeat", type=int, default=1, help="每个 case 重复次数")
    parser.add_argument("--sample", type=int, default=DEFAULT_SAMPLE, help="采样 case 数量")
    parser.add_argument("--step", type=int, default=DEFAULT_STEP, help="窗口步进根数")
    parser.add_argument("--output", default=str(DEFAULT_RESULTS_DIR), help="结果根目录（内部自动创建时间戳子目录）")
    parser.add_argument("--output-dir", default=None, dest="output_dir",
                        help="精确输出目录（直接使用，不再创建子目录）；由外部脚本管理目录时使用")
    parser.add_argument("--lookback", type=int, default=LOOKBACK_BARS, help="分析窗口大小")
    parser.add_argument("--forward", type=int, default=FORWARD_BARS, help="事后窗口大小")
    parser.add_argument(
        "--case-mode",
        choices=CASE_MODE_CHOICES,
        default="non_overlap",
        help="切片模式：rolling 使用 step；non_overlap 使用 lookback+forward",
    )
    parser.add_argument(
        "--warmup-bars",
        type=int,
        default=120,
        help="切片起点预热根数，避免指标冷启动污染",
    )
    parser.add_argument(
        "--artifact-level",
        choices=ARTIFACT_LEVEL_CHOICES,
        default="standard",
        help="产物层级：core|standard|full",
    )
    parser.add_argument(
        "--embed-forward-rows",
        action="store_true",
        help="将 forward_rows 内联写入 runs.jsonl（默认关闭）",
    )
    parser.add_argument("--save-reports", action="store_true", help="保存 LLM 原始文本到 reports/")
    args = parser.parse_args()

    # 读取 CSV
    print(f"📂 读取数据: {args.csv}")
    df = pd.read_csv(args.csv)
    required_cols = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = required_cols - set(df.columns)
    if missing:
        print(f"❌ CSV 缺少列: {missing}", file=sys.stderr)
        sys.exit(1)
    print(f"   共 {len(df)} 根 K 线")

    # 切 case
    cases = make_cases(
        df,
        args.lookback,
        args.forward,
        args.sample,
        args.step,
        case_mode=args.case_mode,
        warmup_bars=args.warmup_bars,
    )
    if not cases:
        sys.exit(1)
    print(
        f"📊 切出 {len(cases)} 个 case "
        f"(mode={args.case_mode}, warmup={args.warmup_bars}, "
        f"lookback={args.lookback}, forward={args.forward}, step={args.step})"
    )

    # 准备输出目录
    if args.output_dir:
        # 外部精确指定，直接使用
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
    else:
        # 默认：在 --output 根目录下创建时间戳子目录
        output_dir = _make_output_dir(Path(args.output), args.symbol, args.interval)
    reports_dir = None
    save_reports = bool(args.save_reports or args.artifact_level == "full")
    if save_reports:
        reports_dir = output_dir / "reports"
        reports_dir.mkdir(exist_ok=True)

    # 保存配置
    _save_config(output_dir, args, len(cases))

    # 组装 system prompt
    print("🔧 组装 system prompt ...")
    system_prompt = build_system_prompt()
    print(f"   system prompt: {len(system_prompt)} 字符")

    # 初始化 OpenAI
    client = OpenAI()

    # 运行
    all_results = []
    for i, case in enumerate(cases):
        print(f"\n{'='*50}")
        print(f"[{i+1}/{len(cases)}] {case['case_id']}")
        print(f"{'='*50}")

        runs = run_single_case(
            client, system_prompt, case,
            args.symbol, args.interval, args.repeat,
            args.lookback, args.forward, reports_dir,
        )
        for r in runs:
            r["run_schema_version"] = RUN_SCHEMA_VERSION
            if args.embed_forward_rows:
                analysis_start = int(case.get("analysis_start", -1))
                forward_start = analysis_start + args.lookback
                forward_end = forward_start + args.forward
                r["forward_rows"] = df.iloc[forward_start:forward_end].to_dict("records")
        all_results.extend(runs)

        # 每个 case 后保存（断点续传）
        _save_results(all_results, output_dir)

    print(f"\n✅ 完成! 共 {len(all_results)} 次 run")
    print(f"📁 结果目录: {output_dir}")
    _print_summary(all_results)


if __name__ == "__main__":
    main()
