const styles: Record<string, string> = {
  long: 'bg-emerald-50 text-emerald-700 ring-emerald-600/20',
  short: 'bg-red-50 text-red-700 ring-red-600/20',
  watch: 'bg-amber-50 text-amber-700 ring-amber-600/20',
  bullish: 'bg-emerald-50 text-emerald-700 ring-emerald-600/20',
  bearish: 'bg-red-50 text-red-700 ring-red-600/20',
  neutral: 'bg-gray-50 text-gray-600 ring-gray-500/20',
  high: 'bg-emerald-50 text-emerald-700 ring-emerald-600/20',
  medium: 'bg-amber-50 text-amber-700 ring-amber-600/20',
  low: 'bg-gray-50 text-gray-500 ring-gray-500/20',
  done: 'bg-emerald-50 text-emerald-700 ring-emerald-600/20',
  failed: 'bg-red-50 text-red-700 ring-red-600/20',
  unknown: 'bg-gray-100 text-gray-400 ring-gray-300/20',
  default: 'bg-gray-50 text-gray-600 ring-gray-500/20',
};

export default function Badge({ value, label, className = '' }: { value: string; label?: string; className?: string }) {
  const key = value?.toLowerCase() || 'unknown';
  const style = styles[key] || styles.default;
  return (
    <span className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${style} ${className}`}>
      {label || value || '-'}
    </span>
  );
}
