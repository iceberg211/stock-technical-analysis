from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class SymbolLayout:
    """单个币种在一批次回测中的物理隔离结构"""
    base_dir: Path

    @property
    def human_dir(self) -> Path:
        return self.base_dir / "human"

    @property
    def machine_dir(self) -> Path:
        return self.base_dir / "machine"

    @property
    def data_dir(self) -> Path:
        return self.base_dir / "data"

    @property
    def debug_dir(self) -> Path:
        return self.base_dir / "debug"

    def setup(self) -> None:
        """创建该 Symbol 在当前 Run 下的所有标准子目录"""
        self.human_dir.mkdir(parents=True, exist_ok=True)
        self.machine_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.debug_dir.mkdir(parents=True, exist_ok=True)
        
        # 调试用：预先创建 debug/cases 目录
        (self.debug_dir / "cases").mkdir(parents=True, exist_ok=True)

    # 常用文件路径 Shortcut (Human)
    @property
    def summary_md(self) -> Path: return self.human_dir / "summary.md"
    
    @property
    def details_md(self) -> Path: return self.human_dir / "details.md"
    
    @property
    def analysis_md(self) -> Path: return self.human_dir / "analysis.md"

    # 常用文件路径 Shortcut (Machine)
    @property
    def config_json(self) -> Path: return self.machine_dir / "config.json"
    
    @property
    def runs_jsonl(self) -> Path: return self.machine_dir / "runs.jsonl"
    
    @property
    def scored_jsonl(self) -> Path: return self.machine_dir / "scored.jsonl"
    
    @property
    def metrics_json(self) -> Path: return self.machine_dir / "metrics.json"

    @property
    def compat_manifest_json(self) -> Path: return self.machine_dir / "compat_manifest.json"

    # 常用文件路径 Shortcut (Data & Debug)
    @property
    def eval_input_csv(self) -> Path: return self.data_dir / "eval_input.csv"
    
    @property
    def analysis_artifacts_json(self) -> Path: return self.debug_dir / "analysis_artifacts.json"
    
    @property
    def cases_dir(self) -> Path: return self.debug_dir / "cases"


class RunLayout:
    """管理一次完整回测批次 (Run) 的目录结构"""
    def __init__(self, run_id: str):
        self.run_id = run_id
        self.runs_root = REPO_ROOT / "outputs" / "runs"
        self.run_dir = self.runs_root / run_id
        self.manifest_path = self.run_dir / "manifest.json"

    def setup(self):
        self.run_dir.mkdir(parents=True, exist_ok=True)

    def get_symbol_layout(self, symbol: str) -> SymbolLayout:
        return SymbolLayout(self.run_dir / symbol)


class DataLayout:
    """管理行情数据与全局注册表结构"""
    
    @staticmethod
    def get_symbol_data_dir(symbol: str, interval: str) -> Path:
        """返回 data/symbols/<symbol>/<interval>"""
        d = REPO_ROOT / "data" / "symbols" / symbol / interval
        d.mkdir(parents=True, exist_ok=True)
        return d
    
    @staticmethod
    def get_registry_file() -> Path:
        """返回全局运行索引 data/registry/runs.jsonl"""
        d = REPO_ROOT / "data" / "registry"
        d.mkdir(parents=True, exist_ok=True)
        return d / "runs.jsonl"
