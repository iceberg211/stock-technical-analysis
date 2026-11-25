# Price Action 状态

## 状态快照

```text
symbol
analysis_mode
analysis_time
last_complete_bar_time
timeframes
session_context
market_context
setup
position
data_fingerprint
version
last_emitted_event_id
```

`market_context` 至少包含：

```text
primary_state
alternate_state
switch_condition
always_in
location
transition
confidence
supporting_evidence
contrary_evidence
```

`setup` 至少包含：

```text
type
status: none | candidate | armed | triggered | managing | invalidated | closed
direction
trade_style: scalp | swing | mixed | no_trade
order_type: market | close | stop | limit | wait
trigger
initial_risk
logical_stop
logical_risk
target_space
targets
invalidation
candidate_since
last_transition_time
last_transition_reason
```

## 生命周期

- `none -> candidate`：状态和位置允许，但确认不足。
- `candidate -> armed`：关键确认已具备，等待明确价格触发。
- `armed -> triggered`：完整K线或计划定义的价格条件触发。
- `triggered -> managing`：入场后开始验证跟进和原交易前提。
- `candidate/armed/triggered/managing -> invalidated`：前提被推翻。
- `managing -> closed`：目标、止损或主动退出完成。
- `invalidated/closed -> none`：旧事件结束。
- `invalidated/closed -> candidate`：出现新的、具有独立证据的战法。

禁止 `none -> triggered` 和 `candidate -> managing` 等跳跃。重新入场必须生成新的事件ID。

`initial_risk`、`logical_risk` 和 `target_space` 使用可观察价位或结构描述。`actual_risk` 只能在行情运行后用于管理和复盘，不得在入场前假设已知。

## 差量输出条件

下列字段改变时视为实质变化：

- 主要状态；
- 备选状态或切换条件；
- Always In；
- 位置或转换状态；
- 主要战法类型或生命周期；
- 触发、逻辑止损、目标或失效条件；
- 剥头皮/波段方式、订单方式、初始风险、逻辑风险或目标空间；
- 数据质量警告；
- 原持仓前提状态。

仅分析时间、最新价格或普通K线追加变化时，不重复推送完整结论。
