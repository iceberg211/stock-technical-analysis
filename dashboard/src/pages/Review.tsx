import { useSignals, useSignalStats, useReview } from '../hooks/useData';
import StatCard from '../components/StatCard';
import OutcomeChart from '../components/OutcomeChart';
import PlaybookChart from '../components/PlaybookChart';
import Badge from '../components/Badge';
import { Target, TrendingUp, TrendingDown, BarChart3 } from 'lucide-react';

const decisionLabel: Record<string, string> = {
  long: '做多', short: '做空', watch: '观望', unknown: '未知',
};

export default function Review() {
  const { data: signals, loading: loadingSignals } = useSignals();
  const { data: review, loading: loadingReview } = useReview();
  const stats = useSignalStats(signals);

  if (loadingSignals || loadingReview) return <div className="p-8 text-gray-500">加载中...</div>;
  if (!review) return <div className="p-8 text-gray-500">暂无数据</div>;

  const tradableRatio = review.total > 0 ? Math.round((review.tradable / review.total) * 100) : 0;

  return (
    <div className="p-6 lg:p-8 space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-xl font-semibold text-gray-100">复盘统计</h2>
        <p className="text-sm text-gray-500 mt-1">
          共 {review.total} 条信号 · {review.tradable} 可交易 · {review.total - review.tradable} 观望
          {review.validated > 0 && ` · 已验证 ${review.validated} 条`}
        </p>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="总信号"
          value={review.total}
          subtitle={`${review.tradable} 可交易`}
          icon={<BarChart3 size={16} />}
        />
        <StatCard
          label="胜率"
          value={stats.winRate !== null ? stats.winRate.toFixed(1) : '-'}
          suffix="%"
          trend={stats.winRate !== null ? (stats.winRate >= 50 ? 'up' : 'down') : 'neutral'}
          subtitle={`${stats.winCount} 胜 / ${stats.lossCount} 负`}
          icon={<Target size={16} />}
        />
        <StatCard
          label="期望 R"
          value={stats.avgR !== null ? (stats.avgR >= 0 ? '+' : '') + stats.avgR.toFixed(2) : '-'}
          suffix="R"
          trend={stats.avgR !== null ? (stats.avgR >= 0 ? 'up' : 'down') : 'neutral'}
          icon={<TrendingUp size={16} />}
        />
        <StatCard
          label="可交易占比"
          value={tradableRatio}
          suffix="%"
          trend={tradableRatio >= 50 ? 'up' : 'neutral'}
          subtitle={`观望 ${review.total - review.tradable} 条`}
          icon={<TrendingDown size={16} />}
        />
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Outcome Distribution */}
        <div className="bg-[#1a2332] rounded-xl border border-gray-800/60 p-5">
          <h3 className="text-[11px] font-medium text-gray-500 uppercase tracking-wider mb-4">验证结果分布</h3>
          <OutcomeChart data={stats.outcomeDistribution} size={190} />
        </div>

        {/* Playbook Performance */}
        <div className="bg-[#1a2332] rounded-xl border border-gray-800/60 p-5">
          <h3 className="text-[11px] font-medium text-gray-500 uppercase tracking-wider mb-4">策略盈亏分布</h3>
          <PlaybookChart data={stats.byPlaybook} height={190} />
        </div>
      </div>

      {/* Decision & Playbook Breakdown */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* By Direction */}
        <div className="bg-[#1a2332] rounded-xl border border-gray-800/60 p-5">
          <h3 className="text-[11px] font-medium text-gray-500 uppercase tracking-wider mb-4">按方向</h3>
          <div className="space-y-4">
            {Object.entries(review.byDecision).map(([dec, s]) => {
              const pct = review.total > 0 ? (s.total / review.total) * 100 : 0;
              const winRate = s.wins + s.losses > 0 ? Math.round((s.wins / (s.wins + s.losses)) * 100) : null;
              return (
                <div key={dec} className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Badge value={dec} label={decisionLabel[dec] || dec} />
                      <span className="text-xs text-gray-500">{s.total} 条</span>
                    </div>
                    <div className="flex items-center gap-3 text-xs">
                      {winRate !== null && (
                        <span className={`font-mono ${winRate >= 50 ? 'text-emerald-400' : 'text-red-400'}`}>
                          {winRate}% 胜率
                        </span>
                      )}
                      {s.wins > 0 && <span className="text-emerald-400/60">{s.wins} 胜</span>}
                      {s.losses > 0 && <span className="text-red-400/60">{s.losses} 负</span>}
                    </div>
                  </div>
                  <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all duration-500 ${
                        dec === 'long' ? 'bg-emerald-500/70' : dec === 'short' ? 'bg-red-500/70' : 'bg-amber-500/50'
                      }`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* By Playbook */}
        <div className="bg-[#1a2332] rounded-xl border border-gray-800/60 p-5">
          <h3 className="text-[11px] font-medium text-gray-500 uppercase tracking-wider mb-4">按策略</h3>
          <div className="space-y-4">
            {Object.entries(review.byPlaybook)
              .sort(([, a], [, b]) => b.total - a.total)
              .map(([pb, s]) => {
                const pct = review.total > 0 ? (s.total / review.total) * 100 : 0;
                const winRate = s.wins + s.losses > 0 ? Math.round((s.wins / (s.wins + s.losses)) * 100) : null;
                return (
                  <div key={pb} className="space-y-1.5">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="text-sm text-gray-300">{pb}</span>
                        <span className="text-xs text-gray-500">{s.total} 条</span>
                      </div>
                      <div className="flex items-center gap-3 text-xs">
                        {winRate !== null && (
                          <span className={`font-mono ${winRate >= 50 ? 'text-emerald-400' : 'text-red-400'}`}>
                            {winRate}% 胜率
                          </span>
                        )}
                        {s.wins > 0 && <span className="text-emerald-400/60">{s.wins} 胜</span>}
                        {s.losses > 0 && <span className="text-red-400/60">{s.losses} 负</span>}
                      </div>
                    </div>
                    <div className="h-1.5 bg-gray-800 rounded-full overflow-hidden">
                      <div className="bg-blue-500/60 h-full rounded-full transition-all duration-500" style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                );
              })}
          </div>
        </div>
      </div>

      {/* Footer note */}
      {review.validated < 30 && (
        <div className="bg-amber-500/5 border border-amber-500/20 rounded-xl px-5 py-3.5 text-sm text-amber-400/80">
          信号量达到 30 条以上后，胜率和盈亏比统计才有参考价值。当前 {review.validated} 条已验证。
        </div>
      )}
    </div>
  );
}
