import { useNavigate } from 'react-router-dom';
import { TrendingUp, Target, BarChart3, AlertTriangle } from 'lucide-react';
import { useSignals, useSignalStats, useBacktests } from '../hooks/useData';
import StatCard from '../components/StatCard';
import OutcomeChart from '../components/OutcomeChart';
import Badge from '../components/Badge';

function formatTime(ts: string) {
  if (!ts || ts === '-') return '-';
  return ts.replace('T', ' ').replace('Z', '').slice(0, 16);
}

function formatPrice(n: unknown) {
  if (n === undefined || n === null || typeof n !== 'number') return '-';
  return n.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 2 });
}

const decisionLabel: Record<string, string> = { long: '做多', short: '做空', watch: '观望' };

const outcomeStyle: Record<string, string> = {
  t1_hit: 'text-emerald-400',
  sl_hit: 'text-red-400',
  neither: 'text-gray-500',
  not_triggered: 'text-amber-400',
  missed_entry: 'text-amber-400',
  pending: 'text-gray-600',
};

const outcomeLabel: Record<string, string> = {
  t1_hit: 'T1 命中',
  sl_hit: '止损',
  neither: '未达标',
  not_triggered: '未触发',
  missed_entry: '未触发',
  pending: '待验证',
};

export default function Dashboard() {
  const { data: signals, loading: loadingSignals } = useSignals();
  const { data: backtests, loading: loadingBt } = useBacktests();
  const stats = useSignalStats(signals);
  const navigate = useNavigate();

  if (loadingSignals || loadingBt) {
    return (
      <div className="p-8 flex items-center justify-center min-h-screen">
        <div className="text-gray-500">加载中...</div>
      </div>
    );
  }

  const skillBacktests = backtests.filter(b => b.type === 'skill').length;
  const recentSignals = signals.slice(0, 8);

  return (
    <div className="p-6 lg:p-8 space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-xl font-semibold text-gray-100">Dashboard</h2>
        <p className="text-sm text-gray-500 mt-1">信号追踪与绩效总览</p>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          label="总信号"
          value={stats.total}
          subtitle={`${stats.tradableCount} 可交易 / ${stats.watchCount} 观望`}
          icon={<TrendingUp size={16} />}
        />
        <StatCard
          label="胜率"
          value={stats.winRate !== null ? stats.winRate.toFixed(1) : '-'}
          suffix="%"
          trend={stats.winRate !== null ? (stats.winRate >= 50 ? 'up' : 'down') : 'neutral'}
          subtitle={stats.validatedCount > 0 ? `${stats.winCount} 胜 / ${stats.lossCount} 负 (${stats.validatedCount} 已验证)` : '暂无验证数据'}
          icon={<Target size={16} />}
        />
        <StatCard
          label="期望 R"
          value={stats.avgR !== null ? (stats.avgR >= 0 ? '+' : '') + stats.avgR.toFixed(2) : '-'}
          suffix="R"
          trend={stats.avgR !== null ? (stats.avgR >= 0 ? 'up' : 'down') : 'neutral'}
          subtitle="平均已实现收益"
          icon={<BarChart3 size={16} />}
        />
        <StatCard
          label="回测次数"
          value={backtests.length}
          subtitle={`${skillBacktests} 次 Skill / ${backtests.length - skillBacktests} 次规则`}
          icon={<AlertTriangle size={16} />}
        />
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Outcome Distribution */}
        <div className="bg-[#1a2332] border border-gray-800/60 rounded-xl p-5">
          <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-4">验证结果分布</h3>
          <OutcomeChart data={stats.outcomeDistribution} size={180} />
        </div>

        {/* Signal Breakdown */}
        <div className="bg-[#1a2332] border border-gray-800/60 rounded-xl p-5">
          <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider mb-4">信号概况</h3>
          <div className="space-y-4">
            {/* Direction distribution */}
            {['long', 'short', 'watch'].map(dec => {
              const count = signals.filter(s => s.decision === dec).length;
              const pct = stats.total > 0 ? (count / stats.total) * 100 : 0;
              return (
                <div key={dec} className="flex items-center gap-3">
                  <Badge value={dec} label={decisionLabel[dec]} className="w-16 justify-center" />
                  <div className="flex-1 h-2 bg-gray-800 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all duration-500 ${
                        dec === 'long' ? 'bg-emerald-500' : dec === 'short' ? 'bg-red-500' : 'bg-amber-500'
                      }`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                  <span className="text-sm font-mono text-gray-300 w-8 text-right">{count}</span>
                </div>
              );
            })}

            {/* Symbols */}
            <div className="pt-3 border-t border-gray-800/60">
              <div className="text-xs text-gray-500 mb-2">活跃品种</div>
              <div className="flex flex-wrap gap-2">
                {stats.symbols.map(sym => (
                  <span key={sym} className="px-2.5 py-1 text-xs font-mono bg-gray-800/60 text-gray-300 rounded-md border border-gray-700/40">
                    {sym}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Recent Signals */}
      <div className="bg-[#1a2332] border border-gray-800/60 rounded-xl overflow-hidden">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-800/60">
          <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wider">最近信号</h3>
          <button
            onClick={() => navigate('/signals')}
            className="text-xs text-cyan-400 hover:text-cyan-300 transition-colors cursor-pointer"
          >
            查看全部
          </button>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-[11px] font-medium text-gray-500 uppercase tracking-wider border-b border-gray-800/40">
              <th className="px-5 py-2.5">时间</th>
              <th className="px-5 py-2.5">品种</th>
              <th className="px-5 py-2.5">方向</th>
              <th className="px-5 py-2.5 text-right">入场</th>
              <th className="px-5 py-2.5 text-right">止损</th>
              <th className="px-5 py-2.5 text-right">T1</th>
              <th className="px-5 py-2.5 text-center">验证</th>
            </tr>
          </thead>
          <tbody>
            {recentSignals.map((s, i) => {
              const outcome = s.validation?.outcome || 'pending';
              return (
                <tr
                  key={s.signal_id + i}
                  onClick={() => navigate('/signals', { state: { selectedId: s.signal_id } })}
                  className="border-b border-gray-800/30 hover:bg-gray-800/30 cursor-pointer transition-colors"
                >
                  <td className="px-5 py-3 text-gray-500 font-mono text-xs whitespace-nowrap">{formatTime(s.timestamp_utc)}</td>
                  <td className="px-5 py-3 font-medium text-gray-200">{s.symbol}</td>
                  <td className="px-5 py-3"><Badge value={s.decision} label={decisionLabel[s.decision]} /></td>
                  <td className="px-5 py-3 text-right font-mono text-gray-300 text-xs">{formatPrice(s.conditional_entry || s.price_at_signal)}</td>
                  <td className="px-5 py-3 text-right font-mono text-red-400/80 text-xs">{formatPrice(s.stop_loss)}</td>
                  <td className="px-5 py-3 text-right font-mono text-emerald-400/80 text-xs">{formatPrice(s.t1)}</td>
                  <td className="px-5 py-3 text-center">
                    <span className={`text-xs font-medium ${outcomeStyle[outcome] || 'text-gray-600'}`}>
                      {outcomeLabel[outcome] || outcome}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Footer note */}
      {stats.validatedCount < 30 && stats.total > 0 && (
        <div className="bg-amber-500/5 border border-amber-500/20 rounded-xl px-5 py-3.5 text-sm text-amber-400/80">
          信号量达到 30 条以上后，胜率和盈亏比统计才有参考价值。当前 {stats.validatedCount} 条已验证。
        </div>
      )}
    </div>
  );
}
