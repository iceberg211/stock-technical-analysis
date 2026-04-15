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
  note?: string;
  snapshot: Record<string, unknown> | null;
  report: string;
  validation?: ValidationResult;
}

export interface ValidationResult {
  outcome: string;
  entry_triggered: boolean;
  entry_exec_price?: number | null;
  bars_to_entry?: number | null;
  bars_to_outcome?: number | null;
  bars_to_t1?: number | null;
  bars_to_t2?: number | null;
  bars_to_sl?: number | null;
  t1_hit?: boolean;
  t2_hit?: boolean;
  mfe?: number | null;
  mae?: number | null;
  realized_r?: number | null;
}

export interface BacktestSymbol {
  symbol: string;
  summary: string;
  metrics: Record<string, unknown> | null;
  config: Record<string, unknown> | null;
}

export interface Backtest {
  run_id: string;
  type: 'skill' | 'local';
  manifest: Record<string, unknown> | null;
  symbols: BacktestSymbol[];
}

export interface GroupStats {
  total: number;
  wins: number;
  losses: number;
}

export interface ReviewData {
  total: number;
  tradable: number;
  validated: number;
  wins: number;
  win_rate: string | null;
  byDecision: Record<string, GroupStats>;
  byPlaybook: Record<string, GroupStats>;
  byOutcome?: Record<string, number>;
}
