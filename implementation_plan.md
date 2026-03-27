# 回测体系优化方案（兼容历史数据、面向人读）

## 摘要
采用业界常见的 5 个原则改造当前回测：`可复现`、`分层产物`、`结果版本化`、`时间序列防泄漏评估`、`向后兼容读取`。  
在不废弃历史数据的前提下，输出改为“一页总览 + 附录明细”，并把大量中间文件改成可选留存（分层留存）。

## 关键改造
1. 回测方法升级（不改策略逻辑，只改评估方法）
2. 增加 `case_mode`：`rolling`（现状）与 `non_overlap`（默认，减少样本重叠偏乐观）
3. 增加 `warmup_bars`（默认 120）避免指标冷启动污染
4. 报告分组输出：`overall + 分市场状态 + 分信心档`
5. 增加核心指标：`entry_trigger_rate`、`missed_entry_rate`、`expectancy_r`、`profit_factor_r`、`median_bars_to_outcome`、`MFE/MAE分位`

6. 人读输出优化（一页总览+附录）
7. [summary.md](file:///Users/hewei/Documents/GitHub/stock-technical-analysis/eval/results/BTCUSDT_1h/BTCUSDT/summary.md) 改为首页只放：结论、风险、样本充分性、是否通过基线
8. 新增 `details.md` 放完整表格（playbook、confidence、market_state、case明细）
9. 新增 `metrics.json` 给程序消费，保证前端/脚本都能稳定读取

10. 数据分层留存
11. [core](file:///Users/hewei/Documents/GitHub/stock-technical-analysis/eval/score_eval.py#361-406)（永久）：`index.json`、`config.json`、`runs.jsonl`、`scored.jsonl`、[summary.md](file:///Users/hewei/Documents/GitHub/stock-technical-analysis/eval/results/BTCUSDT_1h/BTCUSDT/summary.md)、`metrics.json`
12. `debug`（可选/可过期）：[cases/](file:///Users/hewei/Documents/GitHub/stock-technical-analysis/eval/run_eval.py#208-251)、`analysis_artifacts.json`、`eval_input.csv`、[reports/](file:///Users/hewei/Documents/GitHub/stock-technical-analysis/scripts/backtest_skill_json.py#552-597)
13. 默认不再强制写每个 case 的 `analysis_report.md` 与 `backtest_sample_v1.json`，仅在 `--artifact-level full` 时生成
14. 默认不再在 `runs.jsonl` 内联 `forward_rows`（降体积）；改为依赖 `config.json + csv` 重建，必要时可 `--embed-forward-rows` 兼容导出

## 数据必要性结论（回答“这些数据必须吗”）
| 数据 | 是否必须 | 作用 |
|---|---|---|
| `runs.jsonl` | 必须 | 回测原始决策事实（主数据） |
| `config.json` | 必须（新方案） | 可复现评分、重建 forward 窗口 |
| `scored.jsonl` | 建议保留 | 快速复盘与复用，不必每次重算 |
| [summary.md](file:///Users/hewei/Documents/GitHub/stock-technical-analysis/eval/results/BTCUSDT_1h/BTCUSDT/summary.md) | 建议保留 | 人读入口 |
| `metrics.json` | 建议保留 | 程序化消费入口 |
| `eval_input.csv` | 可选 | 调试方便，非必须（有原始 csv 引用即可） |
| `analysis_artifacts.json` | 可选 | 仅索引辅助 |
| `cases/*` 下逐 case 报告与 JSON | 可选 | 审计/演示用途，评分不依赖 |

## 接口与契约变更（公开面）
1. CLI 新增：`--artifact-level core|standard|full`（默认 `standard`）
2. CLI 新增：`--case-mode rolling|non_overlap`（默认 `non_overlap`）
3. CLI 新增：`--embed-forward-rows`（默认 `false`）
4. `runs.jsonl` 增加 `run_schema_version`；`scored.jsonl` 增加 `score_schema_version`
5. 保持 `backtest_sample_v1` 可读，不强制改历史 schema

## 历史兼容与懒迁移（双轨兼容）
1. 读取优先级固定：`config+csv` → `run.forward_rows`（旧数据）→ 同目录 `eval_input.csv` 回退
2. 新增兼容读取层，把旧 `runs/scored/summary` 映射为统一内部结构，不改写旧文件
3. 首次访问旧目录时仅生成轻量 `compat_manifest.json`（懒迁移），不做全量重写
4. 用现有目录（`BTCUSDT_1h`、`btc_formal_check`、`btc_referee_v2*`）做 golden 回归，确保旧数据可继续出报告

## 测试计划
1. 单元测试：窗口切片、forward 重建、旧格式解析、指标聚合
2. 兼容测试：对历史目录重跑 `score_eval/report`，保证可运行且关键统计一致
3. 回归测试：同一输入下旧版与新版 `t1/sl/watch/missed_entry` 一致（容差 0）
4. 存储测试：`standard` 模式下目录体积较当前至少下降 40%
5. 可读性验收：[summary.md](file:///Users/hewei/Documents/GitHub/stock-technical-analysis/eval/results/BTCUSDT_1h/BTCUSDT/summary.md) 首屏可在 1 分钟内读完并得到结论

## 默认假设
1. 仅优化回测框架与产物，不修改现有策略信号规则
2. 历史数据不做破坏性迁移，全部可继续利用
3. 默认服务“人读优先、程序复用并存”的结果消费场景
