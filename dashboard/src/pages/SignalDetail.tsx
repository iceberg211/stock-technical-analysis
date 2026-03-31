import ReactMarkdown from 'react-markdown';
import { ArrowLeft } from 'lucide-react';
import Badge from '../components/Badge';
import type { Signal } from '../types';

function formatPrice(n: unknown) {
  if (n === undefined || n === null || typeof n !== 'number') return '-';
  return n.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 2 });
}

const decisionLabel: Record<string, string> = { long: '做多', short: '做空', watch: '观望' };
const biasLabel: Record<string, string> = { bullish: '看涨', bearish: '看跌', neutral: '中性' };

const outcomeConfig: Record<string, { label: string; color: string; bg: string }> = {
  t1_hit: { label: '✅ 目标 1 命中', color: 'text-emerald-700', bg: 'bg-emerald-50 border-emerald-200' },
  sl_hit: { label: '❌ 止损命中', color: 'text-red-700', bg: 'bg-red-50 border-red-200' },
  neither: { label: '⏸ 未触达目标或止损', color: 'text-gray-600', bg: 'bg-gray-50 border-gray-200' },
  not_triggered: { label: '⏳ 入场条件未触发', color: 'text-amber-700', bg: 'bg-amber-50 border-amber-200' },
  no_data: { label: '无可用 K 线数据', color: 'text-gray-500', bg: 'bg-gray-50 border-gray-200' },
  insufficient_data: { label: '后续 K 线数据不足', color: 'text-gray-500', bg: 'bg-gray-50 border-gray-200' },
  no_levels: { label: '缺少关键点位（无法验证）', color: 'text-gray-500', bg: 'bg-gray-50 border-gray-200' },
  pending: { label: '🔘 待验证', color: 'text-gray-500', bg: 'bg-gray-50 border-gray-200' },
};

export default function SignalDetail({ signal, onBack }: { signal: Signal; onBack: () => void }) {
  const s = signal;
  const snap = s.snapshot as Record<string, unknown> | null;
  const trade = (snap?.trade || {}) as Record<string, unknown>;
  const entry = s.conditional_entry || trade.entry_price as number;
  const sl = s.stop_loss || trade.stop_loss as number;
  const t1 = s.t1 || trade.t1 as number;
  const t2 = s.t2 || trade.t2 as number;
  const price = s.price_at_signal || (snap?.price_now as number);

  const v = s.validation;
  const outcome = v?.outcome || 'pending';
  const cfg = outcomeConfig[outcome] || outcomeConfig.pending;

  return (
    <div className="p-8 max-w-4xl">
      <button onClick={onBack} className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-900 mb-6 transition-colors">
        <ArrowLeft size={14} /> 返回信号列表
      </button>

      {/* Header */}
      <div className="flex items-center gap-3 mb-6">
        <h2 className="text-xl font-semibold text-gray-900">{s.symbol}</h2>
        <Badge value={s.decision} label={decisionLabel[s.decision]} />
        <Badge value={s.bias} label={biasLabel[s.bias]} />
        <Badge value={s.confidence} />
        <span className="text-sm text-gray-400 ml-auto font-mono">{s.timestamp_utc?.replace('T', ' ').replace('Z', '').slice(0, 16)}</span>
      </div>

      {/* 验证结果卡片 */}
      <div className={`rounded-xl border p-5 mb-6 ${cfg.bg}`}>
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-2">事后验证</h3>
            <div className={`text-lg font-semibold ${cfg.color}`}>{cfg.label}</div>
          </div>
          {v && (
            <div className="text-right text-sm">
              {v.entry_triggered && (
                <div className="text-gray-600">
                  入场触发 · {typeof v.bars_to_entry === 'number' ? `第 ${v.bars_to_entry} 根 bar` : '-'}
                </div>
              )}
              {typeof v.bars_to_outcome === 'number' && (
                <div className="text-gray-500">
                  入场后 {v.bars_to_outcome} 根 bar 出结果
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Key Levels Card */}
      <div className="bg-white rounded-xl border border-gray-200 p-5 mb-6 shadow-sm">
        <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-4">关键点位</h3>
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-4">
          {[
            { label: '当前价格', value: price, color: 'text-gray-900' },
            { label: '入场价', value: entry, color: 'text-blue-600' },
            { label: '止损', value: sl, color: 'text-red-600' },
            { label: '目标 1', value: t1, color: 'text-emerald-600' },
            { label: '目标 2', value: t2, color: 'text-emerald-700' },
          ].map(({ label, value, color }) => (
            <div key={label}>
              <div className="text-xs text-gray-500">{label}</div>
              <div className={`text-lg font-semibold font-mono ${color}`}>{formatPrice(value)}</div>
            </div>
          ))}
        </div>
        {s.playbook && s.playbook !== '-' && s.playbook !== 'none' && (
          <div className="mt-4 pt-4 border-t border-gray-100">
            <span className="text-xs text-gray-500">策略: </span>
            <span className="text-sm font-medium text-gray-700">{s.playbook}</span>
          </div>
        )}
      </div>

      {/* Report */}
      {s.report && (
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm mb-6">
          <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-4">分析报告</h3>
          <div className="prose text-sm text-gray-700">
            <ReactMarkdown>{s.report}</ReactMarkdown>
          </div>
        </div>
      )}

      {/* Snapshot JSON */}
      {snap && (
        <details className="bg-white rounded-xl border border-gray-200 shadow-sm">
          <summary className="px-5 py-3 text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-50">
            原始快照数据
          </summary>
          <pre className="px-5 pb-4 text-xs text-gray-600 overflow-x-auto">
            {JSON.stringify(snap, null, 2)}
          </pre>
        </details>
      )}
    </div>
  );
}
