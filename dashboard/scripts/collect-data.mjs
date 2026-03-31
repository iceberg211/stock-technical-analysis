#!/usr/bin/env node
/**
 * Scan outputs/ directory and generate static JSON for the dashboard.
 * Run: node scripts/collect-data.mjs
 */
import { readFileSync, writeFileSync, readdirSync, existsSync, mkdirSync, statSync } from 'fs';
import { join, resolve } from 'path';

const ROOT = resolve(import.meta.dirname, '../../');
const OUTPUTS = join(ROOT, 'outputs');
const OUT_DIR = join(import.meta.dirname, '../public/data');

function readJsonl(path) {
  if (!existsSync(path)) return [];
  return readFileSync(path, 'utf-8')
    .split('\n')
    .filter(l => l.trim())
    .map(l => JSON.parse(l));
}

function readJson(path) {
  if (!existsSync(path)) return null;
  return JSON.parse(readFileSync(path, 'utf-8'));
}

function readMd(path) {
  if (!existsSync(path)) return '';
  return readFileSync(path, 'utf-8');
}

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

      signals.push({
        ...entry,
        symbol,
        snapshot,
        report,
      });
    }
  }

  // Also scan dirs not in index
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

      // Handle both old format (time_utc/price_now/4h/1h) and new format (meta/decision/trade)
      const isOldFormat = snapshot && 'time_utc' in snapshot && !('meta' in snapshot);
      const h4State = snapshot?.['4h']?.state;
      const h1State = snapshot?.['1h']?.state;

      signals.push({
        signal_id: ts,
        symbol,
        timestamp_utc: snapshot?.meta?.analysis_time || snapshot?.time_utc || ts,
        price_at_signal: snapshot?.meta?.price_at_signal || snapshot?.price_now,
        decision: snapshot?.decision?.action || snapshot?.decision || (isOldFormat ? 'watch' : 'unknown'),
        bias: snapshot?.verdict?.bias || snapshot?.bias || (h4State === 'downtrend' ? 'bearish' : h4State === 'uptrend' ? 'bullish' : 'unknown'),
        confidence: snapshot?.verdict?.confidence || snapshot?.confidence || (isOldFormat ? 'medium' : 'unknown'),
        playbook: snapshot?.decision?.playbook || snapshot?.playbook || '-',
        market_structure: isOldFormat ? { h4: h4State, h1: h1State } : undefined,
        snapshot,
        report,
      });
    }
  }

  signals.sort((a, b) => (b.timestamp_utc || '').localeCompare(a.timestamp_utc || ''));
  return signals;
}

function collectReview(signals) {
  const byDecision = {};
  const byPlaybook = {};

  for (const s of signals) {
    const dec = s.decision || 'unknown';
    const pb = s.playbook || 'unknown';

    if (!byDecision[dec]) byDecision[dec] = { total: 0 };
    byDecision[dec].total++;

    if (!byPlaybook[pb]) byPlaybook[pb] = { total: 0 };
    byPlaybook[pb].total++;
  }

  return { total: signals.length, byDecision, byPlaybook };
}

function collectBacktests() {
  const runsDir = join(OUTPUTS, 'runs');
  if (!existsSync(runsDir)) return [];

  const runs = [];
  for (const runId of readdirSync(runsDir)) {
    const runDir = join(runsDir, runId);
    if (!statSync(runDir).isDirectory()) continue;

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

      symbols.push({
        symbol: item,
        summary,
        details,
        metrics,
        config,
      });
    }

    if (symbols.length === 0 && !manifest) continue;

    runs.push({
      run_id: runId,
      manifest,
      symbols,
    });
  }

  runs.sort((a, b) => b.run_id.localeCompare(a.run_id));
  return runs;
}

function collectConversations() {
  const convDir = join(OUTPUTS, 'conversations');
  if (!existsSync(convDir)) return [];

  const globalIndex = readJsonl(join(convDir, 'index.jsonl'));
  const conversations = [];

  for (const entry of globalIndex) {
    const dir = join(convDir, entry.path || `${entry.symbol}/${entry.conversation_id}`);
    const transcript = readMd(join(dir, 'conversation.md'));
    const metadata = readJson(join(dir, 'metadata.json'));

    conversations.push({
      ...entry,
      transcript,
      metadata,
    });
  }

  conversations.sort((a, b) => (b.timestamp_utc || '').localeCompare(a.timestamp_utc || ''));
  return conversations;
}

// Main
mkdirSync(OUT_DIR, { recursive: true });

const signals = collectSignals();
const review = collectReview(signals);
const backtests = collectBacktests();
const conversations = collectConversations();

writeFileSync(join(OUT_DIR, 'signals.json'), JSON.stringify(signals, null, 2));
writeFileSync(join(OUT_DIR, 'review.json'), JSON.stringify(review, null, 2));
writeFileSync(join(OUT_DIR, 'backtests.json'), JSON.stringify(backtests, null, 2));
writeFileSync(join(OUT_DIR, 'conversations.json'), JSON.stringify(conversations, null, 2));

console.log(`✅ Data collected:`);
console.log(`   Signals: ${signals.length}`);
console.log(`   Review: ${review.total} signals`);
console.log(`   Backtests: ${backtests.length}`);
console.log(`   Conversations: ${conversations.length}`);
console.log(`   Output: ${OUT_DIR}`);
