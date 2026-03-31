from src.pipeline.layout import SymbolLayout


def apply_artifact_retention(layout: SymbolLayout, artifact_level: str) -> None:
    """根据保留策略清理冗余文件。

    保留级别:
      full     — 保留所有文件（调试用）
      standard — 只保留核心产物: scored.jsonl, metrics.json, config.json
      core     — 同 standard（最精简）
    """
    if artifact_level not in ("core", "standard", "full"):
        raise ValueError(f"不支持的 artifact_level: {artifact_level}")

    if artifact_level == "full":
        return

    # standard / core: 删除所有中间产物，只保留 scored.jsonl + metrics.json + config.json
    intermediate_files = [
        layout.input_parquet,      # clean data 的副本
        layout.runs_jsonl,         # 评分前的中间数据
        layout.summary_md,         # 可从 metrics.json 再生
        layout.details_md,         # 可从 scored.jsonl 再生
        layout.eval_input_csv,     # 旧兼容文件
    ]
    for f in intermediate_files:
        if f.exists():
            f.unlink()

    cases_dir = layout.base_dir / "cases"
    if cases_dir.is_dir():
        import shutil
        shutil.rmtree(cases_dir)
