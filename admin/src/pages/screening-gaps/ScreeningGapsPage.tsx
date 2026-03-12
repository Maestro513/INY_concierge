import { useState, useEffect } from 'react';
import {
  HeartPulse,
  AlertTriangle,
  CheckCircle2,
  Users,
  TrendingDown,
} from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
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

interface ScreeningStat {
  id: string;
  label: string;
  completed: number;
  not_completed: number;
  total: number;
  completion_pct: number;
}

interface MemberGap {
  phone_last4: string;
  gender: string;
  gap_count: number;
  gaps: string[];
  screened_at: string;
}

interface GapReport {
  total_members: number;
  screenings: ScreeningStat[];
  members_with_gaps: MemberGap[];
  summary: {
    completed_rate: number;
    avg_gaps_per_member: number;
    members_all_complete: number;
    members_with_gaps_count: number;
  };
}

function CompletionBar({ pct }: { pct: number }) {
  const color = pct >= 80 ? '#4CAF50' : pct >= 50 ? '#FF9800' : '#EF4444';
  return (
    <div className="flex items-center gap-2">
      <div className="h-2 flex-1 rounded-full bg-muted/50 overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, backgroundColor: color }}
        />
      </div>
      <span className="text-xs font-bold w-10 text-right" style={{ color }}>
        {pct}%
      </span>
    </div>
  );
}

export default function ScreeningGapsPage() {
  const [data, setData] = useState<GapReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    setLoading(true);
    api.get('/api/admin/screening-gap-report')
      .then((res) => {
        setData(res.data);
        setError('');
      })
      .catch((err) => {
        setError(err.response?.data?.detail || 'Failed to load screening data');
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

  if (!data || data.total_members === 0) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold tracking-tight">Screening Gap Report</h1>
        <div className="flex items-center justify-center py-20">
          <div className="text-center">
            <HeartPulse className="h-10 w-10 text-muted-foreground mx-auto mb-3" />
            <p className="text-sm text-muted-foreground">
              No screening data yet. Members will appear here after completing the health screening checklist.
            </p>
          </div>
        </div>
      </div>
    );
  }

  const { screenings, members_with_gaps, summary, total_members } = data;

  // Chart data — sorted by worst completion first
  const chartData = screenings.map((s) => ({
    name: s.label.length > 20 ? s.label.substring(0, 18) + '...' : s.label,
    completed: s.completion_pct,
    gap: 100 - s.completion_pct,
  }));

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Screening Gap Report</h1>
        <p className="text-sm text-muted-foreground">
          Preventive screening completion rates across all members — target gaps to improve Star Ratings
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
                <p className="text-2xl font-bold">{total_members}</p>
                <p className="text-xs text-muted-foreground">Members Screened</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-border/50 shadow-sm">
          <CardContent className="pt-5 pb-4">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-green-100">
                <CheckCircle2 className="h-5 w-5 text-green-600" />
              </div>
              <div>
                <p className="text-2xl font-bold">{summary.completed_rate}%</p>
                <p className="text-xs text-muted-foreground">All Screenings Complete</p>
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
                <p className="text-2xl font-bold">{summary.members_with_gaps_count}</p>
                <p className="text-xs text-muted-foreground">Members With Gaps</p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-border/50 shadow-sm">
          <CardContent className="pt-5 pb-4">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-red-100">
                <TrendingDown className="h-5 w-5 text-red-600" />
              </div>
              <div>
                <p className="text-2xl font-bold">{summary.avg_gaps_per_member}</p>
                <p className="text-xs text-muted-foreground">Avg Gaps Per Member</p>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Chart + Table Row */}
      <div className="grid grid-cols-2 gap-4">
        {/* Completion Rate Chart */}
        <Card className="border-border/50 shadow-sm">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold text-muted-foreground flex items-center gap-2">
              <HeartPulse className="h-4 w-4" /> Screening Completion Rates
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={Math.max(200, screenings.length * 40)}>
              <BarChart data={chartData} layout="vertical" margin={{ left: 10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#E4E2E8" horizontal={false} />
                <XAxis type="number" domain={[0, 100]} tick={{ fontSize: 11 }} stroke="#7A7585" />
                <YAxis dataKey="name" type="category" tick={{ fontSize: 11 }} stroke="#7A7585" width={130} />
                <Tooltip
                  formatter={(value: number) => `${value}%`}
                  contentStyle={{
                    borderRadius: '10px', border: '1px solid #E4E2E8',
                    boxShadow: '0 4px 12px rgba(123,63,191,0.08)',
                  }}
                />
                <Bar dataKey="completed" fill="#4CAF50" radius={[0, 6, 6, 0]} barSize={18} name="Completed" />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Per-Screening Stats Table */}
        <Card className="border-border/50 shadow-sm">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold text-muted-foreground">
              Per-Screening Breakdown
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs">Screening</TableHead>
                  <TableHead className="text-xs text-center">Yes</TableHead>
                  <TableHead className="text-xs text-center">No</TableHead>
                  <TableHead className="text-xs w-32">Rate</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {screenings.map((s) => (
                  <TableRow key={s.id}>
                    <TableCell className="text-xs font-medium">{s.label}</TableCell>
                    <TableCell className="text-xs text-center font-bold text-green-600">
                      {s.completed}
                    </TableCell>
                    <TableCell className="text-xs text-center font-bold text-orange-600">
                      {s.not_completed}
                    </TableCell>
                    <TableCell>
                      <CompletionBar pct={s.completion_pct} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      </div>

      {/* Members with gaps */}
      {members_with_gaps.length > 0 && (
        <Card className="border-border/50 shadow-sm">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-semibold text-muted-foreground flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 text-orange-500" />
              Members with Screening Gaps ({members_with_gaps.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="text-xs">Member</TableHead>
                  <TableHead className="text-xs">Gender</TableHead>
                  <TableHead className="text-xs text-center">Gaps</TableHead>
                  <TableHead className="text-xs">Missing Screenings</TableHead>
                  <TableHead className="text-xs">Screened</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {members_with_gaps.slice(0, 50).map((m, i) => (
                  <TableRow key={i}>
                    <TableCell className="text-xs font-medium">
                      ***-***-{m.phone_last4}
                    </TableCell>
                    <TableCell className="text-xs capitalize">{m.gender}</TableCell>
                    <TableCell className="text-center">
                      <Badge
                        variant={m.gap_count >= 3 ? 'destructive' : 'secondary'}
                        className="text-[10px]"
                      >
                        {m.gap_count}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1">
                        {m.gaps.map((g) => (
                          <Badge key={g} variant="outline" className="text-[10px]">
                            {g}
                          </Badge>
                        ))}
                      </div>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {m.screened_at ? new Date(m.screened_at).toLocaleDateString() : '—'}
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
