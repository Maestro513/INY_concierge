import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft, Phone, MapPin, Mail, Calendar, Shield,
  KeyRound, Pill, Send, FileText, Check,
  Plus, Trash2, Activity, Eye,
  ClipboardCheck, Heart, Car, UtensilsCrossed, Users, Home,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Separator } from '@/components/ui/separator';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import client from '@/api/client';
import { ENDPOINTS } from '@/config/api';
import { Skeleton } from '@/components/ui/skeleton';

// ── Default screening questions (same as mobile app) ──────────────
const DEFAULT_SHARED_SCREENINGS = [
  { id: 'awv', label: 'Annual Wellness Visit', timeframe: 'in the past year' },
  { id: 'flu', label: 'Flu Shot', timeframe: 'this season' },
  { id: 'colonoscopy', label: 'Colonoscopy', timeframe: 'in the past 5 years' },
  { id: 'cholesterol', label: 'Cholesterol / Blood Work', timeframe: 'in the past year' },
  { id: 'a1c', label: 'Diabetes Screening (A1C)', timeframe: 'in the past year' },
  { id: 'fall_risk', label: 'Fall Risk Assessment', timeframe: 'in the past year' },
];
const DEFAULT_MALE_SCREENINGS = [
  { id: 'prostate', label: 'Prostate (PSA) Screening', timeframe: 'in the past year' },
];
const DEFAULT_FEMALE_SCREENINGS = [
  { id: 'mammogram', label: 'Mammogram', timeframe: 'in the past 1-2 years' },
  { id: 'bone_density', label: 'Bone Density Scan (DEXA)', timeframe: 'in the past 2 years' },
];

const SDOH_QUESTIONS = [
  {
    id: 'transportation',
    icon: Car,
    question: 'In the past 12 months, has lack of reliable transportation kept them from medical appointments?',
    type: 'yesno' as const,
    flagLabel: 'Transportation',
  },
  {
    id: 'food_insecurity',
    icon: UtensilsCrossed,
    question: 'Within the past 12 months, have they worried that food would run out before getting money to buy more?',
    type: 'yesno' as const,
    flagLabel: 'Food Access',
  },
  {
    id: 'social_isolation',
    icon: Users,
    question: 'How often do they feel lonely or isolated from those around them?',
    type: 'scale' as const,
    options: ['never', 'rarely', 'sometimes', 'often', 'always'],
    flagLabel: 'Social Connection',
  },
  {
    id: 'housing_stability',
    icon: Home,
    question: 'Are they worried about losing their housing, or is their current housing situation unsafe?',
    type: 'yesno' as const,
    flagLabel: 'Housing',
  },
];

const CARRIERS = ['Humana', 'Aetna', 'UHC', 'Wellcare', 'Devoted', 'Cigna', 'Blue Cross', 'Other'];

const CARRIER_COLORS: Record<string, string> = {
  Humana: 'bg-chart-1/10 text-chart-1',
  Aetna: 'bg-chart-2/10 text-chart-2',
  UHC: 'bg-chart-3/10 text-chart-3',
  Wellcare: 'bg-chart-4/10 text-chart-4',
  Devoted: 'bg-chart-5/10 text-chart-5',
  Other: 'bg-muted text-muted-foreground',
};

const ACTIVITY_ICONS: Record<string, typeof Activity> = {
  login: KeyRound,
  search: Eye,
  benefits: FileText,
  reminder: Pill,
};

interface MemberDetail {
  id: string;
  first_name: string;
  last_name: string;
  phone: string;
  email: string;
  zip_code: string;
  dob: string;
  address: string;
  carrier: string;
  plan_name: string;
  plan_number: string;
  agent: string;
  status: 'active' | 'inactive';
  created_at: string;
  last_login: string;
  reminders: Array<{ id: number; drug_name: string; dose: string; time: string; enabled: boolean }>;
  activity: Array<{ type: string; desc: string; time: string }>;
}

export default function MemberDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [member, setMember] = useState<MemberDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    client
      .get(ENDPOINTS.MEMBER(id))
      .then((res) => {
        if (!cancelled) {
          setMember(res.data);
          setError('');
        }
      })
      .catch(() => {
        if (!cancelled) setError('Failed to load member details.');
      })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [id]);

  // Edit plan dialog
  const [planDialogOpen, setPlanDialogOpen] = useState(false);
  const [editCarrier, setEditCarrier] = useState('');
  const [editPlanName, setEditPlanName] = useState('');
  const [editPlanNumber, setEditPlanNumber] = useState('');
  const [saving, setSaving] = useState(false);

  const handleOpenPlanDialog = () => {
    if (member) {
      setEditCarrier(member.carrier);
      setEditPlanName(member.plan_name);
      setEditPlanNumber(member.plan_number);
    }
    setPlanDialogOpen(true);
  };

  // Add reminder dialog
  const [reminderDialogOpen, setReminderDialogOpen] = useState(false);
  const [newDrugName, setNewDrugName] = useState('');
  const [newDose, setNewDose] = useState('');
  const [newTime, setNewTime] = useState('08:00');

  // OTP dialog
  const [otpDialogOpen, setOtpDialogOpen] = useState(false);
  const [otpSending, setOtpSending] = useState(false);
  const [otpSent, setOtpSent] = useState(false);

  // Health Screening state
  const [screeningGender, setScreeningGender] = useState<'male' | 'female' | ''>('');
  const [screeningAnswers, setScreeningAnswers] = useState<Record<string, boolean>>({});
  const [screeningSaving, setScreeningSaving] = useState(false);
  const [screeningSaved, setScreeningSaved] = useState(false);
  const [screeningLoading, setScreeningLoading] = useState(false);
  const [screeningLoaded, setScreeningLoaded] = useState(false);

  // SDOH state
  const [sdohAnswers, setSdohAnswers] = useState<Record<string, string>>({
    transportation: 'no',
    food_insecurity: 'no',
    social_isolation: 'never',
    housing_stability: 'no',
  });
  const [sdohSaving, setSdohSaving] = useState(false);
  const [sdohSaved, setSdohSaved] = useState(false);
  const [sdohLoading, setSdohLoading] = useState(false);
  const [sdohLoaded, setSdohLoaded] = useState(false);

  function handlePlanSave() {
    setSaving(true);
    setTimeout(() => {
      setSaving(false);
      setPlanDialogOpen(false);
    }, 800);
  }

  function handleSendOtp() {
    setOtpSending(true);
    setTimeout(() => {
      setOtpSending(false);
      setOtpSent(true);
    }, 1200);
  }

  // ── Load existing screening data ──
  function loadScreeningData() {
    if (!member || screeningLoaded) return;
    setScreeningLoading(true);
    client
      .get(ENDPOINTS.MEMBER_HEALTH_SCREENING(member.phone))
      .then((res) => {
        const s = res.data?.screening;
        if (s) {
          setScreeningGender((s.gender || '') as 'male' | 'female' | '');
          setScreeningAnswers(s.answers || {});
        }
        setScreeningLoaded(true);
      })
      .catch(() => {})
      .finally(() => setScreeningLoading(false));
  }

  function loadSdohData() {
    if (!member || sdohLoaded) return;
    setSdohLoading(true);
    client
      .get(ENDPOINTS.MEMBER_SDOH_SCREENING(member.phone))
      .then((res) => {
        const s = res.data?.screening;
        if (s) {
          setSdohAnswers({
            transportation: s.transportation || 'no',
            food_insecurity: s.food_insecurity || 'no',
            social_isolation: s.social_isolation || 'never',
            housing_stability: s.housing_stability || 'no',
          });
        }
        setSdohLoaded(true);
      })
      .catch(() => {})
      .finally(() => setSdohLoading(false));
  }

  function handleScreeningSave() {
    if (!member) return;
    setScreeningSaving(true);
    setScreeningSaved(false);
    client
      .post(ENDPOINTS.MEMBER_HEALTH_SCREENING(member.phone), {
        gender: screeningGender,
        answers: screeningAnswers,
        reminders: [],
      })
      .then(() => setScreeningSaved(true))
      .catch(() => {})
      .finally(() => setScreeningSaving(false));
  }

  function handleSdohSave() {
    if (!member) return;
    setSdohSaving(true);
    setSdohSaved(false);
    client
      .post(ENDPOINTS.MEMBER_SDOH_SCREENING(member.phone), sdohAnswers)
      .then(() => setSdohSaved(true))
      .catch(() => {})
      .finally(() => setSdohSaving(false));
  }

  function handleAddReminder() {
    // TODO: POST /api/admin/members/:phone/reminders
    setReminderDialogOpen(false);
    setNewDrugName('');
    setNewDose('');
    setNewTime('08:00');
  }

  if (loading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-12 w-64" />
        <div className="grid grid-cols-3 gap-6">
          <Skeleton className="h-64" />
          <Skeleton className="col-span-2 h-64" />
        </div>
      </div>
    );
  }

  if (error || !member) {
    return (
      <div className="flex flex-col items-center justify-center py-20 space-y-4">
        <p className="text-sm text-destructive">{error || 'Member not found.'}</p>
        <Button variant="outline" size="sm" onClick={() => navigate('/admin/members')}>
          <ArrowLeft className="mr-1.5 h-3.5 w-3.5" /> Back to Members
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Back + Header */}
      <div className="flex items-start gap-4">
        <Button variant="ghost" size="sm" className="mt-1 h-8 w-8 p-0" onClick={() => navigate('/admin/members')}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div className="flex-1">
          <div className="flex items-center gap-3">
            <Avatar className="h-12 w-12">
              <AvatarFallback className="bg-primary/10 text-sm font-bold text-primary">
                {member.first_name[0]}{member.last_name[0]}
              </AvatarFallback>
            </Avatar>
            <div>
              <h1 className="text-2xl font-bold tracking-tight">
                {member.first_name} {member.last_name}
              </h1>
              <div className="flex items-center gap-3 mt-0.5">
                <Badge
                  className={`text-[10px] ${
                    member.status === 'active'
                      ? 'bg-success/10 text-success'
                      : 'bg-muted text-muted-foreground'
                  }`}
                >
                  {member.status}
                </Badge>
                <span className="text-xs text-muted-foreground">Member since {member.created_at}</span>
                <span className="text-xs text-muted-foreground">Last login: {member.last_login}</span>
              </div>
            </div>
          </div>
        </div>

        {/* Quick Actions */}
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" className="h-8 text-xs" onClick={() => setOtpDialogOpen(true)}>
            <KeyRound className="mr-1.5 h-3.5 w-3.5" /> Send OTP
          </Button>
          <Button variant="outline" size="sm" className="h-8 text-xs">
            <Phone className="mr-1.5 h-3.5 w-3.5" /> Call
          </Button>
          <Button variant="outline" size="sm" className="h-8 text-xs">
            <Send className="mr-1.5 h-3.5 w-3.5" /> SMS
          </Button>
        </div>
      </div>

      {/* Main Content - Two Column */}
      <div className="grid grid-cols-3 gap-6">
        {/* Left Column — Profile + Contact */}
        <div className="space-y-6">
          {/* Contact Info */}
          <Card className="border-border/50 shadow-sm">
            <CardHeader className="pb-3">
              <CardTitle className="text-sm font-semibold">Contact Information</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex items-center gap-3">
                <div className="h-8 w-8 rounded-lg bg-muted flex items-center justify-center">
                  <Phone className="h-3.5 w-3.5 text-muted-foreground" />
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Phone</p>
                  <p className="text-sm font-mono font-medium">{member.phone}</p>
                </div>
              </div>
              <Separator />
              <div className="flex items-center gap-3">
                <div className="h-8 w-8 rounded-lg bg-muted flex items-center justify-center">
                  <Mail className="h-3.5 w-3.5 text-muted-foreground" />
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Email</p>
                  <p className="text-sm font-medium">{member.email}</p>
                </div>
              </div>
              <Separator />
              <div className="flex items-center gap-3">
                <div className="h-8 w-8 rounded-lg bg-muted flex items-center justify-center">
                  <MapPin className="h-3.5 w-3.5 text-muted-foreground" />
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Address</p>
                  <p className="text-sm font-medium">{member.address}</p>
                </div>
              </div>
              <Separator />
              <div className="flex items-center gap-3">
                <div className="h-8 w-8 rounded-lg bg-muted flex items-center justify-center">
                  <Calendar className="h-3.5 w-3.5 text-muted-foreground" />
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Date of Birth</p>
                  <p className="text-sm font-medium">{member.dob}</p>
                </div>
              </div>
              <Separator />
              <div className="flex items-center gap-3">
                <div className="h-8 w-8 rounded-lg bg-muted flex items-center justify-center">
                  <Shield className="h-3.5 w-3.5 text-muted-foreground" />
                </div>
                <div>
                  <p className="text-xs text-muted-foreground">Agent</p>
                  <p className="text-sm font-medium">{member.agent}</p>
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Right Column — Plan + Tabs */}
        <div className="col-span-2 space-y-6">
          {/* Plan Assignment Card */}
          <Card className="border-border/50 shadow-sm">
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-semibold">Plan Assignment</CardTitle>
                <Button variant="outline" size="sm" className="h-7 text-xs" onClick={() => handleOpenPlanDialog()}>
                  <FileText className="mr-1.5 h-3 w-3" /> Change Plan
                </Button>
              </div>
            </CardHeader>
            <CardContent>
              {member.plan_number ? (
                <div className="grid grid-cols-3 gap-4">
                  <div className="rounded-lg border border-border bg-muted/20 p-3">
                    <p className="text-[11px] text-muted-foreground font-semibold uppercase tracking-wider mb-1">Carrier</p>
                    <Badge variant="secondary" className={`text-xs font-semibold ${CARRIER_COLORS[member.carrier] || CARRIER_COLORS.Other}`}>
                      {member.carrier}
                    </Badge>
                  </div>
                  <div className="rounded-lg border border-border bg-muted/20 p-3">
                    <p className="text-[11px] text-muted-foreground font-semibold uppercase tracking-wider mb-1">Plan Name</p>
                    <p className="text-sm font-medium">{member.plan_name}</p>
                  </div>
                  <div className="rounded-lg border border-border bg-muted/20 p-3">
                    <p className="text-[11px] text-muted-foreground font-semibold uppercase tracking-wider mb-1">Plan Number</p>
                    <p className="text-sm font-mono font-bold text-primary">{member.plan_number}</p>
                    <p className="text-[10px] text-muted-foreground mt-0.5">Links to SOB &amp; benefits</p>
                  </div>
                </div>
              ) : (
                <div className="flex items-center justify-center rounded-lg border border-dashed border-warning/50 bg-warning/5 p-6">
                  <div className="text-center">
                    <FileText className="mx-auto h-8 w-8 text-warning/60" />
                    <p className="mt-2 text-sm font-semibold text-warning">No Plan Assigned</p>
                    <p className="text-xs text-muted-foreground mt-1">Assign a plan to connect this member's app to benefits data.</p>
                    <Button size="sm" className="mt-3 text-xs" onClick={() => handleOpenPlanDialog()}>
                      Assign Plan Now
                    </Button>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Tabs: Reminders / Activity */}
          <Tabs defaultValue="reminders">
            <TabsList className="w-full justify-start bg-muted/30 h-9">
              <TabsTrigger value="reminders" className="text-xs data-[state=active]:bg-background">
                <Pill className="mr-1.5 h-3.5 w-3.5" /> Medication Reminders ({member.reminders.length})
              </TabsTrigger>
              <TabsTrigger value="activity" className="text-xs data-[state=active]:bg-background">
                <Activity className="mr-1.5 h-3.5 w-3.5" /> Activity Log ({member.activity.length})
              </TabsTrigger>
              <TabsTrigger value="screenings" className="text-xs data-[state=active]:bg-background" onClick={loadScreeningData}>
                <ClipboardCheck className="mr-1.5 h-3.5 w-3.5" /> Screenings
              </TabsTrigger>
              <TabsTrigger value="sdoh" className="text-xs data-[state=active]:bg-background" onClick={loadSdohData}>
                <Heart className="mr-1.5 h-3.5 w-3.5" /> Well-Being
              </TabsTrigger>
            </TabsList>

            {/* Reminders Tab */}
            <TabsContent value="reminders" className="mt-4">
              <Card className="border-border/50 shadow-sm">
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-sm font-semibold">Active Reminders</CardTitle>
                    <Button size="sm" className="h-7 text-xs" onClick={() => setReminderDialogOpen(true)}>
                      <Plus className="mr-1.5 h-3 w-3" /> Add Reminder
                    </Button>
                  </div>
                </CardHeader>
                <CardContent className="space-y-2">
                  {member.reminders.map((r) => (
                    <div
                      key={r.id}
                      className={`flex items-center justify-between rounded-lg border p-3 transition-colors ${
                        r.enabled ? 'border-border bg-background' : 'border-border/50 bg-muted/20 opacity-60'
                      }`}
                    >
                      <div className="flex items-center gap-3">
                        <div className={`h-9 w-9 rounded-lg flex items-center justify-center ${
                          r.enabled ? 'bg-chart-2/10' : 'bg-muted'
                        }`}>
                          <Pill className={`h-4 w-4 ${r.enabled ? 'text-chart-2' : 'text-muted-foreground'}`} />
                        </div>
                        <div>
                          <p className="text-sm font-semibold">{r.drug_name}</p>
                          <p className="text-xs text-muted-foreground">{r.dose} &middot; {r.time}</p>
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <Badge
                          variant="secondary"
                          className={`text-[10px] ${r.enabled ? 'bg-success/10 text-success' : 'bg-muted text-muted-foreground'}`}
                        >
                          {r.enabled ? 'Active' : 'Paused'}
                        </Badge>
                        <Button variant="ghost" size="sm" className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive">
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    </div>
                  ))}
                </CardContent>
              </Card>
            </TabsContent>

            {/* Activity Tab */}
            <TabsContent value="activity" className="mt-4">
              <Card className="border-border/50 shadow-sm">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm font-semibold">Recent Activity</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-1">
                    {member.activity.map((a, i) => {
                      const Icon = ACTIVITY_ICONS[a.type] || Activity;
                      return (
                        <div key={i} className="flex items-center gap-3 rounded-lg px-2 py-2.5 hover:bg-accent/30 transition-colors">
                          <div className="h-7 w-7 rounded-lg bg-muted flex items-center justify-center shrink-0">
                            <Icon className="h-3.5 w-3.5 text-muted-foreground" />
                          </div>
                          <p className="text-xs flex-1">{a.desc}</p>
                          <span className="text-[11px] text-muted-foreground shrink-0">{a.time}</span>
                        </div>
                      );
                    })}
                  </div>
                </CardContent>
              </Card>
            </TabsContent>

            {/* Screenings Tab — agent fills on behalf of member */}
            <TabsContent value="screenings" className="mt-4">
              <Card className="border-border/50 shadow-sm">
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-sm font-semibold">Health Screening Checklist</CardTitle>
                    <Badge variant="secondary" className="text-[10px] bg-chart-4/10 text-chart-4">Phone Intake</Badge>
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">
                    Walk through these preventive screenings with the member during the call.
                  </p>
                </CardHeader>
                <CardContent className="space-y-4">
                  {screeningLoading ? (
                    <div className="flex items-center justify-center py-8">
                      <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
                    </div>
                  ) : (
                    <>
                      {/* Gender selection */}
                      <div className="space-y-2">
                        <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Gender</Label>
                        <div className="flex gap-2">
                          {(['male', 'female'] as const).map((g) => (
                            <Button
                              key={g}
                              variant={screeningGender === g ? 'default' : 'outline'}
                              size="sm"
                              className="h-8 text-xs capitalize"
                              onClick={() => setScreeningGender(g)}
                            >
                              {g}
                            </Button>
                          ))}
                        </div>
                      </div>

                      {screeningGender && (
                        <>
                          <Separator />
                          <div className="space-y-2">
                            {(() => {
                              const applicable = [
                                ...DEFAULT_SHARED_SCREENINGS,
                                ...(screeningGender === 'male' ? DEFAULT_MALE_SCREENINGS : DEFAULT_FEMALE_SCREENINGS),
                              ];
                              return applicable.map((s) => (
                                <div
                                  key={s.id}
                                  className={`flex items-center justify-between rounded-lg border p-3 transition-colors cursor-pointer ${
                                    screeningAnswers[s.id] === true
                                      ? 'border-success/50 bg-success/5'
                                      : screeningAnswers[s.id] === false
                                        ? 'border-warning/50 bg-warning/5'
                                        : 'border-border hover:bg-accent/30'
                                  }`}
                                  onClick={() =>
                                    setScreeningAnswers((prev) => ({
                                      ...prev,
                                      [s.id]: prev[s.id] === true ? false : true,
                                    }))
                                  }
                                >
                                  <div className="flex items-center gap-3">
                                    <div className={`h-8 w-8 rounded-lg flex items-center justify-center ${
                                      screeningAnswers[s.id] === true ? 'bg-success/10' : 'bg-muted'
                                    }`}>
                                      {screeningAnswers[s.id] === true ? (
                                        <Check className="h-4 w-4 text-success" />
                                      ) : (
                                        <ClipboardCheck className="h-4 w-4 text-muted-foreground" />
                                      )}
                                    </div>
                                    <div>
                                      <p className="text-sm font-medium">{s.label}</p>
                                      <p className="text-[11px] text-muted-foreground">Have you completed this {s.timeframe}?</p>
                                    </div>
                                  </div>
                                  <Badge
                                    variant="secondary"
                                    className={`text-[10px] ${
                                      screeningAnswers[s.id] === true
                                        ? 'bg-success/10 text-success'
                                        : screeningAnswers[s.id] === false
                                          ? 'bg-warning/10 text-warning'
                                          : 'bg-muted text-muted-foreground'
                                    }`}
                                  >
                                    {screeningAnswers[s.id] === true ? 'Yes' : screeningAnswers[s.id] === false ? 'No' : 'Not asked'}
                                  </Badge>
                                </div>
                              ));
                            })()}
                          </div>

                          <div className="flex items-center justify-between pt-2">
                            {screeningSaved && (
                              <div className="flex items-center gap-1.5 text-success">
                                <Check className="h-3.5 w-3.5" />
                                <span className="text-xs font-medium">Saved successfully</span>
                              </div>
                            )}
                            <div className="ml-auto">
                              <Button
                                size="sm"
                                className="h-8 text-xs"
                                onClick={handleScreeningSave}
                                disabled={screeningSaving || !Object.keys(screeningAnswers).length}
                              >
                                {screeningSaving ? (
                                  <><div className="mr-2 h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" /> Saving...</>
                                ) : (
                                  <><Check className="mr-1.5 h-3.5 w-3.5" /> Save Screening</>
                                )}
                              </Button>
                            </div>
                          </div>
                        </>
                      )}
                    </>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            {/* SDOH / Well-Being Tab — agent fills on behalf of member */}
            <TabsContent value="sdoh" className="mt-4">
              <Card className="border-border/50 shadow-sm">
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-sm font-semibold">Social Determinants of Health</CardTitle>
                    <Badge variant="secondary" className="text-[10px] bg-chart-4/10 text-chart-4">Phone Intake</Badge>
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">
                    Ask the member about social factors that may affect their health and benefits usage.
                  </p>
                </CardHeader>
                <CardContent className="space-y-4">
                  {sdohLoading ? (
                    <div className="flex items-center justify-center py-8">
                      <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
                    </div>
                  ) : (
                    <>
                      {SDOH_QUESTIONS.map((q) => {
                        const Icon = q.icon;
                        return (
                          <div key={q.id} className="rounded-lg border border-border p-4 space-y-3">
                            <div className="flex items-start gap-3">
                              <div className="h-8 w-8 rounded-lg bg-muted flex items-center justify-center shrink-0 mt-0.5">
                                <Icon className="h-4 w-4 text-muted-foreground" />
                              </div>
                              <div>
                                <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-1">{q.flagLabel}</p>
                                <p className="text-sm">{q.question}</p>
                              </div>
                            </div>
                            <div className="flex gap-2 pl-11">
                              {q.type === 'yesno' ? (
                                <>
                                  {(['no', 'yes'] as const).map((val) => (
                                    <Button
                                      key={val}
                                      variant={sdohAnswers[q.id] === val ? (val === 'yes' ? 'destructive' : 'default') : 'outline'}
                                      size="sm"
                                      className="h-7 text-xs capitalize"
                                      onClick={() => setSdohAnswers((prev) => ({ ...prev, [q.id]: val }))}
                                    >
                                      {val}
                                    </Button>
                                  ))}
                                </>
                              ) : (
                                <>
                                  {(q.options || []).map((opt) => (
                                    <Button
                                      key={opt}
                                      variant={sdohAnswers[q.id] === opt ? 'default' : 'outline'}
                                      size="sm"
                                      className="h-7 text-xs capitalize"
                                      onClick={() => setSdohAnswers((prev) => ({ ...prev, [q.id]: opt }))}
                                    >
                                      {opt}
                                    </Button>
                                  ))}
                                </>
                              )}
                            </div>
                          </div>
                        );
                      })}

                      <div className="flex items-center justify-between pt-2">
                        {sdohSaved && (
                          <div className="flex items-center gap-1.5 text-success">
                            <Check className="h-3.5 w-3.5" />
                            <span className="text-xs font-medium">Saved successfully</span>
                          </div>
                        )}
                        <div className="ml-auto">
                          <Button
                            size="sm"
                            className="h-8 text-xs"
                            onClick={handleSdohSave}
                            disabled={sdohSaving}
                          >
                            {sdohSaving ? (
                              <><div className="mr-2 h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" /> Saving...</>
                            ) : (
                              <><Check className="mr-1.5 h-3.5 w-3.5" /> Save Well-Being</>
                            )}
                          </Button>
                        </div>
                      </div>
                    </>
                  )}
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        </div>
      </div>

      {/* ── Change Plan Dialog ── */}
      <Dialog open={planDialogOpen} onOpenChange={setPlanDialogOpen}>
        <DialogContent className="sm:max-w-[480px]">
          <DialogHeader>
            <DialogTitle className="text-lg font-bold">Change Plan Assignment</DialogTitle>
            <DialogDescription className="text-sm">
              Update {member.first_name}'s carrier and plan. The plan number links their app to the extracted SOB &amp; benefits data.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-2">
              <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Carrier</Label>
              <Select value={editCarrier} onValueChange={setEditCarrier}>
                <SelectTrigger className="h-9">
                  <SelectValue placeholder="Select carrier..." />
                </SelectTrigger>
                <SelectContent>
                  {CARRIERS.map((c) => (
                    <SelectItem key={c} value={c}>{c}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Plan Name</Label>
              <Input value={editPlanName} onChange={(e) => setEditPlanName(e.target.value)} placeholder="e.g. Humana Gold Plus (HMO)" className="h-9" />
            </div>
            <div className="space-y-2">
              <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Plan Number</Label>
              <Input value={editPlanNumber} onChange={(e) => setEditPlanNumber(e.target.value)} placeholder="e.g. H0028-014" className="h-9 font-mono" />
              <p className="text-[11px] text-muted-foreground">Links the member's app to SOB extraction &amp; benefits data.</p>
            </div>
            {editPlanNumber && (
              <div className="rounded-lg border border-border bg-muted/30 p-3">
                <div className="flex items-start gap-2">
                  <Check className="mt-0.5 h-4 w-4 text-primary shrink-0" />
                  <p className="text-[11px] text-muted-foreground">
                    <span className="font-mono font-semibold text-foreground">{editPlanNumber}</span> will connect to extracted benefits, formulary, and provider directory.
                  </p>
                </div>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPlanDialogOpen(false)} className="text-xs">Cancel</Button>
            <Button onClick={handlePlanSave} disabled={!editCarrier || !editPlanNumber || saving} className="text-xs">
              {saving ? (
                <><div className="mr-2 h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" /> Saving...</>
              ) : (
                <><Check className="mr-1.5 h-3.5 w-3.5" /> Save Changes</>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Add Reminder Dialog ── */}
      <Dialog open={reminderDialogOpen} onOpenChange={setReminderDialogOpen}>
        <DialogContent className="sm:max-w-[420px]">
          <DialogHeader>
            <DialogTitle className="text-lg font-bold">Add Medication Reminder</DialogTitle>
            <DialogDescription className="text-sm">
              Create a new medication reminder for {member.first_name}. They'll receive push notifications at the scheduled time.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-2">
              <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Medication Name</Label>
              <Input value={newDrugName} onChange={(e) => setNewDrugName(e.target.value)} placeholder="e.g. Lisinopril" className="h-9" />
            </div>
            <div className="space-y-2">
              <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Dosage</Label>
              <Input value={newDose} onChange={(e) => setNewDose(e.target.value)} placeholder="e.g. 10mg" className="h-9" />
            </div>
            <div className="space-y-2">
              <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Reminder Time</Label>
              <Input type="time" value={newTime} onChange={(e) => setNewTime(e.target.value)} className="h-9" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setReminderDialogOpen(false)} className="text-xs">Cancel</Button>
            <Button onClick={handleAddReminder} disabled={!newDrugName || !newDose} className="text-xs">
              <Plus className="mr-1.5 h-3.5 w-3.5" /> Add Reminder
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* ── Send OTP Dialog ── */}
      <Dialog open={otpDialogOpen} onOpenChange={(open) => { setOtpDialogOpen(open); if (!open) setOtpSent(false); }}>
        <DialogContent className="sm:max-w-[400px]">
          <DialogHeader>
            <DialogTitle className="text-lg font-bold">Send OTP Login</DialogTitle>
            <DialogDescription className="text-sm">
              Send a one-time password to {member.first_name}'s phone so they can log into the concierge app.
            </DialogDescription>
          </DialogHeader>
          <div className="py-4">
            <div className="rounded-lg border border-border bg-muted/30 p-4 text-center">
              <Phone className="mx-auto h-8 w-8 text-primary/60 mb-2" />
              <p className="text-sm font-mono font-bold">{member.phone}</p>
              <p className="text-[11px] text-muted-foreground mt-1">OTP will be sent to this number via SMS</p>
            </div>
            {otpSent && (
              <div className="mt-3 flex items-center gap-2 rounded-lg bg-success/10 border border-success/20 p-3">
                <Check className="h-4 w-4 text-success shrink-0" />
                <p className="text-xs font-medium text-success">OTP sent successfully! Member has 5 minutes to use it.</p>
              </div>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setOtpDialogOpen(false); setOtpSent(false); }} className="text-xs">
              {otpSent ? 'Close' : 'Cancel'}
            </Button>
            {!otpSent && (
              <Button onClick={handleSendOtp} disabled={otpSending} className="text-xs">
                {otpSending ? (
                  <><div className="mr-2 h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" /> Sending...</>
                ) : (
                  <><KeyRound className="mr-1.5 h-3.5 w-3.5" /> Send OTP</>
                )}
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
