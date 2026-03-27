# src/pipeline/catalog.py
"""
数据目录管理：从 data/clean/ 读取标准化的 parquet 行情数据。

替代旧的 data_source.py（按优先级搜 3 个目录）和 data_store.py（CSV 规整化）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from src.pipeline.layout import REPO_ROOT


class Catalog:
    """行情数据目录管理器。只从 data/clean/ 读取 parquet。"""

    def __init__(self, root: Path | None = None):
        self.root = root or REPO_ROOT
        self.clean_dir = self.root / "data" / "clean"

    def clean_path(self, symbol: str, interval: str) -> Path:
        return self.clean_dir / symbol / f"{interval}.parquet"

    def read_clean(self, symbol: str, interval: str) -> pd.DataFrame:
        """读取标准化 parquet 数据。"""
        path = self.clean_path(symbol, interval)
        if not path.exists():
            raise FileNotFoundError(
                f"未找到 {symbol}/{interval} 数据: {path}\n"
                f"请先运行数据摄入: python -m src.pipeline.ingest --source binance --symbol {symbol} --interval {interval}"
            )
        return pd.read_parquet(path)

    def ensure_available(self, symbol: str, interval: str) -> Path:
        """确保 parquet 文件存在，返回路径。"""
        path = self.clean_path(symbol, interval)
        if not path.exists():
            raise FileNotFoundError(f"未找到 {symbol}/{interval} 数据: {path}")
        return path

    def prepare_eval_input(self, symbol: str, interval: str, dst: Path) -> dict[str, Any]:
        """从 clean parquet 准备评估用 CSV（兼容旧 pipeline）。"""
        df = self.read_clean(symbol, interval)
        df_out = df.copy()
        df_out["timestamp"] = pd.to_datetime(df_out["timestamp"]).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        dst.parent.mkdir(parents=True, exist_ok=True)
        df_out.to_csv(dst, index=False)
        return {
            "rows": len(df_out),
            "start": df_out["timestamp"].iloc[0] if len(df_out) else None,
            "end": df_out["timestamp"].iloc[-1] if len(df_out) else None,
            "path": str(dst),
        }
