import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip } from 'recharts';

const OUTCOME_CONFIG: Record<string, { label: string; color: string }> = {
  t1_hit: { label: 'T1 命中', color: '#10b981' },
  sl_hit: { label: '止损', color: '#ef4444' },
  neither: { label: '未达标', color: '#6b7280' },
  not_triggered: { label: '未触发', color: '#f59e0b' },
  missed_entry: { label: '未触发', color: '#f59e0b' },
  no_data: { label: '无数据', color: '#374151' },
  insufficient_data: { label: '数据不足', color: '#374151' },
  pending: { label: '待验证', color: '#4b5563' },
  no_levels: { label: '缺点位', color: '#374151' },
};

interface OutcomeChartProps {
  data: Record<string, number>;
  size?: number;
}

export default function OutcomeChart({ data, size = 200 }: OutcomeChartProps) {
  const chartData = Object.entries(data)
    .map(([key, value]) => ({
      name: OUTCOME_CONFIG[key]?.label || key,
      value,
      color: OUTCOME_CONFIG[key]?.color || '#4b5563',
    }))
    .filter(d => d.value > 0)
    .sort((a, b) => b.value - a.value);

  if (chartData.length === 0) {
    return (
      <div className="flex items-center justify-center text-gray-600 text-sm" style={{ height: size }}>
        暂无数据
      </div>
    );
  }

  return (
    <div className="flex items-center gap-6">
      <ResponsiveContainer width={size} height={size}>
        <PieChart>
          <Pie
            data={chartData}
            cx="50%"
            cy="50%"
            innerRadius={size * 0.3}
            outerRadius={size * 0.44}
            paddingAngle={2}
            dataKey="value"
            stroke="none"
          >
            {chartData.map((entry, i) => (
              <Cell key={i} fill={entry.color} />
            ))}
          </Pie>
          <Tooltip
            contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8, fontSize: 13 }}
            itemStyle={{ color: '#cbd5e1' }}
            labelStyle={{ color: '#f1f5f9', fontWeight: 600 }}
          />
        </PieChart>
      </ResponsiveContainer>
      <div className="space-y-2">
        {chartData.map(d => (
          <div key={d.name} className="flex items-center gap-2.5">
            <div className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ background: d.color }} />
            <span className="text-sm text-gray-400">{d.name}</span>
            <span className="text-sm font-mono font-medium text-gray-200 ml-auto">{d.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
