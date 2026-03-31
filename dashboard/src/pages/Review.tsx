import { useState, useEffect } from 'react';

interface GroupStats {
  total: number;
}

interface ReviewData {
  total: number;
  byDecision: Record<string, GroupStats>;
  byPlaybook: Record<string, GroupStats>;
}

const decisionLabel: Record<string, string> = {
  long: '做多', short: '做空', watch: '观望', unknown: '未知'
};

export default function Review() {
  const [data, setData] = useState<ReviewData | null>(null);

  useEffect(() => {
    fetch('/data/review.json').then(r => r.json()).then(setData);
  }, []);

  if (!data) return <div className="p-8 text-gray-400">加载中...</div>;

  const tradable = (data.byDecision['long']?.total || 0) + (data.byDecision['short']?.total || 0);
  const watchCount = data.byDecision['watch']?.total || 0;

  return (
    <div className="p-8">
      <div className="mb-6">
        <h2 className="text-lg font-semibold text-gray-900">复盘统计</h2>
        <p className="text-sm text-gray-500 mt-1">
          共 {data.total} 条信号 · {tradable} 条可交易 · {watchCount} 条观望
        </p>
      </div>

      {/* Overview Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-6">
        <StatCard label="总信号" value={data.total} />
        <StatCard label="可交易" value={tradable} color="text-blue-600" />
        <StatCard label="观望" value={watchCount} color="text-amber-600" />
        <StatCard label="观望占比" value={data.total ? `${Math.round(watchCount / data.total * 100)}%` : '-'} color={watchCount / data.total > 0.6 ? 'text-red-600' : 'text-gray-900'} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* 按方向 */}
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-4">按方向</h3>
          <div className="space-y-3">
            {Object.entries(data.byDecision).map(([dec, stats]) => (
              <div key={dec} className="flex justify-between items-center">
                <span className="text-sm text-gray-700">{decisionLabel[dec] || dec}</span>
                <div className="flex items-center gap-3">
                  <div className="w-32 bg-gray-100 rounded-full h-2">
                    <div
                      className={`h-2 rounded-full ${dec === 'long' ? 'bg-emerald-500' : dec === 'short' ? 'bg-red-500' : 'bg-amber-400'}`}
                      style={{ width: `${data.total ? (stats.total / data.total) * 100 : 0}%` }}
                    />
                  </div>
                  <span className="text-sm font-mono font-semibold text-gray-900 w-8 text-right">{stats.total}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* 按策略 */}
        <div className="bg-white rounded-xl border border-gray-200 p-5 shadow-sm">
          <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-4">按策略</h3>
          <div className="space-y-3">
            {Object.entries(data.byPlaybook).map(([pb, stats]) => (
              <div key={pb} className="flex justify-between items-center">
                <span className="text-sm text-gray-700">{pb === 'none' ? '无匹配' : pb}</span>
                <div className="flex items-center gap-3">
                  <div className="w-32 bg-gray-100 rounded-full h-2">
                    <div className="bg-blue-500 h-2 rounded-full" style={{ width: `${data.total ? (stats.total / data.total) * 100 : 0}%` }} />
                  </div>
                  <span className="text-sm font-mono font-semibold text-gray-900 w-8 text-right">{stats.total}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Note */}
      <div className="mt-6 bg-amber-50 border border-amber-200 rounded-xl p-4 text-sm text-amber-700">
        提示：信号量达到 30 条以上后，胜率和盈亏比统计才有参考价值。当前 {data.total} 条。
      </div>
    </div>
  );
}

function StatCard({ label, value, color = 'text-gray-900' }: { label: string; value: number | string; color?: string }) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm">
      <div className="text-xs text-gray-500">{label}</div>
      <div className={`text-xl font-semibold font-mono ${color}`}>{value}</div>
    </div>
  );
}
