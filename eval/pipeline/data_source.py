from pathlib import Path

from eval.pipeline.layout import REPO_ROOT


class DataSource:
    """行情数据源管理器。
    当前支持：从本地 opend_kline 或 data/symbols 缓存目录提取。
    未来可扩展：通过 MCP / ccxt 实盘获取并自动落盘补充。
    """

    @staticmethod
    def get_local_cache_path(symbol: str, cache_file_name: str) -> Path:
        """从历史遗留架构中寻找数据，如果没有，再找新体系内的缓存。"""
        # Legacy opend_kline 路径
        legacy_dir = REPO_ROOT / "data" / "opend_kline" / symbol
        legacy_path = legacy_dir / cache_file_name
        
        if legacy_path.exists():
            return legacy_path

        # TODO: New symbols directory cache check could be added here
        # or implement auto-fetching logic.
        
        return legacy_path

    @staticmethod
    def ensure_data_available(symbol: str, cache_file_name: str) -> Path:
        """确保能够拿到本地历史数据文件，供回测引擎使用。"""
        path = DataSource.get_local_cache_path(symbol, cache_file_name)
        if not path.exists():
            raise FileNotFoundError(f"未找到标的 {symbol} 的本地缓存数据: {path}。目前尚不支持断网空载运行。")
        return path
