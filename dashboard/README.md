# Trading Copilot Dashboard

AI Signal Dashboard for stock/crypto technical analysis. Reads static JSON data and displays signals, backtest results, and performance metrics.

## Quick Start

```bash
# Collect data from outputs/ directory (requires Python + project dependencies)
npm run collect

# Start dev server
npm run dev

# Build for production
npm run build
```

## Architecture

The dashboard is a standalone React + Vite app that reads pre-computed JSON files:

```
public/data/
  signals.json     # Signal archive with validation results
  backtests.json   # Backtest run results with metrics
  review.json      # Aggregated review statistics
```

Data is collected by `scripts/collect-data.mjs` which scans `../outputs/` and generates static JSON. The dashboard has no runtime Python dependency.

## Pages

| Page | Route | Description |
|------|-------|-------------|
| Dashboard | `/` | KPI cards, outcome distribution chart, signal breakdown, recent signals |
| Signals | `/signals` | Full signal table with filters (direction/search), click for detail view |
| Backtests | `/backtests` | Backtest run list with metrics, click for detailed report |
| Review | `/review` | Performance review with charts: outcome donut, playbook performance bars |

## Tech Stack

- React 19 + TypeScript
- Vite 8
- Tailwind CSS 4
- Recharts (data visualization)
- Lucide React (icons)
- React Router DOM (routing)
- React Markdown (report rendering)

## Data Contract

The dashboard depends on three JSON files. To use independently, provide these files in `public/data/`:

**signals.json**: Array of signal objects with `signal_id`, `symbol`, `timestamp_utc`, `decision`, `bias`, `confidence`, `playbook`, price levels, `snapshot`, `report`, and optional `validation` result.

**backtests.json**: Array of backtest runs with `run_id`, `type` (skill/local), `symbols` array containing `metrics` and `summary`.

**review.json**: Aggregated stats with `total`, `tradable`, `validated`, `wins`, `win_rate`, `byDecision`, `byPlaybook`, `byOutcome`.
