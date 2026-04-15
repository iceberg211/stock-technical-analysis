import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts';

interface PlaybookData {
  total: number;
  wins: number;
  losses: number;
}

interface PlaybookChartProps {
  data: Record<string, PlaybookData>;
  height?: number;
}

export default function PlaybookChart({ data, height = 220 }: PlaybookChartProps) {
  const chartData = Object.entries(data)
    .filter(([key]) => key !== 'none' && key !== '无匹配')
    .map(([name, stats]) => ({
      name: name.length > 16 ? name.slice(0, 14) + '...' : name,
      fullName: name,
      total: stats.total,
      wins: stats.wins,
      losses: stats.losses,
      winRate: stats.wins + stats.losses > 0
        ? Math.round((stats.wins / (stats.wins + stats.losses)) * 100)
        : null,
    }))
    .sort((a, b) => b.total - a.total);

  if (chartData.length === 0) {
    return (
      <div className="flex items-center justify-center text-gray-600 text-sm" style={{ height }}>
        暂无策略数据
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={chartData} layout="vertical" margin={{ left: 8, right: 16, top: 4, bottom: 4 }}>
        <XAxis type="number" tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} />
        <YAxis
          type="category"
          dataKey="name"
          width={120}
          tick={{ fill: '#94a3b8', fontSize: 12 }}
          axisLine={false}
          tickLine={false}
        />
        <Tooltip
          contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8, fontSize: 13 }}
          itemStyle={{ color: '#cbd5e1' }}
          labelStyle={{ color: '#f1f5f9', fontWeight: 600 }}
          formatter={(value, name) => {
            const labels: Record<string, string> = { wins: '盈利', losses: '亏损', total: '总计' };
            return [String(value), labels[String(name)] || String(name)];
          }}
          labelFormatter={(label) => {
            const item = chartData.find(d => d.name === label);
            return item?.fullName || label;
          }}
        />
        <Bar dataKey="wins" stackId="a" radius={[0, 0, 0, 0]} barSize={18}>
          {chartData.map((_, i) => <Cell key={i} fill="#10b981" />)}
        </Bar>
        <Bar dataKey="losses" stackId="a" radius={[0, 4, 4, 0]} barSize={18}>
          {chartData.map((_, i) => <Cell key={i} fill="#ef4444" />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
