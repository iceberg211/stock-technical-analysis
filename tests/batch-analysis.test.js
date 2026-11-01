"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const path = require("node:path");
const api = require("../scripts/batch-analysis.js");

// 合成交易日只验证处理规则，不代表真实交易所日历或行情。
function fixture(count = 160, interval = "60m") {
  const bars = [], days = [];
  const step = parseInt(api.canonicalInterval(interval));
  const day = new Date("2026-08-03T00:00:00Z");
  while (bars.length < count) {
    const d = day.toISOString().slice(0, 10);
    if (day.getUTCDay() !== 0 && day.getUTCDay() !== 6) {
      days.push(d);
      for (const [start, end] of [[570, 690], [780, 900]]) {
        for (let minute = start; minute < end && bars.length < count; minute += step) {
          const hm = String(Math.floor(minute / 60)).padStart(2, "0") + ":" + String(minute % 60).padStart(2, "0");
          const i = bars.length, close = 100 + Math.sin(i / 3) * 2 + i / 20;
          const open = i ? bars[i - 1].close : 100;
          bars.push({ timestamp: new Date(d + "T" + hm + ":00+08:00").toISOString(),
            open, high: Math.max(open, close) + 0.5, low: Math.min(open, close) - 0.5, close, volume: 100 + i });
        }
      }
    }
    day.setUTCDate(day.getUTCDate() + 1);
  }
  return { bars, days };
}

function task(count = 160, interval = "60m", overrides = {}) {
  const f = fixture(count, interval);
  return { market: "cn_equity", source: "longbridge", provider_symbol: "601899.SH", interval,
    adjust_type: "forward", trade_session: "intraday", timestamp_semantics: "open",
    trading_days: f.days, payload: f.bars, ...overrides };
}

const AS_OF = Date.parse("2026-11-01T00:00:00Z");
function analyze(t) { return api.analyzeSeries(t, AS_OF); }
function readRows(brief) {
  const body = JSON.parse(brief.text);
  return body.assets.flatMap(a => a.series.map(row => ({ symbol: a.symbol,
    ...(Array.isArray(row) ? Object.fromEntries(body.columns.map((c, i) => [c, row[i]])) : row) })));
}

test("周期别名归一化且请求键区分复权和时段", () => {
  assert.equal(api.canonicalInterval("1h"), "60m");
  assert.equal(api.canonicalInterval("30min"), "30m");
  assert.equal(api.taskKey(task(160, "1h")), api.taskKey(task(160, "60m")));
  assert.notEqual(api.taskKey(task()), api.taskKey(task(160, "60m", { adjust_type: "none" })));
  assert.notEqual(api.taskKey(task()), api.taskKey(task(160, "60m", { trade_session: "all" })));
});

test("排序去重不改变调用方原始响应", () => {
  const t = task();
  t.payload = [t.payload[10], ...t.payload.slice().reverse()];
  const before = JSON.stringify(t);
  const result = analyze(t);
  assert.equal(result.meta.duplicate_bars, 1);
  assert.equal(result.meta.valid_complete_bars, 160);
  assert.equal(result.meta.analysis_bars, 120);
  assert.equal(result.meta.timeframe_status, "complete");
  assert.equal(JSON.stringify(t), before);
});

test("冲突重复记录会降低质量", () => {
  const t = task(), b = t.payload[10];
  t.payload.push({ ...b, volume: b.volume + 10 });
  assert.equal(analyze(t).meta.timeframe_status, "degraded_quality");
  assert.equal(analyze(t).meta.duplicate_conflicts, 1);
});

test("所有校验先于裁剪和指标预热", () => {
  const t = task();
  t.payload.splice(120, 0, { ...t.payload[119], timestamp: "2026-09-14T06:01:00Z", close: 0 });
  const result = analyze(t), clean = analyze(task());
  assert.equal(result.meta.invalid_bars, 1);
  assert.equal(result.meta.analysis_bars, 120);
  assert.deepEqual(result.window, clean.window);
});

test("OHLC零值、空值、上下界和非法时间均被保留在异常清单", () => {
  const t = task();
  t.payload.push(...[
    { ...t.payload[0], close: 0 }, { ...t.payload[0], open: null },
    { ...t.payload[0], low: 999 }, { ...t.payload[0], volume: -1 },
    { ...t.payload[0], timestamp: "2026-08-03T09:30:00" },
  ]);
  const result = analyze(t);
  assert.equal(result.invalid.length, 5);
  assert.equal(result.meta.valid_complete_bars, 160);
});

test("收盘真实成交与零量占位分开保留，不混入周期指标", () => {
  const t = task(), b = t.payload.at(-1);
  const day = b.timestamp.slice(0, 10);
  t.payload.push({ ...b, timestamp: day + "T07:00:00Z", volume: 200 });
  const result = analyze(t);
  assert.equal(result.meta.valid_complete_bars, 160);
  assert.equal(result.references[0].kind, "closing_reference");
  assert.equal(result.references[0].volume, 200);
  const row = readRows(api.renderBrief([result],[],12000))[0];
  assert.equal(row.close_ref[1], b.close);
  assert.equal(row.close_ref[2], 200);
  assert.equal(result.meta.timeframe_status, "degraded_quality");
  t.payload.at(-1).volume = 0;
  const zero = analyze(t);
  assert.equal(zero.references[0].kind, "zero_volume_placeholder");
  assert.equal(zero.meta.timeframe_status, "complete");
});

test("不规则时间成交保留参考，不自动取整或合并", () => {
  const t = task(), original = { ...t.payload[0], timestamp: "2026-08-03T01:49:00Z" };
  t.payload.push(original);
  const result = analyze(t);
  assert.equal(result.meta.irregular_bars, 1);
  assert.equal(Date.parse(result.references[0].timestamp), Date.parse(original.timestamp));
  assert.equal(result.references[0].volume, original.volume);
  assert.equal(result.meta.valid_complete_bars, 160);
});

test("未完成K线和未来记录不进入分析", () => {
  const t = task(), last = t.payload.at(-1), ms = Date.parse(last.timestamp);
  const result = api.analyzeSeries(t, ms + 30 * 60000);
  assert.equal(result.meta.excluded_incomplete_bar, 1);
  assert.equal(result.all.length, 159);
  t.payload.push({ ...last, timestamp: new Date(ms + 24 * 3600000).toISOString() });
  assert.equal(api.analyzeSeries(t, ms + 30 * 60000).meta.excluded_incomplete_bar, 2);
});

test("午休、周末和窗口截断不计为缺口", () => {
  const t = task(159);
  const result = analyze(t);
  assert.equal(result.meta.missing_bars, 0);
  assert.equal(result.meta.timeframe_status, "complete");
});

test("根数足够时仍能检出覆盖内缺失K线", () => {
  const t = task(164);
  t.payload.splice(60, 1);
  const result = analyze(t);
  assert.equal(result.meta.analysis_bars, 120);
  assert.equal(result.meta.history_status, "complete");
  assert.equal(result.meta.missing_bars, 1);
  assert.equal(result.meta.timeframe_status, "degraded_quality");
});

test("交易日历可发现整日缺失且部分日历不能称完整", () => {
  const t = task(164), day = t.trading_days[10];
  t.payload = t.payload.filter(b => b.timestamp.slice(0, 10) !== day);
  assert.equal(analyze(t).meta.missing_bars, 4);
  t.trading_days = t.trading_days.slice(-3);
  assert.ok(analyze(t).meta.data_quality_warning.includes("calendar_coverage_incomplete"));
});

test("时间语义未知时缺口只是候选，根数足够也不能称完整", () => {
  const t = task(164, "60m", { timestamp_semantics: "unknown" });
  t.payload.splice(60, 1);
  const result = analyze(t);
  assert.equal(result.meta.missing_bars, 0);
  assert.equal(result.meta.suspected_missing_bars, 1);
  assert.equal(result.meta.timeframe_status, "degraded_quality");
  assert.ok(result.meta.data_quality_warning.includes("unverified_grid_gaps"));
});

test("缺少日历明确降级，不猜测休市日", () => {
  const t = task(); delete t.trading_days;
  const result = analyze(t);
  assert.equal(result.meta.timeframe_status, "degraded_quality");
  assert.ok(result.meta.data_quality_warning.includes("calendar_unverified"));
});

test("117根小时窗口降级，49根停止完整分析", () => {
  const recent = analyze(task(117));
  assert.equal(recent.meta.analysis_bars, 117);
  assert.equal(recent.meta.timeframe_status, "degraded_recent_only");
  assert.equal(recent.meta.analysis_eligible, true);
  const missing = analyze(task(49));
  assert.equal(missing.meta.timeframe_status, "missing");
  assert.equal(missing.meta.analysis_eligible, false);
});

test("Wilder RSI14与已知价格样例一致", () => {
  const close = [44.34,44.09,44.15,43.61,44.33,44.83,45.1,45.42,45.84,46.08,45.89,46.03,45.61,46.28,46.28];
  const out = api.addIndicators(close.map(c => ({ close: c, volume: 100 })));
  assert.equal(out[13].rsi, null);
  assert.ok(Math.abs(out[14].rsi - 70.46413502109705) < 1e-10);
});

test("EMA首值与MACD柱口径固定", () => {
  const out = api.addIndicators([100, 110].map(close => ({ close, volume: 100 })));
  assert.equal(out[0].dif, 0);
  assert.ok(Math.abs(out[1].dif - (20/13 - 20/27)) < 1e-10);
  assert.ok(Math.abs(out[1].dea - out[1].dif * 0.2) < 1e-10);
  assert.ok(Math.abs(out[1].histogram - 2 * (out[1].dif - out[1].dea)) < 1e-10);
});

test("上涨、下跌、平价RSI和零成交量不产生NaN", () => {
  for (const [delta, expected] of [[1,100],[-1,0],[0,50]]) {
    const bars = Array.from({ length: 25 }, (_, i) => ({ close: 100 + i * delta, volume: 0 }));
    assert.equal(api.addIndicators(bars).at(-1).rsi, expected);
  }
  const t = task(); t.payload.forEach(b => b.volume = 0);
  const v = analyze(t).evidence.volume;
  assert.equal(v.vma20, 0);
  assert.equal(v.last_ratio, null);
  assert.equal(v.mean5_ratio, null);
});

test("VMA20预热及缺量情况正确", () => {
  const bars = Array.from({ length: 25 }, (_, i) => ({ close: 100, volume: i + 1 }));
  const out = api.addIndicators(bars);
  assert.equal(out[18].vma20, null);
  assert.equal(out[19].vma20, 10.5);
  assert.equal(out[24].vma20, 15.5);
  bars[10].volume = null;
  assert.equal(api.addIndicators(bars)[24].vma20, null);
  const t = task(); delete t.payload[100].volume;
  assert.ok(analyze(t).meta.data_quality_warning.includes("volume_missing"));
});

test("指标使用裁剪前历史预热", () => {
  const t = task(), result = analyze(t), full = api.addIndicators(t.payload);
  assert.equal(result.window.at(-1).rsi, full.at(-1).rsi);
  assert.equal(result.window.at(-1).dif, full.at(-1).dif);
  assert.notEqual(result.window.at(-1).dif, api.addIndicators(t.payload.slice(-120)).at(-1).dif);
});

test("背离不足证据、无关系及数学候选分开", () => {
  const point = (index, price, rsi, dif) => ({ timestamp: "2026-09-30T01:30:00Z", index, price, rsi, dif, confirmed: true });
  const a = point(20, 100, 20, -5), b = point(30, 90, 30, -3);
  assert.equal(api.divergence({ lows: [a], highs: [] }, "rsi", 20).state, "insufficient");
  assert.equal(api.divergence({ lows: [a, {...b, rsi: 10}], highs: [] }, "rsi", 20).state, "none");
  const div = api.divergence({ lows: [a,b], highs: [] }, "rsi", 20);
  assert.equal(div.state, "candidate");
  assert.equal(div.candidates[0].type, "bullish_regular");
  assert.equal(div.candidates[0].anchors.length, 2);
  assert.equal(api.divergence({ lows: [a,{...b, price: 99.999}], highs: [] }, "rsi", 20).state, "none");
});

test("MCP正文与结构化内容都能解析，响应错误不当作行情", () => {
  const t = task(), payload = t.payload;
  assert.equal(analyze({...t, payload: {content: [{type:"text", text: JSON.stringify(payload)}]}}).all.length, 160);
  assert.equal(analyze({...t, payload: {content: [], structuredContent: {candlesticks: payload, symbol: t.provider_symbol}}}).all.length, 160);
  assert.throws(() => analyze({...t, payload: {isError:true, content:[]}}), /供应商返回错误/);
  assert.throws(() => analyze({...t, payload: {symbol:"WRONG",candlesticks:payload}}), /标的/);
});

test("Yahoo复权OHLC使用同一比例，缺少复权数据明确降级", () => {
  const t = task(), bars = t.payload;
  const result = {meta:{symbol:"601899.SS"}, timestamp:bars.map(b=>Date.parse(b.timestamp)/1000),
    indicators:{quote:[Object.fromEntries(["open","high","low","close","volume"].map(k=>[k,bars.map(b=>b[k])]))],
      adjclose:[{adjclose:bars.map(b=>b.close/2)}]}};
  const yahoo = {...t, provider_symbol:"601899.SS", source:"yahoo_finance_chart_api", payload:{chart:{result:[result],error:null}}};
  const snap = analyze(yahoo);
  assert.equal(snap.all[0].open, bars[0].open/2);
  assert.equal(snap.all[0].high, bars[0].high/2);
  assert.equal(snap.all[0].close, bars[0].close/2);
  delete result.indicators.adjclose;
  assert.equal(analyze(yahoo).meta.adjust_type, "unverified");
  assert.equal(analyze(yahoo).meta.timeframe_status, "degraded_quality");
});

test("单序列解析失败隔离，不支持市场明确失败", () => {
  const result = api.analyzeBatch({as_of:AS_OF,series:[task(),task(160,"30m",{payload:{content:[{type:"text",text:"非法JSON"}]}})]});
  assert.equal(result.snapshots.length, 1);
  assert.equal(result.errors.length, 1);
  assert.throws(() => analyze(task(160,"60m",{market:"hk_equity"})), /仅支持A股/);
});

test("摘要在硬上限内保留18组序列、质量字段和价位", () => {
  const series = Array.from({length:6},(_,i)=>["60m","30m","5m"].map(p=>task(p==="60m"?160:240,p,{provider_symbol:`60000${i}.SH`}))).flat();
  const result = api.analyzeBatch({as_of:AS_OF,series,max_chars:12000});
  assert.ok(result.brief.chars <= 12000);
  const rows = readRows(result.brief);
  assert.equal(rows.length, 18);
  assert.equal(new Set(rows.map(r=>r.symbol)).size, 6);
  for (const row of rows) {
    assert.equal(row.n.length, 4);
    assert.ok(row.range[1] >= row.last && row.range[0] <= row.last);
    assert.ok(Array.isArray(row.quality));
  }
  assert.throws(()=>api.renderBrief(result.snapshots,[],100), /预算不足/);
});

test("重新渲染不更改快照，不重复计算指标", () => {
  const snap = analyze(task()), before = JSON.stringify(snap);
  api.renderBrief([snap],[],12000); api.renderBrief([snap],[],12000);
  assert.equal(JSON.stringify(snap), before);
});

test("队列限制并发、去重且跨周期执行", async () => {
  const tasks = Array.from({length:18},(_,i)=>task(160,["60m","30m","5m"][i%3],{provider_symbol:`600${String(i).padStart(3,"0")}.SH`}));
  let active=0,maxActive=0,calls=0; const started=[],saved=[];
  const result = await api.fetchBatch([...tasks,tasks[0]], async t=>{
    active++; calls++; maxActive=Math.max(maxActive,active); started.push(t.interval);
    await new Promise(resolve=>setTimeout(resolve,5)); active--; return [];
  }, {concurrency:4,onResponse:(t,p)=>saved.push(t.provider_symbol)});
  assert.equal(calls,18); assert.equal(saved.length,18);
  assert.equal(maxActive,4); assert.ok(started.slice(0,4).includes("5m"));
  assert.equal(result.metrics.deduplicated_tasks,1);
  assert.equal(result.metrics.duplicate_request_count,0);
});

test("临时失败仅重试失败项一次，成功响应只获取一次", async () => {
  const tasks=[task(),task(160,"30m")],counts=new Map();
  const result = await api.fetchBatch(tasks,async t=>{
    const n=(counts.get(t.interval)||0)+1; counts.set(t.interval,n);
    if(t.interval==="30m"&&n===1){const e=new Error("限流");e.status=429;throw e;} return [];
  },{retryable:e=>e.status===429});
  assert.equal(counts.get("60m"),1); assert.equal(counts.get("30m"),2);
  assert.equal(result.metrics.retry_count,1);
});

test("MCP错误原样保存且鉴权失败不自动重试", async () => {
  const saved=[];let calls=0;
  const result=await api.fetchBatch([task()],async()=>{calls++;return{isError:true,content:[{type:"text",text:"鉴权失败"}]};},
    {onResponse:(t,p)=>saved.push(p)});
  assert.equal(calls,1);assert.equal(saved[0].isError,true);assert.equal(result.series[0].payload.isError,true);
});

test("解析失败不触发重新请求", async () => {
  let calls=0;const fetched=await api.fetchBatch([task()],async()=>{calls++;return{content:[{type:"text",text:"not-json"}]};});
  const result=api.analyzeBatch({as_of:AS_OF,series:fetched.series});
  assert.equal(calls,1);assert.equal(result.errors.length,1);
});

test("CLI标准输入可运行且正常/部分失败退出码明确", () => {
  const cli=path.join(__dirname,"../scripts/batch-analysis.js");
  const input={as_of:AS_OF,series:[task()]};
  const ok=spawnSync(process.execPath,[cli],{input:JSON.stringify(input),encoding:"utf8"});
  assert.equal(ok.status,0);assert.equal(JSON.parse(ok.stdout).brief.assets.length,1);
  input.series.push(task(160,"30m",{payload:{isError:true}}));
  const failed=spawnSync(process.execPath,[cli],{input:JSON.stringify(input),encoding:"utf8"});
  assert.equal(failed.status,2);assert.equal(JSON.parse(failed.stdout).brief.errors.length,1);
});

test("固定窗口代码与文档约定一致", () => {
  const text = require("node:fs").readFileSync(path.join(__dirname,"../workflows/data-acquisition-workflow.md"),"utf8");
  for (const [interval,c] of Object.entries(api.CN_WINDOWS)) {
    const re = new RegExp("\\| A 股 \\| `"+(interval === "1d" ? "1D" : interval)+"` \\| (\\d+) \\| (\\d+) \\| (\\d+) \\|");
    const row = text.match(re);
    assert.ok(row);
    assert.deepEqual(row.slice(1).map(Number),[c.requested,c.minimum,c.analysis]);
  }
});

test("持续临时故障最多两次请求，其他成功项不重试", async () => {
  const calls=new Map();
  const out=await api.fetchBatch([task(),task(160,"30m")],async t=>{
    calls.set(t.interval,(calls.get(t.interval)||0)+1);
    if(t.interval==="30m"){const e=new Error("临时故障");e.status=503;throw e;}
    return [];
  },{retryable:e=>e.status===503});
  assert.equal(calls.get("60m"),1);assert.equal(calls.get("30m"),2);
  assert.equal(out.series[1].payload.isError,true);
  assert.equal(out.metrics.retry_count,1);
});

test("不合法并发度和as_of明确失败", async () => {
  await assert.rejects(api.fetchBatch([task()],async()=>[],{concurrency:7}),/并发度/);
  assert.throws(()=>api.analyzeBatch({as_of:"无时区",series:[]}),/as_of/);
  assert.throws(()=>api.analyzeBatch({as_of:1e100,series:[]}),/as_of/);
  assert.throws(()=>analyze(task(160,"60m",{trade_session:"all"})),/常规交易时段/);
});

test("完整处理器可在工具JS环境加载且不启动CLI或联网", () => {
  const source=require("node:fs").readFileSync(path.join(__dirname,"../scripts/batch-analysis.js"),"utf8");
  const embedded=new Function(source+"\nreturn BatchAnalysis;")();
  const result=embedded.analyzeBatch({as_of:AS_OF,series:[task()]});
  assert.equal(result.snapshots.length,1);
  assert.equal(result.snapshots[0].meta.analysis_bars,120);
});

test("A股日线300根窗口可处理，不套分钟网格", () => {
  const payload = [], days = [], day = new Date("2025-01-02T00:00:00Z");
  while (payload.length < 300) {
    if (![0,6].includes(day.getUTCDay())) {
      const date = day.toISOString().slice(0,10); days.push(date);
      payload.push({timestamp:date+"T01:30:00Z",open:100,high:102,low:99,close:101,volume:1000});
    }
    day.setUTCDate(day.getUTCDate()+1);
  }
  const t = task(160,"1d",{payload,trading_days:days});
  const out = analyze(t);
  assert.equal(out.meta.valid_complete_bars,300);
  assert.equal(out.meta.analysis_bars,300);
  assert.equal(out.meta.timeframe_status,"complete");
});

test("A股日线15:00完成，不能加24小时判断", () => {
  const t = {market:"cn_equity",source:"longbridge",provider_symbol:"601899.SH",interval:"1d",
    timestamp_semantics:"date",payload:[{timestamp:"2026-09-30T01:30:00Z",open:100,high:102,low:99,close:101,volume:1000}]};
  assert.equal(api.analyzeSeries(t,"2026-09-30T06:59:59Z").all.length,0);
  assert.equal(api.analyzeSeries(t,"2026-09-30T07:00:00Z").all.length,1);
});
