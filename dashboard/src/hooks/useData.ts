import { useState, useEffect } from 'react';
import type { Signal, Backtest } from '../types';

async function fetchJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  return res.json();
}

export function useSignals() {
  const [data, setData] = useState<Signal[]>([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    fetchJson<Signal[]>('/data/signals.json').then(d => { setData(d); setLoading(false); });
  }, []);
  return { data, loading };
}

export function useBacktests() {
  const [data, setData] = useState<Backtest[]>([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    fetchJson<Backtest[]>('/data/backtests.json').then(d => { setData(d); setLoading(false); });
  }, []);
  return { data, loading };
}
