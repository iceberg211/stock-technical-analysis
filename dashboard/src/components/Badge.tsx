const styles: Record<string, string> = {
  long: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/25',
  short: 'bg-red-500/15 text-red-400 border-red-500/25',
  watch: 'bg-amber-500/15 text-amber-400 border-amber-500/25',
  bullish: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/25',
  bearish: 'bg-red-500/15 text-red-400 border-red-500/25',
  neutral: 'bg-gray-500/15 text-gray-400 border-gray-500/25',
  high: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/25',
  medium: 'bg-amber-500/15 text-amber-400 border-amber-500/25',
  low: 'bg-gray-500/15 text-gray-500 border-gray-500/25',
  done: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/25',
  failed: 'bg-red-500/15 text-red-400 border-red-500/25',
  unknown: 'bg-gray-500/10 text-gray-500 border-gray-600/25',
  default: 'bg-gray-500/10 text-gray-400 border-gray-600/25',
};

export default function Badge({ value, label, className = '' }: { value: string; label?: string; className?: string }) {
  const key = value?.toLowerCase() || 'unknown';
  const style = styles[key] || styles.default;
  return (
    <span className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium border ${style} ${className}`}>
      {label || value || '-'}
    </span>
  );
}
