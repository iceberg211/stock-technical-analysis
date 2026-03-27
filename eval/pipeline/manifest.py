from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from eval.pipeline.layout import RunLayout, DataLayout


class GlobalRegistry:
    """全局注册表管理器，用于记录所有运行历史"""
    
    @staticmethod
    def append_run(
        run_id: str,
        symbol: str,
        interval: str,
        status: str,
        run_path: str,
        error: str = "",
    ) -> None:
        """追加一条运行记录到全局索引 Runs.jsonl"""
        registry_file = DataLayout.get_registry_file()
        record = {
            "run_id": run_id,
            "symbol": symbol,
            "interval": interval,
            "status": status,
            "path": run_path,
            "error": error,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        with registry_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")


class RunManifest:
    """单批次运行的 Manifest 管理器"""
    
    def __init__(self, layout: RunLayout, symbols: list[str], global_config: dict[str, Any]):
        self.layout = layout
        self.data: dict[str, Any] = {
            "run_id": layout.run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "symbols": symbols,
            "config": global_config,
            "items": []
        }

    def add_symbol_item(self, item: dict[str, Any]) -> None:
        """记录该批次下某个币种的运行状态与结果"""
        self.data["items"].append(item)

    def save(self) -> None:
        """保存为 manifest.json"""
        self.layout.setup()
        self.layout.manifest_path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
