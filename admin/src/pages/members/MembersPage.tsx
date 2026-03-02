import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Search, Filter, MoreHorizontal, Phone, MapPin,
  ChevronLeft, ChevronRight, Eye, Pencil, Shield,
  KeyRound, Pill, Send, FileText, Check, ChevronsUpDown,
  UserPlus, Hash,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
  DropdownMenuSeparator,
} from '@/components/ui/dropdown-menu';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';

// ── Types ──
interface MockMember {
  id: string;
  first_name: string;
  last_name: string;
  phone: string;
  plan_name: string;
  plan_number: string;
  carrier: string;
  agent: string;
  zip_code: string;
  last_login: string;
  status: 'active' | 'inactive';
  reminders: number;
}

// Mock data — will be replaced with TanStack Query hooks
const MOCK_MEMBERS: MockMember[] = [
  { id: '1', first_name: 'Maria', last_name: 'Garcia', phone: '(305) 555-0142', plan_name: 'Humana Gold Plus (HMO)', plan_number: 'H0028-014', carrier: 'Humana', agent: 'John Smith', zip_code: '33142', last_login: '2h ago', status: 'active', reminders: 3 },
  { id: '2', first_name: 'James', last_name: 'Wilson', phone: '(713) 555-0198', plan_name: 'Aetna Medicare Premier (PPO)', plan_number: 'H5521-028', carrier: 'Aetna', agent: 'Sarah Lee', zip_code: '77001', last_login: '1d ago', status: 'active', reminders: 1 },
  { id: '3', first_name: 'Dorothy', last_name: 'Thompson', phone: '(212) 555-0167', plan_name: 'UHC AARP Medicare Advantage (HMO)', plan_number: 'H4590-012', carrier: 'UHC', agent: 'Mike Brown', zip_code: '10001', last_login: '3d ago', status: 'active', reminders: 0 },
  { id: '4', first_name: 'Robert', last_name: 'Johnson', phone: '(404) 555-0134', plan_name: 'Wellcare Simple (HMO)', plan_number: 'H0174-010', carrier: 'Wellcare', agent: 'John Smith', zip_code: '30301', last_login: '5d ago', status: 'active', reminders: 2 },
  { id: '5', first_name: 'Helen', last_name: 'Davis', phone: '(561) 555-0156', plan_name: 'Devoted Health Access (HMO)', plan_number: 'H7040-003', carrier: 'Devoted', agent: 'Lisa Chen', zip_code: '33401', last_login: '12h ago', status: 'active', reminders: 4 },
  { id: '6', first_name: 'William', last_name: 'Martinez', phone: '(786) 555-0178', plan_name: '', plan_number: '', carrier: '', agent: 'Sarah Lee', zip_code: '33101', last_login: '1w ago', status: 'inactive', reminders: 0 },
  { id: '7', first_name: 'Patricia', last_name: 'Anderson', phone: '(813) 555-0189', plan_name: 'Aetna Medicare Signature (HMO-POS)', plan_number: 'H0628-008', carrier: 'Aetna', agent: 'John Smith', zip_code: '33601', last_login: '6h ago', status: 'active', reminders: 1 },
  { id: '8', first_name: 'Charles', last_name: 'Taylor', phone: '(954) 555-0145', plan_name: 'Wellcare Dual Access (HMO-POS D-SNP)', plan_number: 'H0029-007', carrier: 'Wellcare', agent: 'Mike Brown', zip_code: '33301', last_login: '2d ago', status: 'active', reminders: 2 },
];

const CARRIERS = ['Humana', 'Aetna', 'UHC', 'Wellcare', 'Devoted', 'Cigna', 'Blue Cross', 'Other'];

function getInitials(first: string, last: string) {
  return `${first[0]}${last[0]}`.toUpperCase();
}

const CARRIER_COLORS: Record<string, string> = {
  Humana: 'bg-chart-1/10 text-chart-1',
  Aetna: 'bg-chart-2/10 text-chart-2',
  UHC: 'bg-chart-3/10 text-chart-3',
  Wellcare: 'bg-chart-4/10 text-chart-4',
  Devoted: 'bg-chart-5/10 text-chart-5',
  Cigna: 'bg-primary/10 text-primary',
  'Blue Cross': 'bg-blue-500/10 text-blue-600',
  Other: 'bg-muted text-muted-foreground',
};

export default function MembersPage() {
  const [search, setSearch] = useState('');
  const navigate = useNavigate();

  // Plan assignment dialog state
  const [assignOpen, setAssignOpen] = useState(false);
  const [assignMember, setAssignMember] = useState<MockMember | null>(null);
  const [assignCarrier, setAssignCarrier] = useState('');
  const [assignPlanName, setAssignPlanName] = useState('');
  const [assignPlanNumber, setAssignPlanNumber] = useState('');
  const [assignSaving, setAssignSaving] = useState(false);

  // Create member dialog state
  const [createOpen, setCreateOpen] = useState(false);
  const [newFirstName, setNewFirstName] = useState('');
  const [newLastName, setNewLastName] = useState('');
  const [newPhone, setNewPhone] = useState('');
  const [newMedicareNumber, setNewMedicareNumber] = useState('');
  const [newZipCode, setNewZipCode] = useState('');
  const [newCarrier, setNewCarrier] = useState('');
  const [newPlanName, setNewPlanName] = useState('');
  const [newPlanNumber, setNewPlanNumber] = useState('');
  const [createSaving, setCreateSaving] = useState(false);
  const [createSuccess, setCreateSuccess] = useState(false);
  const [otpSentTo, setOtpSentTo] = useState('');

  const filtered = MOCK_MEMBERS.filter((m) => {
    const q = search.toLowerCase();
    return (
      m.first_name.toLowerCase().includes(q) ||
      m.last_name.toLowerCase().includes(q) ||
      m.phone.includes(q) ||
      m.plan_number.toLowerCase().includes(q) ||
      m.plan_name.toLowerCase().includes(q) ||
      m.carrier.toLowerCase().includes(q)
    );
  });

  function openAssignPlan(member: MockMember) {
    setAssignMember(member);
    setAssignCarrier(member.carrier || '');
    setAssignPlanName(member.plan_name || '');
    setAssignPlanNumber(member.plan_number || '');
    setAssignOpen(true);
  }

  function handleAssignSave() {
    setAssignSaving(true);
    // TODO: call PUT /api/admin/members/:phone/plan
    setTimeout(() => {
      setAssignSaving(false);
      setAssignOpen(false);
    }, 800);
  }

  function handleCreateMember() {
    setCreateSaving(true);
    // TODO: call POST /api/admin/members/create with body
    // In production: client.post(ENDPOINTS.MEMBER_CREATE, { ... })
    const phone = newPhone;
    setTimeout(() => {
      setCreateSaving(false);
      setCreateSuccess(true);
      setOtpSentTo(phone);
    }, 1200);
  }

  function closeCreateDialog() {
    setCreateOpen(false);
    setCreateSuccess(false);
    setOtpSentTo('');
    resetCreateForm();
  }

  function resetCreateForm() {
    setNewFirstName('');
    setNewLastName('');
    setNewPhone('');
    setNewMedicareNumber('');
    setNewZipCode('');
    setNewCarrier('');
    setNewPlanName('');
    setNewPlanNumber('');
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Members</h1>
          <p className="text-sm text-muted-foreground">
            Manage member accounts, plans, and services
          </p>
        </div>
        <Button onClick={() => setCreateOpen(true)} className="text-xs">
          <UserPlus className="mr-1.5 h-3.5 w-3.5" /> New Member
        </Button>
      </div>

      {/* Quick Stats */}
      <div className="grid grid-cols-4 gap-4">
        <Card className="border-border/50 shadow-sm">
          <CardContent className="p-4 flex items-center gap-3">
            <div className="h-9 w-9 rounded-lg bg-primary/10 flex items-center justify-center">
              <Shield className="h-4 w-4 text-primary" />
            </div>
            <div>
              <p className="text-xl font-bold">1,834</p>
              <p className="text-[11px] text-muted-foreground">Total Members</p>
            </div>
          </CardContent>
        </Card>
        <Card className="border-border/50 shadow-sm">
          <CardContent className="p-4 flex items-center gap-3">
            <div className="h-9 w-9 rounded-lg bg-success/10 flex items-center justify-center">
              <Phone className="h-4 w-4 text-success" />
            </div>
            <div>
              <p className="text-xl font-bold">1,692</p>
              <p className="text-[11px] text-muted-foreground">Active</p>
            </div>
          </CardContent>
        </Card>
        <Card className="border-border/50 shadow-sm">
          <CardContent className="p-4 flex items-center gap-3">
            <div className="h-9 w-9 rounded-lg bg-warning/10 flex items-center justify-center">
              <MapPin className="h-4 w-4 text-warning" />
            </div>
            <div>
              <p className="text-xl font-bold">38</p>
              <p className="text-[11px] text-muted-foreground">States</p>
            </div>
          </CardContent>
        </Card>
        <Card className="border-border/50 shadow-sm">
          <CardContent className="p-4 flex items-center gap-3">
            <div className="h-9 w-9 rounded-lg bg-chart-2/10 flex items-center justify-center">
              <Pill className="h-4 w-4 text-chart-2" />
            </div>
            <div>
              <p className="text-xl font-bold">892</p>
              <p className="text-[11px] text-muted-foreground">Med Reminders</p>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Table Card */}
      <Card className="border-border/50 shadow-sm">
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base font-semibold">All Members</CardTitle>
            <div className="flex items-center gap-2">
              <div className="relative w-64">
                <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
                <Input
                  placeholder="Search name, phone, plan, carrier..."
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
                <TableHead className="text-[11px] font-semibold uppercase tracking-wider">Member</TableHead>
                <TableHead className="text-[11px] font-semibold uppercase tracking-wider">Phone</TableHead>
                <TableHead className="text-[11px] font-semibold uppercase tracking-wider">Plan</TableHead>
                <TableHead className="text-[11px] font-semibold uppercase tracking-wider">Carrier</TableHead>
                <TableHead className="text-[11px] font-semibold uppercase tracking-wider">Agent</TableHead>
                <TableHead className="text-[11px] font-semibold uppercase tracking-wider text-center">Reminders</TableHead>
                <TableHead className="text-[11px] font-semibold uppercase tracking-wider">Last Login</TableHead>
                <TableHead className="text-[11px] font-semibold uppercase tracking-wider">Status</TableHead>
                <TableHead className="w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((m) => (
                <TableRow
                  key={m.id}
                  className="cursor-pointer hover:bg-accent/30 transition-colors"
                  onClick={() => navigate(`/admin/members/${m.id}`)}
                >
                  <TableCell>
                    <div className="flex items-center gap-3">
                      <Avatar className="h-8 w-8">
                        <AvatarFallback className="bg-primary/10 text-[11px] font-bold text-primary">
                          {getInitials(m.first_name, m.last_name)}
                        </AvatarFallback>
                      </Avatar>
                      <div>
                        <p className="text-sm font-semibold">{m.first_name} {m.last_name}</p>
                        <p className="text-[11px] text-muted-foreground">{m.zip_code}</p>
                      </div>
                    </div>
                  </TableCell>
                  <TableCell className="text-xs font-mono font-medium">{m.phone}</TableCell>
                  <TableCell>
                    {m.plan_number ? (
                      <div>
                        <p className="text-xs font-medium truncate max-w-48">{m.plan_name}</p>
                        <p className="text-[10px] text-muted-foreground font-mono">{m.plan_number}</p>
                      </div>
                    ) : (
                      <Badge variant="secondary" className="text-[10px] bg-warning/10 text-warning font-medium">
                        No Plan Assigned
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell>
                    {m.carrier ? (
                      <Badge variant="secondary" className={`text-[10px] font-semibold ${CARRIER_COLORS[m.carrier] || CARRIER_COLORS.Other}`}>
                        {m.carrier}
                      </Badge>
                    ) : (
                      <span className="text-xs text-muted-foreground">—</span>
                    )}
                  </TableCell>
                  <TableCell className="text-xs">{m.agent}</TableCell>
                  <TableCell className="text-center">
                    {m.reminders > 0 ? (
                      <Badge variant="secondary" className="text-[10px] font-semibold bg-chart-2/10 text-chart-2">
                        <Pill className="mr-1 h-3 w-3" /> {m.reminders}
                      </Badge>
                    ) : (
                      <span className="text-xs text-muted-foreground">—</span>
                    )}
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">{m.last_login}</TableCell>
                  <TableCell>
                    <Badge
                      variant={m.status === 'active' ? 'default' : 'secondary'}
                      className={`text-[10px] ${
                        m.status === 'active'
                          ? 'bg-success/10 text-success hover:bg-success/20'
                          : 'bg-muted text-muted-foreground'
                      }`}
                    >
                      {m.status}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild onClick={(e) => e.stopPropagation()}>
                        <Button variant="ghost" size="sm" className="h-7 w-7 p-0">
                          <MoreHorizontal className="h-4 w-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem className="text-xs" onClick={(e) => { e.stopPropagation(); navigate(`/admin/members/${m.id}`); }}>
                          <Eye className="mr-2 h-3.5 w-3.5" /> View Details
                        </DropdownMenuItem>
                        <DropdownMenuItem className="text-xs" onClick={(e) => { e.stopPropagation(); navigate(`/admin/members/${m.id}`); }}>
                          <Pencil className="mr-2 h-3.5 w-3.5" /> Edit Member
                        </DropdownMenuItem>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem className="text-xs text-primary font-semibold" onClick={(e) => { e.stopPropagation(); openAssignPlan(m); }}>
                          <FileText className="mr-2 h-3.5 w-3.5" /> Assign Plan
                        </DropdownMenuItem>
                        <DropdownMenuItem className="text-xs text-primary font-medium" onClick={(e) => e.stopPropagation()}>
                          <KeyRound className="mr-2 h-3.5 w-3.5" /> Send OTP Login
                        </DropdownMenuItem>
                        <DropdownMenuItem className="text-xs" onClick={(e) => e.stopPropagation()}>
                          <Pill className="mr-2 h-3.5 w-3.5" /> Manage Reminders
                        </DropdownMenuItem>
                        <DropdownMenuSeparator />
                        <DropdownMenuItem className="text-xs" onClick={(e) => e.stopPropagation()}>
                          <Phone className="mr-2 h-3.5 w-3.5" /> Call Member
                        </DropdownMenuItem>
                        <DropdownMenuItem className="text-xs" onClick={(e) => e.stopPropagation()}>
                          <Send className="mr-2 h-3.5 w-3.5" /> Send SMS
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>

          {/* Pagination */}
          <div className="flex items-center justify-between border-t border-border px-4 py-3">
            <p className="text-xs text-muted-foreground">
              Showing {filtered.length} of 1,834 members
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

      {/* ── Assign Plan Dialog ── */}
      <Dialog open={assignOpen} onOpenChange={setAssignOpen}>
        <DialogContent className="sm:max-w-[480px]">
          <DialogHeader>
            <DialogTitle className="text-lg font-bold">Assign Plan</DialogTitle>
            <DialogDescription className="text-sm">
              {assignMember
                ? `Assign a carrier and plan to ${assignMember.first_name} ${assignMember.last_name}. The plan number links the member's app to their SOB & benefits data.`
                : 'Select plan details for this member.'}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-2">
            {/* Carrier */}
            <div className="space-y-2">
              <Label htmlFor="carrier" className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Carrier
              </Label>
              <Select value={assignCarrier} onValueChange={setAssignCarrier}>
                <SelectTrigger className="h-9">
                  <SelectValue placeholder="Select carrier..." />
                </SelectTrigger>
                <SelectContent>
                  {CARRIERS.map((c) => (
                    <SelectItem key={c} value={c}>
                      <div className="flex items-center gap-2">
                        <div className={`h-2 w-2 rounded-full ${
                          c === 'Humana' ? 'bg-chart-1' :
                          c === 'Aetna' ? 'bg-chart-2' :
                          c === 'UHC' ? 'bg-chart-3' :
                          c === 'Wellcare' ? 'bg-chart-4' :
                          c === 'Devoted' ? 'bg-chart-5' :
                          'bg-muted-foreground'
                        }`} />
                        {c}
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Plan Name */}
            <div className="space-y-2">
              <Label htmlFor="plan-name" className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Plan Name
              </Label>
              <Input
                id="plan-name"
                value={assignPlanName}
                onChange={(e) => setAssignPlanName(e.target.value)}
                placeholder="e.g. Humana Gold Plus (HMO)"
                className="h-9"
              />
            </div>

            {/* Plan Number — THE KEY FIELD */}
            <div className="space-y-2">
              <Label htmlFor="plan-number" className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Plan Number
              </Label>
              <Input
                id="plan-number"
                value={assignPlanNumber}
                onChange={(e) => setAssignPlanNumber(e.target.value)}
                placeholder="e.g. H0028-014"
                className="h-9 font-mono"
              />
              <p className="text-[11px] text-muted-foreground">
                This links the member's app to SOB extraction &amp; benefits data.
              </p>
            </div>

            {/* Plan number linkage indicator */}
            {assignPlanNumber && (
              <div className="rounded-lg border border-border bg-muted/30 p-3">
                <div className="flex items-start gap-2">
                  <div className="mt-0.5 h-5 w-5 rounded-full bg-primary/10 flex items-center justify-center shrink-0">
                    <Check className="h-3 w-3 text-primary" />
                  </div>
                  <div>
                    <p className="text-xs font-semibold">Plan Linkage Preview</p>
                    <p className="text-[11px] text-muted-foreground mt-0.5">
                      <span className="font-mono font-medium text-foreground">{assignPlanNumber}</span> will connect{' '}
                      {assignMember?.first_name}'s app to the extracted benefits, formulary, and provider directory.
                    </p>
                  </div>
                </div>
              </div>
            )}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setAssignOpen(false)} className="text-xs">
              Cancel
            </Button>
            <Button
              onClick={handleAssignSave}
              disabled={!assignCarrier || !assignPlanNumber || assignSaving}
              className="text-xs"
            >
              {assignSaving ? (
                <>
                  <div className="mr-2 h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" />
                  Saving...
                </>
              ) : (
                <>
                  <Check className="mr-1.5 h-3.5 w-3.5" /> Assign Plan
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Create Member Dialog ── */}
      <Dialog open={createOpen} onOpenChange={(open) => { if (!open) closeCreateDialog(); else setCreateOpen(true); }}>
        <DialogContent className="sm:max-w-[560px]">
          {!createSuccess ? (
            <>
              <DialogHeader>
                <DialogTitle className="text-lg font-bold">Create New Member</DialogTitle>
                <DialogDescription className="text-sm">
                  Register a new client account. A verification code will be sent to their phone so they can log in.
                </DialogDescription>
              </DialogHeader>

              <div className="space-y-4 py-2">
                {/* Name row */}
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-2">
                    <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                      First Name
                    </Label>
                    <Input value={newFirstName} onChange={(e) => setNewFirstName(e.target.value)} placeholder="Maria" className="h-9" />
                  </div>
                  <div className="space-y-2">
                    <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                      Last Name
                    </Label>
                    <Input value={newLastName} onChange={(e) => setNewLastName(e.target.value)} placeholder="Garcia" className="h-9" />
                  </div>
                </div>

                {/* Phone + Zip */}
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-2">
                    <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Phone Number</Label>
                    <Input value={newPhone} onChange={(e) => setNewPhone(e.target.value)} placeholder="(305) 555-0142" className="h-9 font-mono" />
                    <p className="text-[11px] text-muted-foreground">Used for OTP login &amp; verification</p>
                  </div>
                  <div className="space-y-2">
                    <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Zip Code</Label>
                    <Input value={newZipCode} onChange={(e) => setNewZipCode(e.target.value)} placeholder="33142" className="h-9 font-mono" maxLength={5} />
                  </div>
                </div>

                {/* Medicare Number */}
                <div className="space-y-2">
                  <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                    <Hash className="inline h-3 w-3 mr-1" />
                    Medicare Beneficiary Identifier (MBI)
                  </Label>
                  <Input value={newMedicareNumber} onChange={(e) => setNewMedicareNumber(e.target.value.toUpperCase())} placeholder="1EG4-TE5-MK73" className="h-9 font-mono tracking-wide" maxLength={15} />
                  <p className="text-[11px] text-muted-foreground">11-character Medicare number. Stored encrypted.</p>
                </div>

                {/* Separator */}
                <div className="relative">
                  <div className="absolute inset-0 flex items-center"><span className="w-full border-t border-border" /></div>
                  <div className="relative flex justify-center">
                    <span className="bg-background px-3 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                      Plan Assignment (optional)
                    </span>
                  </div>
                </div>

                {/* Carrier + Plan */}
                <div className="grid grid-cols-3 gap-3">
                  <div className="space-y-2">
                    <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Carrier</Label>
                    <Select value={newCarrier} onValueChange={setNewCarrier}>
                      <SelectTrigger className="h-9"><SelectValue placeholder="Select..." /></SelectTrigger>
                      <SelectContent>
                        {CARRIERS.map((c) => (<SelectItem key={c} value={c}>{c}</SelectItem>))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Plan Name</Label>
                    <Input value={newPlanName} onChange={(e) => setNewPlanName(e.target.value)} placeholder="Gold Plus (HMO)" className="h-9" />
                  </div>
                  <div className="space-y-2">
                    <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Plan Number</Label>
                    <Input value={newPlanNumber} onChange={(e) => setNewPlanNumber(e.target.value)} placeholder="H0028-014" className="h-9 font-mono" />
                  </div>
                </div>

                {newPlanNumber && (
                  <div className="rounded-lg border border-border bg-muted/30 p-3">
                    <div className="flex items-start gap-2">
                      <Check className="mt-0.5 h-4 w-4 text-primary shrink-0" />
                      <p className="text-[11px] text-muted-foreground">
                        <span className="font-mono font-semibold text-foreground">{newPlanNumber}</span> will link this member's app to SOB extraction &amp; benefits data.
                      </p>
                    </div>
                  </div>
                )}
              </div>

              <DialogFooter>
                <Button variant="outline" onClick={closeCreateDialog} className="text-xs">Cancel</Button>
                <Button onClick={handleCreateMember} disabled={!newFirstName || !newLastName || !newPhone || !newMedicareNumber || createSaving} className="text-xs">
                  {createSaving ? (
                    <><div className="mr-2 h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" /> Creating &amp; Sending Code...</>
                  ) : (
                    <><UserPlus className="mr-1.5 h-3.5 w-3.5" /> Create &amp; Send Verification</>
                  )}
                </Button>
              </DialogFooter>
            </>
          ) : (
            /* ── Success State ── */
            <>
              <div className="py-6 text-center">
                <div className="mx-auto mb-4 h-14 w-14 rounded-full bg-success/10 flex items-center justify-center">
                  <Check className="h-7 w-7 text-success" />
                </div>
                <h3 className="text-lg font-bold">Member Created!</h3>
                <p className="text-sm text-muted-foreground mt-1">
                  {newFirstName} {newLastName}'s account is ready.
                </p>

                <div className="mt-4 rounded-lg border border-success/20 bg-success/5 p-4">
                  <div className="flex items-center justify-center gap-2 mb-2">
                    <Phone className="h-4 w-4 text-success" />
                    <span className="text-sm font-semibold text-success">Verification Code Sent</span>
                  </div>
                  <p className="text-sm font-mono font-bold">{otpSentTo}</p>
                  <p className="text-[11px] text-muted-foreground mt-1">
                    The member has 5 minutes to enter the code in the app to complete sign-up.
                  </p>
                </div>

                {newPlanNumber && (
                  <div className="mt-3 rounded-lg border border-border bg-muted/30 p-3 text-left">
                    <p className="text-[11px] text-muted-foreground">
                      <span className="font-semibold text-foreground">Plan linked:</span>{' '}
                      {newCarrier && <><Badge variant="secondary" className="text-[9px] mr-1">{newCarrier}</Badge></>}
                      <span className="font-mono">{newPlanNumber}</span>
                    </p>
                  </div>
                )}

                <div className="mt-4 flex items-center justify-center gap-2">
                  <Button variant="outline" size="sm" className="text-xs" onClick={closeCreateDialog}>
                    Done
                  </Button>
                  <Button size="sm" className="text-xs" onClick={() => { closeCreateDialog(); setCreateOpen(true); }}>
                    <UserPlus className="mr-1.5 h-3 w-3" /> Create Another
                  </Button>
                </div>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
