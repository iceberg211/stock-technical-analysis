from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.scoring.validator import make_cases, validate_backtest_sample
from src.scoring.engine import score_runs as _score_runs, _load_csv_df
from src.reporting.metrics import (
    build_metrics,
    build_playbook_breakdown,
    build_confidence_diagnostics,
    build_market_state_breakdown,
    build_consistency,
)
from src.reporting.markdown import render_summary_markdown, render_details_markdown
from src.pipeline.layout import SymbolLayout, REPO_ROOT
from src.pipeline.analyze import build_local_backtest_sample
from src.pipeline.reporting import build_analysis_report


def _write_case_artifacts(
    case_dir: Path,
    sample: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, str]:
    case_dir.mkdir(parents=True, exist_ok=True)
    sample_file = case_dir / "backtest_sample_v1.json"
    report_file = case_dir / "analysis_report.md"

    sample_file.write_text(json.dumps(sample, ensure_ascii=False, indent=2), encoding="utf-8")
    report_file.write_text(build_analysis_report(sample, context), encoding="utf-8")

    return {
        "sample_json": str(sample_file),
        "analysis_report": str(report_file),
    }


def generate_local_runs(
    eval_csv: Path,
    symbol: str,
    interval: str,
    layout: SymbolLayout,
    repeat: int,
    sample: int,
    step: int,
    lookback: int,
    forward: int,
    case_mode: str,
    warmup_bars: int,
    embed_forward_rows: bool,
    write_case_artifacts: bool,
) -> dict[str, Any]:
    """本地兜底引擎运行主循环"""
    df = pd.read_csv(eval_csv)
    cases = make_cases(df, lookback, forward, sample, step, case_mode=case_mode, warmup_bars=warmup_bars)

    out_runs_file = layout.runs_jsonl
    out_runs_file.parent.mkdir(parents=True, exist_ok=True)

    total_runs, parse_errors = 0, 0

    with out_runs_file.open("w", encoding="utf-8") as f:
        for case in cases:
            for run_id in range(repeat):
                payload, context = build_local_backtest_sample(
                    case["analysis_rows"], symbol, interval, case["case_id"], lookback, forward
                )
                ok, err, normalized = validate_backtest_sample(payload, case["case_id"])
                parse_error = not ok
                if parse_error: parse_errors += 1

                artifacts: dict[str, str] = {}
                if write_case_artifacts:
                    case_dir = layout.base_dir / "cases" / case["case_id"] / f"run_{run_id:02d}"
                    artifacts = _write_case_artifacts(case_dir, normalized if normalized is not None else payload, context)

                analysis_start = int(case.get("analysis_start", -1))
                forward_rows = []
                if "forward_rows" in case and case["forward_rows"] is not None:
                    forward_rows = case["forward_rows"]
                elif analysis_start >= 0:
                    f_start, f_end = analysis_start + lookback, analysis_start + lookback + forward
                    forward_rows = df.iloc[f_start:f_end].to_dict("records")

                run_record = {
                    "run_schema_version": "run_v2",
                    "run_id": run_id, "case_id": case["case_id"],
                    "analysis_start": analysis_start, "symbol": symbol, "interval": interval,
                    "temperature": 0.0, "timestamp": datetime.now(timezone.utc).isoformat(),
                    "parse_error": parse_error, "validation_error": err,
                    "parsed_json": normalized if normalized is not None else payload,
                    "raw_response_preview": "generated_by_local_skill_engine",
                }
                if embed_forward_rows: run_record["forward_rows"] = forward_rows
                if artifacts: run_record["artifacts"] = artifacts
                f.write(json.dumps(run_record, ensure_ascii=False, default=str) + "\n")

                total_runs += 1

    return {"cases": len(cases), "runs": total_runs, "parse_errors": parse_errors}


def score_and_report(layout: SymbolLayout, slippage_pct: float = 0.0005, fee_pct: float = 0.001) -> None:
    """直接调用评分和报告函数，不再通过 subprocess。"""
    runs_file = layout.runs_jsonl
    if not runs_file.exists():
        raise FileNotFoundError(f"runs.jsonl 不存在: {runs_file}")

    # 读取 config 获取 CSV 路径和窗口参数
    config: dict[str, Any] = {}
    if layout.config_json.exists():
        config = json.loads(layout.config_json.read_text(encoding="utf-8"))

    primary_csv_path = config.get("csv") or config.get("args", {}).get("csv")
    lookback = int(config.get("lookback", config.get("args", {}).get("lookback", 200)))
    forward = int(config.get("forward", config.get("args", {}).get("forward", 50)))

    primary_df = _load_csv_df(primary_csv_path)
    fallback_df = None
    fallback_path = layout.eval_input_csv
    if fallback_path.exists():
        fallback_df = _load_csv_df(str(fallback_path))

    # 1) 评分
    scored, source_stats = _score_runs(
        runs_file=runs_file,
        primary_df=primary_df,
        fallback_df=fallback_df,
        default_lookback=lookback,
        default_forward=forward,
        slippage_pct=slippage_pct,
        fee_pct=fee_pct,
    )

    with layout.scored_jsonl.open("w", encoding="utf-8") as f:
        for s in scored:
            f.write(json.dumps(s, ensure_ascii=False, default=str) + "\n")

    # 2) 报告
    metrics = build_metrics(scored)
    playbook_rows = build_playbook_breakdown(scored)
    confidence_rows = build_confidence_diagnostics(scored)
    market_state_rows = build_market_state_breakdown(scored)
    consistency = build_consistency(scored)

    summary_md = render_summary_markdown(layout.scored_jsonl.name, metrics)
    details_md = render_details_markdown(
        scored_name=layout.scored_jsonl.name,
        metrics=metrics,
        playbook_rows=playbook_rows,
        confidence_rows=confidence_rows,
        market_state_rows=market_state_rows,
        consistency=consistency,
    )

    layout.human_dir.mkdir(parents=True, exist_ok=True)
    layout.summary_md.write_text(summary_md, encoding="utf-8")
    layout.details_md.write_text(details_md, encoding="utf-8")
    layout.metrics_json.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
