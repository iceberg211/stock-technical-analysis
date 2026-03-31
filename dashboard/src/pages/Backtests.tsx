import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { ArrowLeft } from 'lucide-react';
import { useBacktests } from '../hooks/useData';
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

function MetricCard({ label, value, suffix, color }: { label: string; value: string; suffix?: string; color?: string }) {
  const isNegative = value.startsWith('-');
  const displayColor = color || (isNegative ? 'text-red-600' : 'text-gray-900');
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
      <div className="text-xs text-gray-500">{label}</div>
      <div className={`text-xl font-semibold font-mono ${displayColor}`}>{value}{suffix || ''}</div>
    </div>
  );
}

function RunDetail({ run, onBack }: { run: Backtest; onBack: () => void }) {
  const [tab, setTab] = useState<'summary' | 'details'>('summary');
  const sym = run.symbols[0];
  const m = sym?.metrics as Record<string, unknown> | null;

  return (
    <div className="p-8 max-w-4xl">
      <button onClick={onBack} className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-gray-900 mb-6 transition-colors">
        <ArrowLeft size={14} /> 返回回测列表
      </button>

      <div className="flex items-center gap-2 mb-1">
        <h2 className="text-xl font-semibold text-gray-900">{sym?.symbol || '-'}</h2>
        <span className={`text-xs px-2 py-0.5 rounded-md ${run.type === 'skill' ? 'bg-blue-50 text-blue-700' : 'bg-gray-100 text-gray-500'}`}>
          {run.type === 'skill' ? 'Skill 信号回测' : 'Local 规则回测'}
        </span>
      </div>
      <p className="text-sm text-gray-500 mb-6">{formatRunDate(run.run_id)}</p>

      {m && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
          <MetricCard label="胜率" value={extractMetric(m, 'win_rate')} suffix="%" />
          <MetricCard label="期望 R" value={extractMetric(m, 'expectancy_r')} />
          <MetricCard label="利润因子" value={extractMetric(m, 'profit_factor_r')} />
          <MetricCard label="交易次数" value={extractMetric(m, 'executed_trades')} color="text-gray-900" />
        </div>
      )}

      <div className="flex gap-1 bg-gray-100 rounded-lg p-1 w-fit mb-4">
        {([['summary', '概览'], ['details', '明细']] as const).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key as 'summary' | 'details')}
            className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
              tab === key ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
        <div className="prose text-sm text-gray-700">
          <ReactMarkdown>{tab === 'summary' ? sym?.summary || '暂无概览' : sym?.details || '暂无明细'}</ReactMarkdown>
        </div>
      </div>
    </div>
  );
}

export default function Backtests() {
  const { data, loading } = useBacktests();
  const [selected, setSelected] = useState<number | null>(null);
  const [filter, setFilter] = useState<'skill' | 'all'>('skill');

  if (loading) return <div className="p-8 text-gray-400">加载中...</div>;
  if (selected !== null) return <RunDetail run={data[selected]} onBack={() => setSelected(null)} />;

  const filtered = filter === 'skill'
    ? data.filter(r => (r as Record<string, unknown>).type === 'skill')
    : data;

  const skillCount = data.filter(r => (r as Record<string, unknown>).type === 'skill').length;
  const localCount = data.length - skillCount;

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">回测报告</h2>
          <p className="text-sm text-gray-500 mt-1">
            {skillCount} 次 Skill 回测{localCount > 0 ? ` · ${localCount} 次规则回测` : ''}
          </p>
        </div>
        <div className="flex gap-1 bg-gray-100 rounded-lg p-1">
          <button
            onClick={() => setFilter('skill')}
            className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
              filter === 'skill' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500'
            }`}
          >
            Skill 信号
          </button>
          <button
            onClick={() => setFilter('all')}
            className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
              filter === 'all' ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500'
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
          const winRate = extractMetric(m, 'win_rate');
          const expectancy = extractMetric(m, 'expectancy_r');
          const trades = extractMetric(m, 'executed_trades');
          const isSkill = run.type === 'skill';

          return (
            <div
              key={run.run_id}
              onClick={() => setSelected(realIndex)}
              className="bg-white rounded-xl border border-gray-200 p-4 hover:border-gray-300 cursor-pointer transition-all shadow-sm"
            >
              <div className="flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-gray-900 text-sm">{sym?.symbol || '-'}</span>
                    <span className={`text-xs px-2 py-0.5 rounded-md ${isSkill ? 'bg-blue-50 text-blue-700' : 'bg-gray-100 text-gray-500'}`}>
                      {isSkill ? 'Skill' : 'Local'}
                    </span>
                    {trades !== '-' && <span className="text-xs text-gray-400">{trades} 笔交易</span>}
                  </div>
                  <div className="text-xs text-gray-500 mt-1 font-mono">{formatRunDate(run.run_id)}</div>
                </div>
                <div className="flex items-center gap-6 text-right">
                  <div>
                    <div className="text-xs text-gray-500">胜率</div>
                    <div className={`text-sm font-semibold font-mono ${winRate !== '-' && parseFloat(winRate) >= 50 ? 'text-emerald-600' : 'text-red-600'}`}>
                      {winRate === '-' ? '-' : `${winRate}%`}
                    </div>
                  </div>
                  <div>
                    <div className="text-xs text-gray-500">期望</div>
                    <div className={`text-sm font-semibold font-mono ${expectancy !== '-' && parseFloat(expectancy) >= 0 ? 'text-emerald-600' : 'text-red-600'}`}>
                      {expectancy === '-' ? '-' : `${expectancy}R`}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          );
        })}

        {filtered.length === 0 && (
          <div className="text-center text-gray-400 py-12 text-sm">暂无回测记录</div>
        )}
      </div>
    </div>
  );
}
