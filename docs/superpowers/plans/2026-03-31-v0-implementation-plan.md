# V0 Implementation Plan — AI Trading Research Copilot

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 从当前 Python 回测引擎 + React Dashboard 的状态出发，实现 PRD（v0-product-spec.md）定义的 F1-F5 五项功能，同时为后续 Mastra Agent 系统预留清晰的接入点。

**Architecture:** 三层架构 — Python 计算层（指标/回测/评分）→ TypeScript Agent 层（Mastra 编排，后续接入）→ React Dashboard 层（展示）。Python 层通过 JSON 文件与 Dashboard 通信，未来 Agent 层通过工具调用与 Python 层交互。核心设计原则：策略即配置（Playbook YAML 化）、信号不可变（append-only）、评估分层（结果 > 过程 > 质量）。

**Tech Stack:** Python 3.11+, React 19 + Vite 8 + Tailwind 4, Mastra（Phase 后续）, 飞书/Telegram Bot（通知）

---

## 0. 当前状态 vs 目标状态

### 已完成

| 项目 | 状态 |
|------|------|
| Phase 1: 数据整理 + 信号保全 | ✅ 完成 |
| Phase 2: 代码重命名 eval/ → src/ | ✅ 完成 |
| 信号追加写入 signals.py | ✅ 完成 |
| 数据摄入 ingest.py + adapters.py | ✅ 完成 |
| 回测引擎 local engine | ✅ 完成（data_source bug 已修复） |
| Dashboard 基础版 | ✅ 完成（信号/回测/对话三页） |

### 待实现（本计划范围）

| PRD 功能 | 对应任务 | 优先级 |
|----------|----------|--------|
| F1 今日分析 + 自动归档 | Task 1-2 | P0 |
| F2 信号档案 + 事后验证 | Task 3 | P0 |
| F3 复盘统计 | Task 4 | P0 |
| F4 策略迭代验证 | Task 5 | P1 |
| F5 条件单通知 | Task 6 | P1 |
| Dashboard 增强 | Task 7 | P1 |
| Agent 层预留 | 贯穿所有 Task 的接口设计 | — |

---

## 1. 文件结构规划

### 新增文件

```
src/
├── pipeline/
│   ├── strategy.py          # Task 1: 策略配置加载器（Playbook YAML → Python dict）
│   ├── price_monitor.py     # Task 6: 价格监控 + 条件单检查
│   └── notifier.py          # Task 6: 通知发送（飞书/Telegram/stdout）
├── scoring/
│   └── signal_scorer.py     # Task 3: 信号事后验证（entry/SL/T1 是否触达）
├── reporting/
│   └── review.py            # Task 4: 复盘统计（按 decision/playbook/market_state 分组）

strategies/                   # Task 1: Playbook 策略配置（YAML）
├── trend-pullback.yaml
├── breakout-retest.yaml
├── range-reversal.yaml
└── _defaults.yaml            # 全局默认参数（ATR 倍数、R:R 阈值等）

tests/
├── test_strategy.py
├── test_signal_scorer.py
├── test_review.py
├── test_price_monitor.py
└── test_notifier.py

dashboard/
└── src/pages/
    └── Review.tsx            # Task 7: 复盘统计页
```

### 修改文件

```
src/pipeline/analyze.py       # Task 1: 从 strategy.py 读取参数，替代硬编码
src/scoring/validator.py      # Task 1: playbook 枚举从 YAML 动态加载
src/pipeline/signals.py       # Task 2: 写入时附带 meta（prompt_version 等）
dashboard/scripts/collect-data.mjs  # Task 7: 采集复盘数据
dashboard/src/components/Layout.tsx # Task 7: 新增复盘导航
dashboard/src/App.tsx          # Task 7: 新增路由
```

### 设计决策：为什么策略用 YAML 不用 Python

1. **可扩展性：** 新增 Playbook 只需加一个 YAML 文件，零代码改动
2. **Agent 友好：** 未来 Mastra Agent 可以读/写 YAML 来调整策略参数
3. **版本可追踪：** YAML diff 比 Python diff 更易 review
4. **业界实践：** QuantConnect、Backtrader、Zipline 均用配置驱动策略参数

---

## Task 1: 策略配置系统（Playbook YAML 化）

**目的：** 将 analyze.py 中硬编码的交易规则提取为可配置的 YAML 文件，实现"改策略不改代码"。

**Files:**
- Create: `strategies/_defaults.yaml`
- Create: `strategies/trend-pullback.yaml`
- Create: `strategies/breakout-retest.yaml`
- Create: `strategies/range-reversal.yaml`
- Create: `src/pipeline/strategy.py`
- Create: `tests/test_strategy.py`
- Modify: `src/pipeline/analyze.py`
- Modify: `src/scoring/validator.py:17` (`_ALLOWED_PLAYBOOK` 动态化)

### Sub-task 1.1: 定义默认策略配置

- [ ] **Step 1: 创建默认策略配置文件**

```yaml
# strategies/_defaults.yaml
# 全局默认参数 — 所有 Playbook 继承此配置
version: "1.0"

entry:
  atr_multiplier: 1.0        # 入场价距当前价的 ATR 倍数

stop_loss:
  atr_multiplier: 1.0        # 止损距入场的 ATR 倍数

targets:
  t1_atr_multiplier: 1.6     # T1 距入场的 ATR 倍数
  t2_atr_multiplier: 3.0     # T2 距入场的 ATR 倍数

filters:
  min_rsi_long: 52            # 做多最低 RSI
  max_rsi_short: 48           # 做空最高 RSI
  min_macd_hist_long: -0.02   # 做多 MACD 柱线下限
  max_macd_hist_short: 0.02   # 做空 MACD 柱线上限

position:
  default_size_pct: 50.0      # 默认仓位百分比
  risk_pct: 1.0               # 单笔风险百分比

scoring:
  slippage_pct: 0.05          # 滑点
  fee_pct: 0.10               # 手续费
```

- [ ] **Step 2: 创建 trend-pullback 策略配置**

```yaml
# strategies/trend-pullback.yaml
name: trend-pullback
description: 顺势回调入场 — 趋势中等待回调到均线附近后入场

extends: _defaults            # 继承全局默认

conditions:
  long:
    market_state: uptrend
    rsi_min: 52
    macd_hist_min: -0.02
  short:
    market_state: downtrend
    rsi_max: 48
    macd_hist_max: 0.02

entry:
  trigger_type_long: close_above
  trigger_type_short: close_below

stop_loss:
  atr_multiplier: 1.0

targets:
  t1_atr_multiplier: 1.6
  t2_atr_multiplier: 3.0
```

- [ ] **Step 3: 创建 breakout-retest 和 range-reversal 配置**

```yaml
# strategies/breakout-retest.yaml
name: breakout-retest
description: 突破回踩确认入场

extends: _defaults

conditions:
  long:
    market_state: uptrend
    rsi_min: 50
    macd_hist_min: 0
  short:
    market_state: downtrend
    rsi_max: 50
    macd_hist_max: 0

stop_loss:
  atr_multiplier: 1.2

targets:
  t1_atr_multiplier: 1.8
  t2_atr_multiplier: 3.5
```

```yaml
# strategies/range-reversal.yaml
name: range-reversal
description: 区间边界反转入场

extends: _defaults

conditions:
  long:
    market_state: range
    rsi_min: 30
    rsi_max: 45
  short:
    market_state: range
    rsi_min: 55
    rsi_max: 70

stop_loss:
  atr_multiplier: 0.8

targets:
  t1_atr_multiplier: 1.5
  t2_atr_multiplier: 2.5
```

- [ ] **Step 4: Commit 策略配置文件**

```bash
git add strategies/
git commit -m "feat: add playbook strategy configs (YAML)"
```

### Sub-task 1.2: 策略加载器

- [ ] **Step 5: 写失败测试**

```python
# tests/test_strategy.py
import unittest
from src.pipeline.strategy import load_strategy, list_strategies, get_conditions

class TestStrategy(unittest.TestCase):
    def test_load_defaults(self):
        s = load_strategy("_defaults")
        self.assertEqual(s["stop_loss"]["atr_multiplier"], 1.0)
        self.assertEqual(s["targets"]["t1_atr_multiplier"], 1.6)

    def test_load_trend_pullback_inherits_defaults(self):
        s = load_strategy("trend-pullback")
        self.assertEqual(s["name"], "trend-pullback")
        # 继承默认值
        self.assertEqual(s["position"]["default_size_pct"], 50.0)
        # 自身值
        self.assertEqual(s["conditions"]["long"]["market_state"], "uptrend")

    def test_list_strategies_excludes_defaults(self):
        names = list_strategies()
        self.assertIn("trend-pullback", names)
        self.assertIn("breakout-retest", names)
        self.assertNotIn("_defaults", names)

    def test_get_conditions_long(self):
        conds = get_conditions("trend-pullback", "long")
        self.assertEqual(conds["market_state"], "uptrend")
        self.assertEqual(conds["rsi_min"], 52)

    def test_unknown_strategy_raises(self):
        with self.assertRaises(FileNotFoundError):
            load_strategy("nonexistent-strategy")
```

- [ ] **Step 6: 运行测试，确认失败**

Run: `python -m pytest tests/test_strategy.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.pipeline.strategy'`

- [ ] **Step 7: 实现策略加载器**

```python
# src/pipeline/strategy.py
"""策略配置加载器 — 从 strategies/ 目录读取 YAML Playbook 配置。"""
from __future__ import annotations

import yaml
from pathlib import Path
from typing import Any

_STRATEGIES_DIR = Path(__file__).resolve().parent.parent.parent / "strategies"
_cache: dict[str, dict[str, Any]] = {}


def _load_yaml(name: str) -> dict[str, Any]:
    path = _STRATEGIES_DIR / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Strategy not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _deep_merge(base: dict, override: dict) -> dict:
    """递归合并，override 覆盖 base 的同名 key。"""
    result = base.copy()
    for k, v in override.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def load_strategy(name: str) -> dict[str, Any]:
    """加载策略配置，自动继承 _defaults。"""
    if name in _cache:
        return _cache[name]

    raw = _load_yaml(name)
    extends = raw.pop("extends", None)

    if extends and extends != name:
        base = load_strategy(extends)
        merged = _deep_merge(base, raw)
    else:
        merged = raw

    _cache[name] = merged
    return merged


def list_strategies() -> list[str]:
    """列出所有可用策略名（排除 _defaults）。"""
    return sorted(
        p.stem for p in _STRATEGIES_DIR.glob("*.yaml")
        if not p.stem.startswith("_")
    )


def get_conditions(name: str, direction: str) -> dict[str, Any]:
    """获取某策略某方向的进场条件。direction: 'long' | 'short'"""
    s = load_strategy(name)
    return s.get("conditions", {}).get(direction, {})


def get_stop_loss_atr(name: str) -> float:
    """获取止损 ATR 倍数。"""
    return load_strategy(name).get("stop_loss", {}).get("atr_multiplier", 1.0)


def get_targets(name: str) -> tuple[float, float]:
    """获取 T1, T2 的 ATR 倍数。"""
    t = load_strategy(name).get("targets", {})
    return t.get("t1_atr_multiplier", 1.6), t.get("t2_atr_multiplier", 3.0)
```

- [ ] **Step 8: 运行测试，确认通过**

Run: `pip install pyyaml && python -m pytest tests/test_strategy.py -v`
Expected: 5 passed

- [ ] **Step 9: Commit**

```bash
git add src/pipeline/strategy.py tests/test_strategy.py
git commit -m "feat: strategy config loader with YAML inheritance"
```

### Sub-task 1.3: 改造 analyze.py 使用策略配置

- [ ] **Step 10: 修改 analyze.py — 从策略配置读取参数**

在 `src/pipeline/analyze.py` 中，替换硬编码的 RSI/MACD 阈值和 ATR 倍数：

```python
# src/pipeline/analyze.py 修改点
# 在文件顶部新增 import
from src.pipeline.strategy import load_strategy, list_strategies, get_conditions, get_stop_loss_atr, get_targets

# 替换原来的硬编码逻辑（约第 50-80 行）
def _match_playbook(market_state: str, rsi: float, macd_hist: float) -> tuple[str, str]:
    """遍历所有策略，返回匹配的 (action, playbook)。"""
    for name in list_strategies():
        for direction in ("long", "short"):
            conds = get_conditions(name, direction)
            if not conds:
                continue
            if conds.get("market_state") and conds["market_state"] != market_state:
                continue
            if direction == "long":
                if rsi < conds.get("rsi_min", 0):
                    continue
                if conds.get("rsi_max") and rsi > conds["rsi_max"]:
                    continue
                if macd_hist < conds.get("macd_hist_min", float("-inf")):
                    continue
            else:  # short
                if rsi > conds.get("rsi_max", 100):
                    continue
                if conds.get("rsi_min") and rsi < conds["rsi_min"]:
                    continue
                if macd_hist > conds.get("macd_hist_max", float("inf")):
                    continue
            return direction, name
    return "watch", "none"
```

- [ ] **Step 11: 修改 validator.py — 动态加载 playbook 枚举**

```python
# src/scoring/validator.py 第 17 行，替换硬编码
from src.pipeline.strategy import list_strategies
_ALLOWED_PLAYBOOK = set(list_strategies()) | {"none"}
```

- [ ] **Step 12: 运行全部测试**

Run: `python -m pytest tests/ -v`
Expected: All existing tests pass

- [ ] **Step 13: Commit**

```bash
git add src/pipeline/analyze.py src/scoring/validator.py
git commit -m "refactor: analyze.py reads strategy params from YAML configs"
```

---

## Task 2: F1 今日分析 — 信号 meta 增强

**目的：** 每次信号写入时附带可复现元数据（prompt_version、model、data_range），满足 PRD F1 的"事后能复现"要求。

**Files:**
- Modify: `src/pipeline/signals.py`
- Modify: `tests/test_signals.py`

- [ ] **Step 1: 写测试 — 信号写入包含 meta**

```python
# tests/test_signals.py 新增测试
def test_append_signal_with_meta(self):
    meta = {
        "prompt_version": "analysis-v1.0",
        "model": "claude-sonnet-4-6",
        "data_range": {
            "symbol": "BTCUSDT",
            "intervals": ["4h", "1h"],
            "start": "2026-03-01T00:00:00Z",
            "end": "2026-03-30T00:00:00Z",
            "bar_count": 200,
        },
        "schema_version": "1.0",
    }
    result = append_signal(
        symbol="BTCUSDT",
        snapshot={"test": True, "meta": meta},
        report_md="# Test",
        signal_meta={"decision": "long", "bias": "bullish", "confidence": "high"},
        outputs_root=self.tmp,
    )
    snapshot = json.loads(result["snapshot_path"].read_text())
    self.assertEqual(snapshot["meta"]["prompt_version"], "analysis-v1.0")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_signals.py::TestSignals::test_append_signal_with_meta -v`

- [ ] **Step 3: 修改 signals.py — 确保 meta 字段被保留**

验证 `append_signal()` 在写入 snapshot.json 时保留 `meta` 字段（当前实现已经直接 dump snapshot，所以这一步可能只需要确认而非修改）。

- [ ] **Step 4: 运行测试确认通过 + Commit**

```bash
python -m pytest tests/test_signals.py -v
git add src/pipeline/signals.py tests/test_signals.py
git commit -m "feat: signal meta preservation for reproducibility"
```

---

## Task 3: F2 信号事后验证

**目的：** 读取历史信号，用后续 K 线验证 entry/SL/T1/T2 是否触达，给每个信号打上结果标签。

**Files:**
- Create: `src/scoring/signal_scorer.py`
- Create: `tests/test_signal_scorer.py`

- [ ] **Step 1: 写测试**

```python
# tests/test_signal_scorer.py
import unittest
from src.scoring.signal_scorer import score_signal

class TestSignalScorer(unittest.TestCase):
    def _make_bars(self, prices):
        """生成模拟 K 线：每根 bar 的 OHLC 都是同一价格。"""
        return [
            {"timestamp": f"2026-01-01T{i:02d}:00:00Z",
             "open": p, "high": p + 50, "low": p - 50, "close": p, "volume": 100}
            for i, p in enumerate(prices)
        ]

    def test_long_t1_hit(self):
        signal = {"decision": "long", "conditional_entry": 100, "stop_loss": 90, "t1": 115, "t2": 130}
        bars = self._make_bars([98, 100, 105, 110, 115, 120])  # 价格上涨到 T1
        result = score_signal(signal, bars)
        self.assertEqual(result["outcome"], "t1_hit")
        self.assertTrue(result["entry_triggered"])

    def test_long_sl_hit(self):
        signal = {"decision": "long", "conditional_entry": 100, "stop_loss": 90, "t1": 115, "t2": 130}
        bars = self._make_bars([98, 100, 95, 88])  # 价格跌破止损
        result = score_signal(signal, bars)
        self.assertEqual(result["outcome"], "sl_hit")

    def test_watch_not_triggered(self):
        signal = {"decision": "watch", "conditional_entry": 100, "stop_loss": 90, "t1": 115}
        bars = self._make_bars([105, 106, 107])  # 价格一直在条件价上方
        result = score_signal(signal, bars)
        self.assertEqual(result["outcome"], "not_triggered")

    def test_no_entry_price(self):
        signal = {"decision": "watch"}  # 没有入场价
        bars = self._make_bars([100, 101])
        result = score_signal(signal, bars)
        self.assertEqual(result["outcome"], "no_levels")
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_signal_scorer.py -v`

- [ ] **Step 3: 实现 signal_scorer.py**

```python
# src/scoring/signal_scorer.py
"""信号事后验证 — 用后续 K 线检查 entry/SL/T1/T2 是否触达。"""
from __future__ import annotations
from typing import Any


def score_signal(signal: dict[str, Any], forward_bars: list[dict[str, Any]]) -> dict[str, Any]:
    """
    对单个信号做事后验证。

    Args:
        signal: 信号字典，需包含 decision, conditional_entry, stop_loss, t1, t2
        forward_bars: 信号发出后的 K 线列表（OHLCV dict）

    Returns:
        验证结果字典
    """
    decision = signal.get("decision", "watch")
    entry = _to_float(signal.get("conditional_entry") or signal.get("entry_price"))
    sl = _to_float(signal.get("stop_loss"))
    t1 = _to_float(signal.get("t1"))
    t2 = _to_float(signal.get("t2"))

    if entry is None or sl is None:
        return {"outcome": "no_levels", "entry_triggered": False}

    is_long = decision == "long"
    is_short = decision == "short"
    is_watch = decision == "watch"

    entry_triggered = False
    entry_bar = None

    for i, bar in enumerate(forward_bars):
        h, l, c = float(bar["high"]), float(bar["low"]), float(bar["close"])

        # 检查入场触发
        if not entry_triggered:
            if is_long and l <= entry <= h:
                entry_triggered = True
                entry_bar = i
            elif is_short and l <= entry <= h:
                entry_triggered = True
                entry_bar = i
            elif is_watch and l <= entry <= h:
                entry_triggered = True
                entry_bar = i
            continue

        # 入场后检查 SL 和 T1/T2
        if is_long or (is_watch and entry < sl):
            # 做多逻辑
            if l <= sl:
                return _result("sl_hit", True, entry_bar, i)
            if t1 and h >= t1:
                return _result("t1_hit", True, entry_bar, i)
        elif is_short or (is_watch and entry > sl):
            # 做空逻辑
            if h >= sl:
                return _result("sl_hit", True, entry_bar, i)
            if t1 and l <= t1:
                return _result("t1_hit", True, entry_bar, i)

    if not entry_triggered:
        return {"outcome": "not_triggered", "entry_triggered": False}

    return _result("neither", True, entry_bar, len(forward_bars) - 1)


def _result(outcome: str, triggered: bool, entry_bar: int | None, outcome_bar: int | None) -> dict:
    return {
        "outcome": outcome,
        "entry_triggered": triggered,
        "bars_to_entry": entry_bar,
        "bars_to_outcome": outcome_bar - entry_bar if entry_bar is not None and outcome_bar is not None else None,
    }


def _to_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None
```

- [ ] **Step 4: 运行测试 + Commit**

```bash
python -m pytest tests/test_signal_scorer.py -v
git add src/scoring/signal_scorer.py tests/test_signal_scorer.py
git commit -m "feat: signal post-hoc scorer (F2 signal validation)"
```

---

## Task 4: F3 复盘统计

**目的：** 按 decision/playbook/market_state 分组统计信号表现。

**Files:**
- Create: `src/reporting/review.py`
- Create: `tests/test_review.py`

- [ ] **Step 1: 写测试**

```python
# tests/test_review.py
import unittest
from src.reporting.review import compute_review

class TestReview(unittest.TestCase):
    def test_group_by_decision(self):
        scored = [
            {"decision": "long", "outcome": "t1_hit"},
            {"decision": "long", "outcome": "sl_hit"},
            {"decision": "long", "outcome": "t1_hit"},
            {"decision": "short", "outcome": "sl_hit"},
            {"decision": "watch", "outcome": "not_triggered"},
        ]
        result = compute_review(scored)
        self.assertEqual(result["by_decision"]["long"]["total"], 3)
        self.assertEqual(result["by_decision"]["long"]["win_rate"], 2 / 3)
        self.assertEqual(result["by_decision"]["short"]["win_rate"], 0.0)
        self.assertEqual(result["by_decision"]["watch"]["total"], 1)

    def test_group_by_playbook(self):
        scored = [
            {"decision": "long", "playbook": "trend-pullback", "outcome": "t1_hit"},
            {"decision": "long", "playbook": "trend-pullback", "outcome": "sl_hit"},
            {"decision": "short", "playbook": "breakout-retest", "outcome": "t1_hit"},
        ]
        result = compute_review(scored)
        self.assertEqual(result["by_playbook"]["trend-pullback"]["win_rate"], 0.5)
        self.assertEqual(result["by_playbook"]["breakout-retest"]["win_rate"], 1.0)

    def test_empty_input(self):
        result = compute_review([])
        self.assertEqual(result["total"], 0)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_review.py -v`

- [ ] **Step 3: 实现 review.py**

```python
# src/reporting/review.py
"""复盘统计 — 按 decision/playbook/market_state 分组计算胜率。"""
from __future__ import annotations
from collections import defaultdict
from typing import Any


def compute_review(scored_signals: list[dict[str, Any]]) -> dict[str, Any]:
    """
    对已评分的信号列表做分组统计。

    Args:
        scored_signals: 每条包含 decision, playbook, market_state, outcome 字段

    Returns:
        {total, by_decision, by_playbook, by_market_state}
    """
    if not scored_signals:
        return {"total": 0, "by_decision": {}, "by_playbook": {}, "by_market_state": {}}

    return {
        "total": len(scored_signals),
        "by_decision": _group_stats(scored_signals, "decision"),
        "by_playbook": _group_stats(scored_signals, "playbook"),
        "by_market_state": _group_stats(scored_signals, "market_state"),
    }


def _group_stats(items: list[dict], key: str) -> dict[str, dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        groups[item.get(key, "unknown")].append(item)

    result = {}
    for name, group in sorted(groups.items()):
        tradable = [g for g in group if g.get("decision") in ("long", "short")]
        wins = [g for g in tradable if g.get("outcome") == "t1_hit"]
        result[name] = {
            "total": len(group),
            "tradable": len(tradable),
            "wins": len(wins),
            "win_rate": len(wins) / len(tradable) if tradable else 0.0,
            "watch_count": len(group) - len(tradable),
        }
    return result
```

- [ ] **Step 4: 运行测试 + Commit**

```bash
python -m pytest tests/test_review.py -v
git add src/reporting/review.py tests/test_review.py
git commit -m "feat: review stats grouped by decision/playbook/market_state (F3)"
```

---

## Task 5: F4 策略迭代验证（Prompt 回归测试）

**目的：** 冻结测试集，对比新旧版本的信号质量。

**Files:**
- Create: `src/scoring/regression.py`
- Create: `tests/test_regression.py`

- [ ] **Step 1: 写测试**

```python
# tests/test_regression.py
import unittest
from src.scoring.regression import compare_versions

class TestRegression(unittest.TestCase):
    def test_new_version_better(self):
        old = [{"outcome": "t1_hit"}, {"outcome": "sl_hit"}, {"outcome": "sl_hit"}]
        new = [{"outcome": "t1_hit"}, {"outcome": "t1_hit"}, {"outcome": "sl_hit"}]
        result = compare_versions(old, new)
        self.assertEqual(result["old_win_rate"], 1 / 3)
        self.assertEqual(result["new_win_rate"], 2 / 3)
        self.assertEqual(result["verdict"], "improved")

    def test_new_version_worse(self):
        old = [{"outcome": "t1_hit"}, {"outcome": "t1_hit"}]
        new = [{"outcome": "sl_hit"}, {"outcome": "sl_hit"}]
        result = compare_versions(old, new)
        self.assertEqual(result["verdict"], "regressed")

    def test_no_significant_change(self):
        old = [{"outcome": "t1_hit"}, {"outcome": "sl_hit"}]
        new = [{"outcome": "sl_hit"}, {"outcome": "t1_hit"}]
        result = compare_versions(old, new)
        self.assertEqual(result["verdict"], "no_change")
```

- [ ] **Step 2: 运行测试确认失败**

- [ ] **Step 3: 实现 regression.py**

```python
# src/scoring/regression.py
"""Prompt 回归测试 — 对比新旧版本信号质量。"""
from __future__ import annotations
from typing import Any

REGRESSION_THRESHOLD = 0.05  # 命中率下降超过 5% 视为退化


def compare_versions(
    old_scored: list[dict[str, Any]],
    new_scored: list[dict[str, Any]],
) -> dict[str, Any]:
    """对比两组已评分信号的命中率。"""
    old_wr = _win_rate(old_scored)
    new_wr = _win_rate(new_scored)
    diff = new_wr - old_wr

    if diff > REGRESSION_THRESHOLD:
        verdict = "improved"
    elif diff < -REGRESSION_THRESHOLD:
        verdict = "regressed"
    else:
        verdict = "no_change"

    return {
        "old_win_rate": old_wr,
        "new_win_rate": new_wr,
        "diff": round(diff, 4),
        "verdict": verdict,
    }


def _win_rate(scored: list[dict]) -> float:
    tradable = [s for s in scored if s.get("outcome") in ("t1_hit", "sl_hit", "neither")]
    if not tradable:
        return 0.0
    wins = [s for s in tradable if s["outcome"] == "t1_hit"]
    return len(wins) / len(tradable)
```

- [ ] **Step 4: 运行测试 + Commit**

```bash
python -m pytest tests/test_regression.py -v
git add src/scoring/regression.py tests/test_regression.py
git commit -m "feat: prompt regression test — compare old vs new signal quality (F4)"
```

---

## Task 6: F5 条件单通知

**目的：** 后台监控活跃信号的价格条件，触发时发送通知。

**Files:**
- Create: `src/pipeline/price_monitor.py`
- Create: `src/pipeline/notifier.py`
- Create: `tests/test_price_monitor.py`
- Create: `tests/test_notifier.py`

### Sub-task 6.1: 通知发送器

- [ ] **Step 1: 写测试**

```python
# tests/test_notifier.py
import unittest
from src.pipeline.notifier import format_notification, StdoutNotifier

class TestNotifier(unittest.TestCase):
    def test_format_entry_triggered(self):
        signal = {
            "symbol": "BTCUSDT",
            "decision": "long",
            "conditional_entry": 60000,
            "stop_loss": 58500,
            "t1": 63000,
            "timestamp_utc": "2026-03-28T10:00:00Z",
        }
        msg = format_notification("entry_triggered", signal, current_price=59980)
        self.assertIn("BTCUSDT", msg)
        self.assertIn("60000", msg)
        self.assertIn("做多", msg)

    def test_stdout_notifier(self):
        notifier = StdoutNotifier()
        result = notifier.send("test message")
        self.assertTrue(result["sent"])
```

- [ ] **Step 2: 实现 notifier.py**

```python
# src/pipeline/notifier.py
"""通知发送器 — 支持 stdout / 飞书 / Telegram。"""
from __future__ import annotations
from typing import Any, Protocol
import json


class Notifier(Protocol):
    def send(self, message: str) -> dict[str, Any]: ...


class StdoutNotifier:
    """开发调试用 — 输出到控制台。"""
    def send(self, message: str) -> dict[str, Any]:
        print(f"[NOTIFY] {message}")
        return {"sent": True, "channel": "stdout"}


class FeishuNotifier:
    """飞书机器人通知 — 通过 webhook 发送。"""
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send(self, message: str) -> dict[str, Any]:
        import urllib.request
        payload = json.dumps({"msg_type": "text", "content": {"text": message}}).encode()
        req = urllib.request.Request(self.webhook_url, data=payload, headers={"Content-Type": "application/json"})
        try:
            urllib.request.urlopen(req, timeout=10)
            return {"sent": True, "channel": "feishu"}
        except Exception as e:
            return {"sent": False, "channel": "feishu", "error": str(e)}


_DECISION_LABEL = {"long": "做多", "short": "做空", "watch": "观望"}


def format_notification(event: str, signal: dict[str, Any], current_price: float | None = None) -> str:
    """格式化通知消息。"""
    sym = signal.get("symbol", "?")
    decision = _DECISION_LABEL.get(signal.get("decision", ""), signal.get("decision", "?"))
    entry = signal.get("conditional_entry", "?")
    sl = signal.get("stop_loss", "?")
    t1 = signal.get("t1", "?")
    ts = signal.get("timestamp_utc", "?")[:16]

    if event == "entry_triggered":
        return f"📍 {sym} 条件单触发\n方向: {decision} | 入场: {entry}\n止损: {sl} | 目标: {t1}\n信号时间: {ts}\n当前价: {current_price}"
    elif event == "sl_warning":
        return f"⚠️ {sym} 接近止损\n止损位: {sl} | 当前价: {current_price}\n方向: {decision} | 信号时间: {ts}"
    elif event == "t1_reached":
        return f"🎯 {sym} 到达目标 1\nT1: {t1} | 当前价: {current_price}\n方向: {decision} | 可考虑部分止盈"
    else:
        return f"📊 {sym} {event}\n{decision} | {entry} → {t1}"
```

- [ ] **Step 3: 运行测试 + Commit**

```bash
python -m pytest tests/test_notifier.py -v
git add src/pipeline/notifier.py tests/test_notifier.py
git commit -m "feat: notification system with stdout/feishu support (F5)"
```

### Sub-task 6.2: 价格监控器

- [ ] **Step 1: 写测试**

```python
# tests/test_price_monitor.py
import unittest
from src.pipeline.price_monitor import check_signals

class TestPriceMonitor(unittest.TestCase):
    def test_entry_triggered(self):
        signals = [{
            "signal_id": "test1",
            "symbol": "BTCUSDT",
            "decision": "long",
            "conditional_entry": 60000,
            "stop_loss": 58500,
            "t1": 63000,
        }]
        events = check_signals(signals, current_prices={"BTCUSDT": 59950})
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["event"], "entry_triggered")

    def test_no_trigger(self):
        signals = [{
            "signal_id": "test1",
            "symbol": "BTCUSDT",
            "decision": "long",
            "conditional_entry": 60000,
            "stop_loss": 58500,
            "t1": 63000,
        }]
        events = check_signals(signals, current_prices={"BTCUSDT": 62000})
        self.assertEqual(len(events), 0)

    def test_sl_warning(self):
        signals = [{
            "signal_id": "test1",
            "symbol": "BTCUSDT",
            "decision": "long",
            "conditional_entry": 60000,
            "stop_loss": 58500,
            "t1": 63000,
            "status": "active",  # 已入场
        }]
        events = check_signals(signals, current_prices={"BTCUSDT": 58800})
        self.assertTrue(any(e["event"] == "sl_warning" for e in events))
```

- [ ] **Step 2: 实现 price_monitor.py**

```python
# src/pipeline/price_monitor.py
"""价格监控 — 检查活跃信号的条件是否满足。"""
from __future__ import annotations
from typing import Any


def check_signals(
    signals: list[dict[str, Any]],
    current_prices: dict[str, float],
) -> list[dict[str, Any]]:
    """
    检查信号列表，返回触发的事件。

    Args:
        signals: 活跃信号列表
        current_prices: {symbol: price} 当前价格

    Returns:
        触发的事件列表 [{event, signal, current_price}]
    """
    events = []

    for sig in signals:
        symbol = sig.get("symbol", "")
        price = current_prices.get(symbol)
        if price is None:
            continue

        decision = sig.get("decision")
        entry = _to_float(sig.get("conditional_entry") or sig.get("entry_price"))
        sl = _to_float(sig.get("stop_loss"))
        t1 = _to_float(sig.get("t1"))
        status = sig.get("status", "pending")

        if status == "pending" and entry is not None:
            # 检查条件单触发
            is_long = decision == "long" or (decision == "watch" and sl and entry > sl)
            if is_long and price <= entry:
                events.append({"event": "entry_triggered", "signal": sig, "current_price": price})
            elif not is_long and price >= entry:
                events.append({"event": "entry_triggered", "signal": sig, "current_price": price})

        if status == "active" and sl is not None:
            # 检查止损预警（距离 < 1%）
            distance_pct = abs(price - sl) / price * 100
            if distance_pct < 1.0:
                events.append({"event": "sl_warning", "signal": sig, "current_price": price})

        if status == "active" and t1 is not None:
            is_long = decision == "long"
            if is_long and price >= t1:
                events.append({"event": "t1_reached", "signal": sig, "current_price": price})
            elif not is_long and price <= t1:
                events.append({"event": "t1_reached", "signal": sig, "current_price": price})

    return events


def _to_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None
```

- [ ] **Step 3: 运行测试 + Commit**

```bash
python -m pytest tests/test_price_monitor.py -v
git add src/pipeline/price_monitor.py tests/test_price_monitor.py
git commit -m "feat: price monitor for signal condition checking (F5)"
```

---

## Task 7: Dashboard 增强 — 复盘统计页 + 事后验证状态

**目的：** 在 Dashboard 中展示复盘统计和信号验证状态。

**Files:**
- Create: `dashboard/src/pages/Review.tsx`
- Modify: `dashboard/scripts/collect-data.mjs`
- Modify: `dashboard/src/components/Layout.tsx`
- Modify: `dashboard/src/App.tsx`

- [ ] **Step 1: 更新 collect-data.mjs — 生成复盘统计数据**

在 `collectSignals()` 之后新增：

```javascript
// dashboard/scripts/collect-data.mjs 新增函数
function collectReview(signals) {
  const byDecision = {};
  const byPlaybook = {};

  for (const s of signals) {
    const dec = s.decision || 'unknown';
    const pb = s.playbook || 'unknown';

    if (!byDecision[dec]) byDecision[dec] = { total: 0, signals: [] };
    byDecision[dec].total++;
    byDecision[dec].signals.push(s);

    if (!byPlaybook[pb]) byPlaybook[pb] = { total: 0, signals: [] };
    byPlaybook[pb].total++;
    byPlaybook[pb].signals.push(s);
  }

  return { total: signals.length, byDecision, byPlaybook };
}
```

在 main 区域：
```javascript
const review = collectReview(signals);
writeFileSync(join(OUT_DIR, 'review.json'), JSON.stringify(review, null, 2));
```

- [ ] **Step 2: 创建复盘统计页**

```tsx
// dashboard/src/pages/Review.tsx
import { useState, useEffect } from 'react';

interface ReviewData {
  total: number;
  byDecision: Record<string, { total: number }>;
  byPlaybook: Record<string, { total: number }>;
}

export default function Review() {
  const [data, setData] = useState<ReviewData | null>(null);

  useEffect(() => {
    fetch('/data/review.json').then(r => r.json()).then(setData);
  }, []);

  if (!data) return <div className="p-8 text-gray-400">加载中...</div>;

  return (
    <div className="p-8">
      <div className="mb-6">
        <h2 className="text-lg font-semibold text-gray-900">复盘统计</h2>
        <p className="text-sm text-gray-500 mt-1">共 {data.total} 条信号</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* 按方向统计 */}
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-4">按方向</h3>
          <div className="space-y-3">
            {Object.entries(data.byDecision).map(([dec, stats]) => (
              <div key={dec} className="flex justify-between items-center">
                <span className="text-sm text-gray-700">{dec}</span>
                <span className="text-sm font-mono font-semibold text-gray-900">{stats.total}</span>
              </div>
            ))}
          </div>
        </div>

        {/* 按策略统计 */}
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-4">按策略</h3>
          <div className="space-y-3">
            {Object.entries(data.byPlaybook).map(([pb, stats]) => (
              <div key={pb} className="flex justify-between items-center">
                <span className="text-sm text-gray-700">{pb}</span>
                <span className="text-sm font-mono font-semibold text-gray-900">{stats.total}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: 更新 Layout 和 App 路由**

Layout.tsx 的 nav 数组新增：
```tsx
{ to: '/review', icon: PieChart, label: '复盘统计' },
```

App.tsx 新增路由：
```tsx
<Route path="/review" element={<Review />} />
```

- [ ] **Step 4: 验证 Dashboard 构建**

```bash
cd dashboard && npm run build
```

- [ ] **Step 5: Commit**

```bash
git add dashboard/
git commit -m "feat: review stats page in dashboard (F3)"
```

---

## Agent 层接入点说明

本计划所有 Python 模块均设计为**纯函数 + 单一职责**，未来 Mastra Agent 可以直接通过工具调用接入：

| Python 模块 | 未来 Agent Tool | 说明 |
|-------------|----------------|------|
| `strategy.py` → `load_strategy()` | `getStrategy` | Agent 读取/选择策略 |
| `signal_scorer.py` → `score_signal()` | `validateSignal` | Agent 验证历史信号 |
| `review.py` → `compute_review()` | `getReviewStats` | Agent 生成复盘报告 |
| `price_monitor.py` → `check_signals()` | `checkPriceAlerts` | Agent 定时监控 |
| `notifier.py` → `Notifier.send()` | `sendNotification` | Agent 发送通知 |
| `signals.py` → `append_signal()` | `persistSignal` | Agent 保存信号 |

策略修改路径：**编辑 YAML 文件 → Agent 重新加载 → 回归测试验证 → 上线**，全程不改 Python 代码。

---

## 文档更新

完成所有 Task 后，需同步更新：

1. `docs/superpowers/specs/2026-03-30-v0-product-spec.md` — 将 Dashboard 从"不做"移到"已完成"
2. `docs/superpowers/specs/2026-03-27-project-restructure-design.md` — 标记为 `Archived`，在文件顶部加注"已被 v0-product-spec.md 和本实现计划取代"
3. `docs/superpowers/specs/2026-03-26-stock-agent-design.md` — 标记为 `Deferred`，在文件顶部加注"Agent 层将在 V0 验证后实施"
4. `CLAUDE.md` / `AGENTS.md` — 更新命令示例，新增 strategies/ 说明
