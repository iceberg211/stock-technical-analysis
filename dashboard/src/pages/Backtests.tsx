import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { ArrowLeft, TrendingUp, TrendingDown, Target, Zap } from 'lucide-react';
import { useBacktests } from '../hooks/useData';
import StatCard from '../components/StatCard';
import type { Backtest } from '../types';

function extractMetric(metrics: Record<string, unknown> | null, key: string): string {
  if (!metrics) return '-';
  const v = metrics[key];
  if (v === null || v === undefined) return '-';
  if (typeof v === 'number') return v % 1 === 0 ? String(v) : v.toFixed(2);
  return String(v);
}

function formatRunDate(runId: string) {
  const m = runId.match(/^(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})/);
  if (!m) return runId;
  return `${m[1]}-${m[2]}-${m[3]} ${m[4]}:${m[5]}`;
}

function RunDetail({ run, onBack }: { run: Backtest; onBack: () => void }) {
  const sym = run.symbols[0];
  const m = sym?.metrics as Record<string, unknown> | null;

  const winRate = extractMetric(m, 'win_rate_pct');
  const expectancy = extractMetric(m, 'expectancy_r');
  const profitFactor = extractMetric(m, 'profit_factor_r');
  const trades = extractMetric(m, 'executed_trade_cases');
  const t1Hit = extractMetric(m, 't1_hit');
  const slHit = extractMetric(m, 'sl_hit');
  const missedEntry = extractMetric(m, 'missed_entry_cases');
  const avgMfe = extractMetric(m, 'avg_mfe');
  const avgMae = extractMetric(m, 'avg_mae');

  return (
    <div className="p-6 lg:p-8 max-w-5xl">
      <button onClick={onBack} className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-300 mb-6 transition-colors cursor-pointer">
        <ArrowLeft size={14} /> 返回回测列表
      </button>

      <div className="flex items-center gap-3 mb-1 flex-wrap">
        <h2 className="text-xl font-semibold text-gray-100">{sym?.symbol || '-'}</h2>
        <span className={`text-xs px-2.5 py-1 rounded-md border ${
          run.type === 'skill'
            ? 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20'
            : 'bg-gray-500/10 text-gray-400 border-gray-600/20'
        }`}>
          {run.type === 'skill' ? 'Skill 信号回测' : 'Local 规则回测'}
        </span>
      </div>
      <p className="text-sm text-gray-500 mb-6 font-mono">{formatRunDate(run.run_id)}</p>

      {m && (
        <>
          {/* Primary metrics */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-4">
            <StatCard
              label="胜率"
              value={winRate}
              suffix="%"
              trend={winRate !== '-' && parseFloat(winRate) >= 50 ? 'up' : 'down'}
              icon={<Target size={14} />}
            />
            <StatCard
              label="期望 R"
              value={expectancy}
              suffix="R"
              trend={expectancy !== '-' && parseFloat(expectancy) >= 0 ? 'up' : 'down'}
              icon={<TrendingUp size={14} />}
            />
            <StatCard
              label="利润因子"
              value={profitFactor}
              trend={profitFactor !== '-' && parseFloat(profitFactor) >= 1 ? 'up' : 'down'}
              icon={<Zap size={14} />}
            />
            <StatCard label="执行笔数" value={trades} icon={<TrendingDown size={14} />} />
          </div>

          {/* Secondary metrics */}
          <div className="grid grid-cols-3 sm:grid-cols-5 gap-3 mb-6">
            <div className="bg-[#1a2332] border border-gray-800/60 rounded-lg p-3">
              <div className="text-[11px] text-gray-500">T1 命中</div>
              <div className="text-lg font-mono font-semibold text-emerald-400">{t1Hit}</div>
            </div>
            <div className="bg-[#1a2332] border border-gray-800/60 rounded-lg p-3">
              <div className="text-[11px] text-gray-500">止损触发</div>
              <div className="text-lg font-mono font-semibold text-red-400">{slHit}</div>
            </div>
            <div className="bg-[#1a2332] border border-gray-800/60 rounded-lg p-3">
              <div className="text-[11px] text-gray-500">漏触发</div>
              <div className="text-lg font-mono font-semibold text-amber-400">{missedEntry}</div>
            </div>
            <div className="bg-[#1a2332] border border-gray-800/60 rounded-lg p-3">
              <div className="text-[11px] text-gray-500">Avg MFE</div>
              <div className="text-lg font-mono font-semibold text-gray-200">{avgMfe}</div>
            </div>
            <div className="bg-[#1a2332] border border-gray-800/60 rounded-lg p-3">
              <div className="text-[11px] text-gray-500">Avg MAE</div>
              <div className="text-lg font-mono font-semibold text-gray-200">{avgMae}</div>
            </div>
          </div>
        </>
      )}

      {/* Summary markdown */}
      <div className="bg-[#1a2332] rounded-xl border border-gray-800/60 p-5">
        <h3 className="text-[11px] font-medium text-gray-500 uppercase tracking-wider mb-4">详细报告</h3>
        <div className="prose text-sm">
          <ReactMarkdown>{sym?.summary || '暂无数据'}</ReactMarkdown>
        </div>
      </div>
    </div>
  );
}

export default function Backtests() {
  const { data, loading } = useBacktests();
  const [selected, setSelected] = useState<number | null>(null);
  const [filter, setFilter] = useState<'skill' | 'all'>('skill');

  if (loading) return <div className="p-8 text-gray-500">加载中...</div>;
  if (selected !== null) return <RunDetail run={data[selected]} onBack={() => setSelected(null)} />;

  const filtered = filter === 'skill' ? data.filter(r => r.type === 'skill') : data;
  const skillCount = data.filter(r => r.type === 'skill').length;
  const localCount = data.length - skillCount;

  return (
    <div className="p-6 lg:p-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-semibold text-gray-100">回测报告</h2>
          <p className="text-sm text-gray-500 mt-1">
            {skillCount} 次 Skill 回测{localCount > 0 ? ` · ${localCount} 次规则回测` : ''}
          </p>
        </div>
        <div className="flex gap-1 bg-[#1a2332] rounded-lg p-1 border border-gray-800/60">
          <button
            onClick={() => setFilter('skill')}
            className={`px-3 py-1.5 text-xs font-medium rounded-md transition-all duration-150 cursor-pointer ${
              filter === 'skill' ? 'bg-gray-700/60 text-gray-100 shadow-sm' : 'text-gray-500 hover:text-gray-300'
            }`}
          >
            Skill 信号
          </button>
          <button
            onClick={() => setFilter('all')}
            className={`px-3 py-1.5 text-xs font-medium rounded-md transition-all duration-150 cursor-pointer ${
              filter === 'all' ? 'bg-gray-700/60 text-gray-100 shadow-sm' : 'text-gray-500 hover:text-gray-300'
            }`}
          >
            全部
          </button>
        </div>
      </div>

      <div className="space-y-3">
        {filtered.map((run) => {
          const realIndex = data.indexOf(run);
          const sym = run.symbols[0];
          const m = sym?.metrics as Record<string, unknown> | null;
          const winRate = extractMetric(m, 'win_rate_pct');
          const expectancy = extractMetric(m, 'expectancy_r');
          const trades = extractMetric(m, 'executed_trade_cases');
          const isSkill = run.type === 'skill';

          return (
            <div
              key={run.run_id}
              onClick={() => setSelected(realIndex)}
              className="bg-[#1a2332] rounded-xl border border-gray-800/60 p-4 hover:border-gray-700/50 cursor-pointer transition-all duration-150"
            >
              <div className="flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-2.5">
                    <span className="font-medium text-gray-100 text-sm">{sym?.symbol || '-'}</span>
                    <span className={`text-xs px-2 py-0.5 rounded-md border ${
                      isSkill
                        ? 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20'
                        : 'bg-gray-500/10 text-gray-400 border-gray-600/20'
                    }`}>
                      {isSkill ? 'Skill' : 'Local'}
                    </span>
                    {trades !== '-' && <span className="text-xs text-gray-500">{trades} 笔交易</span>}
                  </div>
                  <div className="text-xs text-gray-500 mt-1.5 font-mono">{formatRunDate(run.run_id)}</div>
                </div>
                <div className="flex items-center gap-8 text-right">
                  <div>
                    <div className="text-[11px] text-gray-500">胜率</div>
                    <div className={`text-sm font-semibold font-mono ${
                      winRate !== '-' && parseFloat(winRate) >= 50 ? 'text-emerald-400' : 'text-red-400'
                    }`}>
                      {winRate === '-' ? '-' : `${winRate}%`}
                    </div>
                  </div>
                  <div>
                    <div className="text-[11px] text-gray-500">期望</div>
                    <div className={`text-sm font-semibold font-mono ${
                      expectancy !== '-' && parseFloat(expectancy) >= 0 ? 'text-emerald-400' : 'text-red-400'
                    }`}>
                      {expectancy === '-' ? '-' : `${expectancy}R`}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          );
        })}

        {filtered.length === 0 && (
          <div className="text-center text-gray-600 py-16 text-sm">暂无回测记录</div>
        )}
      </div>
    </div>
  );
}
