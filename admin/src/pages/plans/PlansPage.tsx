import { useState, useEffect, useCallback } from 'react';
import {
  Search, Filter, FileText, CheckCircle2, XCircle,
  ChevronLeft, ChevronRight, AlertCircle, RefreshCw,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import client from '@/api/client';
import { ENDPOINTS } from '@/config/api';

interface PlanEntry {
  plan_number: string;
  plan_name: string;
  carrier: string;
  plan_type: string;
  has_pdf: boolean;
  has_extraction: boolean;
  has_benefits: boolean;
}

interface PlansResponse {
  data: PlanEntry[];
  total: number;
  page: number;
  per_page: number;
}

function StatusDot({ ok }: { ok: boolean }) {
  return ok ? (
    <CheckCircle2 className="h-4 w-4 text-success" />
  ) : (
    <XCircle className="h-4 w-4 text-destructive/60" />
  );
}

export default function PlansPage() {
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [plans, setPlans] = useState<PlanEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const perPage = 50;

  const fetchPlans = useCallback(async (searchQuery: string, pageNum: number) => {
    setLoading(true);
    setError('');
    try {
      const res = await client.get<PlansResponse>(ENDPOINTS.PLANS, {
        params: { search: searchQuery, page: pageNum, per_page: perPage },
      });
      setPlans(res.data.data);
      setTotal(res.data.total);
    } catch {
      setError('Failed to load plans.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchPlans(search, page);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, fetchPlans]); // search triggers via debounced effect below, not on every keystroke

  // Debounced search: reset to page 1 when searching
  useEffect(() => {
    const timer = setTimeout(() => {
      setPage(1);
      fetchPlans(search, 1);
    }, 400);
    return () => clearTimeout(timer);
  }, [search, fetchPlans]);

  // Compute stats from total data
  const statsWithExtraction = plans.filter((p) => p.has_extraction).length;
  const statsWithBenefits = plans.filter((p) => p.has_benefits).length;
  const statsWithoutPdf = plans.filter((p) => !p.has_pdf).length;

  const totalPages = Math.ceil(total / perPage);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Plans</h1>
          <p className="text-sm text-muted-foreground">
            Browse all plans, extraction status, and benefits data
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          className="h-8 text-xs"
          onClick={() => fetchPlans(search, page)}
          disabled={loading}
        >
          <RefreshCw className={`mr-1.5 h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      {/* Quick Stats */}
      <div className="grid grid-cols-4 gap-4">
        <Card className="border-border/50 shadow-sm">
          <CardContent className="p-4 flex items-center gap-3">
            <div className="h-9 w-9 rounded-lg bg-primary/10 flex items-center justify-center">
              <FileText className="h-4 w-4 text-primary" />
            </div>
            <div>
              <p className="text-xl font-bold">{loading ? '...' : total.toLocaleString()}</p>
              <p className="text-[11px] text-muted-foreground">Total Plans</p>
            </div>
          </CardContent>
        </Card>
        <Card className="border-border/50 shadow-sm">
          <CardContent className="p-4 flex items-center gap-3">
            <div className="h-9 w-9 rounded-lg bg-success/10 flex items-center justify-center">
              <CheckCircle2 className="h-4 w-4 text-success" />
            </div>
            <div>
              <p className="text-xl font-bold">{loading ? '...' : statsWithExtraction.toLocaleString()}</p>
              <p className="text-[11px] text-muted-foreground">Extracted (this page)</p>
            </div>
          </CardContent>
        </Card>
        <Card className="border-border/50 shadow-sm">
          <CardContent className="p-4 flex items-center gap-3">
            <div className="h-9 w-9 rounded-lg bg-chart-2/10 flex items-center justify-center">
              <FileText className="h-4 w-4 text-chart-2" />
            </div>
            <div>
              <p className="text-xl font-bold">{loading ? '...' : statsWithBenefits.toLocaleString()}</p>
              <p className="text-[11px] text-muted-foreground">With Benefits (this page)</p>
            </div>
          </CardContent>
        </Card>
        <Card className="border-border/50 shadow-sm">
          <CardContent className="p-4 flex items-center gap-3">
            <div className="h-9 w-9 rounded-lg bg-warning/10 flex items-center justify-center">
              <AlertCircle className="h-4 w-4 text-warning" />
            </div>
            <div>
              <p className="text-xl font-bold">{loading ? '...' : statsWithoutPdf.toLocaleString()}</p>
              <p className="text-[11px] text-muted-foreground">Missing PDF (this page)</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Error */}
      {error && (
        <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
          <AlertCircle className="h-4 w-4 shrink-0" />
          <span>{error}</span>
          <Button variant="outline" size="sm" className="ml-auto h-7 text-xs" onClick={() => fetchPlans(search, page)}>
            Retry
          </Button>
        </div>
      )}

      {/* Table */}
      <Card className="border-border/50 shadow-sm">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base font-semibold">All Plans</CardTitle>
            <div className="flex items-center gap-2">
              <div className="relative w-64">
                <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                <Input
                  placeholder="Search plan name, number, carrier..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="h-8 pl-9 text-xs bg-muted/30"
                />
              </div>
              <Button variant="outline" size="sm" className="h-8 text-xs">
                <Filter className="mr-1.5 h-3.5 w-3.5" /> Filter
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                <TableHead className="text-[11px] font-semibold uppercase tracking-wider">Plan Number</TableHead>
                <TableHead className="text-[11px] font-semibold uppercase tracking-wider">Plan Name</TableHead>
                <TableHead className="text-[11px] font-semibold uppercase tracking-wider">Carrier</TableHead>
                <TableHead className="text-[11px] font-semibold uppercase tracking-wider">Type</TableHead>
                <TableHead className="text-[11px] font-semibold uppercase tracking-wider text-center">PDF</TableHead>
                <TableHead className="text-[11px] font-semibold uppercase tracking-wider text-center">Extracted</TableHead>
                <TableHead className="text-[11px] font-semibold uppercase tracking-wider text-center">Benefits</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading
                ? Array.from({ length: 8 }).map((_, i) => (
                    <TableRow key={i}>
                      <TableCell><Skeleton className="h-4 w-24" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-48" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-16" /></TableCell>
                      <TableCell><Skeleton className="h-4 w-12" /></TableCell>
                      <TableCell className="text-center"><Skeleton className="h-4 w-4 mx-auto" /></TableCell>
                      <TableCell className="text-center"><Skeleton className="h-4 w-4 mx-auto" /></TableCell>
                      <TableCell className="text-center"><Skeleton className="h-4 w-4 mx-auto" /></TableCell>
                    </TableRow>
                  ))
                : plans.map((p) => (
                    <TableRow key={p.plan_number} className="cursor-pointer hover:bg-accent/30 transition-colors">
                      <TableCell className="text-xs font-mono font-semibold text-primary">{p.plan_number}</TableCell>
                      <TableCell className="text-xs font-medium max-w-64 truncate">{p.plan_name}</TableCell>
                      <TableCell>
                        <Badge variant="secondary" className="text-[10px] font-semibold">{p.carrier}</Badge>
                      </TableCell>
                      <TableCell className="text-xs text-muted-foreground">{p.plan_type}</TableCell>
                      <TableCell className="text-center"><StatusDot ok={p.has_pdf} /></TableCell>
                      <TableCell className="text-center"><StatusDot ok={p.has_extraction} /></TableCell>
                      <TableCell className="text-center"><StatusDot ok={p.has_benefits} /></TableCell>
                    </TableRow>
                  ))
              }
              {!loading && plans.length === 0 && (
                <TableRow>
                  <TableCell colSpan={7} className="text-center py-8 text-sm text-muted-foreground">
                    {search ? `No plans matching "${search}"` : 'No plans found'}
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>

          <div className="flex items-center justify-between border-t border-border px-4 py-3">
            <p className="text-xs text-muted-foreground">
              Showing {plans.length} of {total.toLocaleString()} plans
            </p>
            <div className="flex items-center gap-1">
              <Button
                variant="outline"
                size="sm"
                className="h-7 w-7 p-0"
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
              {Array.from({ length: Math.min(totalPages, 5) }, (_, i) => {
                const pageNum = i + 1;
                return (
                  <Button
                    key={pageNum}
                    variant={page === pageNum ? 'default' : 'outline'}
                    size="sm"
                    className="h-7 min-w-7 p-0 text-xs"
                    onClick={() => setPage(pageNum)}
                  >
                    {pageNum}
                  </Button>
                );
              })}
              {totalPages > 5 && (
                <span className="text-xs text-muted-foreground px-1">...</span>
              )}
              <Button
                variant="outline"
                size="sm"
                className="h-7 w-7 p-0"
                disabled={page >= totalPages}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
