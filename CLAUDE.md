# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run full pipeline (local engine, 5 samples for BTCUSDT at 1h)
python -m src --symbols BTCUSDT --interval 1h --engine local --sample 5

# Ingest market data from Binance into data/clean/
python -m src.pipeline.ingest --source binance --symbol BTCUSDT --interval 1h --limit 1000

# Run all tests
python -m unittest discover -s tests -p "test_*.py"

# Run a single test module
python -m unittest tests.test_ingest
```

Key CLI flags for `python -m src`:
- `--engine`: `auto` | `openai` | `local`
- `--repeat`: consistency test repetitions (default 3)
- `--lookback`: analysis window in bars (default 200)
- `--forward`: post-analysis eval window in bars (default 50)
- `--artifact-level`: `core` | `standard` | `full`
- `--prepare-only`: skip backtest, only prepare input parquet

Environment variable overrides: `EVAL_MODEL`, `EVAL_TEMPERATURE`, `EVAL_MAX_TOKENS`, `EVAL_LOOKBACK`, `EVAL_FORWARD`.

## Architecture

This is a **Python pipeline that backtests an AI-based technical analysis workflow** against historical OHLCV data. The core loop: ingest data → generate LLM analysis → score predictions → report metrics.

### Data flow

```
ingest.py / adapters.py
    → data/clean/{SYMBOL}/{interval}.parquet
    → catalog.py (data index)
    → analyze.py (rolling window samples)
    → scoring/engine.py (LLM evaluation via OpenAI API)
    → pipeline/backtest.py (score runs)
    → reporting/metrics.py + reporting/markdown.py
    → outputs/runs/{run_id}/{symbol}/  (scored.jsonl, metrics.json, summary.md, details.md)
    → outputs/signals/{symbol}/{signal_id}/  (snapshot.json, report.md)
```

### Key modules

| Module | Role |
|--------|------|
| `src/pipeline/layout.py` | `SymbolLayout`, `RunLayout`, `DataLayout` — all path definitions live here |
| `src/pipeline/manifest.py` | `RunManifest` + `GlobalRegistry` (append-only `outputs/registry.jsonl`) |
| `src/pipeline/adapters.py` | Data source adapters; all must return `timestamp/open/high/low/close/volume` |
| `src/pipeline/signals.py` | Immutable signal archive (never overwrites; auto-assigns signal IDs) |
| `src/pipeline/signal_backtest.py` | Validates saved signals against future price action |
| `src/scoring/engine.py` | LLM-based evaluation engine (OpenAI integration, 683 lines) |
| `src/reporting/metrics.py` | Aggregated metrics including playbook breakdown and confidence diagnostics |
| `src/indicators/calc.py` | Technical indicators: `ema()`, `rsi()`, `atr()`, `macd()`, `add_all_indicators()` |
| `src/config.py` | All global constants; all overridable via env vars |

### Workflow & knowledge docs

- `workflows/chart-analysis-workflow.md` — 8-step analysis flow (Steps 0–8) used as the AI agent prompt scaffold
- `workflows/trading-decision.md` — Playbook matching, checklists, risk control
- `references/` — Modular knowledge base: `core/`, `patterns/`, `indicators/`, `playbooks/`, `checklists/`, `risk/`
- `SKILL.md` — Mode routing table and knowledge loading rules for the AI skill

### Output layout

```
outputs/
  registry.jsonl               # append-only global run history
  runs/{run_id}/{symbol}/
    config.json, input.parquet, runs.jsonl, scored.jsonl, metrics.json, summary.md, details.md
  signals/{symbol}/{signal_id}/
    snapshot.json, report.md
  signals/{symbol}/index.jsonl # per-symbol cumulative signal index
```

## Development conventions

- Commit style: `feat:`, `fix:`, `chore:` + short description (match repo history)
- When modifying `layout.py`, `manifest.py`, or `signals.py`, also check `tests/test_layout.py` and `tests/test_signals.py` for path/index regressions
- New data source adapters go in `adapters.py`; must return consistent field names
- New indicators go in `src/indicators/calc.py` with a matching test in `tests/test_indicators.py`
- Changes to prompt/scoring logic require checking `SKILL.md` and `workflows/` for consistency
- `data/raw/`, `data/clean/`, `outputs/runs/` are gitignored (regenerable)
