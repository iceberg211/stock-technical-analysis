import { useState, useEffect, useMemo } from 'react';
import type { Signal, Backtest, ReviewData } from '../types';

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  return res.json();
}

export function useSignals() {
  const [data, setData] = useState<Signal[]>([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    fetchJson<Signal[]>('/data/signals.json')
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);
  return { data, loading };
}

export function useBacktests() {
  const [data, setData] = useState<Backtest[]>([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    fetchJson<Backtest[]>('/data/backtests.json')
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);
  return { data, loading };
}

export function useReview() {
  const [data, setData] = useState<ReviewData | null>(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    fetchJson<ReviewData>('/data/review.json')
      .then(d => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);
  return { data, loading };
}

/** Derived statistics computed from signals data */
export function useSignalStats(signals: Signal[]) {
  return useMemo(() => {
    const total = signals.length;
    const tradable = signals.filter(s => s.decision === 'long' || s.decision === 'short');
    const watchCount = signals.filter(s => s.decision === 'watch').length;
    const validated = tradable.filter(s =>
      s.validation && ['t1_hit', 'sl_hit', 'neither'].includes(s.validation.outcome)
    );
    const wins = validated.filter(s => s.validation!.outcome === 't1_hit');
    const losses = validated.filter(s => s.validation!.outcome === 'sl_hit');
    const winRate = validated.length > 0 ? (wins.length / validated.length) * 100 : null;

    // Outcome distribution
    const outcomeDistribution: Record<string, number> = {};
    for (const s of signals) {
      const outcome = s.validation?.outcome || 'pending';
      outcomeDistribution[outcome] = (outcomeDistribution[outcome] || 0) + 1;
    }

    // By playbook with win/loss
    const byPlaybook: Record<string, { total: number; wins: number; losses: number }> = {};
    for (const s of tradable) {
      const pb = s.playbook && s.playbook !== '-' && s.playbook !== 'none' ? s.playbook : 'none';
      if (!byPlaybook[pb]) byPlaybook[pb] = { total: 0, wins: 0, losses: 0 };
      byPlaybook[pb].total++;
      if (s.validation?.outcome === 't1_hit') byPlaybook[pb].wins++;
      if (s.validation?.outcome === 'sl_hit') byPlaybook[pb].losses++;
    }

    // Realized R values
    const realizedRs = signals
      .map(s => s.validation?.realized_r)
      .filter((r): r is number => typeof r === 'number');
    const avgR = realizedRs.length > 0
      ? realizedRs.reduce((a, b) => a + b, 0) / realizedRs.length
      : null;

    // Signals by date (for timeline)
    const byDate: Record<string, { total: number; long: number; short: number; watch: number }> = {};
    for (const s of signals) {
      const date = (s.timestamp_utc || '').slice(0, 10);
      if (!date) continue;
      if (!byDate[date]) byDate[date] = { total: 0, long: 0, short: 0, watch: 0 };
      byDate[date].total++;
      const dec = s.decision as 'long' | 'short' | 'watch';
      if (dec in byDate[date]) byDate[date][dec]++;
    }

    // Unique symbols
    const symbols = [...new Set(signals.map(s => s.symbol))];

    return {
      total,
      tradableCount: tradable.length,
      watchCount,
      validatedCount: validated.length,
      winCount: wins.length,
      lossCount: losses.length,
      winRate,
      avgR,
      outcomeDistribution,
      byPlaybook,
      byDate,
      symbols,
    };
  }, [signals]);
}
