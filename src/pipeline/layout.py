# src/pipeline/layout.py
"""
目录结构定义 — 扁平化布局。

SymbolLayout: 单个 symbol 在一次回测 run 中的所有文件（扁平，无子目录）。
RunLayout: 一次完整回测批次的目录。
DataLayout: 全局数据目录（注册表等）。
"""

from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class SymbolLayout:
    """单个币种在一批次回测中的扁平文件结构。

    所有产物直接放在 base_dir/ 下，不再有 human/machine/data/debug 子目录。
    """
    base_dir: Path

    def setup(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)

    # ── 配置 & 输入 ──
    @property
    def config_json(self) -> Path:
        return self.base_dir / "config.json"

    @property
    def input_parquet(self) -> Path:
        return self.base_dir / "input.parquet"

    # ── 机器产物 ──
    @property
    def runs_jsonl(self) -> Path:
        return self.base_dir / "runs.jsonl"

    @property
    def scored_jsonl(self) -> Path:
        return self.base_dir / "scored.jsonl"

    @property
    def metrics_json(self) -> Path:
        return self.base_dir / "metrics.json"

    # ── 人读产物 ──
    @property
    def summary_md(self) -> Path:
        return self.base_dir / "summary.md"

    @property
    def details_md(self) -> Path:
        return self.base_dir / "details.md"

    # ── 兼容旧代码过渡 ──
    @property
    def eval_input_csv(self) -> Path:
        return self.base_dir / "eval_input.csv"

    @property
    def machine_dir(self) -> Path:
        """兼容旧代码：指向 base_dir 自身。"""
        return self.base_dir

    @property
    def human_dir(self) -> Path:
        """兼容旧代码：指向 base_dir 自身。"""
        return self.base_dir

    @property
    def data_dir(self) -> Path:
        """兼容旧代码：指向 base_dir 自身（原 data/ 子目录已扁平化）。"""
        return self.base_dir

    @property
    def debug_dir(self) -> Path:
        """兼容旧代码：指向 base_dir 自身（原 debug/ 子目录已扁平化）。"""
        return self.base_dir

    @property
    def cases_dir(self) -> Path:
        """兼容旧代码：指向 base_dir 自身。"""
        return self.base_dir

    @property
    def analysis_artifacts_json(self) -> Path:
        """兼容旧代码：指向 base_dir/analysis_artifacts.json。"""
        return self.base_dir / "analysis_artifacts.json"


class RunLayout:
    """管理一次完整回测批次的目录结构。"""
    def __init__(self, run_id: str):
        self.run_id = run_id
        self.runs_root = REPO_ROOT / "outputs" / "runs"
        self.run_dir = self.runs_root / run_id
        self.manifest_path = self.run_dir / "manifest.json"

    def setup(self) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)

    def get_symbol_layout(self, symbol: str) -> SymbolLayout:
        return SymbolLayout(self.run_dir / symbol)


class DataLayout:
    """全局数据目录与注册表文件路径。"""
    _registry_dir = REPO_ROOT / "outputs"

    @classmethod
    def get_registry_file(cls) -> Path:
        cls._registry_dir.mkdir(parents=True, exist_ok=True)
        return cls._registry_dir / "runs.jsonl"
