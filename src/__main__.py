"""
Pipeline 主入口。

用法：
    python -m src --symbols BTCUSDT --interval 1h
    python -m src --symbols BTCUSDT ETHUSDT --engine local --sample 5
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.pipeline.cli import parse_args
from src.pipeline.layout import RunLayout, REPO_ROOT
from src.pipeline.manifest import RunManifest, GlobalRegistry
from src.pipeline.catalog import Catalog
from src.pipeline.backtest import generate_local_runs, score_and_report
from src.pipeline.reporting import score_summary
from src.pipeline.retention import apply_artifact_retention


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
    catalog = Catalog()

    for symbol in symbols:
        sym_layout = layout.get_symbol_layout(symbol)
        item = {"symbol": symbol, "status": "unknown"}

        try:
            sym_layout.setup()

            interval = args.interval
            item["input"] = catalog.prepare_eval_input(symbol, interval, sym_layout.eval_input_csv)

            config_record = {"run_id": run_id, "symbol": symbol, "args": vars(args)}
            sym_layout.config_json.write_text(json.dumps(config_record, ensure_ascii=False, indent=2))

            if args.prepare_only:
                item["status"] = "prepared"
                manifest.add_symbol_item(item)
                GlobalRegistry.append_run(run_id, symbol, args.interval, "prepared", str(sym_layout.base_dir))
                continue

            meta = generate_local_runs(
                sym_layout.eval_input_csv, symbol, args.interval, sym_layout,
                args.repeat, args.sample, args.step, args.lookback, args.forward,
                args.case_mode, args.warmup_bars, args.embed_forward_rows,
                write_case_artifacts=(args.artifact_level == "full"),
            )
            item["local_generation"] = meta

            score_and_report(sym_layout)

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
    print(f"\n✅ 批次 {run_id} 执行完毕，Manifest: {layout.manifest_path}")


if __name__ == "__main__":
    main()
