import {
  Server, HardDrive, Wifi, Clock, AlertTriangle,
  CheckCircle2, Zap,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';

const MOCK_HEALTH = {
  status: 'healthy' as const,
  uptime: '14d 7h 32m',
  total_requests: 128432,
  error_count: 47,
  avg_latency_ms: 142,
  active_sessions: 34,
  disk_usage_gb: 27.4,
  disk_total_gb: 40,
  api_version: '1.2.0',
  last_deploy: '2 days ago',
};

const SERVICES = [
  { name: 'FastAPI Backend', status: 'healthy', latency: '42ms' },
  { name: 'Zoho CRM Sync', status: 'healthy', latency: '380ms' },
  { name: 'Claude API (Extraction)', status: 'healthy', latency: '2.1s' },
  { name: 'SQLite Database', status: 'healthy', latency: '3ms' },
  { name: 'PDF Storage (Render)', status: 'healthy', latency: '18ms' },
];

const RECENT_ERRORS = [
  { time: '2h ago', endpoint: 'POST /api/v1/chat', error: 'Claude API rate limit', status: 429 },
  { time: '5h ago', endpoint: 'GET /api/v1/plan/benefits', error: 'Plan not found: H9999-001', status: 404 },
  { time: '1d ago', endpoint: 'POST /api/v1/login', error: 'Zoho CRM timeout', status: 504 },
];

function StatusBadge({ status }: { status: string }) {
  const colors = {
    healthy: 'bg-success/10 text-success',
    degraded: 'bg-warning/10 text-warning',
    down: 'bg-destructive/10 text-destructive',
  };
  return (
    <Badge variant="secondary" className={`text-[10px] font-semibold ${colors[status as keyof typeof colors] || ''}`}>
      <CheckCircle2 className="mr-1 h-3 w-3" />
      {status}
    </Badge>
  );
}

export default function SystemPage() {
  const h = MOCK_HEALTH;
  const diskPct = Math.round((h.disk_usage_gb / h.disk_total_gb) * 100);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">System Health</h1>
        <p className="text-sm text-muted-foreground">
          Monitor API performance, services, and infrastructure
        </p>
      </div>

      {/* Status Banner */}
      <Card className="border-success/30 bg-success/5 shadow-sm">
        <CardContent className="flex items-center gap-4 p-4">
          <CheckCircle2 className="h-6 w-6 text-success" />
          <div>
            <p className="text-sm font-semibold text-success">All Systems Operational</p>
            <p className="text-xs text-muted-foreground">Uptime: {h.uptime} &bull; Last deploy: {h.last_deploy}</p>
          </div>
        </CardContent>
      </Card>

      {/* Metric Cards */}
      <div className="grid grid-cols-4 gap-4">
        <Card className="border-border/50 shadow-sm">
          <CardContent className="p-4 flex items-center gap-3">
            <div className="h-9 w-9 rounded-lg bg-primary/10 flex items-center justify-center">
              <Zap className="h-4 w-4 text-primary" />
            </div>
            <div>
              <p className="text-xl font-bold">{h.total_requests.toLocaleString()}</p>
              <p className="text-[11px] text-muted-foreground">Total Requests</p>
            </div>
          </CardContent>
        </Card>
        <Card className="border-border/50 shadow-sm">
          <CardContent className="p-4 flex items-center gap-3">
            <div className="h-9 w-9 rounded-lg bg-chart-2/10 flex items-center justify-center">
              <Clock className="h-4 w-4 text-chart-2" />
            </div>
            <div>
              <p className="text-xl font-bold">{h.avg_latency_ms}ms</p>
              <p className="text-[11px] text-muted-foreground">Avg Latency</p>
            </div>
          </CardContent>
        </Card>
        <Card className="border-border/50 shadow-sm">
          <CardContent className="p-4 flex items-center gap-3">
            <div className="h-9 w-9 rounded-lg bg-chart-3/10 flex items-center justify-center">
              <Wifi className="h-4 w-4 text-chart-3" />
            </div>
            <div>
              <p className="text-xl font-bold">{h.active_sessions}</p>
              <p className="text-[11px] text-muted-foreground">Active Sessions</p>
            </div>
          </CardContent>
        </Card>
        <Card className="border-border/50 shadow-sm">
          <CardContent className="p-4 flex items-center gap-3">
            <div className="h-9 w-9 rounded-lg bg-destructive/10 flex items-center justify-center">
              <AlertTriangle className="h-4 w-4 text-destructive" />
            </div>
            <div>
              <p className="text-xl font-bold">{h.error_count}</p>
              <p className="text-[11px] text-muted-foreground">Errors (24h)</p>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-2 gap-4">
        {/* Services */}
        <Card className="border-border/50 shadow-sm">
          <CardHeader className="pb-3">
            <CardTitle className="text-base font-semibold flex items-center gap-2">
              <Server className="h-4 w-4 text-muted-foreground" /> Services
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {SERVICES.map((s) => (
              <div key={s.name} className="flex items-center justify-between rounded-lg border border-border/50 p-3">
                <div className="flex items-center gap-3">
                  <div className="h-2 w-2 rounded-full bg-success" />
                  <span className="text-sm font-medium">{s.name}</span>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-muted-foreground font-mono">{s.latency}</span>
                  <StatusBadge status={s.status} />
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        {/* Disk + Recent Errors */}
        <div className="space-y-4">
          {/* Disk Usage */}
          <Card className="border-border/50 shadow-sm">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-semibold flex items-center gap-2">
                <HardDrive className="h-4 w-4 text-muted-foreground" /> Storage
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium">Persistent Disk</span>
                <span className="text-xs text-muted-foreground font-mono">
                  {h.disk_usage_gb} / {h.disk_total_gb} GB
                </span>
              </div>
              <Progress value={diskPct} className="h-2.5" />
              <p className="text-xs text-muted-foreground">{diskPct}% used</p>
            </CardContent>
          </Card>

          {/* Recent Errors */}
          <Card className="border-border/50 shadow-sm">
            <CardHeader className="pb-3">
              <CardTitle className="text-base font-semibold flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 text-muted-foreground" /> Recent Errors
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {RECENT_ERRORS.map((e, i) => (
                <div key={i} className="flex items-start gap-3 rounded-lg border border-border/50 p-3">
                  <Badge variant="secondary" className="text-[10px] font-mono bg-destructive/10 text-destructive">
                    {e.status}
                  </Badge>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-medium truncate">{e.endpoint}</p>
                    <p className="text-[11px] text-muted-foreground">{e.error}</p>
                  </div>
                  <span className="text-[10px] text-muted-foreground whitespace-nowrap">{e.time}</span>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
