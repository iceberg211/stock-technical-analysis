import argparse

ARTIFACT_LEVEL_CHOICES = ("core", "standard", "full")
CASE_MODE_CHOICES = ("rolling", "non_overlap")
DEFAULT_CACHE_FILE = "kline_1h_clean.csv"

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="回测引擎集成主入口 (Pipeline v2)")
    parser.add_argument(
        "--symbols",
        nargs="+",
        required=True,
        help="标的列表，例如 SH.600410 SZ.300033 BTCUSDT",
    )
    parser.add_argument(
        "--interval",
        default="1h",
        help="回测主周期标记（传给提示词与路径），默认 1h",
    )
    parser.add_argument("--repeat", type=int, default=1, help="每个 case 重复调用次数")
    parser.add_argument("--sample", type=int, default=20, help="每个标的采样 case 数")
    parser.add_argument("--step", type=int, default=10, help="滑窗步长")
    parser.add_argument("--lookback", type=int, default=160, help="分析窗口根数")
    parser.add_argument("--forward", type=int, default=40, help="事后评估窗口根数")
    parser.add_argument(
        "--case-mode",
        choices=CASE_MODE_CHOICES,
        default="non_overlap",
        help="切片模式：rolling 或 non_overlap",
    )
    parser.add_argument(
        "--warmup-bars",
        type=int,
        default=120,
        help="切片起点预热根数，避免指标冷启动污染",
    )
    parser.add_argument(
        "--artifact-level",
        choices=ARTIFACT_LEVEL_CHOICES,
        default="standard",
        help="产物留存层级：core|standard|full",
    )
    parser.add_argument(
        "--embed-forward-rows",
        action="store_true",
        help="将 forward_rows 内联写入 runs.jsonl（默认关闭）",
    )
    parser.add_argument(
        "--cache-file",
        default=DEFAULT_CACHE_FILE,
        help=f"原始 K 线文件名（默认 {DEFAULT_CACHE_FILE}）",
    )
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="只做数据准备（输出 eval_input.csv），不跑 LLM 回测",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="可选，覆盖大模型配置（如 gpt-4o / gpt-4o-mini）",
    )
    parser.add_argument(
        "--engine",
        choices=["auto", "openai", "local"],
        default="auto",
        help="回测引擎：openai（大模型）或 local（基于指标规则打底）",
    )
    parser.add_argument(
        "--hide-analysis",
        action="store_true",
        help="不在控制台打印每个案子的分析过程文本",
    )
    return parser.parse_args()
