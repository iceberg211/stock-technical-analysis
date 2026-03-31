#!/usr/bin/env node
/**
 * 扫描 outputs/ 目录，为每条信号计算事后验证状态，生成 Dashboard 所需的静态 JSON。
 * Run: node scripts/collect-data.mjs
 */
import { readFileSync, writeFileSync, readdirSync, existsSync, mkdirSync, statSync } from 'fs';
import { join, resolve } from 'path';
import { execSync } from 'child_process';

const ROOT = resolve(import.meta.dirname, '../../');
const OUTPUTS = join(ROOT, 'outputs');
const CLEAN_DIR = join(ROOT, 'data', 'clean');
const OUT_DIR = join(import.meta.dirname, '../public/data');

function readJsonl(path) {
  if (!existsSync(path)) return [];
  return readFileSync(path, 'utf-8').split('\n').filter(l => l.trim()).map(l => JSON.parse(l));
}

function readJson(path) {
  if (!existsSync(path)) return null;
  return JSON.parse(readFileSync(path, 'utf-8'));
}

function readMd(path) {
  if (!existsSync(path)) return '';
  return readFileSync(path, 'utf-8');
}

// ─── 信号验证：用 Python signal_scorer 对每条信号做事后验证 ───

function runSignalValidation(signals) {
  // 构建一个临时 JSON 给 Python 脚本
  const input = signals.map(s => ({
    signal_id: s.signal_id,
    symbol: s.symbol,
    timestamp_utc: s.timestamp_utc,
    decision: s.decision,
    conditional_entry: s.conditional_entry || s.snapshot?.trade?.entry_price || s.snapshot?.entry_price,
    entry_price: s.snapshot?.trade?.entry_price || s.snapshot?.entry_price,
    stop_loss: s.stop_loss || s.snapshot?.trade?.stop_loss || s.snapshot?.stop_loss,
    t1: s.t1 || s.snapshot?.trade?.t1 || s.snapshot?.t1,
    t2: s.t2 || s.snapshot?.trade?.t2 || s.snapshot?.t2,
  }));

  const tmpIn = join(OUT_DIR, '_signals_to_validate.json');
  const tmpOut = join(OUT_DIR, '_validation_results.json');
  writeFileSync(tmpIn, JSON.stringify(input));

  try {
    execSync(`python3 -c "
import json, sys, os
sys.path.insert(0, '${ROOT}')

from src.scoring.signal_scorer import score_signal

# 读取 parquet 数据（用 pandas）
import pandas as pd

signals = json.loads(open('${tmpIn}').read())
results = {}

# 按 symbol 分组加载 K 线
kline_cache = {}
for sig in signals:
    symbol = sig.get('symbol', '')
    if symbol not in kline_cache:
        path_1h = os.path.join('${CLEAN_DIR}', symbol, '1h.parquet')
        if os.path.exists(path_1h):
            df = pd.read_parquet(path_1h)
            df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
            kline_cache[symbol] = df
        else:
            kline_cache[symbol] = None

for sig in signals:
    sid = sig.get('signal_id', '')
    symbol = sig.get('symbol', '')
    ts_str = sig.get('timestamp_utc')
    decision = sig.get('decision', 'watch')

    df = kline_cache.get(symbol)
    if df is None or not ts_str:
        results[sid] = {'outcome': 'no_data', 'entry_triggered': False}
        continue

    # 找到信号时间之后的 K 线作为 forward bars
    ts = pd.to_datetime(ts_str, utc=True)
    mask = df['timestamp'] > ts
    forward_df = df[mask].head(40)

    if len(forward_df) < 5:
        results[sid] = {'outcome': 'insufficient_data', 'entry_triggered': False}
        continue

    forward_bars = forward_df.to_dict('records')
    for bar in forward_bars:
        bar['high'] = float(bar['high'])
        bar['low'] = float(bar['low'])
        bar['close'] = float(bar['close'])

    result = score_signal(sig, forward_bars)
    results[sid] = result

json.dump(results, open('${tmpOut}', 'w'))
"`, { cwd: ROOT, timeout: 30000 });

    const results = readJson(tmpOut);
    return results || {};
  } catch (e) {
    console.warn('⚠️ Signal validation failed:', e.message?.slice(0, 200));
    return {};
  } finally {
    try { require('fs').unlinkSync(tmpIn); } catch {}
    try { require('fs').unlinkSync(tmpOut); } catch {}
  }
}

// ─── 信号采集 ───

function collectSignals() {
  const signalsDir = join(OUTPUTS, 'signals');
  if (!existsSync(signalsDir)) return [];

  const signals = [];
  for (const symbol of readdirSync(signalsDir)) {
    const symbolDir = join(signalsDir, symbol);
    if (!statSync(symbolDir).isDirectory()) continue;

    const index = readJsonl(join(symbolDir, 'index.jsonl'));
    for (const entry of index) {
      const tsDir = join(symbolDir, entry.signal_id || entry.path?.split('/')?.[1] || '');
      const snapshot = readJson(join(tsDir, 'snapshot.json'));
      const report = readMd(join(tsDir, 'report.md'));
      signals.push({ ...entry, symbol, snapshot, report });
    }
  }

  // 扫描不在 index 里的目录
  for (const symbol of readdirSync(signalsDir)) {
    const symbolDir = join(signalsDir, symbol);
    if (!statSync(symbolDir).isDirectory()) continue;
    for (const ts of readdirSync(symbolDir)) {
      const tsDir = join(symbolDir, ts);
      if (!statSync(tsDir).isDirectory()) continue;
      if (signals.some(s => s.signal_id === ts || s.path?.includes(ts))) continue;

      const snapshot = readJson(join(tsDir, 'snapshot.json'));
      const report = readMd(join(tsDir, 'report.md'));
      if (!snapshot && !report) continue;

      const isOldFormat = snapshot && 'time_utc' in snapshot && !('meta' in snapshot);
      const h4State = snapshot?.['4h']?.state;

      signals.push({
        signal_id: ts,
        symbol,
        timestamp_utc: snapshot?.meta?.analysis_time || snapshot?.time_utc || ts,
        price_at_signal: snapshot?.meta?.price_at_signal || snapshot?.price_now,
        decision: snapshot?.decision?.action || snapshot?.decision || (isOldFormat ? 'watch' : 'unknown'),
        bias: snapshot?.verdict?.bias || snapshot?.bias || (h4State === 'downtrend' ? 'bearish' : h4State === 'uptrend' ? 'bullish' : 'unknown'),
        confidence: snapshot?.verdict?.confidence || snapshot?.confidence || (isOldFormat ? 'medium' : 'unknown'),
        playbook: snapshot?.decision?.playbook || snapshot?.playbook || '-',
        snapshot,
        report,
      });
    }
  }

  signals.sort((a, b) => (b.timestamp_utc || '').localeCompare(a.timestamp_utc || ''));
  return signals;
}

// ─── 回测采集（只取 signal backtest，过滤掉 local engine） ───

function collectBacktests() {
  const runsDir = join(OUTPUTS, 'runs');
  if (!existsSync(runsDir)) return [];

  const runs = [];
  for (const runId of readdirSync(runsDir)) {
    const runDir = join(runsDir, runId);
    if (!statSync(runDir).isDirectory()) continue;

    // 只保留 signal backtest 的运行（run_id 包含 signalbt）
    const isSignalBacktest = runId.includes('signalbt');

    const manifest = readJson(join(runDir, 'manifest.json'));
    const symbols = [];

    for (const item of readdirSync(runDir)) {
      const symDir = join(runDir, item);
      if (!statSync(symDir).isDirectory()) continue;

      const summary = readMd(join(symDir, 'summary.md'));
      const details = readMd(join(symDir, 'details.md'));
      const metrics = readJson(join(symDir, 'metrics.json'));
      const config = readJson(join(symDir, 'config.json'));

      if (!summary && !metrics) continue;
      symbols.push({ symbol: item, summary, details, metrics, config });
    }

    if (symbols.length === 0 && !manifest) continue;

    runs.push({
      run_id: runId,
      type: isSignalBacktest ? 'skill' : 'local',
      manifest,
      symbols,
    });
  }

  runs.sort((a, b) => b.run_id.localeCompare(a.run_id));
  return runs;
}

// ─── 对话采集 ───

function collectConversations() {
  const convDir = join(OUTPUTS, 'conversations');
  if (!existsSync(convDir)) return [];

  const globalIndex = readJsonl(join(convDir, 'index.jsonl'));
  const conversations = [];

  for (const entry of globalIndex) {
    const dir = join(convDir, entry.path || `${entry.symbol}/${entry.conversation_id}`);
    const transcript = readMd(join(dir, 'conversation.md'));
    const metadata = readJson(join(dir, 'metadata.json'));
    conversations.push({ ...entry, transcript, metadata });
  }

  conversations.sort((a, b) => (b.timestamp_utc || '').localeCompare(a.timestamp_utc || ''));
  return conversations;
}

// ─── Main ───

mkdirSync(OUT_DIR, { recursive: true });

console.log('📊 Collecting signals...');
const signals = collectSignals();

console.log('🔍 Validating signals against forward K-lines...');
const validationResults = runSignalValidation(signals);

// 将验证结果合并到信号数据中
for (const s of signals) {
  const v = validationResults[s.signal_id];
  if (v) {
    s.validation = v;
  } else {
    s.validation = { outcome: 'pending', entry_triggered: false };
  }
}

// 生成复盘统计
const tradable = signals.filter(s => s.decision === 'long' || s.decision === 'short');
const validated = tradable.filter(s => s.validation && ['t1_hit', 'sl_hit', 'neither'].includes(s.validation.outcome));
const wins = validated.filter(s => s.validation.outcome === 't1_hit');

const byDecision = {};
const byPlaybook = {};
for (const s of signals) {
  const dec = s.decision || 'unknown';
  const pb = (s.playbook && s.playbook !== '-' && s.playbook !== 'none') ? s.playbook : '无匹配';
  if (!byDecision[dec]) byDecision[dec] = { total: 0, wins: 0, losses: 0 };
  byDecision[dec].total++;
  if (s.validation?.outcome === 't1_hit') byDecision[dec].wins++;
  if (s.validation?.outcome === 'sl_hit') byDecision[dec].losses++;

  if (!byPlaybook[pb]) byPlaybook[pb] = { total: 0, wins: 0, losses: 0 };
  byPlaybook[pb].total++;
  if (s.validation?.outcome === 't1_hit') byPlaybook[pb].wins++;
  if (s.validation?.outcome === 'sl_hit') byPlaybook[pb].losses++;
}

const review = {
  total: signals.length,
  tradable: tradable.length,
  validated: validated.length,
  wins: wins.length,
  win_rate: validated.length > 0 ? (wins.length / validated.length * 100).toFixed(1) : null,
  byDecision,
  byPlaybook,
};

console.log('📋 Collecting backtests...');
const backtests = collectBacktests();

console.log('💬 Collecting conversations...');
const conversations = collectConversations();

writeFileSync(join(OUT_DIR, 'signals.json'), JSON.stringify(signals, null, 2));
writeFileSync(join(OUT_DIR, 'review.json'), JSON.stringify(review, null, 2));
writeFileSync(join(OUT_DIR, 'backtests.json'), JSON.stringify(backtests, null, 2));
writeFileSync(join(OUT_DIR, 'conversations.json'), JSON.stringify(conversations, null, 2));

const skillBacktests = backtests.filter(b => b.type === 'skill').length;

console.log(`\n✅ Data collected:`);
console.log(`   Signals: ${signals.length} (${tradable.length} tradable, ${validated.length} validated)`);
console.log(`   Validation: ${wins.length} wins / ${validated.length} total${review.win_rate ? ` (${review.win_rate}%)` : ''}`);
console.log(`   Backtests: ${backtests.length} total (${skillBacktests} skill, ${backtests.length - skillBacktests} local)`);
console.log(`   Conversations: ${conversations.length}`);
