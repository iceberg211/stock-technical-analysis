# Phase 4-5 实施规划（数据摄入 + 信号回测）

> 日期：2026-03-27
> 目标：在不破坏既有产物可读性的前提下，补齐数据摄入适配层与信号回测引擎，形成可持续扩展的多标的体系。

## 一、约束与设计原则

1. 旧数据可用性优先：历史 `outputs/runs/*`、`outputs/signals/*`、旧 `eval_input.csv` 目录必须可读，采用懒迁移记录，不改写旧文件。
2. 扩展性优先：新增交易所或币种时，只改 adapter 层，不改评分/报告逻辑。
3. 单一真相源：行情统一沉淀到 `data/clean/{symbol}/{interval}.parquet`。
4. 产物分层：人读、机读、可复现输入分开，避免目录继续膨胀。

---

## 二、Phase 4：ingest 适配层

### 4.1 目标

补齐 `src/pipeline/ingest.py`，统一三类数据源：
- Binance
- Futu(OpenD)
- Yahoo Finance

并提供统一 CLI：
```bash
python -m src.pipeline.ingest \
  --source binance|futu|yahoo \
  --symbol BTCUSDT \
  --interval 1h \
  --start 2025-01-01 \
  --end 2026-03-27
```

### 4.2 文件与模块

1. 新增 [ingest.py](/Users/hewei/Documents/GitHub/stock-technical-analysis/src/pipeline/ingest.py)
2. 新增 [adapters.py](/Users/hewei/Documents/GitHub/stock-technical-analysis/src/pipeline/adapters.py)
3. 新增 [test_ingest.py](/Users/hewei/Documents/GitHub/stock-technical-analysis/tests/test_ingest.py)

### 4.3 统一接口（Protocol）

定义 `KlineAdapter` 协议：
- `fetch(symbol, interval, start, end, limit) -> pd.DataFrame`
- 统一列输出：`timestamp, open, high, low, close, volume`

每个 adapter 负责：
- 时间字段标准化到 UTC
- OHLCV 数值化
- 数据去重键：`timestamp`

### 4.4 ingest 主流程

1. 拉取原始响应并落盘 `data/raw/{source}/{symbol}/{interval}/{ts}.json`
2. 标准化为 DataFrame
3. 与 `data/clean/{symbol}/{interval}.parquet` 合并
4. 去重、排序、写回 parquet
5. 更新 `data/catalog.json`

### 4.5 兼容策略

1. 若 `clean` 不存在，支持 `--bootstrap-legacy`：从旧 CSV（如 `data/binance_kline/*_accum.csv`）一次性导入 clean。
2. 生成 `compat_manifest.json` 记录导入来源，不修改旧目录内容。
3. `Catalog.read_clean` 不感知来源，只读 clean。

### 4.6 验收标准

1. 三个 source 都能跑通最小拉取（最近 200 根）。
2. 多次 ingest 为追加行为，不重复、不覆盖历史。
3. `catalog.json` 的 `rows/start/end/updated_at` 与 clean 文件一致。
4. `--bootstrap-legacy` 对已有 BTC 历史数据导入后，行数与旧 accum 一致（容差 0）。

---

## 三、Phase 5：信号回测引擎

### 5.1 目标

基于 `outputs/signals/{symbol}/index.jsonl` + `data/clean/{symbol}/{interval}.parquet`，按“逐信号”而非“逐随机切片”回测，支持历史信号累计复盘。

### 5.2 文件与模块

1. 新增 [signal_backtest.py](/Users/hewei/Documents/GitHub/stock-technical-analysis/src/pipeline/signal_backtest.py)
2. 新增 [signal_loader.py](/Users/hewei/Documents/GitHub/stock-technical-analysis/src/pipeline/signal_loader.py)
3. 新增 [test_signal_backtest.py](/Users/hewei/Documents/GitHub/stock-technical-analysis/tests/test_signal_backtest.py)

### 5.3 执行流程

1. 读取 `index.jsonl`（可按 `--since --until --signal-id-prefix` 过滤）
2. 加载每条信号的 `snapshot.json`
3. 转换成统一 `parsed_json` 结构（沿用 `score_trade/score_watch`）
4. 在 clean 数据上按信号时间定位 `analysis_start`
5. 构造 `runs.jsonl`（`run_schema_version=run_v2`）
6. 复用 `src/scoring/engine.py` 打分
7. 输出 `summary.md/details.md/metrics.json`

### 5.4 输出结构

沿用当前 run 扁平结构：
- `outputs/runs/{run_id}/{symbol}/config.json`
- `outputs/runs/{run_id}/{symbol}/input.parquet`
- `outputs/runs/{run_id}/{symbol}/runs.jsonl`
- `outputs/runs/{run_id}/{symbol}/scored.jsonl`
- `outputs/runs/{run_id}/{symbol}/metrics.json`
- `outputs/runs/{run_id}/{symbol}/summary.md`
- `outputs/runs/{run_id}/{symbol}/details.md`

### 5.5 兼容策略

1. 新信号源：`outputs/signals/*`（主路径）
2. 旧信号源：支持一次性扫描 `data/binance_kline/*/analysis_skill_snapshot.json` 导入 `outputs/signals`（可选命令）
3. 评分读取优先级保持：
   - `config` 指定数据文件重建
   - `run.forward_rows`（旧格式兼容）
   - run 目录内 `input.parquet`/`eval_input.csv` 回退

### 5.6 验收标准

1. 同一批历史信号重复执行，`t1/sl/watch/missed_entry` 结果稳定一致。
2. 对 `watch/missed_entry` 不进入胜率分母，但在 summary 单独展示。
3. 对旧 run 目录回放评分可读（生成 `compat_manifest.json`）。
4. 运行时长满足 1000 条信号 < 3 分钟（本地模式）。

---

## 四、实施顺序与里程碑

1. M1（1 天）：`ingest.py + binance adapter + test_ingest`
2. M2（1 天）：`futu/yahoo adapter + catalog 更新 + bootstrap-legacy`
3. M3（1 天）：`signal_loader + signal_backtest + 回放到 scored`
4. M4（0.5 天）：报告接线 + 全量回归 + 文档补齐

---

## 五、风险与应对

1. Futu 依赖 OpenD 本地状态：
   - 应对：adapter 内做连接健康检查；失败时给出明确修复提示，不阻塞 binance/yahoo。
2. 不同 source 时间粒度不一致：
   - 应对：统一 UTC、统一 interval 映射表，写单测锁定。
3. 旧数据字段缺失：
   - 应对：转换层做容错映射，缺字段时在 compat_manifest 记录降级行为。

---

## 六、完成定义（DoD）

1. `python -m src.pipeline.ingest` 三源可用。
2. `python -m src.pipeline.signal_backtest` 能直接消费 `outputs/signals`。
3. 新旧 run 都可评分与出报告。
4. 测试通过（新增测试 + 现有测试）。
5. 文档更新：spec、plan、README 命令示例一致。
