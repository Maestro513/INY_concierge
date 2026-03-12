import { useState, useEffect } from 'react';
import {
  Home,
  AlertTriangle,
  Users,
  Car,
  UtensilsCrossed,
  UsersRound,
  ShieldAlert,
} from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Skeleton } from '@/components/ui/skeleton';
import api from '@/api/client';

interface FlagSummary {
  flag: string;
  label: string;
  count: number;
  total: number;
  pct: number;
  benefit: string;
  action: string;
}

interface FlaggedMember {
  phone_last4: string;
  transportation: string;
  food_insecurity: string;
  social_isolation: string;
  housing_stability: string;
  flags: string[];
  flag_count: number;
  created_at: string;
}

interface SDoHReport {
  total_screened: number;
  total_with_flags: number;
  flag_summary: FlagSummary[];
  members: FlaggedMember[];
  benefit_recommendations: { label: string; benefit: string; action: string }[];
}

const FLAG_ICONS: Record<string, typeof Car> = {
  transportation: Car,
  food_insecurity: UtensilsCrossed,
  social_isolation: UsersRound,
  housing_stability: Home,
};

const FLAG_COLORS: Record<string, { bg: string; text: string; bar: string }> = {
  transportation: { bg: 'bg-blue-100', text: 'text-blue-600', bar: '#3B82F6' },
  food_insecurity: { bg: 'bg-orange-100', text: 'text-orange-600', bar: '#F97316' },
  social_isolation: { bg: 'bg-purple-100', text: 'text-purple-600', bar: '#8B5CF6' },
  housing_stability: { bg: 'bg-red-100', text: 'text-red-600', bar: '#EF4444' },
};

export default function SDoHReportPage() {
  const [data, setData] = useState<SDoHReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    setLoading(true);
    api.get('/api/admin/sdoh-report')
      .then((res) => {
        setData(res.data);
        setError('');
      })
      .catch((err) => {
        setError(err.response?.data?.detail || 'Failed to load SDoH data');
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-64" />
        <div className="grid grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-24" />)}
        </div>
        <Skeleton className="h-80" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="text-center">
          <AlertTriangle className="h-10 w-10 text-destructive mx-auto mb-3" />
          <p className="text-sm text-muted-foreground">{error}</p>
        </div>
      </div>
    );
  }

  if (!data || data.total_screened === 0) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold tracking-tight">SDoH Risk Report</h1>
        <div className="flex items-center justify-center py-20">
          <div className="text-center">
            <ShieldAlert className="h-10 w-10 text-muted-foreground mx-auto mb-3" />
            <p className="text-sm text-muted-foreground">
              No SDoH screening data yet. Members will appear here after completing the well-being check.
            </p>
          </div>
        </div>
      </div>
    );
  }

  const { total_screened, total_with_flags, flag_summary, members } = data;
  const flaggedPct = total_screened > 0 ? Math.round((total_with_flags / total_screened) * 100) : 0;

  const chartData = flag_summary.map((f) => ({
    name: f.label,
    pct: f.pct,
    count: f.count,
    fill: FLAG_COLORS[f.flag]?.bar || '#8B5CF6',
  }));

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight">SDoH Risk Report</h1>
        <p className="text-sm text-muted-foreground">
          Social Determinants of Health flags — identify barriers and connect members to plan benefits
        </p>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-4 gap-4">
        <Card className="border-border/50 shadow-sm">
          <CardContent className="pt-5 pb-4">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-purple-100">
                <Users className="h-5 w-5 text-purple-600" />
              </div>
              <div>
                <p className="text-2xl font-bold">{total_screened}</p>
                <p className="text-xs text-muted-foreground">Members Screened</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-border/50 shadow-sm">
          <CardContent className="pt-5 pb-4">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-orange-100">
                <AlertTriangle className="h-5 w-5 text-orange-600" />
              </div>
              <div>
                <p className="text-2xl font-bold">{total_with_flags}</p>
                <p className="text-xs text-muted-foreground">Members With Risks</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-border/50 shadow-sm">
          <CardContent className="pt-5 pb-4">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-red-100">
                <ShieldAlert className="h-5 w-5 text-red-600" />
              </div>
              <div>
                <p className="text-2xl font-bold">{flaggedPct}%</p>
                <p className="text-xs text-muted-foreground">Risk Rate</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-border/50 shadow-sm">
          <CardContent className="pt-5 pb-4">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-green-100">
                <Users className="h-5 w-5 text-green-600" />
              </div>
              <div>
                <p className="text-2xl font-bold">{total_screened - total_with_flags}</p>
                <p className="text-xs text-muted-foreground">No Risks Identified</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Chart + Benefit Recommendations */}
      <div className="grid grid-cols-2 gap-4">
        {/* Flag Distribution Chart */}
        <Card className="border-border/50 shadow-sm">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold text-muted-foreground flex items-center gap-2">
              <ShieldAlert className="h-4 w-4" /> Risk Flag Distribution
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={chartData} margin={{ left: 10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E4E2E8" vertical={false} />
                <XAxis dataKey="name" tick={{ fontSize: 11 }} stroke="#7A7585" />
                <YAxis tick={{ fontSize: 11 }} stroke="#7A7585" domain={[0, 100]} />
                <Tooltip
                  formatter={(value) => `${value}%`}
                  contentStyle={{
                    borderRadius: '10px', border: '1px solid #E4E2E8',
                    boxShadow: '0 4px 12px rgba(123,63,191,0.08)',
                  }}
                />
                <Bar dataKey="pct" radius={[6, 6, 0, 0]} barSize={40} name="Rate">
                  {chartData.map((entry, i) => (
                    <Cell key={i} fill={entry.fill} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Benefit Recommendations */}
        <Card className="border-border/50 shadow-sm">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold text-muted-foreground">
              Benefit Recommendations by Flag
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {flag_summary.map((f) => {
              const Icon = FLAG_ICONS[f.flag] || ShieldAlert;
              const colors = FLAG_COLORS[f.flag] || { bg: 'bg-gray-100', text: 'text-gray-600' };
              return (
                <div key={f.flag} className="flex items-start gap-3 p-3 rounded-lg bg-muted/30">
                  <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-md ${colors.bg}`}>
                    <Icon className={`h-4 w-4 ${colors.text}`} />
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-semibold">{f.label}</p>
                      <Badge variant="secondary" className="text-[10px]">
                        {f.count}/{f.total}
                      </Badge>
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      <span className="font-medium">Benefit:</span> {f.benefit}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      <span className="font-medium">Action:</span> {f.action}
                    </p>
                  </div>
                </div>
              );
            })}
          </CardContent>
        </Card>
      </div>

      {/* Flagged Members Table */}
      {members.length > 0 && (
        <Card className="border-border/50 shadow-sm">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold text-muted-foreground flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-orange-500" />
              Members with Social Risk Flags ({members.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs">Member</TableHead>
                  <TableHead className="text-xs text-center">Flags</TableHead>
                  <TableHead className="text-xs">Risk Areas</TableHead>
                  <TableHead className="text-xs">Screened</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {members.slice(0, 50).map((m, i) => (
                  <TableRow key={i}>
                    <TableCell className="text-xs font-medium">
                      ***-***-{m.phone_last4}
                    </TableCell>
                    <TableCell className="text-center">
                      <Badge
                        variant={m.flag_count >= 3 ? 'destructive' : 'secondary'}
                        className="text-[10px]"
                      >
                        {m.flag_count}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1">
                        {m.flags.map((f) => {
                          const info = flag_summary.find((fs) => fs.flag === f);
                          return (
                            <Badge key={f} variant="outline" className="text-[10px]">
                              {info?.label || f}
                            </Badge>
                          );
                        })}
                      </div>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {m.created_at ? new Date(m.created_at).toLocaleDateString() : '—'}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
