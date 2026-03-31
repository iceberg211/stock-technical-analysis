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

export default function Signals() {
  const { data, loading } = useSignals();
  const [selected, setSelected] = useState<number | null>(null);

  if (loading) return <div className="p-8 text-gray-400">加载中...</div>;
  if (selected !== null) return <SignalDetail signal={data[selected]} onBack={() => setSelected(null)} />;

  const tradable = data.filter(s => s.decision === 'long' || s.decision === 'short').length;
  const watchCount = data.filter(s => s.decision === 'watch').length;

  return (
    <div className="p-8">
      <div className="mb-6">
        <h2 className="text-lg font-semibold text-gray-900">交易信号</h2>
        <p className="text-sm text-gray-500 mt-1">
          共 {data.length} 条信号 · {tradable} 条可交易 · {watchCount} 条观望
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
              <th className="px-4 py-3">置信度</th>
              <th className="px-4 py-3">Playbook</th>
              <th className="px-4 py-3 text-right">价格</th>
              <th className="px-4 py-3 text-right">止损</th>
              <th className="px-4 py-3 text-right">目标 1</th>
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
                <td className="px-4 py-3"><Badge value={s.confidence} /></td>
                <td className="px-4 py-3 text-gray-600 text-xs">{s.playbook === '-' || s.playbook === 'none' ? '-' : s.playbook}</td>
                <td className="px-4 py-3 text-right font-mono text-gray-700 text-xs">{formatPrice(s.conditional_entry || s.price_at_signal)}</td>
                <td className="px-4 py-3 text-right font-mono text-red-600 text-xs">{formatPrice(s.stop_loss)}</td>
                <td className="px-4 py-3 text-right font-mono text-emerald-600 text-xs">{formatPrice(s.t1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
