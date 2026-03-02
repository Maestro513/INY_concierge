// ── Auth ──
export interface AdminUser {
  id: number;
  email: string;
  first_name: string;
  last_name: string;
  role: 'super_admin' | 'admin' | 'viewer';
  is_active: boolean;
}

// ── Members ──
export interface Member {
  id: string;
  first_name: string;
  last_name: string;
  phone: string;
  plan_name: string;
  plan_number: string;
  agent: string;
  zip_code: string;
  medications: string;
  last_login?: string;
  created_at?: string;
}

export interface MemberActivity {
  reminders: Reminder[];
  usage: UsageEntry[];
  logins: LoginEvent[];
}

export interface Reminder {
  id: number;
  drug_name: string;
  dose_label: string;
  time_hour: number;
  time_minute: number;
  enabled: boolean;
}

export interface UsageEntry {
  id: number;
  category: string;
  amount: number;
  description: string;
  usage_date: string;
}

// ── Analytics ──
export type TimeRange = 'daily' | 'weekly' | 'monthly';

export interface KPIData {
  label: string;
  value: number | string;
  change?: number;        // percentage change from prior period
  trend?: 'up' | 'down' | 'flat';
}

export interface ChartPoint {
  date: string;
  value: number;
}

export interface CarrierBreakdown {
  carrier: string;
  count: number;
  percentage: number;
}

export interface StateBreakdown {
  state: string;
  count: number;
}

export interface AgeGroupBreakdown {
  group: string;
  count: number;
}

export interface FeatureUsage {
  feature: string;
  count: number;
}

export interface LoginEvent {
  phone: string;
  success: boolean;
  created_at: string;
  ip_address?: string;
}

// ── Plans ──
export interface Plan {
  plan_number: string;
  plan_name: string;
  plan_type: string;
  carrier: string;
  has_extraction: boolean;
  has_benefits: boolean;
  has_pdf: boolean;
}

// ── System ──
export interface SystemHealth {
  status: 'healthy' | 'degraded' | 'down';
  uptime_seconds: number;
  total_requests: number;
  error_count: number;
  avg_latency_ms: number;
  active_sessions: number;
  disk_usage_gb: number;
  disk_total_gb: number;
}

// ── Paginated response ──
export interface PaginatedResponse<T> {
  data: T[];
  total: number;
  page: number;
  per_page: number;
}
