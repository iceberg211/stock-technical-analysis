import shutil
from pathlib import Path

from eval.pipeline.layout import SymbolLayout


def _safe_remove(path: Path) -> None:
    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def apply_artifact_retention(layout: SymbolLayout, artifact_level: str) -> None:
    """根据保留策略清理冗余的人机文件"""
    if artifact_level not in ("core", "standard", "full"):
        raise ValueError(f"不支持的 artifact_level: {artifact_level}")
    
    if artifact_level == "full":
        return

    # standard 和 core 首先删掉 debug 目录下所有的沉重产物
    _safe_remove(layout.debug_dir)

    if artifact_level == "core":
        # core 还需删掉 human/details.md 和 data/eval_input.csv
        _safe_remove(layout.details_md)
        _safe_remove(layout.data_dir)
