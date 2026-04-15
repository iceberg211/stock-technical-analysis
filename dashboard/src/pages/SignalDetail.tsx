import ReactMarkdown from 'react-markdown';
import { ArrowLeft, ExternalLink } from 'lucide-react';
import Badge from '../components/Badge';
import PriceLevels from '../components/PriceLevels';
import type { Signal } from '../types';

const decisionLabel: Record<string, string> = { long: '做多', short: '做空', watch: '观望' };
const biasLabel: Record<string, string> = { bullish: '看涨', bearish: '看跌', neutral: '中性' };

const outcomeConfig: Record<string, { label: string; color: string; bg: string }> = {
  t1_hit: { label: 'T1 命中', color: 'text-emerald-300', bg: 'bg-emerald-500/10 border-emerald-500/20' },
  sl_hit: { label: '止损触发', color: 'text-red-300', bg: 'bg-red-500/10 border-red-500/20' },
  neither: { label: '未触达目标', color: 'text-gray-300', bg: 'bg-gray-500/10 border-gray-500/20' },
  not_triggered: { label: '入场未触发', color: 'text-amber-300', bg: 'bg-amber-500/10 border-amber-500/20' },
  missed_entry: { label: '入场未触发', color: 'text-amber-300', bg: 'bg-amber-500/10 border-amber-500/20' },
  no_data: { label: '无可用数据', color: 'text-gray-400', bg: 'bg-gray-500/10 border-gray-600/20' },
  insufficient_data: { label: '数据不足', color: 'text-gray-400', bg: 'bg-gray-500/10 border-gray-600/20' },
  no_levels: { label: '缺少关键点位', color: 'text-gray-400', bg: 'bg-gray-500/10 border-gray-600/20' },
  pending: { label: '待验证', color: 'text-gray-400', bg: 'bg-gray-500/10 border-gray-600/20' },
};

export default function SignalDetail({ signal, onBack }: { signal: Signal; onBack: () => void }) {
  const s = signal;
  const snap = s.snapshot as Record<string, unknown> | null;
  const trade = (snap?.trade || {}) as Record<string, unknown>;
  const entry = s.conditional_entry || trade.entry_price as number | undefined;
  const sl = s.stop_loss || trade.stop_loss as number | undefined;
  const t1 = s.t1 || trade.t1 as number | undefined;
  const t2 = s.t2 || trade.t2 as number | undefined;
  const price = s.price_at_signal || (snap?.price_now as number | undefined);

  const v = s.validation;
  const outcome = v?.outcome || 'pending';
  const cfg = outcomeConfig[outcome] || outcomeConfig.pending;
  const realizedR = v?.realized_r;

  // Risk/Reward calculation
  let riskReward: string | null = null;
  if (typeof entry === 'number' && typeof sl === 'number' && typeof t1 === 'number') {
    const risk = Math.abs(entry - sl);
    const reward = Math.abs(t1 - entry);
    if (risk > 0) riskReward = (reward / risk).toFixed(2);
  }

  return (
    <div className="p-6 lg:p-8 max-w-4xl">
      {/* Back button */}
      <button
        onClick={onBack}
        className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-300 mb-6 transition-colors cursor-pointer"
      >
        <ArrowLeft size={14} /> 返回信号列表
      </button>

      {/* Header */}
      <div className="flex items-center gap-3 mb-6 flex-wrap">
        <h2 className="text-xl font-semibold text-gray-100">{s.symbol}</h2>
        <Badge value={s.decision} label={decisionLabel[s.decision]} />
        <Badge value={s.bias} label={biasLabel[s.bias]} />
        <Badge value={s.confidence} />
        {s.playbook && s.playbook !== '-' && s.playbook !== 'none' && (
          <span className="text-xs px-2.5 py-1 bg-blue-500/10 text-blue-400 rounded-md border border-blue-500/20">
            {s.playbook}
          </span>
        )}
        <span className="text-sm text-gray-500 ml-auto font-mono">
          {s.timestamp_utc?.replace('T', ' ').replace('Z', '').slice(0, 16)}
        </span>
      </div>

      {/* Validation Result Card */}
      <div className={`rounded-xl border p-5 mb-6 ${cfg.bg}`}>
        <div className="flex items-center justify-between flex-wrap gap-4">
          <div>
            <h3 className="text-[11px] font-medium text-gray-500 uppercase tracking-wider mb-2">事后验证</h3>
            <div className={`text-lg font-semibold ${cfg.color}`}>{cfg.label}</div>
          </div>
          <div className="flex gap-6 text-right">
            {typeof realizedR === 'number' && (
              <div>
                <div className="text-[11px] text-gray-500">Realized R</div>
                <div className={`text-lg font-mono font-semibold ${realizedR >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {realizedR >= 0 ? '+' : ''}{realizedR.toFixed(2)}R
                </div>
              </div>
            )}
            {v && v.entry_triggered && (
              <div className="text-sm text-right space-y-1">
                {typeof v.bars_to_entry === 'number' && (
                  <div className="text-gray-400">
                    入场: <span className="font-mono text-gray-300">第 {v.bars_to_entry} 根 bar</span>
                  </div>
                )}
                {typeof v.bars_to_outcome === 'number' && (
                  <div className="text-gray-400">
                    出场: <span className="font-mono text-gray-300">第 {v.bars_to_outcome} 根 bar</span>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        {/* MFE/MAE */}
        {v && (typeof v.mfe === 'number' || typeof v.mae === 'number') && (
          <div className="mt-4 pt-3 border-t border-gray-700/30 flex gap-6">
            {typeof v.mfe === 'number' && (
              <div>
                <span className="text-[11px] text-gray-500">MFE (最大浮盈) </span>
                <span className="font-mono text-sm text-emerald-400">{v.mfe.toFixed(2)}</span>
              </div>
            )}
            {typeof v.mae === 'number' && (
              <div>
                <span className="text-[11px] text-gray-500">MAE (最大浮亏) </span>
                <span className="font-mono text-sm text-red-400">{v.mae.toFixed(2)}</span>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Price Levels Visual */}
      <div className="bg-[#1a2332] rounded-xl border border-gray-800/60 p-5 mb-6">
        <h3 className="text-[11px] font-medium text-gray-500 uppercase tracking-wider mb-4">关键点位</h3>
        <PriceLevels
          entry={entry}
          stopLoss={sl}
          t1={t1}
          t2={t2}
          current={price}
          action={s.decision}
        />
        {riskReward && (
          <div className="mt-4 pt-3 border-t border-gray-800/60 flex items-center gap-4">
            <div>
              <span className="text-[11px] text-gray-500">风险回报比 </span>
              <span className="font-mono text-sm text-cyan-400">1:{riskReward}</span>
            </div>
            {s.note && (
              <div className="text-xs text-gray-500 flex-1 text-right truncate" title={s.note}>
                {s.note}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Report */}
      {s.report && (
        <div className="bg-[#1a2332] rounded-xl border border-gray-800/60 p-5 mb-6">
          <h3 className="text-[11px] font-medium text-gray-500 uppercase tracking-wider mb-4">分析报告</h3>
          <div className="prose text-sm">
            <ReactMarkdown>{s.report}</ReactMarkdown>
          </div>
        </div>
      )}

      {/* Snapshot JSON */}
      {snap && (
        <details className="bg-[#1a2332] rounded-xl border border-gray-800/60 overflow-hidden">
          <summary className="px-5 py-3.5 text-[11px] font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-800/30 transition-colors flex items-center gap-2">
            <ExternalLink size={12} />
            原始快照数据
          </summary>
          <pre className="px-5 pb-4 text-xs text-gray-500 overflow-x-auto font-mono leading-relaxed">
            {JSON.stringify(snap, null, 2)}
          </pre>
        </details>
      )}
    </div>
  );
}
