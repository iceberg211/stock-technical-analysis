# Project Restructure Implementation Plan (Phase 1-3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the project from chaotic data/eval layout to clean Medallion Architecture with `src/`, signal persistence, and flat output layout.

**Architecture:** Phase 1 migrates data + signals to new directories. Phase 2 renames `eval/` → `src/` with all imports updated. Phase 3 rewrites layout to flat structure, adds signal append mechanism, and wires everything end-to-end.

**Tech Stack:** Python 3.10+, pandas, pyarrow (parquet), pytest

**Spec:** `docs/superpowers/specs/2026-03-27-project-restructure-design.md`

**Scope:** Phase 1-3 only. Phase 4 (ingest adapters) and Phase 5 (signal backtest engine) are separate follow-up plans.

---

## File Map

### New files to create

| File | Responsibility |
|------|---------------|
| `src/__init__.py` | Package marker |
| `src/config.py` | Global config constants (moved from `eval/config.py`) |
| `src/indicators/__init__.py` | Re-export `ema`, `rsi`, `atr`, `add_macd_rsi`, etc. |
| `src/indicators/calc.py` | Indicator calculations (moved from `eval/indicator_calc.py`) |
| `src/pipeline/__init__.py` | Package marker |
| `src/pipeline/cli.py` | CLI arg parsing (moved from `eval/pipeline/cli.py`) |
| `src/pipeline/layout.py` | Flat directory layout (rewritten) |
| `src/pipeline/catalog.py` | Data catalog management (replaces `data_source.py` + `data_store.py`) |
| `src/pipeline/signals.py` | Signal append mechanism (NEW) |
| `src/pipeline/manifest.py` | Run manifest + global registry (moved from `eval/pipeline/manifest.py`) |
| `src/pipeline/backtest.py` | Backtest orchestration (moved from `eval/pipeline/backtest.py`) |
| `src/pipeline/analyze.py` | Local rules engine (moved from `eval/pipeline/analyze.py`) |
| `src/pipeline/retention.py` | Artifact cleanup (moved from `eval/pipeline/retention.py`) |
| `src/pipeline/reporting.py` | Analysis reporting (moved from `eval/pipeline/reporting.py`) |
| `src/scoring/__init__.py` | Package marker |
| `src/scoring/engine.py` | Scoring engine (moved from `eval/score_eval.py`) |
| `src/scoring/validator.py` | Backtest sample validation (extracted from `eval/run_eval.py`) |
| `src/reporting/__init__.py` | Package marker |
| `src/reporting/metrics.py` | Metrics aggregation (extracted from `eval/report.py`) |
| `src/reporting/markdown.py` | Markdown rendering (extracted from `eval/report.py`) |
| `src/prompt/__init__.py` | Package marker |
| `src/prompt/builder.py` | Prompt builder (moved from `eval/prompt_builder.py`) |
| `src/__main__.py` | Entry point for `python -m src` |
| `tests/test_scoring.py` | Scoring tests (moved from `eval/tests/test_eval_v2.py`) |
| `data/catalog.json` | Data catalog index |
| `outputs/signals/BTCUSDT/index.jsonl` | Signal index |

### Files to delete after migration

| File | Reason |
|------|--------|
| `eval/` (entire directory) | Replaced by `src/` |
| `scripts/run_pipeline.py` | Replaced by `src/__main__.py` |
| `scripts/calc_data_mode_indicators.py` | Functionality covered by `src/indicators/calc.py` |
| `scripts/reanalyze_with_opend.py` | Will be replaced in Phase 4 |
| `data/opend_kline/` | Data migrated to `data/clean/` |
| `data/mcp_kline/` | Data migrated to `data/clean/` |
| `data/binance_kline/` | Data migrated to `data/clean/` |
| `outputs/runs/` (3 empty runs) | No useful data, safe to delete |

---

## Task 1: Migrate core asset data (signals + K-line)

**Files:**
- Create: `outputs/signals/BTCUSDT/20260326_170000/snapshot.json`
- Create: `outputs/signals/BTCUSDT/20260326_170000/report.md`
- Create: `outputs/signals/BTCUSDT/index.jsonl`
- Create: `data/clean/BTCUSDT/1h.parquet`
- Create: `data/clean/BTCUSDT/4h.parquet`
- Create: `data/catalog.json`

- [ ] **Step 1: Create signal archive directory and copy snapshot**

```bash
mkdir -p outputs/signals/BTCUSDT/20260326_170000
cp data/binance_kline/BTCUSDT/analysis_skill_snapshot.json outputs/signals/BTCUSDT/20260326_170000/snapshot.json
cp data/binance_kline/BTCUSDT/analysis_skill_report.md outputs/signals/BTCUSDT/20260326_170000/report.md
```

- [ ] **Step 2: Create index.jsonl from snapshot**

```bash
python3 -c "
import json
snap = json.load(open('outputs/signals/BTCUSDT/20260326_170000/snapshot.json'))
entry = {
    'signal_id': '20260326_170000',
    'symbol': 'BTCUSDT',
    'timestamp_utc': snap.get('time_utc', '2026-03-26T17:00:00Z'),
    'price_at_signal': snap.get('price_now'),
    'decision': 'watch',
    'bias': 'bearish',
    'confidence': 'medium',
    'playbook': 'trend-pullback',
    'conditional_entry': 70050,
    'stop_loss': 70680,
    't1': 68150,
    't2': 67450,
    'market_state_4h': snap.get('4h', {}).get('state'),
    'market_state_1h': snap.get('1h', {}).get('state'),
    'rsi_divergence': snap.get('1h', {}).get('rsi_divergence'),
    'path': '20260326_170000/'
}
with open('outputs/signals/BTCUSDT/index.jsonl', 'w') as f:
    f.write(json.dumps(entry, ensure_ascii=False) + '\n')
print('Created index.jsonl')
"
```

- [ ] **Step 3: Convert K-line CSVs to parquet**

```bash
pip install pyarrow  # if not already installed
python3 -c "
import pandas as pd
from pathlib import Path

Path('data/clean/BTCUSDT').mkdir(parents=True, exist_ok=True)

for interval in ('1h', '4h'):
    src = Path(f'data/binance_kline/BTCUSDT/kline_{interval}_accum.csv')
    if not src.exists():
        print(f'SKIP: {src} not found')
        continue
    df = pd.read_csv(src)
    # Normalize column names
    if 'time' in df.columns and 'timestamp' not in df.columns:
        df = df.rename(columns={'time': 'timestamp'})
    df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
    df = df.dropna(subset=['timestamp']).sort_values('timestamp').reset_index(drop=True)
    for col in ('open', 'high', 'low', 'close', 'volume'):
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']].dropna()
    dst = Path(f'data/clean/BTCUSDT/{interval}.parquet')
    df.to_parquet(dst, index=False)
    print(f'{src} ({len(df)} rows) -> {dst}')
"
```

- [ ] **Step 4: Create data/catalog.json**

```bash
python3 -c "
import json, pandas as pd
from pathlib import Path

catalog = {'version': 1, 'symbols': {}}
clean_dir = Path('data/clean')
for sym_dir in sorted(clean_dir.iterdir()):
    if not sym_dir.is_dir():
        continue
    symbol = sym_dir.name
    intervals = {}
    for pq in sorted(sym_dir.glob('*.parquet')):
        df = pd.read_parquet(pq)
        intervals[pq.stem] = {
            'rows': len(df),
            'start': str(df['timestamp'].min()),
            'end': str(df['timestamp'].max()),
            'file': str(pq.relative_to(Path('.'))),
        }
    catalog['symbols'][symbol] = intervals

Path('data/catalog.json').write_text(json.dumps(catalog, indent=2, ensure_ascii=False))
print(json.dumps(catalog, indent=2, ensure_ascii=False))
"
```

- [ ] **Step 5: Verify migrated data**

```bash
python3 -c "
import pandas as pd, json
df = pd.read_parquet('data/clean/BTCUSDT/1h.parquet')
print(f'1h.parquet: {len(df)} rows, {df.timestamp.min()} to {df.timestamp.max()}')
idx = open('outputs/signals/BTCUSDT/index.jsonl').readline()
print(f'Signal index: {json.loads(idx)[\"signal_id\"]}')
cat = json.load(open('data/catalog.json'))
print(f'Catalog symbols: {list(cat[\"symbols\"].keys())}')
"
```

Expected: 1h.parquet has 8760+ rows, signal_id is 20260326_170000, catalog lists BTCUSDT.

- [ ] **Step 6: Commit**

```bash
git add outputs/signals/ data/clean/ data/catalog.json
git commit -m "feat: migrate core assets to new Medallion structure

- Signals archived to outputs/signals/BTCUSDT/20260326_170000/
- K-line data converted to parquet in data/clean/BTCUSDT/
- Created data/catalog.json index"
```

---

## Task 2: Clean up old data directories and update .gitignore

**Files:**
- Delete: `data/opend_kline/`, `data/mcp_kline/`, `data/binance_kline/`
- Delete: `outputs/runs/` (3 empty runs)
- Delete: `data/registry/`
- Modify: `.gitignore`

- [ ] **Step 1: Remove old data directories from git tracking**

```bash
git rm -r --cached data/opend_kline/ data/mcp_kline/ data/binance_kline/ data/registry/ 2>/dev/null || true
git rm -r --cached outputs/runs/ 2>/dev/null || true
```

- [ ] **Step 2: Delete old directories from disk**

```bash
rm -rf data/opend_kline/ data/mcp_kline/ data/binance_kline/ data/registry/
rm -rf outputs/runs/
```

- [ ] **Step 3: Update .gitignore**

Replace the entire `.gitignore` with:

```gitignore
# macOS / 系统文件
.DS_Store

# Python 缓存与虚拟环境
__pycache__/
*.py[cod]
*.so
.python-version
.venv/
venv/
env/

# 测试与工具缓存
.pytest_cache/
.mypy_cache/
.ruff_cache/

# 本地环境变量
.env
.env.*

# 通用日志
*.log

# ── 行情数据（可重新拉取）──
data/raw/
data/clean/

# ── 回测运行产物（可重新生成）──
outputs/runs/

# ── 保留入 git 的关键文件 ──
# data/catalog.json       — 数据目录索引
# outputs/signals/        — 模型分析信号（核心资产）
# outputs/registry.jsonl  — 全局运行索引
```

- [ ] **Step 4: Verify clean state**

```bash
git status
# Should show: deleted data files, modified .gitignore, no untracked data files
ls data/
# Should show: catalog.json  clean/  (clean/ is gitignored)
ls outputs/
# Should show: signals/
```

- [ ] **Step 5: Commit**

```bash
git add .gitignore
git add -u  # stage deletions
git commit -m "chore: remove old data directories, update .gitignore

- Deleted opend_kline/, mcp_kline/, binance_kline/ (migrated to data/clean/)
- Deleted 3 empty run outputs
- .gitignore now excludes data/raw/, data/clean/, outputs/runs/
- Signals and catalog.json preserved in git"
```

---

## Task 3: Create src/ package structure with __init__.py files

**Files:**
- Create: `src/__init__.py`, `src/indicators/__init__.py`, `src/pipeline/__init__.py`, `src/scoring/__init__.py`, `src/reporting/__init__.py`, `src/prompt/__init__.py`

- [ ] **Step 1: Create all package directories and __init__.py files**

```bash
mkdir -p src/indicators src/pipeline src/scoring src/reporting src/prompt tests
```

```python
# src/__init__.py
```

```python
# src/indicators/__init__.py
from src.indicators.calc import ema, rsi, atr, add_macd_rsi, add_all_indicators, maybe_float, normalize_ohlcv_df, indicator_snapshot_from_rows
```

```python
# src/pipeline/__init__.py
```

```python
# src/scoring/__init__.py
```

```python
# src/reporting/__init__.py
```

```python
# src/prompt/__init__.py
```

- [ ] **Step 2: Commit skeleton**

```bash
git add src/ tests/
git commit -m "chore: create src/ package skeleton"
```

---

## Task 4: Move indicator_calc.py → src/indicators/calc.py

**Files:**
- Create: `src/indicators/calc.py` (copy from `eval/indicator_calc.py`)
- Test: `tests/test_indicators.py`

- [ ] **Step 1: Write test for indicators**

```python
# tests/test_indicators.py
import unittest
import pandas as pd
import numpy as np


class TestIndicators(unittest.TestCase):
    def _make_df(self, n: int = 100) -> pd.DataFrame:
        np.random.seed(42)
        close = 100 + np.cumsum(np.random.randn(n) * 0.5)
        return pd.DataFrame({
            "timestamp": pd.date_range("2026-01-01", periods=n, freq="h"),
            "open": close - 0.1,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": np.random.rand(n) * 1000,
        })

    def test_ema_length(self):
        from src.indicators.calc import ema
        df = self._make_df()
        result = ema(df["close"], 12)
        self.assertEqual(len(result), len(df))

    def test_rsi_range(self):
        from src.indicators.calc import rsi
        df = self._make_df()
        result = rsi(df["close"], 14).dropna()
        self.assertTrue((result >= 0).all() and (result <= 100).all())

    def test_atr_positive(self):
        from src.indicators.calc import atr
        df = self._make_df()
        result = atr(df, 14).dropna()
        self.assertTrue((result > 0).all())

    def test_add_all_indicators_columns(self):
        from src.indicators.calc import add_all_indicators
        df = self._make_df()
        out = add_all_indicators(df)
        for col in ("ma20", "ma60", "rsi14", "atr14", "macd", "signal", "hist"):
            self.assertIn(col, out.columns, f"Missing column: {col}")

    def test_maybe_float_nan(self):
        from src.indicators.calc import maybe_float
        self.assertIsNone(maybe_float(None))
        self.assertIsNone(maybe_float(float("nan")))
        self.assertEqual(maybe_float(3.14159, 2), 3.14)

    def test_normalize_ohlcv_df_renames_time(self):
        from src.indicators.calc import normalize_ohlcv_df
        df = pd.DataFrame({
            "time": ["2026-01-01T00:00:00Z"],
            "open": [100], "high": [101], "low": [99],
            "close": [100], "volume": [10],
        })
        out = normalize_ohlcv_df(df)
        self.assertIn("timestamp", out.columns)
        self.assertEqual(len(out), 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_indicators.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.indicators.calc'`

- [ ] **Step 3: Copy indicator_calc.py to new location**

```bash
cp eval/indicator_calc.py src/indicators/calc.py
```

No import changes needed inside calc.py — it only imports numpy and pandas.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_indicators.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/indicators/calc.py tests/test_indicators.py
git commit -m "feat: move indicator_calc.py to src/indicators/calc.py with tests"
```

---

## Task 5: Move config.py → src/config.py

**Files:**
- Create: `src/config.py` (adapted from `eval/config.py`)

- [ ] **Step 1: Create src/config.py**

```python
# src/config.py
"""
全局配置常量。

通过环境变量覆盖默认值：
    EVAL_MODEL=gpt-4o-mini python -m src ...
"""

import os
from pathlib import Path

# ── 路径 ──────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parent.parent

# ── LLM ───────────────────────────────────────────────
MODEL = os.getenv("EVAL_MODEL", "gpt-4o")
TEMPERATURE_EVAL = float(os.getenv("EVAL_TEMPERATURE", "0.3"))
TEMPERATURE_CONSISTENCY = float(os.getenv("EVAL_TEMP_CONSISTENCY", "0.7"))
MAX_TOKENS = int(os.getenv("EVAL_MAX_TOKENS", "4096"))

# ── 数据窗口 ──────────────────────────────────────────
LOOKBACK_BARS = int(os.getenv("EVAL_LOOKBACK", "200"))
FORWARD_BARS = int(os.getenv("EVAL_FORWARD", "50"))
DEFAULT_REPEAT = int(os.getenv("EVAL_REPEAT", "3"))
DEFAULT_SAMPLE = int(os.getenv("EVAL_SAMPLE", "50"))
DEFAULT_STEP = int(os.getenv("EVAL_STEP", "10"))

# ── Skill 文件（按拼接顺序） ─────────────────────────
SKILL_FILES = [
    REPO_ROOT / "SKILL.md",
    REPO_ROOT / "workflows" / "chart-analysis-workflow.md",
    REPO_ROOT / "workflows" / "output-templates.md",
    REPO_ROOT / "workflows" / "trading-decision.md",
]
```

- [ ] **Step 2: Verify import works**

Run: `python -c "from src.config import REPO_ROOT; print(REPO_ROOT)"`
Expected: prints the project root path

- [ ] **Step 3: Commit**

```bash
git add src/config.py
git commit -m "feat: move config.py to src/config.py"
```

---

## Task 6: Move prompt_builder.py → src/prompt/builder.py

**Files:**
- Create: `src/prompt/builder.py` (from `eval/prompt_builder.py`)

- [ ] **Step 1: Copy and update imports**

```bash
cp eval/prompt_builder.py src/prompt/builder.py
```

Then edit `src/prompt/builder.py` — change:
```python
# OLD
from eval.indicator_calc import add_macd_rsi, indicator_snapshot_from_rows
from eval.config import SKILL_FILES
```
to:
```python
# NEW
from src.indicators.calc import add_macd_rsi, indicator_snapshot_from_rows
from src.config import SKILL_FILES
```

- [ ] **Step 2: Verify import works**

Run: `python -c "from src.prompt.builder import build_system_prompt; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/prompt/builder.py
git commit -m "feat: move prompt_builder.py to src/prompt/builder.py"
```

---

## Task 7: Move scoring engine (score_eval.py → src/scoring/engine.py)

**Files:**
- Create: `src/scoring/engine.py` (from `eval/score_eval.py`)

- [ ] **Step 1: Copy and verify standalone**

```bash
cp eval/score_eval.py src/scoring/engine.py
```

`score_eval.py` only imports `pandas`, `argparse`, `json`, `sys`, `pathlib` — no internal project imports. No changes needed.

- [ ] **Step 2: Verify import**

Run: `python -c "from src.scoring.engine import score_trade, score_runs; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/scoring/engine.py
git commit -m "feat: move score_eval.py to src/scoring/engine.py"
```

---

## Task 8: Extract validator from run_eval.py → src/scoring/validator.py

**Files:**
- Create: `src/scoring/validator.py` (extract `validate_backtest_sample`, `extract_json`, `make_cases` from `eval/run_eval.py`)

- [ ] **Step 1: Create validator.py with extracted functions**

Read `eval/run_eval.py` and extract the three functions that are used by other modules: `validate_backtest_sample`, `extract_json`, `make_cases`. These functions do not depend on OpenAI or LLM code.

```python
# src/scoring/validator.py
"""Backtest sample validation and case generation utilities."""

from __future__ import annotations

import json
import re
from typing import Any

import pandas as pd
```

Copy the body of `validate_backtest_sample`, `extract_json`, and `make_cases` from `eval/run_eval.py` into this file. These functions have no internal imports — they only use `json`, `re`, `pandas`.

- [ ] **Step 2: Verify import**

Run: `python -c "from src.scoring.validator import validate_backtest_sample, make_cases; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/scoring/validator.py
git commit -m "feat: extract validator.py from run_eval.py"
```

---

## Task 9: Move reporting (report.py → src/reporting/metrics.py + markdown.py)

**Files:**
- Create: `src/reporting/metrics.py` (from `eval/report.py` — metrics computation functions)
- Create: `src/reporting/markdown.py` (from `eval/report.py` — rendering functions)

- [ ] **Step 1: Split report.py**

`eval/report.py` has two clear halves:
1. **Metrics functions** (`build_metrics`, `build_playbook_breakdown`, `build_confidence_diagnostics`, `build_market_state_breakdown`, `build_consistency`, `load_scored`) → `src/reporting/metrics.py`
2. **Markdown renderers** (`render_summary_markdown`, `render_details_markdown`) → `src/reporting/markdown.py`

Copy each half. Neither has internal project imports — they only use `pandas`, `json`, `statistics`, `pathlib`.

- [ ] **Step 2: Verify imports**

Run:
```bash
python -c "from src.reporting.metrics import build_metrics, load_scored; print('metrics OK')"
python -c "from src.reporting.markdown import render_summary_markdown, render_details_markdown; print('markdown OK')"
```
Expected: Both print OK

- [ ] **Step 3: Commit**

```bash
git add src/reporting/metrics.py src/reporting/markdown.py
git commit -m "feat: split report.py into src/reporting/metrics.py + markdown.py"
```

---

## Task 10: Move pipeline modules to src/pipeline/

**Files:**
- Create: `src/pipeline/cli.py` (from `eval/pipeline/cli.py`)
- Create: `src/pipeline/analyze.py` (from `eval/pipeline/analyze.py`)
- Create: `src/pipeline/retention.py` (from `eval/pipeline/retention.py`)
- Create: `src/pipeline/reporting.py` (from `eval/pipeline/reporting.py`)
- Create: `src/pipeline/manifest.py` (from `eval/pipeline/manifest.py`)

- [ ] **Step 1: Copy all pipeline modules and update imports**

```bash
cp eval/pipeline/cli.py src/pipeline/cli.py
cp eval/pipeline/analyze.py src/pipeline/analyze.py
cp eval/pipeline/retention.py src/pipeline/retention.py
cp eval/pipeline/reporting.py src/pipeline/reporting.py
cp eval/pipeline/manifest.py src/pipeline/manifest.py
```

Update imports in each file — replace all `from eval.` with `from src.`:

In `src/pipeline/analyze.py`:
```python
# OLD
from eval.indicator_calc import ema, rsi, atr, add_all_indicators
# NEW
from src.indicators.calc import ema, rsi, atr, add_all_indicators
```

In `src/pipeline/retention.py`:
```python
# OLD
from eval.pipeline.layout import SymbolLayout
# NEW
from src.pipeline.layout import SymbolLayout
```

In `src/pipeline/manifest.py`:
```python
# OLD
from eval.pipeline.layout import RunLayout, DataLayout
# NEW
from src.pipeline.layout import RunLayout
```

In `src/pipeline/reporting.py`:
```python
# OLD (if any eval.* imports exist)
# NEW — change all eval.* to src.*
```

`src/pipeline/cli.py` has no internal imports — no changes needed.

- [ ] **Step 2: Verify imports**

```bash
python -c "from src.pipeline.cli import parse_args; print('cli OK')"
python -c "from src.pipeline.analyze import build_local_backtest_sample; print('analyze OK')"
```

Expected: Both OK (layout.py not moved yet, so manifest/retention may fail — that's expected and will be fixed in Task 11)

- [ ] **Step 3: Commit**

```bash
git add src/pipeline/cli.py src/pipeline/analyze.py src/pipeline/retention.py src/pipeline/reporting.py src/pipeline/manifest.py
git commit -m "feat: move pipeline modules to src/pipeline/"
```

---

## Task 11: Rewrite layout.py — flat structure (Phase 3 core)

**Files:**
- Create: `src/pipeline/layout.py` (rewritten — flat, no human/machine/data/debug)

- [ ] **Step 1: Write test for new layout**

```python
# tests/test_layout.py
import unittest
import tempfile
from pathlib import Path


class TestLayout(unittest.TestCase):
    def test_symbol_layout_flat_paths(self):
        from src.pipeline.layout import SymbolLayout
        sl = SymbolLayout(Path("/tmp/test_run/BTCUSDT"))
        # All files should be directly under base_dir — no human/machine/data subdirs
        self.assertEqual(sl.config_json, Path("/tmp/test_run/BTCUSDT/config.json"))
        self.assertEqual(sl.runs_jsonl, Path("/tmp/test_run/BTCUSDT/runs.jsonl"))
        self.assertEqual(sl.scored_jsonl, Path("/tmp/test_run/BTCUSDT/scored.jsonl"))
        self.assertEqual(sl.metrics_json, Path("/tmp/test_run/BTCUSDT/metrics.json"))
        self.assertEqual(sl.summary_md, Path("/tmp/test_run/BTCUSDT/summary.md"))
        self.assertEqual(sl.details_md, Path("/tmp/test_run/BTCUSDT/details.md"))
        self.assertEqual(sl.input_parquet, Path("/tmp/test_run/BTCUSDT/input.parquet"))

    def test_run_layout_relative_manifest(self):
        from src.pipeline.layout import RunLayout
        rl = RunLayout("20260327_120000_btcusdt")
        sl = rl.get_symbol_layout("BTCUSDT")
        self.assertTrue(str(sl.base_dir).endswith("BTCUSDT"))

    def test_symbol_layout_setup_creates_dir(self):
        from src.pipeline.layout import SymbolLayout
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            sl = SymbolLayout(Path(td) / "BTCUSDT")
            sl.setup()
            self.assertTrue(sl.base_dir.exists())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_layout.py -v`
Expected: FAIL — `ModuleNotFoundError` or `AttributeError`

- [ ] **Step 3: Write new flat layout.py**

```python
# src/pipeline/layout.py
"""
目录结构定义 — 扁平化布局。

SymbolLayout: 单个 symbol 在一次回测 run 中的所有文件（扁平，无子目录）。
RunLayout: 一次完整回测批次的目录。
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

    # ── 兼容旧代码过渡（Phase 2 迁移期间临时保留） ──
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_layout.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/layout.py tests/test_layout.py
git commit -m "feat: rewrite layout.py with flat structure (no human/machine/data subdirs)"
```

---

## Task 12: Create catalog.py (replaces data_source.py + data_store.py)

**Files:**
- Create: `src/pipeline/catalog.py`
- Test: `tests/test_catalog.py`

- [ ] **Step 1: Write test**

```python
# tests/test_catalog.py
import unittest
import tempfile
import json
from pathlib import Path

import pandas as pd


class TestCatalog(unittest.TestCase):
    def test_read_clean_parquet(self):
        from src.pipeline.catalog import Catalog
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            clean_dir = root / "data" / "clean" / "BTCUSDT"
            clean_dir.mkdir(parents=True)
            df = pd.DataFrame({
                "timestamp": pd.date_range("2026-01-01", periods=10, freq="h"),
                "open": range(10), "high": range(10),
                "low": range(10), "close": range(10), "volume": range(10),
            })
            df.to_parquet(clean_dir / "1h.parquet", index=False)

            cat = Catalog(root)
            result = cat.read_clean("BTCUSDT", "1h")
            self.assertEqual(len(result), 10)
            self.assertIn("timestamp", result.columns)

    def test_read_clean_missing_raises(self):
        from src.pipeline.catalog import Catalog
        with tempfile.TemporaryDirectory() as td:
            cat = Catalog(Path(td))
            with self.assertRaises(FileNotFoundError):
                cat.read_clean("NOPE", "1h")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_catalog.py -v`
Expected: FAIL

- [ ] **Step 3: Implement catalog.py**

```python
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
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_catalog.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/catalog.py tests/test_catalog.py
git commit -m "feat: create catalog.py (replaces data_source.py + data_store.py)"
```

---

## Task 13: Create signals.py — Signal Append mechanism

**Files:**
- Create: `src/pipeline/signals.py`
- Test: `tests/test_signals.py`

- [ ] **Step 1: Write test**

```python
# tests/test_signals.py
import unittest
import tempfile
import json
from pathlib import Path


class TestSignals(unittest.TestCase):
    def test_append_signal_creates_directory_and_index(self):
        from src.pipeline.signals import append_signal
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            snapshot = {
                "time_utc": "2026-03-27T12:00:00Z",
                "price_now": 70000,
                "1h": {"state": "downtrend"},
                "4h": {"state": "downtrend"},
            }
            report_md = "# Test Report\nBTC is bearish."
            signal_meta = {
                "decision": "watch",
                "bias": "bearish",
                "confidence": "medium",
                "playbook": "trend-pullback",
                "conditional_entry": 70050,
                "stop_loss": 70680,
                "t1": 68150,
                "t2": 67450,
            }

            result = append_signal(
                symbol="BTCUSDT",
                snapshot=snapshot,
                report_md=report_md,
                signal_meta=signal_meta,
                outputs_root=root / "outputs",
            )

            # Verify files created
            self.assertTrue(result["snapshot_path"].exists())
            self.assertTrue(result["report_path"].exists())
            self.assertTrue(result["index_path"].exists())

            # Verify index.jsonl has one line
            lines = result["index_path"].read_text().strip().split("\n")
            self.assertEqual(len(lines), 1)
            entry = json.loads(lines[0])
            self.assertEqual(entry["symbol"], "BTCUSDT")
            self.assertEqual(entry["decision"], "watch")
            self.assertEqual(entry["stop_loss"], 70680)

    def test_append_signal_never_overwrites(self):
        from src.pipeline.signals import append_signal
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            kwargs = dict(
                symbol="BTCUSDT",
                snapshot={"time_utc": "2026-03-27T12:00:00Z", "price_now": 70000},
                report_md="report",
                signal_meta={"decision": "long", "bias": "bullish"},
                outputs_root=root / "outputs",
            )
            r1 = append_signal(**kwargs)
            r2 = append_signal(**kwargs)

            # Two different directories
            self.assertNotEqual(r1["signal_dir"], r2["signal_dir"])

            # Index has 2 lines
            lines = r1["index_path"].read_text().strip().split("\n")
            self.assertEqual(len(lines), 2)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_signals.py -v`
Expected: FAIL

- [ ] **Step 3: Implement signals.py**

```python
# src/pipeline/signals.py
"""
Signal Append 机制：每次分析输出追加到 outputs/signals/，永不覆盖。

核心函数：append_signal() — Skill 每次分析后调用。
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.pipeline.layout import REPO_ROOT


def append_signal(
    symbol: str,
    snapshot: dict[str, Any],
    report_md: str,
    signal_meta: dict[str, Any] | None = None,
    outputs_root: Path | None = None,
) -> dict[str, Path]:
    """
    追加一条分析信号到 outputs/signals/{symbol}/{timestamp}/.

    Parameters
    ----------
    symbol : str
        标的代码，如 BTCUSDT
    snapshot : dict
        结构化信号数据（snapshot.json 内容）
    report_md : str
        人可读分析报告文本
    signal_meta : dict, optional
        额外元数据（decision, bias, confidence, entry, stop, t1, t2 等）
    outputs_root : Path, optional
        输出根目录，默认 REPO_ROOT / "outputs"

    Returns
    -------
    dict with keys: signal_dir, snapshot_path, report_path, index_path
    """
    outputs_root = outputs_root or (REPO_ROOT / "outputs")
    signals_dir = outputs_root / "signals" / symbol

    # 生成唯一时间戳目录（精确到秒，冲突时追加序号）
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    signal_dir = signals_dir / ts
    counter = 1
    while signal_dir.exists():
        signal_dir = signals_dir / f"{ts}_{counter:02d}"
        counter += 1

    signal_dir.mkdir(parents=True, exist_ok=True)

    # 写 snapshot.json
    snapshot_path = signal_dir / "snapshot.json"
    snapshot_path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 写 report.md
    report_path = signal_dir / "report.md"
    report_path.write_text(report_md, encoding="utf-8")

    # 构建 index 条目
    meta = signal_meta or {}
    index_entry = {
        "signal_id": signal_dir.name,
        "symbol": symbol,
        "timestamp_utc": snapshot.get("time_utc", datetime.now(timezone.utc).isoformat()),
        "price_at_signal": snapshot.get("price_now"),
        "decision": meta.get("decision"),
        "bias": meta.get("bias"),
        "confidence": meta.get("confidence"),
        "playbook": meta.get("playbook"),
        "conditional_entry": meta.get("conditional_entry"),
        "stop_loss": meta.get("stop_loss"),
        "t1": meta.get("t1"),
        "t2": meta.get("t2"),
        "market_state_4h": snapshot.get("4h", {}).get("state") if isinstance(snapshot.get("4h"), dict) else None,
        "market_state_1h": snapshot.get("1h", {}).get("state") if isinstance(snapshot.get("1h"), dict) else None,
        "rsi_divergence": snapshot.get("1h", {}).get("rsi_divergence") if isinstance(snapshot.get("1h"), dict) else None,
        "path": f"{signal_dir.name}/",
    }

    # 追加到 index.jsonl
    index_path = signals_dir / "index.jsonl"
    with index_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(index_entry, ensure_ascii=False) + "\n")

    return {
        "signal_dir": signal_dir,
        "snapshot_path": snapshot_path,
        "report_path": report_path,
        "index_path": index_path,
    }
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_signals.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/signals.py tests/test_signals.py
git commit -m "feat: implement Signal Append mechanism (outputs/signals/)"
```

---

## Task 14: Rewrite backtest.py for new structure

**Files:**
- Modify: `src/pipeline/backtest.py`

- [ ] **Step 1: Rewrite backtest.py with new imports**

```python
# src/pipeline/backtest.py
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from src.scoring.validator import make_cases, validate_backtest_sample
from src.scoring.engine import score_runs as _score_runs, _load_csv_df
from src.reporting.metrics import (
    build_metrics,
    build_playbook_breakdown,
    build_confidence_diagnostics,
    build_market_state_breakdown,
    build_consistency,
)
from src.reporting.markdown import render_summary_markdown, render_details_markdown
from src.pipeline.layout import SymbolLayout, REPO_ROOT
from src.pipeline.analyze import build_local_backtest_sample
from src.pipeline.reporting import build_analysis_report


def _write_case_artifacts(
    case_dir: Path,
    sample: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, str]:
    case_dir.mkdir(parents=True, exist_ok=True)
    sample_file = case_dir / "backtest_sample_v1.json"
    report_file = case_dir / "analysis_report.md"

    sample_file.write_text(json.dumps(sample, ensure_ascii=False, indent=2), encoding="utf-8")
    report_file.write_text(build_analysis_report(sample, context), encoding="utf-8")

    return {
        "sample_json": str(sample_file),
        "analysis_report": str(report_file),
    }


def generate_local_runs(
    eval_csv: Path,
    symbol: str,
    interval: str,
    layout: SymbolLayout,
    repeat: int,
    sample: int,
    step: int,
    lookback: int,
    forward: int,
    case_mode: str,
    warmup_bars: int,
    embed_forward_rows: bool,
    write_case_artifacts: bool,
) -> dict[str, Any]:
    """本地兜底引擎运行主循环"""
    df = pd.read_csv(eval_csv)
    cases = make_cases(df, lookback, forward, sample, step, case_mode=case_mode, warmup_bars=warmup_bars)

    out_runs_file = layout.runs_jsonl
    out_runs_file.parent.mkdir(parents=True, exist_ok=True)

    total_runs, parse_errors = 0, 0
    artifact_rows: list[dict[str, Any]] = []

    with out_runs_file.open("w", encoding="utf-8") as f:
        for case in cases:
            for run_id in range(repeat):
                payload, context = build_local_backtest_sample(
                    case["analysis_rows"], symbol, interval, case["case_id"], lookback, forward
                )
                ok, err, normalized = validate_backtest_sample(payload, case["case_id"])
                parse_error = not ok
                if parse_error:
                    parse_errors += 1

                artifacts: dict[str, str] = {}
                if write_case_artifacts:
                    case_dir = layout.base_dir / "cases" / case["case_id"] / f"run_{run_id:02d}"
                    artifacts = _write_case_artifacts(case_dir, normalized if normalized is not None else payload, context)

                analysis_start = int(case.get("analysis_start", -1))
                forward_rows = []
                if "forward_rows" in case and case["forward_rows"] is not None:
                    forward_rows = case["forward_rows"]
                elif analysis_start >= 0:
                    f_start, f_end = analysis_start + lookback, analysis_start + lookback + forward
                    forward_rows = df.iloc[f_start:f_end].to_dict("records")

                run_record = {
                    "run_schema_version": "run_v2",
                    "run_id": run_id,
                    "case_id": case["case_id"],
                    "analysis_start": analysis_start,
                    "symbol": symbol,
                    "interval": interval,
                    "temperature": 0.0,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "parse_error": parse_error,
                    "validation_error": err,
                    "parsed_json": normalized if normalized is not None else payload,
                    "raw_response_preview": "generated_by_local_skill_engine",
                }
                if embed_forward_rows:
                    run_record["forward_rows"] = forward_rows
                if artifacts:
                    run_record["artifacts"] = artifacts
                f.write(json.dumps(run_record, ensure_ascii=False, default=str) + "\n")

                total_runs += 1
                if artifacts:
                    artifact_rows.append({"case_id": case["case_id"], "run_id": run_id, **artifacts})

    return {"cases": len(cases), "runs": total_runs, "parse_errors": parse_errors}


def score_and_report(layout: SymbolLayout, slippage_pct: float = 0.0005, fee_pct: float = 0.001) -> None:
    """直接调用评分和报告函数。"""
    runs_file = layout.runs_jsonl
    if not runs_file.exists():
        raise FileNotFoundError(f"runs.jsonl 不存在: {runs_file}")

    config: dict[str, Any] = {}
    if layout.config_json.exists():
        config = json.loads(layout.config_json.read_text(encoding="utf-8"))

    primary_csv_path = config.get("csv") or config.get("args", {}).get("csv")
    lookback = int(config.get("lookback", config.get("args", {}).get("lookback", 200)))
    forward = int(config.get("forward", config.get("args", {}).get("forward", 50)))

    primary_df = _load_csv_df(primary_csv_path)
    fallback_df = None
    fallback_path = layout.eval_input_csv
    if fallback_path.exists():
        fallback_df = _load_csv_df(str(fallback_path))

    scored, source_stats = _score_runs(
        runs_file=runs_file,
        primary_df=primary_df,
        fallback_df=fallback_df,
        default_lookback=lookback,
        default_forward=forward,
        slippage_pct=slippage_pct,
        fee_pct=fee_pct,
    )

    with layout.scored_jsonl.open("w", encoding="utf-8") as f:
        for s in scored:
            f.write(json.dumps(s, ensure_ascii=False, default=str) + "\n")

    metrics = build_metrics(scored)
    playbook_rows = build_playbook_breakdown(scored)
    confidence_rows = build_confidence_diagnostics(scored)
    market_state_rows = build_market_state_breakdown(scored)
    consistency = build_consistency(scored)

    summary_md = render_summary_markdown(layout.scored_jsonl.name, metrics)
    details_md = render_details_markdown(
        scored_name=layout.scored_jsonl.name,
        metrics=metrics,
        playbook_rows=playbook_rows,
        confidence_rows=confidence_rows,
        market_state_rows=market_state_rows,
        consistency=consistency,
    )

    layout.base_dir.mkdir(parents=True, exist_ok=True)
    layout.summary_md.write_text(summary_md, encoding="utf-8")
    layout.details_md.write_text(details_md, encoding="utf-8")
    layout.metrics_json.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
```

- [ ] **Step 2: Verify import chain**

```bash
python -c "from src.pipeline.backtest import generate_local_runs, score_and_report; print('OK')"
```

Expected: OK

- [ ] **Step 3: Commit**

```bash
git add src/pipeline/backtest.py
git commit -m "feat: rewrite backtest.py with new imports and flat layout"
```

---

## Task 15: Create __main__.py entry point and manifest.py

**Files:**
- Create: `src/__main__.py` (replaces `scripts/run_pipeline.py`)
- Modify: `src/pipeline/manifest.py` (update for new layout)

- [ ] **Step 1: Create src/__main__.py**

```python
# src/__main__.py
"""
Pipeline 主入口。

用法：
    python -m src --symbols BTCUSDT --interval 1h
    python -m src --symbols BTCUSDT ETHUSDT --engine local --sample 5
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.pipeline.cli import parse_args
from src.pipeline.layout import RunLayout, REPO_ROOT
from src.pipeline.manifest import RunManifest, GlobalRegistry
from src.pipeline.catalog import Catalog
from src.pipeline.backtest import generate_local_runs, score_and_report
from src.pipeline.reporting import score_summary
from src.pipeline.retention import apply_artifact_retention


def normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper()


def main():
    args = parse_args()
    symbols = [normalize_symbol(s) for s in args.symbols]
    run_ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    tag = "_".join(s.lower().replace(".", "") for s in symbols)
    run_id = f"{run_ts}_{tag}"

    layout = RunLayout(run_id)
    manifest = RunManifest(layout, symbols, vars(args))
    catalog = Catalog()

    for symbol in symbols:
        sym_layout = layout.get_symbol_layout(symbol)
        item = {"symbol": symbol, "status": "unknown"}

        try:
            sym_layout.setup()

            # 从 clean parquet 准备 eval CSV
            interval = args.interval.replace("h", "h").replace("d", "d")  # normalize
            item["input"] = catalog.prepare_eval_input(symbol, interval, sym_layout.eval_input_csv)

            config_record = {"run_id": run_id, "symbol": symbol, "args": vars(args)}
            sym_layout.config_json.write_text(json.dumps(config_record, ensure_ascii=False, indent=2))

            if args.prepare_only:
                item["status"] = "prepared"
                manifest.add_symbol_item(item)
                GlobalRegistry.append_run(run_id, symbol, args.interval, "prepared", str(sym_layout.base_dir))
                continue

            meta = generate_local_runs(
                sym_layout.eval_input_csv, symbol, args.interval, sym_layout,
                args.repeat, args.sample, args.step, args.lookback, args.forward,
                args.case_mode, args.warmup_bars, args.embed_forward_rows,
                write_case_artifacts=(args.artifact_level == "full"),
            )
            item["local_generation"] = meta

            score_and_report(sym_layout)

            apply_artifact_retention(sym_layout, args.artifact_level)

            item["status"] = "done"
            item["summary"] = score_summary(sym_layout.scored_jsonl)
            GlobalRegistry.append_run(run_id, symbol, args.interval, "done", str(sym_layout.base_dir))

        except Exception as e:
            item["status"] = "failed"
            item["error"] = str(e)
            GlobalRegistry.append_run(run_id, symbol, args.interval, "failed", str(sym_layout.base_dir), error=str(e))

        manifest.add_symbol_item(item)

    manifest.save()
    print(f"\n✅ 批次 {run_id} 执行完毕，Manifest: {layout.manifest_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Update manifest.py for new layout**

In `src/pipeline/manifest.py`, update the import:

```python
# OLD
from eval.pipeline.layout import RunLayout, DataLayout
# NEW
from src.pipeline.layout import RunLayout, REPO_ROOT
```

Update `GlobalRegistry.append_run` to write to `outputs/registry.jsonl`:

```python
@staticmethod
def append_run(...) -> None:
    registry_file = REPO_ROOT / "outputs" / "registry.jsonl"
    registry_file.parent.mkdir(parents=True, exist_ok=True)
    # ... rest stays the same
```

- [ ] **Step 3: Test entry point**

```bash
python -m src --symbols BTCUSDT --interval 1h --engine local --sample 1 --prepare-only
```

Expected: Creates a run directory under `outputs/runs/` with `eval_input.csv` and status `prepared`.

- [ ] **Step 4: Commit**

```bash
git add src/__main__.py src/pipeline/manifest.py
git commit -m "feat: create src/__main__.py entry point (replaces scripts/run_pipeline.py)"
```

---

## Task 16: Migrate tests and verify full test suite

**Files:**
- Create: `tests/test_scoring.py` (from `eval/tests/test_eval_v2.py`)

- [ ] **Step 1: Copy and update imports in test file**

```bash
cp eval/tests/test_eval_v2.py tests/test_scoring.py
```

Edit `tests/test_scoring.py` — change:
```python
# OLD
from eval.report import build_metrics
from eval.run_eval import make_cases
from eval.score_eval import score_runs
# NEW
from src.reporting.metrics import build_metrics
from src.scoring.validator import make_cases
from src.scoring.engine import score_runs
```

- [ ] **Step 2: Run all tests**

```bash
python -m pytest tests/ -v
```

Expected: All tests pass (test_scoring.py: 4, test_indicators.py: 6, test_layout.py: 3, test_catalog.py: 2, test_signals.py: 2 = 17 total)

- [ ] **Step 3: Commit**

```bash
git add tests/test_scoring.py
git commit -m "feat: migrate tests to tests/ with new imports"
```

---

## Task 17: Delete old eval/ and scripts/ directories

**Files:**
- Delete: `eval/` (entire directory)
- Delete: `scripts/run_pipeline.py`
- Delete: `scripts/calc_data_mode_indicators.py`

- [ ] **Step 1: Remove old files from git**

```bash
git rm -r eval/
git rm scripts/run_pipeline.py
git rm scripts/calc_data_mode_indicators.py
```

Note: Keep `scripts/reanalyze_with_opend.py` for now — it will be replaced in Phase 4.

- [ ] **Step 2: Run tests to confirm nothing breaks**

```bash
python -m pytest tests/ -v
```

Expected: All 17 tests PASS (no test imports `eval.*` anymore)

- [ ] **Step 3: Verify entry point still works**

```bash
python -m src --symbols BTCUSDT --interval 1h --engine local --sample 1 --prepare-only
```

Expected: Runs successfully, creates output.

- [ ] **Step 4: Commit**

```bash
git add -u
git commit -m "chore: delete eval/ and old scripts (replaced by src/)

BREAKING: All imports change from eval.* to src.*
- eval/ directory removed entirely
- scripts/run_pipeline.py replaced by src/__main__.py
- scripts/calc_data_mode_indicators.py replaced by src/indicators/calc.py
- scripts/reanalyze_with_opend.py kept temporarily (Phase 4)"
```

---

## Task 18: End-to-end verification

- [ ] **Step 1: Run full pipeline**

```bash
python -m src --symbols BTCUSDT --interval 1h --engine local --sample 3 --lookback 160 --forward 40
```

Expected: Creates run directory with flat structure:
```
outputs/runs/{run_id}/BTCUSDT/
├── config.json
├── eval_input.csv
├── runs.jsonl
├── scored.jsonl
├── metrics.json
├── summary.md
└── details.md
```

- [ ] **Step 2: Verify signal append works**

```bash
python3 -c "
from src.pipeline.signals import append_signal
result = append_signal(
    symbol='BTCUSDT',
    snapshot={'time_utc': '2026-03-27T15:00:00Z', 'price_now': 69500, '1h': {'state': 'downtrend'}, '4h': {'state': 'downtrend'}},
    report_md='# Test\nManual signal append test.',
    signal_meta={'decision': 'watch', 'bias': 'bearish', 'confidence': 'medium'},
)
print(f'Signal saved to: {result[\"signal_dir\"]}')

# Verify index now has 2 entries (original migration + this one)
lines = result['index_path'].read_text().strip().split('\n')
print(f'Index entries: {len(lines)}')
"
```

Expected: Signal saved, index has 2 entries.

- [ ] **Step 3: Verify no absolute paths in manifest**

```bash
python3 -c "
import json, glob
for f in glob.glob('outputs/runs/*/manifest.json'):
    m = json.load(open(f))
    text = json.dumps(m)
    assert '/Users/' not in text, f'Absolute path found in {f}'
    print(f'{f}: OK (no absolute paths)')
"
```

- [ ] **Step 4: Run full test suite one last time**

```bash
python -m pytest tests/ -v
```

Expected: All 17 tests PASS.

- [ ] **Step 5: Final commit**

```bash
git add outputs/signals/ outputs/registry.jsonl
git commit -m "feat: Phase 1-3 complete — Medallion Architecture restructure

Summary:
- data/ cleaned: single parquet per symbol/interval in data/clean/
- outputs/signals/ with append-only signal persistence
- src/ flat package structure (no more eval/)
- Flat run output layout (no human/machine/data/debug subdirs)
- 17 tests passing"
```
