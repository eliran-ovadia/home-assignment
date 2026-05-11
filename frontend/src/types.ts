// TypeScript interfaces mirroring `src/api/schemas.py`. Numeric values that
// the backend serializes from `Decimal` arrive as strings (e.g. "200.000000");
// callers `parseFloat` at the display boundary.

export interface UploadSummary {
  transactions_loaded: number;
  positions_computed: number;
  violations_detected: number;
}

export interface UploadResponse {
  upload_id: number;
  status: string;
  summary: UploadSummary;
}

export interface RejectedRow {
  row_number: number;
  transaction_id: string | null;
  column: string;
  reason: string;
}

export interface RejectedRowsResponse {
  detail: string;
  rejected_rows: RejectedRow[];
}

export interface ClientSummary {
  client_id: string;
  transaction_count: number;
  position_count: number;
  violation_count: number;
}

// Decimal fields arrive as strings to preserve precision.
export interface PositionResponse {
  isin: string;
  quantity: string;
  avg_cost: string;
  realized_pnl: string;
  unrealized_pnl: string;
  last_price: string;
}

export interface ViolationResponse {
  id: number;
  transaction_id: string | null;
  client_id: string;
  isin: string | null;
  violation_type: string;
  severity: string;
  description: string;
  detected_at: string;
}

export interface TopTradedIsin {
  isin: string;
  transaction_count: number;
}

export interface HoldingTimeEntry {
  client_id: string;
  avg_holding_days: string | null;
}

export interface MostVolatileClient {
  client_id: string;
  max_portfolio_value: string;
  min_portfolio_value: string;
  value_range: string;
}

export interface IsinConcentrationEntry {
  isin: string;
  client_count: number;
  total_clients: number;
  concentration_pct: number;
  clients: string[];
}

export interface TopRealizedPnlClient {
  client_id: string;
  realized_pnl: string;
}

export interface WinRateEntry {
  client_id: string;
  win_rate: number;
  winning_trades: number;
  total_trades: number;
}

export interface MostTradedDay {
  date: string;
  transaction_count: number;
}

export interface BonusAnalytics {
  top_realized_pnl_client: TopRealizedPnlClient | null;
  win_rate_per_client: WinRateEntry[];
  most_traded_day: MostTradedDay | null;
}

export interface AnalyticsResponse {
  top_traded_isins: TopTradedIsin[];
  avg_holding_time_per_client: HoldingTimeEntry[];
  most_volatile_client: MostVolatileClient | null;
  isin_concentration: IsinConcentrationEntry[];
  bonus: BonusAnalytics | null;
}

export interface UploadHistoryItem {
  id: number;
  filename: string;
  row_count: number;
  violation_count: number;
  uploaded_at: string;
  is_last_viewed: boolean;
}
