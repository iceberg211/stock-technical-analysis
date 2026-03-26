# 交易剧本索引 (Playbooks Index)

> **Playbook = 一套完整的入场规则。不在 Playbook 里的交易，不做。**

| Playbook | 适用场景 | 核心逻辑 | 文件 |
|----------|---------|---------|------|
| **顺势回调** | 明确趋势 + 健康回调 | 趋势为友，在回调结束点顺势入场 | `trend-pullback.md` |
| **突破回踩** | 关键位被有效突破 | 等回踩确认翻转，不追突破 | `breakout-retest.md` |
| **区间反转** | 成熟震荡区间 | 仅在边缘做拒绝反转，中间不碰 | `range-reversal.md` |

不匹配任何 Playbook → 输出"当前不满足任何已定义 setup，建议观望"

匹配后，还需通过 `checklists/pre-trade-checklist.md` 的最终过滤才能输出方案
