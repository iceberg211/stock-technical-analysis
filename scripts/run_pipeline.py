#!/usr/bin/env python3
import os
import sys
import json
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from eval.pipeline.cli import parse_args
from eval.pipeline.layout import RunLayout, REPO_ROOT
from eval.pipeline.manifest import RunManifest, GlobalRegistry
from eval.pipeline.data_source import DataSource
from eval.pipeline.data_store import DataStore
from eval.pipeline.backtest import generate_local_runs, run_openai_eval, score_and_report
from eval.pipeline.reporting import append_template_alignment_details, score_summary
from eval.pipeline.retention import apply_artifact_retention

def normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper()

def main():
    args = parse_args()
    symbols = [normalize_symbol(s) for s in args.symbols]
    run_ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    
    tag = "_".join(s.lower().replace(".", "") for s in symbols)
    run_id = f"{run_ts}_{tag}"
    
    layout = RunLayout(run_id)
    manifest = RunManifest(layout, symbols, vars(args))
    
    env = os.environ.copy()
    if args.model:
        env["EVAL_MODEL"] = args.model

    engine = args.engine
    has_api_key = bool(env.get("OPENAI_API_KEY"))
    if engine == "auto":
        engine = "openai" if has_api_key else "local"
    if engine == "openai" and not has_api_key and not args.prepare_only:
        engine = "local"
        
    for symbol in symbols:
        sym_layout = layout.get_symbol_layout(symbol)
        item = {"symbol": symbol, "status": "unknown"}
        
        try:
            # 1. 物理目录建仓
            sym_layout.setup()
            
            # 2. 行情源拉取 (DataSource)
            src_csv = DataSource.ensure_data_available(symbol, args.cache_file)
            
            # 3. 数据规整并下发到管线 data/ 内 (DataStore)
            item["input"] = DataStore.prepare_eval_csv(src_csv, sym_layout.eval_input_csv)
            
            # config json 只做记录，写在 machine 下
            config_record = {"run_id": run_id, "symbol": symbol, "args": vars(args)}
            sym_layout.config_json.write_text(json.dumps(config_record, ensure_ascii=False, indent=2))
            
            if args.prepare_only:
                item["status"] = "prepared"
                manifest.add_symbol_item(item)
                GlobalRegistry.append_run(run_id, symbol, args.interval, "prepared", str(sym_layout.base_dir))
                continue
            
            # 4. 回测调度执行 (Backtest)
            if engine == "openai":
                # 将输出强行接管到 machine_dir 里
                run_openai_eval(env, sym_layout.eval_input_csv, symbol, args.interval, sym_layout, args)
            else:
                meta = generate_local_runs(
                    sym_layout.eval_input_csv, symbol, args.interval, sym_layout,
                    args.repeat, args.sample, args.step, args.lookback, args.forward,
                    args.case_mode, args.warmup_bars, args.embed_forward_rows,
                    write_case_artifacts=(args.artifact_level == "full")
                )
                item["local_generation"] = meta
            
            # 5. 打分与生成报告 (Scoring & Reporting)
            score_and_report(env, sym_layout)
            
            # 6. 报告对齐说明与瘦身修剪 (Retention)
            if args.artifact_level == "full":
                append_template_alignment_details(
                    sym_layout.details_md, 
                    sym_layout.analysis_artifacts_json if sym_layout.analysis_artifacts_json.exists() else None,
                    REPO_ROOT / "workflows" / "output-templates.md"
                )
            
            apply_artifact_retention(sym_layout, args.artifact_level)
            
            item["status"] = "done"
            item["summary"] = score_summary(sym_layout.scored_jsonl)
            GlobalRegistry.append_run(run_id, symbol, args.interval, "done", str(sym_layout.base_dir))
            
        except Exception as e:
            item["status"] = "failed"
            item["error"] = str(e)
            GlobalRegistry.append_run(run_id, symbol, args.interval, "failed", str(sym_layout.base_dir), error=str(e))
            
        manifest.add_symbol_item(item)
        
    manifest.save()
    print(f"\n✅ 批次 {run_id} 执行完毕，总级 Manifest: {layout.manifest_path}")

if __name__ == "__main__":
    main()
