"use strict";

// 无外部依赖；只处理调用方已取得的数据，不联网、不写行情文件。
const CN_WINDOWS = Object.freeze({
  "1d": { requested: 300, minimum: 200, analysis: 300 },
  "60m": { requested: 160, minimum: 80, analysis: 120 },
  "30m": { requested: 240, minimum: 120, analysis: 180 },
  "15m": { requested: 240, minimum: 120, analysis: 180 },
  "5m": { requested: 240, minimum: 120, analysis: 200 },
});
const US_WINDOWS = Object.freeze({
  "1d": { requested: 300, minimum: 200, analysis: 300 },
  "60m": { requested: 300, minimum: 160, analysis: 240 },
  "30m": { requested: 500, minimum: 240, analysis: 500 },
  "15m": { requested: 600, minimum: 300, analysis: 500 },
});
const CRYPTO_WINDOWS = Object.freeze({
  "1d": { requested: 300, minimum: 200, analysis: 300 },
  "4h": { requested: 300, minimum: 200, analysis: 300 },
  "60m": { requested: 500, minimum: 300, analysis: 500 },
  "30m": { requested: 500, minimum: 300, analysis: 500 },
  "15m": { requested: 500, minimum: 300, analysis: 500 },
});

function canonicalInterval(value) {
  const key = String(value).toLowerCase().replace(/min$/, "m");
  return key === "1h" ? "60m" : key === "day" ? "1d" : key;
}

function binanceRequest(task, serverTime) {
  const interval = canonicalInterval(task.interval), settings = CRYPTO_WINDOWS[interval];
  const clock = timestamp(serverTime), count = task.requested_bars ?? (settings && settings.requested);
  if (!settings || !Number.isFinite(clock)) throw new Error("币安请求需要支持的周期和服务器时钟");
  if (!Number.isInteger(count) || count < 1 || count > 1000) throw new Error("币安单次请求根数必须为1到1000");
  const ms = interval === "1d" ? 86400000 : interval === "4h" ? 14400000 : parseInt(interval, 10) * 60000;
  return { symbol: task.provider_symbol, interval: interval === "60m" ? "1h" : interval,
    limit: count, timeZone: "0", endTime: Math.floor(clock / ms) * ms - 1 };
}

function taskKey(task) {
  return JSON.stringify([
    task.source, task.provider_symbol, canonicalInterval(task.interval),
    task.adjust_type || (task.market === "crypto_spot" ? "none" : "forward"),
    task.trade_session || (task.market === "crypto_spot" ? "continuous" : "intraday"),
  ]);
}

function number(value) {
  if (value === null || value === undefined || value === "" || typeof value === "boolean") return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function timestamp(value) {
  if (typeof value === "number") {
    const ms = value < 1e12 ? value * 1000 : value;
    return Number.isFinite(ms) && Math.abs(ms) <= 8.64e15 ? ms : NaN;
  }
  // 无时区字符串不能依赖执行机器的本地时区解释。
  if (typeof value !== "string" || !/(Z|[+-]\d\d:\d\d)$/.test(value)) return NaN;
  return Date.parse(value);
}

function cnTime(ms) {
  return new Date(ms + 8 * 3600000).toISOString().slice(0, 16);
}

// 缓存格式器；由纽约时区规则处理夏令时，不使用固定UTC偏移。
const nyFormatter = new Intl.DateTimeFormat("en-CA", {
  timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit",
  hour: "2-digit", minute: "2-digit", hourCycle: "h23",
});
function exchangeTime(ms, market) {
  if (market === "cn_equity") return cnTime(ms);
  if (market === "crypto_spot") return new Date(ms).toISOString().slice(0, 16);
  const parts = Object.fromEntries(nyFormatter.formatToParts(ms).map(p => [p.type, p.value]));
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`;
}
function exchangeTimestamp(day, minute, market) {
  const hm = String(Math.floor(minute / 60)).padStart(2, "0") + ":" + String(minute % 60).padStart(2, "0");
  if (market === "cn_equity") return Date.parse(day + "T" + hm + ":00+08:00");
  if (market === "crypto_spot") return Date.parse(day + "T" + hm + ":00Z");
  // 美股开收盘均不处于夏令时切换的凌晨，迭代偏移可唯一定位。
  const desired = Date.parse(day + "T" + hm + ":00Z");
  let guess = desired;
  for (let i = 0; i < 3; i++) {
    const delta = desired - Date.parse(exchangeTime(guess, market) + ":00Z");
    guess += delta;
    if (!delta) break;
  }
  return guess;
}
function sessionClose(task, day, market) {
  const close = task.session_closes && task.session_closes[day];
  if (close !== undefined && ![780, 960].includes(close)) throw new Error("美股收盘分钟只支持13:00或16:00");
  return market === "cn_equity" ? 900 : close ?? 960;
}

function unpack(payload) {
  let body = payload;
  if (typeof body === "string") body = JSON.parse(body);
  if (body && body.isError) {
    const detail = (body.content || []).filter(c => c.type === "text").map(c => c.text).join(" ").slice(0, 240);
    throw new Error("供应商返回错误，不能作为行情解析" + (detail ? "：" + detail : ""));
  }
  if (body && Array.isArray(body.content)) {
    body = body.structuredContent ?? JSON.parse(body.content
      .filter(item => item.type === "text").map(item => item.text).join("\n"));
  }
  if (body && body.chart) {
    if (body.chart.error) throw new Error("Yahoo返回错误：" + JSON.stringify(body.chart.error));
    const result = body.chart.result && body.chart.result[0];
    if (!result) throw new Error("Yahoo缺少chart.result");
    const q = result.indicators && result.indicators.quote && result.indicators.quote[0];
    if (!q || !Array.isArray(result.timestamp)) throw new Error("Yahoo缺少OHLC序列");
    const adj = result.indicators.adjclose && result.indicators.adjclose[0].adjclose;
    return { symbol: result.meta && result.meta.symbol, yahoo: true, adjusted: !!adj,
      bars: result.timestamp.map((t, i) => ({ timestamp: t, open: q.open[i], high: q.high[i],
        low: q.low[i], close: q.close[i], volume: q.volume && q.volume[i], adjclose: adj && adj[i] })) };
  }
  const data = body && !Array.isArray(body) && body.data ? body.data : body;
  const bars = Array.isArray(data) ? data : data && (data.candlesticks || data.result);
  if (!Array.isArray(bars)) throw new Error("行情响应不是支持的K线数组");
  const binance = bars.length > 0 && Array.isArray(bars[0]);
  return { bars: binance ? bars.map(b => ({timestamp: b[0], open: b[1], high: b[2], low: b[3],
    close: b[4], volume: b[5], close_time: b[6]})) : bars,
    symbol: data && data.symbol, yahoo: false, adjusted: false, binance };
}

function grid(interval, market = "cn_equity", close = 960) {
  const minutes = parseInt(interval, 10);
  const result = [];
  for (const [start, end] of market === "us_equity" ? [[570, close]] : [[570, 690], [780, 900]]) {
    for (let m = start; m < end; m += minutes) result.push(m);
  }
  return result;
}

function addIndicators(bars) {
  let e12 = bars[0] && bars[0].close, e26 = e12, signal = 0, gain = 0, loss = 0;
  let volumeSum = 0, volumeCount = 0;
  return bars.map((bar, i) => {
    if (i) {
      e12 += (bar.close - e12) * 2 / 13;
      e26 += (bar.close - e26) * 2 / 27;
      const delta = bar.close - bars[i - 1].close;
      if (i <= 14) {
        gain += Math.max(delta, 0) / 14;
        loss += Math.max(-delta, 0) / 14;
      } else {
        gain = (gain * 13 + Math.max(delta, 0)) / 14;
        loss = (loss * 13 + Math.max(-delta, 0)) / 14;
      }
    }
    const dif = e12 - e26;
    signal = i ? signal + (dif - signal) * 2 / 10 : dif;
    if (bar.volume !== null) { volumeSum += bar.volume; volumeCount++; }
    if (i >= 20 && bars[i - 20].volume !== null) {
      volumeSum -= bars[i - 20].volume; volumeCount--;
    }
    return { ...bar, index: i, rsi: i < 14 ? null : loss === 0 ? gain === 0 ? 50 : 100 : 100 - 100 / (1 + gain / loss),
      dif, dea: signal, histogram: 2 * (dif - signal),
      vma20: i >= 19 && volumeCount === 20 ? volumeSum / 20 : null };
  });
}

function swingPoints(bars, windowStart) {
  const highs = [], lows = [];
  for (let i = Math.max(2, windowStart); i < bars.length - 2; i++) {
    const b = bars[i], left = bars.slice(i - 2, i), right = bars.slice(i + 1, i + 3);
    const point = price => ({ timestamp: b.timestamp, index: i, price,
      rsi: b.rsi, dif: b.dif, confirmed: true, scope: "local" });
    // 平台高低点只保留第一个候选，防止把相邻等价点当成背离锚点。
    if (left.every(x => b.high > x.high) && right.every(x => b.high >= x.high)) highs.push(point(b.high));
    if (left.every(x => b.low < x.low) && right.every(x => b.low <= x.low)) lows.push(point(b.low));
  }
  return { highs, lows };
}

function divergence(points, field, range) {
  const candidates = [];
  let comparisons = 0;
  for (const [kind, anchors] of [["low", points.lows], ["high", points.highs]]) {
    const recent = anchors.slice(-5), b = recent[recent.length - 1];
    if (!b || b[field] === null) continue;
    for (const a of recent.slice(0, -1).reverse()) {
      if (a[field] === null || b.index - a.index < 3 || b.index - a.index > 60) continue;
      comparisons++;
      const priceDelta = b.price - a.price, indicatorDelta = b[field] - a[field];
      const meaningfulPrice = Math.max(Math.abs(a.price) * 0.001, range * 0.01);
      const meaningfulIndicator = field === "rsi" ? 3 : Math.max(Math.abs(a.dif), Math.abs(b.dif), range * 0.001) * 0.1;
      if (Math.abs(priceDelta) < meaningfulPrice || Math.abs(indicatorDelta) < meaningfulIndicator) continue;
      let type = null;
      if (kind === "low" && priceDelta < 0 && indicatorDelta > 0) type = "bullish_regular";
      if (kind === "low" && priceDelta > 0 && indicatorDelta < 0) type = "bullish_hidden";
      if (kind === "high" && priceDelta > 0 && indicatorDelta < 0) type = "bearish_regular";
      if (kind === "high" && priceDelta < 0 && indicatorDelta > 0) type = "bearish_hidden";
      if (type) candidates.push({ type, scope: "local", anchors: [a, b].map(p => ({
        timestamp: p.timestamp, price: p.price, value: p[field], confirmed: p.confirmed,
      })) });
    }
  }
  // 数值关系只构成候选；结构相关性、主要摆动和价格确认交给分析层。
  return { state: candidates.length ? "candidate" : comparisons ? "none" : "insufficient",
    comparisons, candidates };
}

function analyzeSeries(task, asOf) {
  const market = task.market || "cn_equity", interval = canonicalInterval(task.interval);
  const settings = (market === "cn_equity" ? CN_WINDOWS : market === "us_equity" ? US_WINDOWS
    : market === "crypto_spot" ? CRYPTO_WINDOWS : {})[interval];
  if (!settings) throw new Error("处理器仅支持A股1d/5m/15m/30m/60m、美股1d/15m/30m/60m及币圈现货1d/4h/60m/30m/15m");
  asOf = timestamp(asOf);
  if (!Number.isFinite(asOf)) throw new Error("必须提供带时区的as_of或UTC时间戳");
  if (!task.provider_symbol || !task.source) throw new Error("缺少供应商代码或数据通道");
  const continuous = market === "crypto_spot";
  if (task.trade_session && task.trade_session !== (continuous ? "continuous" : "intraday")) throw new Error("股票仅支持常规交易时段intraday，币圈为continuous");
  const serverTime = continuous ? timestamp(task.server_time) : null;
  if (continuous && !Number.isFinite(serverTime)) throw new Error("币圈必须提供Binance服务器时钟server_time");
  if (continuous && /futures|perpetual/.test(task.source)) throw new Error("币圈现货不能使用合约行情");
  const intervalMs = continuous ? interval === "1d" ? 86400000 : interval === "4h" ? 14400000
    : parseInt(interval, 10) * 60000 : null;
  const daily = interval === "1d";
  if (!(daily ? ["open", "date", "unknown"] : ["open", "unknown"]).includes(task.timestamp_semantics || "unknown")) throw new Error("不支持的时间戳语义");
  const parsed = unpack(task.payload);
  if (parsed.symbol && parsed.symbol !== task.provider_symbol) throw new Error("响应标的与请求不一致");
  const warnings = new Set(), invalid = [], references = [], byTime = new Map();
  let duplicates = 0, duplicateConflicts = 0;
  const requestedAdjust = task.adjust_type || (continuous ? "none" : "forward");
  if (continuous && requestedAdjust !== "none") throw new Error("币圈现货行情不使用股票复权");
  if (parsed.yahoo && requestedAdjust === "forward" && !parsed.adjusted) warnings.add("adjustment_unverified");
  for (const raw of parsed.bars) {
    const ms = timestamp(raw.timestamp), close = number(raw.close);
    let ratio = 1;
    if (parsed.yahoo && requestedAdjust === "forward" && parsed.adjusted) {
      const adj = number(raw.adjclose);
      ratio = adj !== null && close > 0 ? adj / close : NaN;
    }
    const b = { timestamp: Number.isFinite(ms) ? new Date(ms).toISOString() : null,
      open: number(raw.open), high: number(raw.high), low: number(raw.low), close, volume: number(raw.volume) };
    if (continuous) {
      const end = timestamp(raw.close_time);
      if (!Number.isFinite(end) || end - ms !== intervalMs - 1) {
        invalid.push({reason: "invalid_close_time", raw}); continue;
      }
      b.close_time = new Date(end).toISOString();
    }
    for (const field of ["open", "high", "low", "close"]) b[field] = b[field] === null ? null : b[field] * ratio;
    if (!Number.isFinite(ms) || [b.open, b.high, b.low, b.close].some(x => !Number.isFinite(x) || x <= 0)
      || b.low > Math.min(b.open, b.close) || b.high < Math.max(b.open, b.close) || b.low > b.high
      || b.volume !== null && b.volume < 0) { invalid.push({ reason: "invalid_ohlcv", raw }); continue; }
    if (b.volume === null) warnings.add("volume_missing");
    if (byTime.has(ms)) {
      duplicates++;
      if (JSON.stringify(byTime.get(ms)) !== JSON.stringify(b)) { duplicateConflicts++; warnings.add("duplicate_conflict"); }
    }
    byTime.set(ms, b);
  }
  if (invalid.length) warnings.add("invalid_records");
  const sorted = [...byTime.entries()].sort((a, b) => a[0] - b[0]);
  const timestampKnown = task.timestamp_semantics === "open" || daily && task.timestamp_semantics === "date" || continuous && parsed.binance;
  const sessionKnown = continuous || market === "cn_equity" || task.session_closes_verified === true;
  if (!sessionKnown) warnings.add("session_calendar_unverified");
  if (!timestampKnown) warnings.add("timestamp_semantics_unverified");
  const accepted = [], incomplete = [], offgrid = [], dailyDates = new Set();
  for (const [ms, b] of sorted) {
    if (continuous) {
      if (ms % intervalMs !== 0) {
        offgrid.push(b); warnings.add("irregular_timestamp");
        references.push({...b, kind:"irregular_reference"}); continue;
      }
      if (timestamp(b.close_time) > Math.min(serverTime, asOf)) { incomplete.push(b); continue; }
      accepted.push(b); continue;
    }
    if (ms > asOf) { incomplete.push(b); continue; }
    const local = exchangeTime(ms, market), day = local.slice(0, 10);
    const minutes = Number(local.slice(11, 13)) * 60 + Number(local.slice(14));
    const close = sessionClose(task, day, market), closeTime = exchangeTimestamp(day, close, market);
    const expected = daily ? [] : grid(interval, market, close);
    if (!daily && minutes === close) {
      references.push({ ...b, kind: b.volume === 0 ? "zero_volume_placeholder" : "closing_reference" });
      if (b.volume !== 0) warnings.add("closing_reference_unmerged");
      continue;
    }
    if (!daily && (!expected.includes(minutes) || ms % 60000 !== 0)) {
      offgrid.push(b); warnings.add("irregular_timestamp");
      // 未确认归属的真实成交保留为参考，不进行取整、合并或无声删除。
      references.push({ ...b, kind: "irregular_reference" }); continue;
    }
    // 日线按当日收盘判断；美股最后一根小时线在收盘截短为30分钟。
    const end = daily || !timestampKnown ? closeTime
      : Math.min(ms + parseInt(interval, 10) * 60000, closeTime);
    if (end > asOf) { incomplete.push(b); continue; }
    if (daily && dailyDates.has(day)) {
      warnings.add("duplicate_daily_date");
      references.push({ ...b, kind: "duplicate_daily_reference" }); continue;
    }
    dailyDates.add(day);
    accepted.push(b);
  }
  // 只检查返回覆盖范围内的缺口；首尾截断不会被误认为整日缺失。
  const missing = [];
  if (accepted.length && continuous) {
    const first = timestamp(accepted[0].timestamp), last = timestamp(accepted.at(-1).timestamp);
    if ((last - first) / intervalMs > 20000) throw new Error("币圈覆盖跨度异常，停止生成过大的缺口网格");
    const existing = new Set(accepted.map(b => b.timestamp));
    for (let t = first; t <= last; t += intervalMs) {
      const iso = new Date(t).toISOString();
      if (!existing.has(iso)) missing.push(iso);
    }
    if (missing.length) warnings.add(timestampKnown ? "session_gaps" : "unverified_grid_gaps");
  } else if (accepted.length) {
    const first = timestamp(accepted[0].timestamp), last = timestamp(accepted[accepted.length - 1].timestamp);
    const represented = new Set(accepted.map(b => exchangeTime(timestamp(b.timestamp), market).slice(0, 10)));
    const days = task.trading_days || [...represented];
    if (!Array.isArray(days)) throw new Error("trading_days必须为日期数组");
    if (days.some(day => typeof day !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(day) || !Number.isFinite(Date.parse(day + "T00:00:00Z")))) throw new Error("交易日必须为ISO日期");
    if (!task.trading_days) warnings.add("calendar_unverified");
    if (task.trading_days && [...represented].some(day => !days.includes(day))) warnings.add("calendar_coverage_incomplete");
    // 美股日历声明覆盖边界；不能用仅包含已有记录的日期数组证明整日没有缺失。
    const firstDay = exchangeTime(first, market).slice(0, 10), lastDay = exchangeTime(last, market).slice(0, 10);
    if (market === "us_equity" && task.trading_days && (!task.calendar_coverage
      || task.calendar_coverage.start > firstDay || task.calendar_coverage.end < lastDay
      || !task.calendar_coverage.start || !task.calendar_coverage.end)) warnings.add("calendar_coverage_incomplete");
    const existing = new Set(accepted.map(b => b.timestamp));
    for (const day of [...new Set(days)]) {
      if (daily) {
        if (day >= firstDay && day <= lastDay && !represented.has(day)) missing.push(day);
        continue;
      }
      for (const minute of grid(interval, market, sessionClose(task, day, market))) {
        const t = exchangeTimestamp(day, minute, market);
        if (t >= first && t <= last && !existing.has(new Date(t).toISOString())) missing.push(new Date(t).toISOString());
      }
    }
    if (missing.length) warnings.add(timestampKnown && sessionKnown ? "session_gaps" : "unverified_grid_gaps");
  }
  const all = addIndicators(accepted), window = all.slice(-settings.analysis), last = all[all.length - 1];
  const historyStatus = all.length < settings.minimum ? "below_minimum"
    : window.length < settings.analysis ? "insufficient_window" : "complete";
  const quality = warnings.size ? "warning" : "verified";
  const status = all.length < 50 ? "missing" : historyStatus !== "complete" ? "degraded_recent_only"
    : quality !== "verified" ? "degraded_quality" : "complete";
  const range = window.length ? { low: Math.min(...window.map(b => b.low)), high: Math.max(...window.map(b => b.high)) } : null;
  const points = swingPoints(all, all.length - window.length);
  const recent = all.slice(-5), lastVolumeMean = last && last.vma20;
  const mean5 = recent.length === 5 && recent.every(b => b.volume !== null)
    ? recent.reduce((n, b) => n + b.volume, 0) / 5 : null;
  return { meta: { symbol: task.symbol || task.provider_symbol, provider_symbol: task.provider_symbol,
    market, exchange_timezone: continuous ? "UTC" : market === "us_equity" ? "America/New_York" : "Asia/Shanghai",
    interval, as_of: new Date(asOf).toISOString(), data_channel: task.source,
    timestamp_semantics: continuous && parsed.binance ? "open" : task.timestamp_semantics || "unknown",
    server_time: continuous ? new Date(serverTime).toISOString() : null,
    requested_bars: task.requested_bars ?? settings.requested,
    actual_bars: parsed.bars.length, valid_complete_bars: all.length, analysis_bars: window.length,
    adjust_type: parsed.yahoo && requestedAdjust === "forward" && !parsed.adjusted ? "unverified" : requestedAdjust,
    trade_session: task.trade_session || (continuous ? "continuous" : "intraday"), derived_from: null,
    source_fallback_reason: task.source_fallback_reason || null, fallback_detail: task.fallback_detail || null,
    timeframe_status: status, history_status: historyStatus, data_quality: quality, is_complete: status === "complete",
    analysis_eligible: all.length >= 50, degrade_reason: status === "complete" ? null : status === "missing"
      ? "below_50_bars" : historyStatus !== "complete" ? historyStatus : "data_quality_warning",
    coverage_start: window[0] && window[0].timestamp || null, coverage_end: last && last.timestamp || null,
    excluded_incomplete_bar: incomplete.length, invalid_bars: invalid.length, duplicate_bars: duplicates,
    duplicate_conflicts: duplicateConflicts, irregular_bars: offgrid.length,
    missing_bars: timestampKnown && sessionKnown ? missing.length : 0,
    suspected_missing_bars: timestampKnown && sessionKnown ? 0 : missing.length,
    data_quality_warning: [...warnings].sort() }, all, window, references, invalid, incomplete, missing,
    evidence: { range, last, recent, swings: points, rsi: divergence(points, "rsi", range ? range.high - range.low : 0),
      macd: divergence(points, "dif", range ? range.high - range.low : 0),
      volume: { vma20: lastVolumeMean ?? null,
        last_ratio: lastVolumeMean > 0 && last.volume !== null ? last.volume / lastVolumeMean : null,
        mean5_ratio: lastVolumeMean > 0 && mean5 !== null ? mean5 / lastVolumeMean : null } } };
}

function rounded(n) { return Number.isFinite(n) ? Number(n.toFixed(4)) : n; }

function briefSeries(snapshot, level) {
  const m = snapshot.meta, e = snapshot.evidence;
  const closing = snapshot.references.filter(b => b.kind === "closing_reference").at(-1);
  const point = p => p && [p.timestamp.slice(0, 16), rounded(p.price), rounded(p.rsi), rounded(p.dif)];
  const compactDiv = d => ({ state: d.state, candidates: d.candidates.slice(0, level === 2 ? 2 : 1).map(c => ({
    type: c.type, anchors: c.anchors.map(p => [p.timestamp.slice(0, 16), rounded(p.price), rounded(p.value)]),
  })) });
  const result = { tf: m.interval, n: [m.requested_bars, m.actual_bars, m.valid_complete_bars, m.analysis_bars],
    status: m.timeframe_status, quality: m.data_quality_warning, from: m.coverage_start, to: m.coverage_end,
    issues: [m.invalid_bars, m.irregular_bars, m.excluded_incomplete_bar, m.missing_bars, m.suspected_missing_bars],
    range: e.range && [e.range.low, e.range.high], last: e.last && e.last.close,
    close_ref: closing ? [closing.timestamp, closing.close, closing.volume] : null,
    indicators: e.last && [rounded(e.last.rsi), rounded(e.last.dif), rounded(e.last.dea), rounded(e.last.histogram)],
    volume: [rounded(e.volume.last_ratio), rounded(e.volume.mean5_ratio)],
    highs: e.swings.highs.slice(-(level === 2 ? 3 : 1)).map(point),
    lows: e.swings.lows.slice(-(level === 2 ? 3 : 1)).map(point), rsi: compactDiv(e.rsi), macd: compactDiv(e.macd) };
  if (level > 0) result.bars = e.recent.slice(-(level === 2 ? 5 : 3)).map(b => [b.timestamp.slice(11, 16), b.open, b.high, b.low, b.close, b.volume]);
  return result;
}

function renderBrief(snapshots, errors, maxChars = 12000) {
  if (!Number.isInteger(maxChars) || maxChars <= 0) throw new Error("摘要长度上限必须为正整数");
  for (const level of [2, 1, 0]) {
    const groups = new Map();
    const qualities = [...new Set(snapshots.flatMap(s => s.meta.data_quality_warning))].sort();
    const profiles = [];
    for (const s of snapshots) {
      if (!groups.has(s.meta.provider_symbol)) groups.set(s.meta.provider_symbol, { symbol: s.meta.provider_symbol, series: [] });
      const profile = { market: s.meta.market, timezone: s.meta.exchange_timezone,
        source: s.meta.data_channel, adjust: s.meta.adjust_type,
        session: s.meta.trade_session, time_semantics: s.meta.timestamp_semantics,
        fallback: s.meta.source_fallback_reason, fallback_detail: s.meta.fallback_detail };
      let profileIndex = profiles.findIndex(p => JSON.stringify(p) === JSON.stringify(profile));
      if (profileIndex < 0) { profileIndex = profiles.length; profiles.push(profile); }
      const brief = briefSeries(s, level);
      brief.profile = profileIndex;
      brief.quality = s.meta.data_quality_warning.map(w => qualities.indexOf(w));
      groups.get(s.meta.provider_symbol).series.push(brief);
    }
    const columns = ["tf", "n", "status", "quality", "profile", "from", "to", "issues", "range", "last", "close_ref",
      "indicators", "volume", "highs", "lows", "rsi", "macd"];
    const assets = [...groups.values()];
    if (level === 0) {
      // 最低档用带字段表的行数组减少重复键名，全部周期和必要证据仍保留。
      for (const asset of assets) asset.series = asset.series.map(row => columns.map(key => {
        if (key === "rsi" || key === "macd") return [row[key].state, ...row[key].candidates.map(c => [c.type, c.anchors])];
        return row[key];
      }));
    }
    const text = JSON.stringify({ schema: "batch_evidence_v1", as_of: snapshots[0] && snapshots[0].meta.as_of,
      profiles, quality_codes: qualities, level,
      columns: level === 0 ? columns : undefined,
      legend: { n: "请求/返回/有效完整/分析", indicators: "RSI/DIF/DEA/2*(DIF-DEA)", volume: "末根/20均量、近5均量/20均量",
        issues: "非法OHLCV/不规则时间/未完成/确认缺口/候选缺口", pivots: "UTC时间/价格/RSI/DIF，均为局部已确认枢轴",
        close_ref: "未合并收盘参考：UTC时间/价/量；last是周期K线收盘，不是官方报价",
        divergence: "最低档为[状态,[类型,锚点]]；锚点=UTC时间/价格/指标" },
      assets, errors });
    if (text.length <= maxChars) return { text, chars: text.length, level };
  }
  // 不截断JSON或无声删除标的、价位锚点、数据质量字段。
  throw new Error("摘要预算不足以保留全部标的证据；请拆分批次或提高max_chars");
}

function analyzeBatch(input) {
  const start = Date.now(), asOf = timestamp(input.as_of);
  if (!Number.isFinite(asOf)) throw new Error("必须提供带时区的as_of或UTC时间戳");
  if (!Array.isArray(input.series)) throw new Error("series必须为数组");
  const snapshots = [], errors = [], seen = new Set();
  for (const task of input.series) {
    const key = taskKey(task);
    if (seen.has(key)) { errors.push({ symbol: task.provider_symbol, interval: task.interval, error: "重复序列，保留首个响应" }); continue; }
    seen.add(key);
    try { snapshots.push(analyzeSeries(task, asOf)); }
    catch (error) { errors.push({ symbol: task.provider_symbol, interval: task.interval, error: error.message }); }
  }
  const processed = Date.now();
  const brief = renderBrief(snapshots, errors, input.max_chars ?? 12000);
  return { snapshots, errors, brief, metrics: { input_series: input.series.length, unique_series: seen.size,
    failed_series: errors.filter(e => !e.error.startsWith("重复")).length,
    duplicate_series: input.series.length - seen.size, normalize_indicator_ms: processed - start,
    render_ms: Date.now() - processed, total_processing_ms: Date.now() - start, output_chars: brief.chars } };
}

async function fetchBatch(tasks, fetcher, options = {}) {
  const concurrency = options.concurrency ?? 6;
  if (!Number.isInteger(concurrency) || concurrency < 1 || concurrency > 6) throw new Error("并发度必须为1到6");
  const byKey = new Map();
  for (const t of tasks) if (!byKey.has(taskKey(t))) byKey.set(taskKey(t), t);
  const unique = [...byKey.values()];
  const outcomes = Array(unique.length), started = Date.now();
  let next = 0, calls = 0, retries = 0;
  await Promise.all(Array.from({ length: Math.min(concurrency, unique.length) }, async () => {
    while (next < unique.length) {
      const index = next++, task = unique[index];
      for (let attempt = 0; attempt < 2; attempt++) {
        try {
          calls++;
          const payload = await fetcher(task);
          // 先保留每个实际响应，包括isError；由调用方提供会话内存保存函数。
          if (options.onResponse) await options.onResponse(task, payload, attempt);
          if (payload && payload.isError) {
            const error = new Error("供应商返回isError"); error.payload = payload; throw error;
          }
          outcomes[index] = { ...task, payload }; break;
        } catch (error) {
          // 只有调用方明确识别可重试的限流/临时故障才重试一次。
          if (attempt === 0 && options.retryable && options.retryable(error)) { retries++; continue; }
          outcomes[index] = { ...task, payload: error.payload || { isError: true,
            content: [{ type: "text", text: error.message }] } }; break;
        }
      }
    }
  }));
  return { series: outcomes, metrics: { fetch_wall_ms: Date.now() - started,
    request_count: calls, retry_count: retries, duplicate_request_count: 0,
    deduplicated_tasks: tasks.length - unique.length } };
}

// 跨工具调用保留同一个实例；计时从实际初始化起算，不能冒充用户端总等待。
function createRunTrace(options = {}) {
  const now = options.now || Date.now, state = options.state;
  if (state && (state.schema !== "analysis_trace_v1" || !Number.isFinite(state.started_ms))) throw new Error("无效的计时状态");
  const started = state ? state.started_ms : now(), events = state ? state.events.map(e => ({ ...e })) : [];
  const active = new Map(state ? state.active : []), auxiliaryResults = new Map(state ? state.auxiliary_results : []);
  const auxiliary = new Map(), auxiliaryBudget = options.auxiliary_budget_ms ?? (state ? state.auxiliary_budget_ms : 120000);
  if (!Number.isFinite(auxiliaryBudget) || auxiliaryBudget < 0) throw new Error("辅助预算必须为非负毫秒数");
  let auxiliaryRequests = state ? state.auxiliary_requests : 0, auxiliarySkipped = state ? state.auxiliary_skipped : 0;
  for (const [key, result] of auxiliaryResults) auxiliary.set(key, Promise.resolve(result));
  function mark(phase, event) {
    if (!["start", "end"].includes(event)) throw new Error("阶段事件必须为start或end");
    if (event === "start" && active.has(phase)) throw new Error("阶段已经开始：" + phase);
    if (event === "end" && !active.has(phase)) throw new Error("阶段尚未开始：" + phase);
    const at = now();
    if (event === "start") active.set(phase, at); else active.delete(phase);
    events.push({ phase, event, elapsed_ms: at - started });
  }
  async function measure(phase, work) {
    mark(phase, "start");
    try { return await work(); } finally { mark(phase, "end"); }
  }
  // 同一辅助项目最多实际请求一次；失败也保存，换日期参数不再触发请求。
  function auxiliaryOnce(key, work) {
    if (auxiliary.has(key)) return auxiliary.get(key);
    const pending = Promise.resolve().then(async () => {
      if (now() - started >= auxiliaryBudget) {
        auxiliarySkipped++;
        return { ok: false, skipped: true, error: "已达到观察预算，辅助校验未请求" };
      }
      const at = now();
      const phase = "auxiliary:" + key;
      mark(phase, "start");
      try {
        auxiliaryRequests++;
        const payload = await work();
        let body = payload;
        if (payload && Array.isArray(payload.content)) {
          const text = payload.content.filter(c => c.type === "text").map(c => c.text).join("\n");
          try { body = payload.structuredContent ?? JSON.parse(text); } catch { body = payload; }
        }
        if (payload && payload.isError || body && (body.error || body.error_code)) {
          return { ok: false, payload, error: body && body.message || "辅助接口返回错误", wall_ms: now() - at };
        }
        return { ok: true, payload, wall_ms: now() - at };
      } catch (error) { return { ok: false, error: error.message, wall_ms: now() - at }; }
      finally { mark(phase, "end"); }
    }).then(result => { auxiliaryResults.set(key, result); return result; });
    auxiliary.set(key, pending);
    return pending;
  }
  function snapshot() {
    const phaseMs = {}, starts = new Map();
    for (const e of events) {
      if (e.event === "start") starts.set(e.phase, e.elapsed_ms);
      else phaseMs[e.phase] = (phaseMs[e.phase] || 0) + e.elapsed_ms - starts.get(e.phase);
    }
    return { scope: "observed_run", observed_elapsed_ms: now() - started,
      end_to_end_ms: null, phases_ms: phaseMs, open_phases: [...active.keys()],
      auxiliary_request_count: auxiliaryRequests, auxiliary_skipped_count: auxiliarySkipped,
      events: events.map(e => ({ ...e })) };
  }
  function exportState() {
    if (auxiliary.size !== auxiliaryResults.size) throw new Error("辅助请求尚未结束，先await再保存状态");
    return { schema: "analysis_trace_v1", started_ms: started, events: events.map(e => ({ ...e })),
      active: [...active], auxiliary_results: [...auxiliaryResults],
      auxiliary_requests: auxiliaryRequests, auxiliary_skipped: auxiliarySkipped, auxiliary_budget_ms: auxiliaryBudget };
  }
  return Object.freeze({ mark, measure, auxiliaryOnce, snapshot, exportState });
}

async function runAnalysis(input, fetcher, options = {}) {
  const trace = options.trace || createRunTrace();
  const fetched = await trace.measure("fetch", () => fetchBatch(input.tasks, fetcher, options));
  const result = await trace.measure("process", () => analyzeBatch({
    as_of: input.as_of, series: fetched.series, max_chars: input.max_chars,
  }));
  return { ...result, metrics: { ...fetched.metrics, ...result.metrics, timing: trace.snapshot() } };
}

const BatchAnalysis = Object.freeze({ CN_WINDOWS, US_WINDOWS, CRYPTO_WINDOWS, canonicalInterval, binanceRequest, taskKey, analyzeSeries,
  analyzeBatch, renderBrief, fetchBatch, runAnalysis, createRunTrace, exchangeTime, exchangeTimestamp,
  addIndicators, divergence });

if (typeof module !== "undefined" && module.exports) {
  module.exports = BatchAnalysis;
  if (require.main === module) {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", chunk => { data += chunk; });
    process.stdin.on("end", () => {
      try {
        const result = analyzeBatch(JSON.parse(data));
        process.stdout.write(JSON.stringify({ brief: JSON.parse(result.brief.text), metrics: result.metrics }) + "\n");
        if (result.errors.some(e => !e.error.startsWith("重复"))) process.exitCode = 2;
      } catch (error) { process.stderr.write(error.message + "\n"); process.exitCode = 1; }
    });
  }
}
