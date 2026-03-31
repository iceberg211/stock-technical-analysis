export interface Signal {
  signal_id: string;
  symbol: string;
  timestamp_utc: string;
  decision: string;
  bias: string;
  confidence: string;
  playbook: string;
  price_at_signal?: number;
  conditional_entry?: number;
  stop_loss?: number;
  t1?: number;
  t2?: number;
  snapshot: Record<string, unknown> | null;
  report: string;
  validation?: ValidationResult;
}

export interface BacktestSymbol {
  symbol: string;
  summary: string;
  details: string;
  metrics: Record<string, unknown> | null;
  config: Record<string, unknown> | null;
}

export interface Backtest {
  run_id: string;
  type: 'skill' | 'local';
  manifest: Record<string, unknown> | null;
  symbols: BacktestSymbol[];
}

export interface ValidationResult {
  outcome: string;
  entry_triggered: boolean;
  bars_to_entry?: number | null;
  bars_to_outcome?: number | null;
}

export interface Conversation {
  conversation_id: string;
  symbol: string;
  source: string;
  title: string;
  timestamp_utc: string;
  transcript: string;
  metadata: Record<string, unknown> | null;
}
