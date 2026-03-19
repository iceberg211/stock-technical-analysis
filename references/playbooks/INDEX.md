# 交易剧本索引 (Playbooks Index)

> **Playbook = 一套完整的入场规则。不在 Playbook 里的交易，不做。**

---

## Setup 选择决策树

```
收到分析结论（Step 7 综合研判）
  │
  ├── 市场状态 = 上升/下降趋势？
  │     │
  │     ├── 是 → 正在回调到关键位？
  │     │       ├── 是 → 📘 trend-pullback.md（顺势回调）
  │     │       └── 否 → 刚突破关键位？
  │     │               ├── 是 → 📗 breakout-retest.md（突破回踩）
  │     │               └── 否 → 形成旗形/楔形中继？
  │     │                       ├── 是 → 📒 flag-wedge-breakout.md（旗形/楔形突破）
  │     │                       └── 否 → ⏳ 等回调或等突破，不追
  │     │
  │     └── 否 → 市场状态 = 震荡区间？
  │             │
  │             ├── 是 → 价格靠近区间边缘？
  │             │       ├── 是 → 刚发生假突破收回？
  │             │       │       ├── 是 → 📕 false-breakout-reversal.md（假突破反转）
  │             │       │       └── 否 → 📙 range-reversal.md（区间反转）
  │             │       └── 否 → ⏳ 区间中间不做，等靠近边缘
  │             │
  │             └── 否 → 市场状态 = 混乱/过渡
  │                     └── ❌ 不做，等结构清晰
  │
  └── 任何状态下，关键位被突破后 1~3 根 K 线内实体收回？
        └── 📕 false-breakout-reversal.md（假突破反转）
```

---

## Playbook 一览

| Playbook | 适用场景 | 核心逻辑 | 文件 |
|----------|---------|---------|------|
| **顺势回调** | 明确趋势 + 健康回调 | 趋势为友，在回调结束点顺势入场 | `trend-pullback.md` |
| **突破回踩** | 关键位被有效突破 | 等回踩确认翻转，不追突破 | `breakout-retest.md` |
| **区间反转** | 成熟震荡区间 | 仅在边缘做拒绝反转，中间不碰 | `range-reversal.md` |
| **假突破反转** | 突破后快速收回 | 被困交易者出逃 = 反向燃料 | `false-breakout-reversal.md` |
| **旗形/楔形突破** | 趋势中继形态 | 推动 → 整理 → 突破延续 | `flag-wedge-breakout.md` |

---

## 使用规则

1. **一次只匹配一个 Playbook**：如果同时匹配多个，取信心最高的那个
2. **不匹配 = 不做**：没有对应 Playbook 的行情，就是"不属于你的机会"
3. **Playbook 只管入场逻辑**：入场后的管理看 `checklists/in-trade-management.md`
4. **仓位和风控**：统一由 `risk/position-sizing.md` 决定

### 优先级（同时匹配多个时）

| 优先级 | Playbook | 原因 |
|--------|----------|------|
| 1 | trend-pullback | 顺势 + 关键位 + 回调，胜率最高 |
| 2 | false-breakout-reversal | 止损紧 + R:R 好，但需精确判断 |
| 3 | flag-wedge-breakout | 经典中继，但形态判断有主观性 |
| 4 | breakout-retest | 等回踩降低了风险，但回踩不一定来 |
| 5 | range-reversal | 区间利润有限，但在区间明确时可靠 |

---

## AI 使用指引

- 完成 Step 7 综合研判后，按上方决策树匹配 Playbook
- 如果匹配到某个 Playbook，加载对应文件获取入场/止损/目标的具体规则
- 如果不匹配任何 Playbook，在 Step 8 输出"当前不满足任何已定义 setup，建议观望"
- 匹配后，还需通过 `checklists/pre-trade-checklist.md` 的最终过滤才能输出方案
