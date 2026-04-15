interface PriceLevelsProps {
  entry: number | null | undefined;
  stopLoss: number | null | undefined;
  t1: number | null | undefined;
  t2: number | null | undefined;
  current: number | null | undefined;
  action: string;
}

function fmt(n: number | null | undefined): string {
  if (n === null || n === undefined) return '-';
  return n.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 2 });
}

export default function PriceLevels({ entry, stopLoss, t1, t2, current, action }: PriceLevelsProps) {
  const levels = [
    { label: '止损', value: stopLoss, color: '#ef4444', textColor: 'text-red-400' },
    { label: '入场', value: entry, color: '#3b82f6', textColor: 'text-blue-400' },
    { label: '现价', value: current, color: '#94a3b8', textColor: 'text-gray-300' },
    { label: 'T1', value: t1, color: '#10b981', textColor: 'text-emerald-400' },
    { label: 'T2', value: t2, color: '#059669', textColor: 'text-emerald-500' },
  ].filter(l => l.value != null && l.value !== undefined) as Array<{ label: string; value: number; color: string; textColor: string }>;

  if (levels.length < 2) return null;

  const values = levels.map(l => l.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const padding = range * 0.08;

  const scaleMin = min - padding;
  const scaleMax = max + padding;
  const scaleRange = scaleMax - scaleMin;

  const getPos = (v: number) => ((v - scaleMin) / scaleRange) * 100;

  // Risk/reward zones
  const isLong = action === 'long';
  const entryVal = entry ?? 0;
  const slVal = stopLoss ?? 0;
  const t1Val = t1 ?? 0;

  const showZones = entry != null && stopLoss != null && t1 != null;
  const riskStart = showZones ? getPos(isLong ? slVal : entryVal) : 0;
  const riskEnd = showZones ? getPos(isLong ? entryVal : slVal) : 0;
  const rewardStart = showZones ? getPos(isLong ? entryVal : t1Val) : 0;
  const rewardEnd = showZones ? getPos(isLong ? t1Val : entryVal) : 0;

  return (
    <div className="space-y-4">
      {/* Visual bar */}
      <div className="relative h-10 bg-gray-800/50 rounded-lg overflow-hidden border border-gray-700/50">
        {/* Risk zone */}
        {showZones && (
          <div
            className="absolute top-0 bottom-0 bg-red-500/10"
            style={{ left: `${Math.min(riskStart, riskEnd)}%`, width: `${Math.abs(riskEnd - riskStart)}%` }}
          />
        )}
        {/* Reward zone */}
        {showZones && (
          <div
            className="absolute top-0 bottom-0 bg-emerald-500/10"
            style={{ left: `${Math.min(rewardStart, rewardEnd)}%`, width: `${Math.abs(rewardEnd - rewardStart)}%` }}
          />
        )}
        {/* Level markers */}
        {levels.map(l => (
          <div
            key={l.label}
            className="absolute top-0 bottom-0 w-0.5"
            style={{ left: `${getPos(l.value)}%`, background: l.color }}
          >
            <div
              className="absolute -top-0.5 left-1/2 -translate-x-1/2 w-2.5 h-2.5 rounded-full border-2"
              style={{ background: l.color, borderColor: l.color }}
            />
          </div>
        ))}
      </div>

      {/* Labels */}
      <div className="grid grid-cols-5 gap-2">
        {[
          { label: '止损', value: stopLoss, color: 'text-red-400' },
          { label: '入场', value: entry, color: 'text-blue-400' },
          { label: '现价', value: current, color: 'text-gray-300' },
          { label: 'T1', value: t1, color: 'text-emerald-400' },
          { label: 'T2', value: t2, color: 'text-emerald-500' },
        ].map(l => (
          <div key={l.label} className="text-center">
            <div className="text-[11px] text-gray-500 mb-0.5">{l.label}</div>
            <div className={`text-sm font-mono font-medium ${l.color}`}>{fmt(l.value)}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
