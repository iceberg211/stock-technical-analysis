"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const api = require("../scripts/batch-analysis.js");

// 合成连续现货行情，验证协议与处理规则，不代表真实币价。
const START = Date.parse("2026-08-01T00:00:00Z");
function fixture(count = 500, interval = "1h") {
  const key = api.canonicalInterval(interval);
  const step = key === "1d" ? 86400000 : key === "4h" ? 14400000 : parseInt(key) * 60000;
  const bars = Array.from({ length: count }, (_, i) => {
    const open = START + i * step, close = 100 + i / 10 + Math.sin(i);
    return [open, String(close - 1), String(close + 1), String(close - 2), String(close),
      String(1000 + i), open + step - 1, "0", 100, "0", "0", "0"];
  });
  return { bars, serverTime: START + count * step, step };
}
function task(count = 500, interval = "1h", overrides = {}) {
  const f = fixture(count, interval);
  return { market: "crypto_spot", provider_symbol: "BTCUSDT", interval,
    source: "binance_spot_skill:/api/v3/klines", adjust_type: "none", trade_session: "continuous",
    server_time: f.serverTime, payload: f.bars, ...overrides };
}
function analyze(t) { return api.analyzeSeries(t, t.server_time); }

test("Binance原始数组转统一OHLCV及close_time，固定UTC时段", () => {
  const out = analyze(task());
  assert.equal(out.meta.analysis_bars, 500);
  assert.equal(out.meta.timeframe_status, "complete");
  assert.equal(out.meta.exchange_timezone, "UTC");
  assert.equal(out.meta.trade_session, "continuous");
  assert.equal(out.meta.adjust_type, "none");
  assert.equal(out.meta.timestamp_semantics, "open");
  assert.equal(typeof out.all[0].close, "number");
  assert.equal(out.all[0].close_time, "2026-08-01T00:59:59.999Z");
});

test("Binance插件result包装、正文与结构化响应都可解析", () => {
  const t = task();
  for (const payload of [{result:t.payload},
    {content:[{type:"text",text:JSON.stringify({result:t.payload})}]},
    {content:[],structuredContent:{result:t.payload}}]) {
    assert.equal(analyze({...t,payload}).meta.analysis_bars, 500);
  }
});

test("forming bar按服务器时钟过滤，闭合边界毫秒精度正确", () => {
  const t = task(501), closeTime = t.payload.at(-1)[6];
  const before = analyze({...t,server_time:closeTime - 1});
  assert.equal(before.meta.valid_complete_bars, 500);
  assert.equal(before.meta.excluded_incomplete_bar, 1);
  assert.equal(before.meta.timeframe_status, "complete");
  assert.equal(analyze({...t,server_time:closeTime}).meta.valid_complete_bars, 501);
});

test("历史as_of不得使用在该时刻之后才完成的K线", () => {
  const t = task(501);
  const out = api.analyzeSeries(t, t.payload.at(-1)[0]);
  assert.equal(out.meta.valid_complete_bars, 500);
  assert.equal(out.meta.excluded_incomplete_bar, 1);
});

test("缺少服务器时钟明确失败，不以本机时钟替代", () => {
  const t = task(); delete t.server_time;
  assert.throws(() => api.analyzeSeries(t, "2026-10-03T00:00:00Z"), /服务器时钟/);
});

test("UTC连续交易包含周末，无股票午休和日历警告", () => {
  const out = analyze(task());
  assert.equal(out.all[0].timestamp, "2026-08-01T00:00:00.000Z");
  assert.equal(out.meta.missing_bars, 0);
  assert.deepEqual(out.meta.data_quality_warning, []);
});

test("连续市场整段与单根缺口能识别并降级", () => {
  const t = task(525); t.payload.splice(20, 24);
  const out = analyze(t);
  assert.equal(out.meta.valid_complete_bars, 501);
  assert.equal(out.meta.analysis_bars, 500);
  assert.equal(out.meta.missing_bars, 24);
  assert.equal(out.meta.timeframe_status, "degraded_quality");
});

test("多个币圈周期窗口与文档配置一致", () => {
  for (const [interval, config] of Object.entries(api.CRYPTO_WINDOWS)) {
    const out = analyze(task(config.requested, interval));
    assert.equal(out.meta.requested_bars, config.requested);
    assert.equal(out.meta.valid_complete_bars, config.requested);
    assert.equal(out.meta.analysis_bars, config.analysis);
    assert.equal(out.meta.timeframe_status, "complete");
  }
});

test("完成窗口请求使用UTC与上一根已闭合endTime", () => {
  const clock = Date.parse("2026-10-03T04:21:00Z");
  assert.deepEqual(api.binanceRequest({provider_symbol:"BTCUSDT",interval:"1h"},clock),
    {symbol:"BTCUSDT",interval:"1h",limit:500,timeZone:"0",endTime:Date.parse("2026-10-03T03:59:59.999Z")});
  assert.equal(api.binanceRequest({provider_symbol:"BTCUSDT",interval:"4h"},clock).limit,300);
  assert.equal(api.binanceRequest({provider_symbol:"BTCUSDT",interval:"1d"},clock).endTime,
    Date.parse("2026-10-02T23:59:59.999Z"));
});

test("缺少请求时钟、不支持周期与超单次limit明确失败", () => {
  const t = {provider_symbol:"BTCUSDT",interval:"1h"};
  assert.throws(() => api.binanceRequest(t), /服务器时钟/);
  assert.throws(() => api.binanceRequest({...t,interval:"5m"},START), /支持的周期/);
  assert.throws(() => api.binanceRequest({...t,requested_bars:1001},START), /1到1000/);
});

test("非法close_time、缺失OHLC与不规则开盘时间保留异常", () => {
  const t = task(503);
  t.payload[0][6] += 1; t.payload[1][4] = null;
  t.payload[2][0] += 1; t.payload[2][6] += 1;
  const out = analyze(t);
  assert.equal(out.meta.invalid_bars,2);
  assert.equal(out.meta.irregular_bars,1);
  assert.equal(out.meta.valid_complete_bars,500);
  assert.equal(out.references[0].kind,"irregular_reference");
  assert.equal(out.meta.timeframe_status,"degraded_quality");
});

test("排序去重、冲突分类与原始响应不变", () => {
  const t = task();
  t.payload = [...t.payload].reverse(); t.payload.push([...t.payload[10]]);
  const before = JSON.stringify(t.payload);
  assert.equal(analyze(t).meta.duplicate_bars,1);
  assert.equal(JSON.stringify(t.payload),before);
  t.payload.at(-1)[5] = "9999";
  assert.equal(analyze(t).meta.duplicate_conflicts,1);
});

test("指标使用全历史预热，不从500根裁剪处重启", () => {
  const out = analyze(task(600));
  assert.equal(out.window.at(-1).dif,api.addIndicators(out.all).at(-1).dif);
  assert.notEqual(out.window[0].dif,api.addIndicators(out.all.slice(-500))[0].dif);
});

test("现货处理拒绝合约来源、股票复权与股票时段", () => {
  assert.throws(() => analyze(task(500,"1h",{source:"binance_futures"})), /合约行情/);
  assert.throws(() => analyze(task(500,"1h",{adjust_type:"forward"})), /股票复权/);
  assert.throws(() => analyze(task(500,"1h",{trade_session:"intraday"})), /continuous/);
});

test("币圈低于50根停止完整分析，低于固定窗口明确降级", () => {
  assert.equal(analyze(task(49)).meta.analysis_eligible,false);
  assert.equal(analyze(task(499)).meta.timeframe_status,"degraded_recent_only");
});

test("异常覆盖跨度停止，避免缺口枚举无界增长", () => {
  const t = task(2), shift = 25000 * 3600000;
  t.payload[1][0] += shift; t.payload[1][6] += shift; t.server_time += shift;
  assert.throws(() => analyze(t), /覆盖跨度异常/);
});

test("统一队列混合三市场，错误只影响单序列", async () => {
  const crypto = task(300,"4h");
  const out = await api.runAnalysis({as_of:crypto.server_time,tasks:[crypto,
    {...crypto,provider_symbol:"ETHUSDT",payload:{isError:true}},
    {market:"us_equity",provider_symbol:"SNDK.US",source:"longbridge",interval:"1d",payload:[]},
    {market:"cn_equity",provider_symbol:"601899.SH",source:"longbridge",interval:"1d",payload:[]} ]},
    async t=>t.payload);
  assert.equal(out.snapshots.length,3);
  assert.equal(out.errors.length,1);
  assert.equal(out.metrics.request_count,4);
  assert.equal(out.snapshots[0].meta.timeframe_status,"complete");
});
