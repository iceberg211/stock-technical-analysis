# src/config.py
"""
全局配置常量。

通过环境变量覆盖默认值：
    EVAL_MODEL=gpt-4o-mini python -m src ...
"""

import os
from pathlib import Path

# ── 路径 ──────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent  # 项目根目录
EVAL_DIR = REPO_ROOT / "eval"
DEFAULT_RESULTS_DIR = EVAL_DIR / "results"

# ── LLM ───────────────────────────────────────────────
MODEL = os.getenv("EVAL_MODEL", "gpt-4o")
TEMPERATURE_EVAL = float(os.getenv("EVAL_TEMPERATURE", "0.3"))
TEMPERATURE_CONSISTENCY = float(os.getenv("EVAL_TEMP_CONSISTENCY", "0.7"))
MAX_TOKENS = int(os.getenv("EVAL_MAX_TOKENS", "4096"))

# ── 数据窗口 ──────────────────────────────────────────
LOOKBACK_BARS = int(os.getenv("EVAL_LOOKBACK", "200"))   # 分析窗口
FORWARD_BARS = int(os.getenv("EVAL_FORWARD", "50"))      # 事后评估窗口
DEFAULT_REPEAT = int(os.getenv("EVAL_REPEAT", "3"))      # 一致性测试重复次数
DEFAULT_SAMPLE = int(os.getenv("EVAL_SAMPLE", "50"))     # 默认采样数量
DEFAULT_STEP = int(os.getenv("EVAL_STEP", "10"))         # 窗口步进

# ── Skill 文件（按拼接顺序） ─────────────────────────
SKILL_FILES = [
    REPO_ROOT / "SKILL.md",
    REPO_ROOT / "workflows" / "chart-analysis-workflow.md",
    REPO_ROOT / "workflows" / "output-templates.md",
    REPO_ROOT / "workflows" / "trading-decision.md",
]
