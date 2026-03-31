import { useState } from 'react';
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
  t1_hit: { label: '✅ T1 命中', color: 'text-emerald-600' },
  sl_hit: { label: '❌ 止损', color: 'text-red-600' },
  neither: { label: '⏸ 未达标', color: 'text-gray-500' },
  not_triggered: { label: '⏳ 未触发', color: 'text-amber-600' },
  no_levels: { label: '-', color: 'text-gray-400' },
  no_data: { label: '-', color: 'text-gray-400' },
  insufficient_data: { label: '📊 数据不足', color: 'text-gray-400' },
  pending: { label: '🔘 待验证', color: 'text-gray-400' },
};

function OutcomeLabel({ outcome }: { outcome: string }) {
  const cfg = outcomeConfig[outcome] || outcomeConfig.pending;
  return <span className={`text-xs font-medium ${cfg.color}`}>{cfg.label}</span>;
}

export default function Signals() {
  const { data, loading } = useSignals();
  const [selected, setSelected] = useState<number | null>(null);

  if (loading) return <div className="p-8 text-gray-400">加载中...</div>;
  if (selected !== null) return <SignalDetail signal={data[selected]} onBack={() => setSelected(null)} />;

  const tradable = data.filter(s => s.decision === 'long' || s.decision === 'short').length;
  const watchCount = data.filter(s => s.decision === 'watch').length;
  const validated = data.filter(s => s.validation && ['t1_hit', 'sl_hit', 'neither'].includes(s.validation.outcome));
  const wins = validated.filter(s => s.validation.outcome === 't1_hit').length;

  return (
    <div className="p-8">
      <div className="mb-6">
        <h2 className="text-lg font-semibold text-gray-900">交易信号</h2>
        <p className="text-sm text-gray-500 mt-1">
          共 {data.length} 条信号 · {tradable} 条可交易 · {watchCount} 条观望
          {validated.length > 0 && ` · 已验证 ${validated.length} 条 (${wins} 胜)`}
        </p>
      </div>

      <div className="bg-white rounded-xl border border-gray-200 overflow-hidden shadow-sm">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
              <th className="px-4 py-3">时间</th>
              <th className="px-4 py-3">品种</th>
              <th className="px-4 py-3">方向</th>
              <th className="px-4 py-3">偏向</th>
              <th className="px-4 py-3">Playbook</th>
              <th className="px-4 py-3 text-right">入场</th>
              <th className="px-4 py-3 text-right">止损</th>
              <th className="px-4 py-3 text-right">目标 1</th>
              <th className="px-4 py-3 text-center">验证结果</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {data.map((s, i) => (
              <tr
                key={s.signal_id + i}
                onClick={() => setSelected(i)}
                className="hover:bg-gray-50 cursor-pointer transition-colors"
              >
                <td className="px-4 py-3 text-gray-600 font-mono text-xs whitespace-nowrap">{formatTime(s.timestamp_utc)}</td>
                <td className="px-4 py-3 font-medium text-gray-900">{s.symbol}</td>
                <td className="px-4 py-3"><Badge value={s.decision} label={decisionLabel[s.decision]} /></td>
                <td className="px-4 py-3"><Badge value={s.bias} label={biasLabel[s.bias]} /></td>
                <td className="px-4 py-3 text-gray-600 text-xs">{s.playbook === '-' || s.playbook === 'none' ? '-' : s.playbook}</td>
                <td className="px-4 py-3 text-right font-mono text-gray-700 text-xs">{formatPrice(s.conditional_entry || s.price_at_signal)}</td>
                <td className="px-4 py-3 text-right font-mono text-red-600 text-xs">{formatPrice(s.stop_loss)}</td>
                <td className="px-4 py-3 text-right font-mono text-emerald-600 text-xs">{formatPrice(s.t1)}</td>
                <td className="px-4 py-3 text-center"><OutcomeLabel outcome={s.validation?.outcome || 'pending'} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
