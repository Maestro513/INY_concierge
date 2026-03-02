import { useState } from 'react';
import {
  Users,
  LogIn,
  Smartphone,
  MapPin,
  Calendar,
} from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, AreaChart, Area,
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import KPICard from '@/components/charts/KPICard';
import type { TimeRange } from '@/types';

// ── Mock data (replace with API hooks) ──
const MOCK_KPI = {
  daily: [
    { label: 'New Enrollments', value: 12, change: 8, trend: 'up' as const },
    { label: 'Logins Today', value: 247, change: 15, trend: 'up' as const },
    { label: 'Active Members', value: 1834, change: 3, trend: 'up' as const },
    { label: 'Avg Session', value: '4m 32s', change: -2, trend: 'down' as const },
  ],
  weekly: [
    { label: 'New Enrollments', value: 84, change: 12, trend: 'up' as const },
    { label: 'Logins This Week', value: 1640, change: 8, trend: 'up' as const },
    { label: 'Active Members', value: 1834, change: 5, trend: 'up' as const },
    { label: 'Avg Session', value: '4m 18s', change: 1, trend: 'up' as const },
  ],
  monthly: [
    { label: 'New Enrollments', value: 342, change: 22, trend: 'up' as const },
    { label: 'Logins This Month', value: 6823, change: 18, trend: 'up' as const },
    { label: 'Active Members', value: 1834, change: 14, trend: 'up' as const },
    { label: 'Avg Session', value: '4m 45s', change: 5, trend: 'up' as const },
  ],
};

const KPI_ICONS = [
  <Users className="h-5 w-5" />,
  <LogIn className="h-5 w-5" />,
  <Smartphone className="h-5 w-5" />,
  <Calendar className="h-5 w-5" />,
];

const ENROLLMENT_TREND = [
  { date: 'Mon', value: 14 }, { date: 'Tue', value: 18 },
  { date: 'Wed', value: 12 }, { date: 'Thu', value: 22 },
  { date: 'Fri', value: 16 }, { date: 'Sat', value: 8 },
  { date: 'Sun', value: 6 },
];

const LOGIN_TREND = [
  { date: 'Mon', value: 280 }, { date: 'Tue', value: 320 },
  { date: 'Wed', value: 290 }, { date: 'Thu', value: 340 },
  { date: 'Fri', value: 310 }, { date: 'Sat', value: 180 },
  { date: 'Sun', value: 150 },
];

const CARRIERS = [
  { carrier: 'Humana', count: 624, percentage: 34 },
  { carrier: 'Aetna', count: 401, percentage: 22 },
  { carrier: 'UHC', count: 329, percentage: 18 },
  { carrier: 'Wellcare', count: 220, percentage: 12 },
  { carrier: 'Devoted', count: 147, percentage: 8 },
  { carrier: 'Other', count: 113, percentage: 6 },
];

const FEATURES = [
  { feature: 'Benefits Lookup', count: 3240 },
  { feature: 'Drug Search', count: 2180 },
  { feature: 'Find Doctor', count: 1650 },
  { feature: 'AI Chat', count: 1420 },
  { feature: 'ID Card', count: 980 },
  { feature: 'SOB Download', count: 720 },
];

const AGE_GROUPS = [
  { group: '65-69', count: 480 },
  { group: '70-74', count: 620 },
  { group: '75-79', count: 410 },
  { group: '80-84', count: 210 },
  { group: '85+', count: 114 },
];

const STATES = [
  { state: 'FL', count: 412 }, { state: 'TX', count: 298 },
  { state: 'CA', count: 264 }, { state: 'NY', count: 198 },
  { state: 'OH', count: 156 }, { state: 'PA', count: 142 },
  { state: 'IL', count: 118 }, { state: 'GA', count: 96 },
];

const PIE_COLORS = ['#7B3FBF', '#3D6B99', '#3A7D5C', '#C0392B', '#F5A623', '#9B6BD4'];

export default function DashboardPage() {
  const [range, setRange] = useState<TimeRange>('daily');
  const kpis = MOCK_KPI[range];

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
        <Tabs value={range} onValueChange={(v) => setRange(v as TimeRange)}>
          <TabsList className="bg-muted/50">
            <TabsTrigger value="daily" className="text-xs">Daily</TabsTrigger>
            <TabsTrigger value="weekly" className="text-xs">Weekly</TabsTrigger>
            <TabsTrigger value="monthly" className="text-xs">Monthly</TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-4 gap-4">
        {kpis.map((kpi, i) => (
          <KPICard key={kpi.label} {...kpi} icon={KPI_ICONS[i]} />
        ))}
      </div>

      {/* Charts Row 1 — Enrollment + Login Trends */}
      <div className="grid grid-cols-2 gap-4">
        <Card className="border-border/50 shadow-sm">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold text-muted-foreground">
              Enrollment Trend
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={220}>
              <AreaChart data={ENROLLMENT_TREND}>
                <defs>
                  <linearGradient id="enrollGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#7B3FBF" stopOpacity={0.3} />
                    <stop offset="100%" stopColor="#7B3FBF" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#E4E2E8" />
                <XAxis dataKey="date" tick={{ fontSize: 12 }} stroke="#7A7585" />
                <YAxis tick={{ fontSize: 12 }} stroke="#7A7585" />
                <Tooltip
                  contentStyle={{
                    borderRadius: '10px', border: '1px solid #E4E2E8',
                    boxShadow: '0 4px 12px rgba(123,63,191,0.08)',
                  }}
                />
                <Area type="monotone" dataKey="value" stroke="#7B3FBF" strokeWidth={2.5} fill="url(#enrollGrad)" />
              </AreaChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card className="border-border/50 shadow-sm">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold text-muted-foreground">
              Login Activity
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={220}>
              <AreaChart data={LOGIN_TREND}>
                <defs>
                  <linearGradient id="loginGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#3D6B99" stopOpacity={0.3} />
                    <stop offset="100%" stopColor="#3D6B99" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#E4E2E8" />
                <XAxis dataKey="date" tick={{ fontSize: 12 }} stroke="#7A7585" />
                <YAxis tick={{ fontSize: 12 }} stroke="#7A7585" />
                <Tooltip
                  contentStyle={{
                    borderRadius: '10px', border: '1px solid #E4E2E8',
                    boxShadow: '0 4px 12px rgba(123,63,191,0.08)',
                  }}
                />
                <Area type="monotone" dataKey="value" stroke="#3D6B99" strokeWidth={2.5} fill="url(#loginGrad)" />
              </AreaChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      </div>

      {/* Charts Row 2 — Carriers + Features */}
      <div className="grid grid-cols-2 gap-4">
        {/* Carrier Distribution */}
        <Card className="border-border/50 shadow-sm">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold text-muted-foreground">
              Members by Carrier
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-6">
              <ResponsiveContainer width={180} height={180}>
                <PieChart>
                  <Pie
                    data={CARRIERS}
                    cx="50%" cy="50%"
                    innerRadius={50} outerRadius={80}
                    paddingAngle={3}
                    dataKey="count"
                  >
                    {CARRIERS.map((_, i) => (
                      <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                    ))}
                  </Pie>
                </PieChart>
              </ResponsiveContainer>
              <div className="flex-1 space-y-2">
                {CARRIERS.map((c, i) => (
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
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={FEATURES} layout="vertical" margin={{ left: 20 }}>
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
          </CardContent>
        </Card>
      </div>

      {/* Charts Row 3 — Age Groups + States */}
      <div className="grid grid-cols-2 gap-4">
        {/* Age Groups */}
        <Card className="border-border/50 shadow-sm">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold text-muted-foreground flex items-center gap-2">
              <Calendar className="h-4 w-4" /> Age Groups
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={AGE_GROUPS}>
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
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={STATES}>
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
