import { useState, useMemo } from 'react';
import { Search } from 'lucide-react';
import { useSignals } from '../hooks/useData';
import Badge from '../components/Badge';
import SignalDetail from './SignalDetail';

function formatTime(ts: string) {
  if (!ts || ts === '-') return '-';
  return ts.replace('T', ' ').replace('Z', '').slice(0, 16);
}

function formatPrice(n: unknown) {
  if (n === undefined || n === null || typeof n !== 'number') return '-';
  return n.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 2 });
}

const decisionLabel: Record<string, string> = { long: '做多', short: '做空', watch: '观望' };
const biasLabel: Record<string, string> = { bullish: '看涨', bearish: '看跌', neutral: '中性' };

const outcomeConfig: Record<string, { label: string; color: string }> = {
  t1_hit: { label: 'T1 命中', color: 'text-emerald-400' },
  sl_hit: { label: '止损', color: 'text-red-400' },
  neither: { label: '未达标', color: 'text-gray-500' },
  not_triggered: { label: '未触发', color: 'text-amber-400' },
  missed_entry: { label: '未触发', color: 'text-amber-400' },
  no_levels: { label: '-', color: 'text-gray-600' },
  no_data: { label: '-', color: 'text-gray-600' },
  insufficient_data: { label: '数据不足', color: 'text-gray-600' },
  pending: { label: '待验证', color: 'text-gray-600' },
};

type FilterType = 'all' | 'long' | 'short' | 'watch';

export default function Signals() {
  const { data, loading } = useSignals();
  const [selected, setSelected] = useState<number | null>(null);
  const [filter, setFilter] = useState<FilterType>('all');
  const [search, setSearch] = useState('');

  const filtered = useMemo(() => {
    let result = data;
    if (filter !== 'all') {
      result = result.filter(s => s.decision === filter);
    }
    if (search) {
      const q = search.toLowerCase();
      result = result.filter(s =>
        s.symbol.toLowerCase().includes(q) ||
        s.playbook?.toLowerCase().includes(q) ||
        s.note?.toLowerCase().includes(q)
      );
    }
    return result;
  }, [data, filter, search]);

  if (loading) return <div className="p-8 text-gray-500">加载中...</div>;

  if (selected !== null) {
    const signal = filtered[selected];
    if (!signal) { setSelected(null); return null; }
    return <SignalDetail signal={signal} onBack={() => setSelected(null)} />;
  }

  const tradable = data.filter(s => s.decision === 'long' || s.decision === 'short').length;
  const watchCount = data.filter(s => s.decision === 'watch').length;
  const validated = data.filter(s => s.validation && ['t1_hit', 'sl_hit', 'neither'].includes(s.validation.outcome));
  const wins = validated.filter(s => s.validation!.outcome === 't1_hit').length;

  const filters: { key: FilterType; label: string; count: number }[] = [
    { key: 'all', label: '全部', count: data.length },
    { key: 'long', label: '做多', count: data.filter(s => s.decision === 'long').length },
    { key: 'short', label: '做空', count: data.filter(s => s.decision === 'short').length },
    { key: 'watch', label: '观望', count: watchCount },
  ];

  return (
    <div className="p-6 lg:p-8">
      {/* Header */}
      <div className="mb-6">
        <h2 className="text-xl font-semibold text-gray-100">交易信号</h2>
        <p className="text-sm text-gray-500 mt-1">
          共 {data.length} 条信号 · {tradable} 可交易 · {watchCount} 观望
          {validated.length > 0 && ` · 已验证 ${validated.length} 条 (${wins} 胜)`}
        </p>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-4 mb-5">
        <div className="flex gap-1 bg-[#1a2332] rounded-lg p-1 border border-gray-800/60">
          {filters.map(f => (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              className={`px-3 py-1.5 text-xs font-medium rounded-md transition-all duration-150 cursor-pointer ${
                filter === f.key
                  ? 'bg-gray-700/60 text-gray-100 shadow-sm'
                  : 'text-gray-500 hover:text-gray-300'
              }`}
            >
              {f.label}
              <span className="ml-1.5 text-gray-600">{f.count}</span>
            </button>
          ))}
        </div>
        <div className="relative flex-1 max-w-xs">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-600" />
          <input
            type="text"
            placeholder="搜索品种 / 策略..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="w-full pl-8 pr-3 py-2 text-sm bg-[#1a2332] border border-gray-800/60 rounded-lg text-gray-200 placeholder-gray-600 focus:outline-none focus:border-gray-600 transition-colors"
          />
        </div>
      </div>

      {/* Table */}
      <div className="bg-[#1a2332] rounded-xl border border-gray-800/60 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-800/60 text-left text-[11px] font-medium text-gray-500 uppercase tracking-wider">
              <th className="px-5 py-3">时间</th>
              <th className="px-5 py-3">品种</th>
              <th className="px-5 py-3">方向</th>
              <th className="px-5 py-3">偏向</th>
              <th className="px-5 py-3">策略</th>
              <th className="px-5 py-3 text-right">入场</th>
              <th className="px-5 py-3 text-right">止损</th>
              <th className="px-5 py-3 text-right">T1</th>
              <th className="px-5 py-3 text-center">验证结果</th>
              <th className="px-5 py-3 text-right">R 值</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((s, i) => {
              const outcome = s.validation?.outcome || 'pending';
              const cfg = outcomeConfig[outcome] || outcomeConfig.pending;
              const realizedR = s.validation?.realized_r;
              return (
                <tr
                  key={s.signal_id + i}
                  onClick={() => setSelected(i)}
                  className="border-b border-gray-800/30 hover:bg-gray-800/30 cursor-pointer transition-colors"
                >
                  <td className="px-5 py-3 text-gray-500 font-mono text-xs whitespace-nowrap">{formatTime(s.timestamp_utc)}</td>
                  <td className="px-5 py-3 font-medium text-gray-200">{s.symbol}</td>
                  <td className="px-5 py-3"><Badge value={s.decision} label={decisionLabel[s.decision]} /></td>
                  <td className="px-5 py-3"><Badge value={s.bias} label={biasLabel[s.bias]} /></td>
                  <td className="px-5 py-3 text-gray-500 text-xs">{s.playbook === '-' || s.playbook === 'none' ? '-' : s.playbook}</td>
                  <td className="px-5 py-3 text-right font-mono text-gray-300 text-xs">{formatPrice(s.conditional_entry || s.price_at_signal)}</td>
                  <td className="px-5 py-3 text-right font-mono text-red-400/80 text-xs">{formatPrice(s.stop_loss)}</td>
                  <td className="px-5 py-3 text-right font-mono text-emerald-400/80 text-xs">{formatPrice(s.t1)}</td>
                  <td className="px-5 py-3 text-center">
                    <span className={`text-xs font-medium ${cfg.color}`}>{cfg.label}</span>
                  </td>
                  <td className="px-5 py-3 text-right font-mono text-xs">
                    {typeof realizedR === 'number' ? (
                      <span className={realizedR >= 0 ? 'text-emerald-400' : 'text-red-400'}>
                        {realizedR >= 0 ? '+' : ''}{realizedR.toFixed(2)}R
                      </span>
                    ) : (
                      <span className="text-gray-600">-</span>
                    )}
                  </td>
                </tr>
              );
            })}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={10} className="px-5 py-12 text-center text-gray-600 text-sm">
                  {search ? '未找到匹配的信号' : '暂无信号数据'}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
