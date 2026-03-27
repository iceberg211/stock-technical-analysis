from typing import Any
from pathlib import Path
import pandas as pd


class DataStore:
    """回测数据管线预处理器。负责对拉取到的原始数据进行时区对标、字段映射与空缺补全。"""

    @staticmethod
    def prepare_eval_csv(src_csv: Path, dst_csv: Path) -> dict[str, Any]:
        """
        将原始缓存的行情数据，规整化为 Eval Engine 统一约定的格式。
        必须包含字段：timestamp, open, high, low, close, volume
        时间戳统一转为 UTC ISO8601。
        """
        df = pd.read_csv(src_csv)
        
        # 兼容原本可能叫 time 字段的逻辑
        if "time" not in df.columns and "timestamp" not in df.columns:
            raise ValueError(f"缺少 time/timestamp 列: {src_csv}")
            
        time_col = "time" if "time" in df.columns else "timestamp"

        required = {"open", "high", "low", "close", "volume"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"缺少必填 K 线列 {missing}: {src_csv}")

        out = df.copy()
        out["timestamp"] = pd.to_datetime(out[time_col], errors="coerce")
        out = out.dropna(subset=["timestamp"])

        # 转换为无歧义的 UTC 字符串，时间序列分析的核心在于相对先后和断点判断，避免时区造成的困扰
        out["timestamp"] = out["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        out = out[["timestamp", "open", "high", "low", "close", "volume"]]
        out = out.sort_values("timestamp").reset_index(drop=True)

        dst_csv.parent.mkdir(parents=True, exist_ok=True)
        out.to_csv(dst_csv, index=False)
        
        return {
            "rows": int(len(out)),
            "start": out["timestamp"].iloc[0] if len(out) else None,
            "end": out["timestamp"].iloc[-1] if len(out) else None,
            "path": str(dst_csv),
        }
