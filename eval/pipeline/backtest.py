from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from eval.run_eval import make_cases, validate_backtest_sample
from eval.pipeline.layout import SymbolLayout, REPO_ROOT
from eval.pipeline.analyze import build_local_backtest_sample
from eval.pipeline.reporting import build_analysis_report


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
    artifact_rows: list[dict[str, Any]] = []

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
                    case_dir = layout.cases_dir / case["case_id"] / f"run_{run_id:02d}"
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
                if artifacts:
                    artifact_rows.append({"case_id": case["case_id"], "run_id": run_id, **artifacts})

    artifact_index = None
    if write_case_artifacts:
        layout.analysis_artifacts_json.write_text(json.dumps(artifact_rows, ensure_ascii=False, indent=2), encoding="utf-8")
        artifact_index = str(layout.analysis_artifacts_json)

    return {"cases": len(cases), "runs": total_runs, "parse_errors": parse_errors, "artifact_index": artifact_index}


def run_openai_eval(env: dict[str, str], eval_csv: Path, symbol: str, interval: str, layout: SymbolLayout, args: Any) -> None:
    """包装原始脚本对 OpenAI 模型的主调度"""
    cmd = [
        "python3", "-m", "eval.run_eval",
        "--csv", str(eval_csv), "--symbol", symbol, "--interval", interval,
        "--repeat", str(args.repeat), "--sample", str(args.sample),
        "--step", str(args.step), "--lookback", str(args.lookback),
        "--forward", str(args.forward), "--case-mode", args.case_mode,
        "--warmup-bars", str(args.warmup_bars),
        "--artifact-level", args.artifact_level,
        "--output-dir", str(layout.machine_dir)  # 严格写到 machine_dir
    ]
    if args.embed_forward_rows:
        cmd.append("--embed-forward-rows")
    subprocess.run(cmd, cwd=REPO_ROOT, env=env, check=True)

def score_and_report(env: dict[str, str], layout: SymbolLayout) -> None:
    """封装对后置评分引擎和报告引擎的调用"""
    # 评分 (machine)
    subprocess.run([
        "python3", "-m", "eval.score_eval",
        "--dir", str(layout.machine_dir),
        "--output", str(layout.scored_jsonl)
    ], cwd=REPO_ROOT, env=env, check=True)
    
    # 报告 (human) => 但是旧版的 eval.report 是直接生成在传进去的 dir 下。
    # 为了适配输出结构，这里我们让它读 machine_dir，然后在 Python 里进行文件移动
    subprocess.run([
        "python3", "-m", "eval.report",
        "--dir", str(layout.machine_dir),
        "--save"
    ], cwd=REPO_ROOT, env=env, check=True)
    
    # 将 summary.md 和 details.md 等人读物从 machine_dir 剪切到 human_dir
    for fname in ["summary.md", "details.md", "analysis.md"]:
        machine_file = layout.machine_dir / fname
        if machine_file.exists():
            machine_file.replace(layout.human_dir / fname)
