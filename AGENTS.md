# Repository Guidelines

## 项目结构与模块组织

本仓库是 Python 技术分析与回测流水线项目，核心代码在 `src/`：

- `src/pipeline/`：数据摄入、回测、信号写入、目录布局与 CLI 入口。
- `src/indicators/`、`src/scoring/`、`src/reporting/`、`src/prompt/`：指标计算、评分、报告与提示词拼装。
- `tests/`：单元测试，按模块拆分（如 `test_ingest.py`、`test_scoring.py`）。
- `data/`：行情索引与输入数据目录；`outputs/`：回测与信号产物；`workflows/` 与 `references/`：流程与知识库文档。

## 构建、测试与开发命令

- `python -m src --symbols BTCUSDT --interval 1h --engine local --sample 5`：运行主流水线（本地规则引擎示例）。
- `python -m src.pipeline.ingest --source binance --symbol BTCUSDT --interval 1h --limit 1000`：拉取并整理行情到 `data/clean/`。
- `python -m unittest discover -s tests -p "test_*.py"`：运行全部测试。
- `python -m unittest tests.test_ingest`：定向运行单个测试模块。

## 代码风格与命名规范

- 遵循 PEP 8，使用 4 空格缩进，类型注解与小函数优先。
- 文件/模块/函数使用 `snake_case`，类名使用 `PascalCase`，常量使用全大写（如 `DEFAULT_CACHE_FILE`）。
- 注释与文档优先中文，强调“输入-处理-输出”与边界条件，避免空泛注释。

## 测试规范

- 测试框架为 `unittest`，测试文件命名为 `test_*.py`，测试类以 `Test` 开头。
- 新增功能需覆盖正常路径与失败路径；涉及数据合并、时间戳、目录写入时必须加回归测试。
- 涉及 parquet 的用例可参考现有 `skipUnless` 写法，避免本地缺依赖导致误报。

## 提交与 Pull Request 规范

- 提交信息沿用仓库历史风格：`feat:`、`fix:`、`chore:` + 简短描述。
- 单次提交聚焦单一目的（功能、重构或修复不要混在一起）。
- PR 需说明：变更动机、核心改动、测试命令与结果、对 `data/`/`outputs/` 产物的影响。
- 如调整报告模板或信号格式，请附示例输出路径（如 `outputs/signals/<SYMBOL>/<RUN_ID>/report.md`）。

## 数据与安全说明

- 默认不提交可再生数据：`data/raw/`、`data/clean/`、`outputs/runs/`、`eval/results/`（见 `.gitignore`）。
- 严禁提交密钥与本地环境文件（`.env*`）；模型参数请通过环境变量注入（如 `EVAL_MODEL`）。

## 架构与协作建议

- 先摄入后回测：建议流程为 `ingest -> main pipeline -> scoring/reporting`，避免直接手改 `outputs/` 产物。
- 修改 `src/pipeline/layout.py`、`manifest.py` 或 `signals.py` 时，需同步检查 `tests/test_layout.py`、`tests/test_signals.py`，防止路径与索引格式回归。
- 新增数据源适配器时，优先扩展 `src/pipeline/adapters.py` 并保持返回字段一致（`timestamp/open/high/low/close/volume`）。
- 对 Agent 提示词相关变更，需同时检查 `SKILL.md` 与 `workflows/`，确保输入输出模板与评分逻辑一致。

## 常见开发任务示例

- 新增指标：在 `src/indicators/calc.py` 增加函数，在 `tests/test_indicators.py` 增加同名场景测试。
- 新增信号规则：修改 `src/pipeline/signals.py` 或 `src/pipeline/signal_backtest.py`，并验证 `outputs/signals/<SYMBOL>/index.jsonl` 结构未破坏。
- 调整评分逻辑：修改 `src/scoring/engine.py`、`src/reporting/metrics.py` 后，至少运行 `python -m unittest tests.test_scoring`。
- 回归验证建议：提交前执行一次 `python -m unittest discover -s tests -p "test_*.py"` 并在 PR 描述中粘贴关键结果。
