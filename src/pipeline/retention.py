from src.pipeline.layout import SymbolLayout


def apply_artifact_retention(layout: SymbolLayout, artifact_level: str) -> None:
    """根据保留策略清理冗余文件。

    扁平布局下不再有 debug/data 子目录，所以 standard/core 只需删除特定文件。
    """
    if artifact_level not in ("core", "standard", "full"):
        raise ValueError(f"不支持的 artifact_level: {artifact_level}")

    if artifact_level == "full":
        return

    # standard: 删掉 cases 子目录（如果 full 模式产生过）
    cases_dir = layout.base_dir / "cases"
    if cases_dir.is_dir():
        import shutil
        shutil.rmtree(cases_dir)

    if artifact_level == "core":
        # core: 还需删掉 details 与输入切片（只留最精简产物）
        for f in (layout.details_md, layout.input_parquet, layout.eval_input_csv):
            if f.exists():
                f.unlink()
