"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const api = require("../scripts/batch-analysis.js");

// 合成行情只验证处理行为，不代表真实价格或交易所日历。
function bar(timestamp, close = 100) {
  return { timestamp, open: close - 1, high: close + 1, low: close - 2, close, volume: 1000 };
}
function usTask(interval, payload, overrides = {}) {
  const days = [...new Set(payload.map(b => api.exchangeTime(Date.parse(b.timestamp), "us_equity").slice(0, 10)))];
  return { market: "us_equity", provider_symbol: "SNDK.US", source: "longbridge", interval,
    adjust_type: "forward", trade_session: "intraday", timestamp_semantics: interval === "1d" ? "date" : "open",
    trading_days: days, calendar_coverage: { start: days[0], end: days.at(-1) }, session_closes_verified: true,
    payload, ...overrides };
}
function history(interval, count = 300) {
  const result = [], day = new Date("2025-01-02T00:00:00Z");
  while (result.length < count) {
    if (![0, 6].includes(day.getUTCDay())) {
      const date = day.toISOString().slice(0, 10);
      const minutes = interval === "1d" ? [0] : [570, 630, 690, 750, 810, 870, 930];
      for (const minute of minutes) {
        if (result.length === count) break;
        result.push(bar(new Date(api.exchangeTimestamp(date, minute, "us_equity")).toISOString(),
          100 + result.length / 10 + Math.sin(result.length)));
      }
    }
    day.setUTCDate(day.getUTCDate() + 1);
  }
  return result;
}

test("美股纽约时区自动处理冬夏令时，开收盘UTC定位正确", () => {
  for (const [date, open, close] of [
    ["2026-03-06", "2026-03-06T14:30:00Z", "2026-03-06T21:00:00Z"],
    ["2026-03-09", "2026-03-09T13:30:00Z", "2026-03-09T20:00:00Z"],
    ["2026-11-02", "2026-11-02T14:30:00Z", "2026-11-02T21:00:00Z"],
  ]) {
    assert.equal(api.exchangeTimestamp(date, 570, "us_equity"), Date.parse(open));
    assert.equal(api.exchangeTimestamp(date, 960, "us_equity"), Date.parse(close));
    assert.equal(api.exchangeTime(Date.parse(open), "us_equity"), date + "T09:30");
  }
});

test("最后15:30小时K线在16:00完成，不误删成16:30未完成", () => {
  const t = usTask("60m", [bar("2026-10-01T19:30:00Z")]);
  assert.equal(api.analyzeSeries(t, "2026-10-01T19:59:59Z").all.length, 0);
  const result = api.analyzeSeries(t, "2026-10-01T20:00:00Z");
  assert.equal(result.all.length, 1);
  assert.equal(result.meta.irregular_bars, 0);
});

test("美股午间持续交易，不套A股午休；16:00附加记录保留参考", () => {
  const t = usTask("60m", [bar("2026-10-01T15:30:00Z"), bar("2026-10-01T16:30:00Z"),
    bar("2026-10-01T20:00:00Z")]);
  const result = api.analyzeSeries(t, "2026-10-02T00:00:00Z");
  assert.equal(result.all.length, 2);
  assert.equal(result.references[0].kind, "closing_reference");
  assert.ok(result.meta.data_quality_warning.includes("closing_reference_unmerged"));
});

test("已确认半日市末根12:30小时线在13:00完成", () => {
  const t = usTask("60m", [bar("2026-11-27T17:30:00Z")], { session_closes: { "2026-11-27": 780 } });
  assert.equal(api.analyzeSeries(t, "2026-11-27T17:59:59Z").all.length, 0);
  assert.equal(api.analyzeSeries(t, "2026-11-27T18:00:00Z").all.length, 1);
});

test("日线当地零点标签按同日收盘判断，不加24小时", () => {
  const t = usTask("1d", [bar("2026-10-01T04:00:00Z")]);
  assert.equal(api.analyzeSeries(t, "2026-10-01T19:59:59Z").all.length, 0);
  assert.equal(api.analyzeSeries(t, "2026-10-01T20:00:00Z").all.length, 1);
  assert.equal(api.analyzeSeries(t, "2026-10-02T06:36:00Z").all.length, 1);
});

test("半日市日线同样在13:00完成", () => {
  const t = usTask("1d", [bar("2026-11-27T05:00:00Z")], { session_closes: { "2026-11-27": 780 } });
  assert.equal(api.analyzeSeries(t, "2026-11-27T18:00:00Z").all.length, 1);
});

test("默认300根日线与300根小时线固定窗口和指标预热正确", () => {
  for (const [interval, count] of [["1d", 300], ["60m", 240]]) {
    const t = usTask(interval, history(interval));
    const out = api.analyzeSeries(t, "2026-10-03T00:00:00Z");
    assert.equal(out.meta.requested_bars, 300);
    assert.equal(out.meta.valid_complete_bars, 300);
    assert.equal(out.meta.analysis_bars, count);
    assert.equal(out.meta.timeframe_status, "complete");
    assert.equal(out.window.at(-1).dif, api.addIndicators(out.all).at(-1).dif);
    assert.equal(out.meta.exchange_timezone, "America/New_York");
  }
});

test("未核验日历和半日市时保留质量降级，不凭根数称完整", () => {
  const t = usTask("60m", history("60m"));
  delete t.trading_days; delete t.calendar_coverage; delete t.session_closes_verified;
  const out = api.analyzeSeries(t, "2026-10-03T00:00:00Z");
  assert.equal(out.meta.analysis_bars, 240);
  assert.equal(out.meta.timeframe_status, "degraded_quality");
  assert.ok(out.meta.data_quality_warning.includes("calendar_unverified"));
  assert.ok(out.meta.data_quality_warning.includes("session_calendar_unverified"));
});

test("日线日历能识别整日缺失，部分覆盖声明不能称完整", () => {
  const t = usTask("1d", history("1d", 301));
  t.payload.splice(100, 1);
  const out = api.analyzeSeries(t, "2026-10-03T00:00:00Z");
  assert.equal(out.meta.missing_bars, 1);
  assert.equal(out.meta.timeframe_status, "degraded_quality");
  t.calendar_coverage.start = t.trading_days[20];
  assert.ok(api.analyzeSeries(t, "2026-10-03T00:00:00Z").meta.data_quality_warning.includes("calendar_coverage_incomplete"));
});

test("美股未知时间语义仍可分析闭市历史，并明确标记限制", () => {
  const t = usTask("60m", history("60m"), { timestamp_semantics: "unknown" });
  const out = api.analyzeSeries(t, "2026-10-03T00:00:00Z");
  assert.equal(out.meta.valid_complete_bars, 300);
  assert.equal(out.meta.timeframe_status, "degraded_quality");
});

test("同市场辅助日历并发与失败后再调用均只请求一次", async () => {
  const trace = api.createRunTrace(); let calls = 0;
  const fetcher = async () => {
    calls++;
    return { isError: true, content: [{ type: "text", text: JSON.stringify({error_code:301600,message:"too many query days"}) }] };
  };
  const results = await Promise.all([trace.auxiliaryOnce("calendar:US", fetcher), trace.auxiliaryOnce("calendar:US", fetcher)]);
  assert.equal(calls, 1); assert.equal(results[0].ok, false);
  assert.equal(results[0].error, "too many query days");
  await trace.auxiliaryOnce("calendar:US", fetcher);
  assert.equal(calls, 1); assert.equal(trace.snapshot().auxiliary_request_count, 1);
});

test("辅助预算耗尽直接跳过请求，不伪造完成校验", async () => {
  let clock = 0, calls = 0;
  const trace = api.createRunTrace({ now: () => clock, auxiliary_budget_ms: 100 });
  clock = 100;
  const result = await trace.auxiliaryOnce("calendar:US", async () => { calls++; });
  assert.equal(calls, 0); assert.equal(result.ok, false); assert.equal(result.skipped, true);
  assert.equal(trace.snapshot().auxiliary_request_count, 0);
  assert.equal(trace.snapshot().auxiliary_skipped_count, 1);
});

test("阶段时长与观察总时长分开记录，未伪造端到端耗时", async () => {
  let clock = 100;
  const trace = api.createRunTrace({ now: () => clock });
  trace.mark("rules", "start"); clock = 120; trace.mark("rules", "end");
  await trace.measure("fetch", async () => { clock = 160; });
  clock = 200;
  const out = trace.snapshot();
  assert.deepEqual(out.phases_ms, { rules: 20, fetch: 40 });
  assert.equal(out.observed_elapsed_ms, 100);
  assert.equal(out.end_to_end_ms, null);
  await assert.rejects(trace.measure("auxiliary", async () => { throw Error("失败"); }), /失败/);
  assert.deepEqual(trace.snapshot().open_phases, []);
});

test("两周期一次运行并发取数、单次处理、保存原始响应和计时", async () => {
  const tasks = [usTask("1d", history("1d")), usTask("60m", history("60m"))];
  let active = 0, maxActive = 0, calls = 0; const saved = [];
  const trace = api.createRunTrace();
  const out = await api.runAnalysis({ tasks, as_of: "2026-10-03T00:00:00Z" }, async t => {
    calls++; active++; maxActive = Math.max(maxActive, active);
    await new Promise(resolve => setTimeout(resolve, 5)); active--;
    return t.payload;
  }, { trace, onResponse: (task, payload) => saved.push(payload) });
  assert.equal(calls, 2); assert.equal(maxActive, 2); assert.equal(saved.length, 2);
  assert.equal(out.errors.length, 0); assert.equal(out.snapshots.length, 2);
  assert.equal(out.metrics.input_series, 2); assert.equal(out.metrics.request_count, 2);
  assert.ok(out.metrics.timing.phases_ms.fetch >= 0); assert.ok(out.metrics.timing.phases_ms.process >= 0);
  assert.equal(out.metrics.timing.end_to_end_ms, null);
  assert.ok(out.brief.chars < 6000);
});

test("美股不支持周期明确失败，日线别名一致", () => {
  assert.equal(api.canonicalInterval("1D"), "1d");
  assert.equal(api.canonicalInterval("day"), "1d");
  assert.throws(() => api.analyzeSeries(usTask("5m", []), "2026-10-03T00:00:00Z"), /仅支持/);
});

test("计时状态可序列化跨工具恢复，保留开始时间和失败去重", async () => {
  let clock = 100, calls = 0;
  const trace = api.createRunTrace({ now: () => clock });
  trace.mark("rules", "start"); clock = 120; trace.mark("rules", "end");
  await trace.auxiliaryOnce("calendar:US", async () => { calls++; throw Error("范围受限"); });
  const state = JSON.parse(JSON.stringify(trace.exportState()));
  clock = 200;
  const resumed = api.createRunTrace({ state, now: () => clock });
  const result = await resumed.auxiliaryOnce("calendar:US", async () => { calls++; return []; });
  assert.equal(calls, 1); assert.equal(result.ok, false);
  assert.equal(resumed.snapshot().observed_elapsed_ms, 100);
  assert.equal(resumed.snapshot().phases_ms.rules, 20);
  assert.equal(resumed.snapshot().auxiliary_request_count, 1);
  assert.equal(resumed.snapshot().phases_ms["auxiliary:calendar:US"], 0);
});
