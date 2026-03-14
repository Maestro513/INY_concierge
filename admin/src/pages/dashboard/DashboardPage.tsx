import { useState, useEffect, useCallback } from 'react';
import {
  Users,
  LogIn,
  Smartphone,
  MapPin,
  Calendar,
  AlertCircle,
  RefreshCw,
} from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell,
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import KPICard from '@/components/charts/KPICard';
import client from '@/api/client';
import { ENDPOINTS } from '@/config/api';
import type { TimeRange } from '@/types';

// ── Map TimeRange to API `days` param ──
const RANGE_DAYS: Record<TimeRange, number> = { daily: 1, weekly: 7, monthly: 30 };

// ── Fallback data for endpoints not yet live on backend ──
const PLACEHOLDER_STATES = [
  { state: 'FL', count: 412 }, { state: 'TX', count: 298 },
  { state: 'CA', count: 264 }, { state: 'NY', count: 198 },
  { state: 'OH', count: 156 }, { state: 'PA', count: 142 },
  { state: 'IL', count: 118 }, { state: 'GA', count: 96 },
];

const PLACEHOLDER_AGE_GROUPS = [
  { group: '65-69', count: 480 },
  { group: '70-74', count: 620 },
  { group: '75-79', count: 410 },
  { group: '80-84', count: 210 },
  { group: '85+', count: 114 },
];

const KPI_ICONS = [
  <Users className="h-5 w-5" />,
  <LogIn className="h-5 w-5" />,
  <Smartphone className="h-5 w-5" />,
  <Calendar className="h-5 w-5" />,
];

const PIE_COLORS = ['#7B3FBF', '#3D6B99', '#3A7D5C', '#C0392B', '#F5A623', '#9B6BD4'];

// ── Types for API responses ──
interface LoginStats { total_logins: number; unique_users: number; failed_logins: number; days: number }
interface FeatureStats { total: number; by_type: Record<string, number> }
interface CarrierItem { carrier: string; count: number; percentage: number }

export default function DashboardPage() {
  const [range, setRange] = useState<TimeRange>('daily');

  // API data state
  const [loginStats, setLoginStats] = useState<LoginStats | null>(null);
  const [featureStats, setFeatureStats] = useState<FeatureStats | null>(null);
  const [carriers, setCarriers] = useState<CarrierItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async (days: number) => {
    setLoading(true);
    setError(null);
    try {
      const [loginsRes, featuresRes, carriersRes] = await Promise.all([
        client.get<LoginStats>(ENDPOINTS.ANALYTICS_LOGINS, { params: { days } }),
        client.get<FeatureStats>(ENDPOINTS.ANALYTICS_FEATURES, { params: { days } }),
        client.get<CarrierItem[]>(ENDPOINTS.ANALYTICS_CARRIERS),
      ]);
      setLoginStats(loginsRes.data);
      setFeatureStats(featuresRes.data);
      setCarriers(Array.isArray(carriersRes.data) ? carriersRes.data : []);
    } catch (err) {
      console.error('Dashboard fetch failed:', err);
      setError('Failed to load dashboard data. Retrying may help.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData(RANGE_DAYS[range]);
  }, [range, fetchData]);

  // Build KPI cards from real data
  const kpis = loginStats
    ? [
        { label: 'Total Logins', value: loginStats.total_logins, trend: 'up' as const },
        { label: 'Unique Users', value: loginStats.unique_users, trend: 'up' as const },
        { label: 'Failed Logins', value: loginStats.failed_logins, trend: loginStats.failed_logins > 0 ? 'down' as const : 'flat' as const },
        { label: 'Total Carriers', value: carriers.length, trend: 'flat' as const },
      ]
    : [];

  // Transform feature stats for bar chart
  const featureChartData = featureStats
    ? Object.entries(featureStats.by_type)
        .map(([feature, count]) => ({ feature, count }))
        .sort((a, b) => b.count - a.count)
        .slice(0, 8)
    : [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
          <p className="text-sm text-muted-foreground">
            Real-time metrics and analytics
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            className="h-8 text-xs"
            onClick={() => fetchData(RANGE_DAYS[range])}
            disabled={loading}
          >
            <RefreshCw className={`mr-1.5 h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </Button>
          <Tabs value={range} onValueChange={(v) => setRange(v as TimeRange)}>
            <TabsList className="bg-muted/50">
              <TabsTrigger value="daily" className="text-xs">Daily</TabsTrigger>
              <TabsTrigger value="weekly" className="text-xs">Weekly</TabsTrigger>
              <TabsTrigger value="monthly" className="text-xs">Monthly</TabsTrigger>
            </TabsList>
          </Tabs>
        </div>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
          <AlertCircle className="h-4 w-4 shrink-0" />
          <span>{error}</span>
          <Button variant="outline" size="sm" className="ml-auto h-7 text-xs" onClick={() => fetchData(RANGE_DAYS[range])}>
            Retry
          </Button>
        </div>
      )}

      {/* KPI Cards */}
      <div className="grid grid-cols-4 gap-4">
        {loading
          ? Array.from({ length: 4 }).map((_, i) => (
              <Card key={i} className="border-border/50 shadow-sm">
                <CardContent className="p-5 space-y-3">
                  <Skeleton className="h-3 w-24" />
                  <Skeleton className="h-7 w-16" />
                </CardContent>
              </Card>
            ))
          : kpis.map((kpi, i) => (
              <KPICard key={kpi.label} {...kpi} icon={KPI_ICONS[i]} />
            ))
        }
      </div>

      {/* Charts Row 1 — Carriers + Features (real data) */}
      <div className="grid grid-cols-2 gap-4">
        {/* Carrier Distribution */}
        <Card className="border-border/50 shadow-sm">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold text-muted-foreground">
              Members by Carrier
            </CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="flex items-center justify-center h-[200px]">
                <Skeleton className="h-[160px] w-[160px] rounded-full" />
              </div>
            ) : carriers.length > 0 ? (
              <div className="flex items-center gap-6">
                <ResponsiveContainer width={180} height={180}>
                  <PieChart>
                    <Pie
                      data={carriers}
                      cx="50%" cy="50%"
                      innerRadius={50} outerRadius={80}
                      paddingAngle={3}
                      dataKey="count"
                    >
                      {carriers.map((_, i) => (
                        <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                      ))}
                    </Pie>
                  </PieChart>
                </ResponsiveContainer>
                <div className="flex-1 space-y-2">
                  {carriers.map((c, i) => (
                    <div key={c.carrier} className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <div
                          className="h-2.5 w-2.5 rounded-full"
                          style={{ backgroundColor: PIE_COLORS[i % PIE_COLORS.length] }}
                        />
                        <span className="text-xs font-medium">{c.carrier}</span>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-bold">{c.count}</span>
                        <span className="text-[10px] text-muted-foreground">{c.percentage}%</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <p className="text-xs text-muted-foreground text-center py-8">No carrier data available</p>
            )}
          </CardContent>
        </Card>

        {/* Most Used Features */}
        <Card className="border-border/50 shadow-sm">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold text-muted-foreground">
              Most Used Features
            </CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <div className="space-y-3 py-4">
                {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-4 w-full" />)}
              </div>
            ) : featureChartData.length > 0 ? (
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={featureChartData} layout="vertical" margin={{ left: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#E4E2E8" horizontal={false} />
                  <XAxis type="number" tick={{ fontSize: 11 }} stroke="#7A7585" />
                  <YAxis dataKey="feature" type="category" tick={{ fontSize: 11 }} stroke="#7A7585" width={100} />
                  <Tooltip
                    contentStyle={{
                      borderRadius: '10px', border: '1px solid #E4E2E8',
                      boxShadow: '0 4px 12px rgba(123,63,191,0.08)',
                    }}
                  />
                  <Bar dataKey="count" fill="#7B3FBF" radius={[0, 6, 6, 0]} barSize={18} />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <p className="text-xs text-muted-foreground text-center py-8">No feature usage data yet</p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Charts Row 2 — Age Groups + States (placeholders until Zoho CRM) */}
      <div className="grid grid-cols-2 gap-4">
        {/* Age Groups */}
        <Card className="border-border/50 shadow-sm">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold text-muted-foreground flex items-center gap-2">
              <Calendar className="h-4 w-4" /> Age Groups
              <span className="text-[10px] font-normal text-muted-foreground/60 ml-1">(sample data)</span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={PLACEHOLDER_AGE_GROUPS}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E4E2E8" />
                <XAxis dataKey="group" tick={{ fontSize: 12 }} stroke="#7A7585" />
                <YAxis tick={{ fontSize: 12 }} stroke="#7A7585" />
                <Tooltip
                  contentStyle={{
                    borderRadius: '10px', border: '1px solid #E4E2E8',
                    boxShadow: '0 4px 12px rgba(123,63,191,0.08)',
                  }}
                />
                <Bar dataKey="count" fill="#3A7D5C" radius={[6, 6, 0, 0]} barSize={36} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Top States */}
        <Card className="border-border/50 shadow-sm">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold text-muted-foreground flex items-center gap-2">
              <MapPin className="h-4 w-4" /> Top States
              <span className="text-[10px] font-normal text-muted-foreground/60 ml-1">(sample data)</span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={PLACEHOLDER_STATES}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E4E2E8" />
                <XAxis dataKey="state" tick={{ fontSize: 12 }} stroke="#7A7585" />
                <YAxis tick={{ fontSize: 12 }} stroke="#7A7585" />
                <Tooltip
                  contentStyle={{
                    borderRadius: '10px', border: '1px solid #E4E2E8',
                    boxShadow: '0 4px 12px rgba(123,63,191,0.08)',
                  }}
                />
                <Bar dataKey="count" fill="#3D6B99" radius={[6, 6, 0, 0]} barSize={30} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
