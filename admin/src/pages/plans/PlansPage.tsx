import { useState } from 'react';
import {
  Search, Filter, FileText, CheckCircle2, XCircle,
  ChevronLeft, ChevronRight, AlertCircle,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';

const MOCK_PLANS = [
  { plan_number: 'H0028-014', plan_name: 'Humana Gold Plus (HMO)', carrier: 'Humana', plan_type: 'HMO', has_pdf: true, has_extraction: true, has_benefits: true },
  { plan_number: 'H5521-028', plan_name: 'Aetna Medicare Premier (PPO)', carrier: 'Aetna', plan_type: 'PPO', has_pdf: true, has_extraction: true, has_benefits: true },
  { plan_number: 'H4590-012', plan_name: 'UHC AARP Medicare Advantage (HMO)', carrier: 'UHC', plan_type: 'HMO', has_pdf: true, has_extraction: true, has_benefits: false },
  { plan_number: 'H0174-010', plan_name: 'Wellcare Simple (HMO)', carrier: 'Wellcare', plan_type: 'HMO', has_pdf: true, has_extraction: false, has_benefits: false },
  { plan_number: 'H7040-003', plan_name: 'Devoted Health Access (HMO)', carrier: 'Devoted', plan_type: 'HMO', has_pdf: true, has_extraction: true, has_benefits: true },
  { plan_number: 'H1036-077', plan_name: 'Humana Honor (PPO)', carrier: 'Humana', plan_type: 'PPO', has_pdf: true, has_extraction: true, has_benefits: true },
  { plan_number: 'H0628-008', plan_name: 'Aetna Medicare Signature (HMO-POS)', carrier: 'Aetna', plan_type: 'HMO-POS', has_pdf: true, has_extraction: true, has_benefits: false },
  { plan_number: 'H0029-007', plan_name: 'Wellcare Dual Access (HMO-POS D-SNP)', carrier: 'Wellcare', plan_type: 'HMO-POS D-SNP', has_pdf: false, has_extraction: false, has_benefits: false },
];

function StatusDot({ ok }: { ok: boolean }) {
  return ok ? (
    <CheckCircle2 className="h-4 w-4 text-success" />
  ) : (
    <XCircle className="h-4 w-4 text-destructive/60" />
  );
}

export default function PlansPage() {
  const [search, setSearch] = useState('');

  const filtered = MOCK_PLANS.filter((p) => {
    const q = search.toLowerCase();
    return (
      p.plan_name.toLowerCase().includes(q) ||
      p.plan_number.toLowerCase().includes(q) ||
      p.carrier.toLowerCase().includes(q)
    );
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Plans</h1>
        <p className="text-sm text-muted-foreground">
          Browse all plans, extraction status, and benefits data
        </p>
      </div>

      {/* Quick Stats */}
      <div className="grid grid-cols-4 gap-4">
        <Card className="border-border/50 shadow-sm">
          <CardContent className="p-4 flex items-center gap-3">
            <div className="h-9 w-9 rounded-lg bg-primary/10 flex items-center justify-center">
              <FileText className="h-4 w-4 text-primary" />
            </div>
            <div>
              <p className="text-xl font-bold">3,840</p>
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
              <p className="text-xl font-bold">3,612</p>
              <p className="text-[11px] text-muted-foreground">Extracted</p>
            </div>
          </CardContent>
        </Card>
        <Card className="border-border/50 shadow-sm">
          <CardContent className="p-4 flex items-center gap-3">
            <div className="h-9 w-9 rounded-lg bg-chart-2/10 flex items-center justify-center">
              <FileText className="h-4 w-4 text-chart-2" />
            </div>
            <div>
              <p className="text-xl font-bold">2,800</p>
              <p className="text-[11px] text-muted-foreground">With Benefits</p>
            </div>
          </CardContent>
        </Card>
        <Card className="border-border/50 shadow-sm">
          <CardContent className="p-4 flex items-center gap-3">
            <div className="h-9 w-9 rounded-lg bg-warning/10 flex items-center justify-center">
              <AlertCircle className="h-4 w-4 text-warning" />
            </div>
            <div>
              <p className="text-xl font-bold">228</p>
              <p className="text-[11px] text-muted-foreground">Missing PDF</p>
            </div>
          </CardContent>
        </Card>
      </div>

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
              {filtered.map((p) => (
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
              ))}
            </TableBody>
          </Table>

          <div className="flex items-center justify-between border-t border-border px-4 py-3">
            <p className="text-xs text-muted-foreground">
              Showing {filtered.length} of 3,840 plans
            </p>
            <div className="flex items-center gap-1">
              <Button variant="outline" size="sm" className="h-7 w-7 p-0">
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <Button variant="default" size="sm" className="h-7 min-w-7 p-0 text-xs">1</Button>
              <Button variant="outline" size="sm" className="h-7 min-w-7 p-0 text-xs">2</Button>
              <Button variant="outline" size="sm" className="h-7 min-w-7 p-0 text-xs">3</Button>
              <Button variant="outline" size="sm" className="h-7 w-7 p-0">
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
