import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft, Phone, MapPin, Mail, Calendar, Shield,
  KeyRound, Pill, Send, FileText, Check,
  Plus, Trash2, Activity, Eye, AlertCircle, Bell,
  ClipboardCheck, Heart, Car, UtensilsCrossed, Users, Home,
  AlertTriangle, Clock, History, NotebookPen,
  PhoneIncoming, PhoneOutgoing, PhoneForwarded, RefreshCw,
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

  const [otpError, setOtpError] = useState('');

  async function handleSendOtp() {
    if (!member) return;
    setOtpSending(true);
    setOtpError('');
    try {
      await client.post(ENDPOINTS.MEMBER_SEND_OTP, {
        phone: member.phone,
      });
      setOtpSent(true);
    } catch (err: unknown) {
      const axiosErr = err as { response?: { status?: number; data?: { detail?: string } } };
      if (axiosErr.response?.status === 429) {
        setOtpError('Too many OTP requests. Please wait and try again.');
      } else {
        setOtpError(axiosErr.response?.data?.detail || 'Failed to send OTP.');
      }
    } finally {
      setOtpSending(false);
    }
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

  // Notification dialog
  const [notifDialogOpen, setNotifDialogOpen] = useState(false);
  const [notifTitle, setNotifTitle] = useState('');
  const [notifBody, setNotifBody] = useState('');
  const [notifCategory, setNotifCategory] = useState('general');
  const [notifSending, setNotifSending] = useState(false);
  const [notifSent, setNotifSent] = useState(false);
  const [notifError, setNotifError] = useState('');
  const [notifResult, setNotifResult] = useState<{ push_delivered: boolean; push_tokens_found: number } | null>(null);

  // Notification history
  const [notifications, setNotifications] = useState<Array<{ id: number; title: string; body: string; category: string; read: number; created_at: string }>>([]);
  const [notifHistoryLoaded, setNotifHistoryLoaded] = useState(false);

  async function handleSendNotification() {
    if (!member) return;
    setNotifSending(true);
    setNotifError('');
    try {
      const res = await client.post(ENDPOINTS.MEMBER_NOTIFICATIONS(member.phone), {
        title: notifTitle,
        body: notifBody,
        category: notifCategory,
      });
      setNotifSent(true);
      setNotifResult(res.data);
      // Refresh history
      loadNotificationHistory();
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } };
      setNotifError(axiosErr.response?.data?.detail || 'Failed to send notification.');
    } finally {
      setNotifSending(false);
    }
  }

  function loadNotificationHistory() {
    if (!member) return;
    client
      .get(ENDPOINTS.MEMBER_NOTIFICATIONS(member.phone))
      .then((res) => {
        setNotifications(res.data?.notifications || []);
        setNotifHistoryLoaded(true);
      })
      .catch(() => {});
  }

  function closeNotifDialog() {
    setNotifDialogOpen(false);
    setNotifSent(false);
    setNotifError('');
    setNotifResult(null);
    setNotifTitle('');
    setNotifBody('');
    setNotifCategory('general');
  }

  const NOTIF_TEMPLATES = [
    { label: 'OTC Allowance Reminder', title: 'Use Your OTC Allowance!', body: 'You still have unused OTC benefits this quarter. Visit your plan\'s OTC catalog to order health essentials at no cost.' },
    { label: 'Appointment Confirmed', title: 'Appointment Confirmed', body: 'Your upcoming appointment has been confirmed. Please arrive 15 minutes early with your insurance card.' },
    { label: 'Screening Reminder', title: 'Preventive Screening Due', body: 'You may be due for a preventive health screening. These are covered at $0 under your plan. Call us to schedule.' },
    { label: 'Benefits Renewal', title: 'Your Benefits Reset Soon', body: 'Your plan benefits reset on January 1st. Make sure to use your remaining allowances before they expire.' },
  ];

  // ── C: Screening/SDOH History ──
  interface ScreeningEntry {
    id: number;
    gender: string;
    answers: Record<string, boolean>;
    gaps: string[];
    completed: string[];
    gap_count: number;
    completed_count: number;
    total_count: number;
    created_at: string;
  }
  interface SdohEntry {
    id: number;
    transportation: string;
    food_insecurity: string;
    social_isolation: string;
    housing_stability: string;
    flags: string[];
    flag_count: number;
    created_at: string;
  }
  const [screeningHistory, setScreeningHistory] = useState<ScreeningEntry[]>([]);
  const [sdohHistory, setSdohHistory] = useState<SdohEntry[]>([]);
  const [historyLoaded, setHistoryLoaded] = useState(false);

  function loadHistory() {
    if (!member || historyLoaded) return;
    client
      .get(ENDPOINTS.MEMBER_SCREENING_HISTORY(member.phone))
      .then((res) => {
        setScreeningHistory(res.data?.screenings || []);
        setSdohHistory(res.data?.sdoh || []);
        setHistoryLoaded(true);
      })
      .catch(() => {});
  }

  // ── E: Utilization Alerts ──
  interface UtilAlert {
    type: string;
    severity: string;
    title: string;
    body: string;
    gaps?: string[];
    flags?: string[];
    cap?: number;
    spent?: number;
    remaining?: number;
    period?: string;
  }
  const [utilAlerts, setUtilAlerts] = useState<UtilAlert[]>([]);
  const [alertsLoaded, setAlertsLoaded] = useState(false);
  const [alertsLoading, setAlertsLoading] = useState(false);

  function loadAlerts() {
    if (!member || alertsLoaded) return;
    setAlertsLoading(true);
    client
      .get(ENDPOINTS.MEMBER_UTILIZATION_ALERTS(member.phone))
      .then((res) => {
        setUtilAlerts(res.data?.alerts || []);
        setAlertsLoaded(true);
      })
      .catch(() => {})
      .finally(() => setAlertsLoading(false));
  }

  // ── L: Call Notes ──
  interface CallNote {
    id: number;
    subject: string;
    body: string;
    call_type: string;
    duration_minutes: number;
    agent_name: string;
    zoho_synced: number;
    created_at: string;
  }
  const [callNotes, setCallNotes] = useState<CallNote[]>([]);
  const [callNotesLoaded, setCallNotesLoaded] = useState(false);
  const [callNoteDialogOpen, setCallNoteDialogOpen] = useState(false);
  const [noteSubject, setNoteSubject] = useState('');
  const [noteBody, setNoteBody] = useState('');
  const [noteCallType, setNoteCallType] = useState('outbound');
  const [noteDuration, setNoteDuration] = useState('');
  const [noteSyncToZoho, setNoteSyncToZoho] = useState(true);
  const [noteSaving, setNoteSaving] = useState(false);
  const [noteError, setNoteError] = useState('');
  const [noteResult, setNoteResult] = useState<{ zoho_synced: boolean; zoho_error: string } | null>(null);

  function loadCallNotes() {
    if (!member) return;
    client
      .get(ENDPOINTS.MEMBER_CALL_NOTES(member.phone))
      .then((res) => {
        setCallNotes(res.data?.notes || []);
        setCallNotesLoaded(true);
      })
      .catch(() => {});
  }

  async function handleCreateCallNote() {
    if (!member || !noteSubject.trim() || !noteBody.trim()) return;
    setNoteSaving(true);
    setNoteError('');
    setNoteResult(null);
    try {
      const res = await client.post(ENDPOINTS.MEMBER_CALL_NOTES(member.phone), {
        subject: noteSubject.trim(),
        body: noteBody.trim(),
        call_type: noteCallType,
        duration_minutes: parseInt(noteDuration) || 0,
        sync_to_zoho: noteSyncToZoho,
      });
      setCallNotes([res.data.note, ...callNotes]);
      setNoteResult({
        zoho_synced: res.data.zoho_synced,
        zoho_error: res.data.zoho_error || '',
      });
      setNoteSubject('');
      setNoteBody('');
      setNoteDuration('');
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Failed to save note';
      setNoteError(detail);
    } finally {
      setNoteSaving(false);
    }
  }

  const [reminderSaving, setReminderSaving] = useState(false);
  const [reminderError, setReminderError] = useState('');

  async function handleAddReminder() {
    if (!member) return;
    setReminderSaving(true);
    setReminderError('');
    const [hourStr, minuteStr] = newTime.split(':');
    try {
      const res = await client.post(ENDPOINTS.MEMBER_REMINDERS(member.phone), {
        drug_name: newDrugName,
        dose_label: newDose,
        time_hour: parseInt(hourStr, 10),
        time_minute: parseInt(minuteStr, 10),
      });
      // Add the new reminder to the local state
      const newReminder = res.data.reminder;
      setMember({
        ...member,
        reminders: [
          ...member.reminders,
          {
            id: newReminder.id,
            drug_name: newReminder.drug_name,
            dose: newReminder.dose_label,
            time: newTime,
            enabled: true,
          },
        ],
      });
      setReminderDialogOpen(false);
      setNewDrugName('');
      setNewDose('');
      setNewTime('08:00');
    } catch (err: unknown) {
      const axiosErr = err as { response?: { data?: { detail?: string } } };
      setReminderError(axiosErr.response?.data?.detail || 'Failed to create reminder.');
    } finally {
      setReminderSaving(false);
    }
  }

  async function handleDeleteReminder(reminderId: number) {
    if (!member) return;
    try {
      await client.delete(ENDPOINTS.MEMBER_REMINDER(member.phone, reminderId));
      setMember({
        ...member,
        reminders: member.reminders.filter((r) => r.id !== reminderId),
      });
    } catch {
      // Silent fail — could add toast here
    }
  }

  async function handleToggleReminder(reminderId: number, enabled: boolean) {
    if (!member) return;
    try {
      await client.put(ENDPOINTS.MEMBER_REMINDER(member.phone, reminderId), { enabled });
      setMember({
        ...member,
        reminders: member.reminders.map((r) =>
          r.id === reminderId ? { ...r, enabled } : r
        ),
      });
    } catch {
      // Silent fail
    }
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
          <Button variant="default" size="sm" className="h-8 text-xs" onClick={() => setNotifDialogOpen(true)}>
            <Bell className="mr-1.5 h-3.5 w-3.5" /> Send Notification
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
              <TabsTrigger value="history" className="text-xs data-[state=active]:bg-background" onClick={loadHistory}>
                <History className="mr-1.5 h-3.5 w-3.5" /> History
              </TabsTrigger>
              <TabsTrigger value="alerts" className="text-xs data-[state=active]:bg-background" onClick={loadAlerts}>
                <AlertTriangle className="mr-1.5 h-3.5 w-3.5" /> Alerts
              </TabsTrigger>
<TabsTrigger value="call-notes" className="text-xs data-[state=active]:bg-background" onClick={loadCallNotes}>
                <NotebookPen className="mr-1.5 h-3.5 w-3.5" /> Call Notes
              </TabsTrigger>
              <TabsTrigger value="notifications" className="text-xs data-[state=active]:bg-background" onClick={loadNotificationHistory}>
                <Bell className="mr-1.5 h-3.5 w-3.5" /> Notifications
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
                          className={`text-[10px] cursor-pointer ${r.enabled ? 'bg-success/10 text-success' : 'bg-muted text-muted-foreground'}`}
                          onClick={() => handleToggleReminder(r.id, !r.enabled)}
                        >
                          {r.enabled ? 'Active' : 'Paused'}
                        </Badge>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
                          onClick={() => handleDeleteReminder(r.id)}
                        >
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

            {/* C: Screening/SDOH History Tab */}
            <TabsContent value="history" className="mt-4">
              <Card className="border-border/50 shadow-sm">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm font-semibold">Screening & SDOH History</CardTitle>
                  <p className="text-xs text-muted-foreground mt-1">
                    Timeline of all completed screenings and social determinant assessments.
                  </p>
                </CardHeader>
                <CardContent>
                  {!historyLoaded ? (
                    <div className="flex items-center justify-center py-8">
                      <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
                    </div>
                  ) : screeningHistory.length === 0 && sdohHistory.length === 0 ? (
                    <div className="text-center py-8">
                      <ClipboardCheck className="mx-auto h-8 w-8 text-muted-foreground/40" />
                      <p className="mt-2 text-sm text-muted-foreground">No screenings or SDOH assessments on file</p>
                    </div>
                  ) : (
                    <div className="space-y-4">
                      {/* Merge and sort by date */}
                      {[
                        ...screeningHistory.map((s) => ({ ...s, _type: 'screening' as const })),
                        ...sdohHistory.map((s) => ({ ...s, _type: 'sdoh' as const })),
                      ]
                        .sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''))
                        .map((entry, i) => (
                          <div key={`${entry._type}-${entry.id}`} className="relative flex gap-4">
                            {/* Timeline line */}
                            {i > 0 && (
                              <div className="absolute left-[15px] -top-4 w-px h-4 bg-border" />
                            )}
                            <div className={`h-8 w-8 rounded-full flex items-center justify-center shrink-0 ${
                              entry._type === 'screening' ? 'bg-chart-2/10' : 'bg-chart-4/10'
                            }`}>
                              {entry._type === 'screening' ? (
                                <ClipboardCheck className="h-4 w-4 text-chart-2" />
                              ) : (
                                <Heart className="h-4 w-4 text-chart-4" />
                              )}
                            </div>
                            <div className="flex-1 rounded-lg border border-border p-3">
                              <div className="flex items-center justify-between mb-2">
                                <div className="flex items-center gap-2">
                                  <p className="text-sm font-semibold">
                                    {entry._type === 'screening' ? 'Health Screening' : 'SDOH Assessment'}
                                  </p>
                                  {entry._type === 'screening' && 'gender' in entry && (
                                    <Badge variant="secondary" className="text-[10px]">{(entry as ScreeningEntry).gender}</Badge>
                                  )}
                                </div>
                                <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                                  <Clock className="h-3 w-3" />
                                  {entry.created_at}
                                </div>
                              </div>

                              {entry._type === 'screening' ? (() => {
                                const s = entry as ScreeningEntry;
                                return (
                                  <div className="space-y-2">
                                    <div className="flex items-center gap-4 text-xs">
                                      <span className="text-success font-medium">{s.completed_count} completed</span>
                                      <span className="text-warning font-medium">{s.gap_count} gap{s.gap_count !== 1 ? 's' : ''}</span>
                                      <span className="text-muted-foreground">{s.total_count} total</span>
                                    </div>
                                    {s.gaps.length > 0 && (
                                      <div className="flex flex-wrap gap-1">
                                        {s.gaps.map((g) => (
                                          <Badge key={g} variant="secondary" className="text-[10px] bg-warning/10 text-warning">
                                            {g}
                                          </Badge>
                                        ))}
                                      </div>
                                    )}
                                  </div>
                                );
                              })() : (() => {
                                const s = entry as SdohEntry;
                                return (
                                  <div className="space-y-2">
                                    {s.flag_count > 0 ? (
                                      <div className="flex flex-wrap gap-1">
                                        {s.flags.map((f) => (
                                          <Badge key={f} variant="secondary" className="text-[10px] bg-destructive/10 text-destructive">
                                            {f}
                                          </Badge>
                                        ))}
                                      </div>
                                    ) : (
                                      <p className="text-xs text-success font-medium">No risk factors identified</p>
                                    )}
                                  </div>
                                );
                              })()}
                            </div>
                          </div>
                        ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            {/* E: Utilization Alerts Tab */}
            <TabsContent value="alerts" className="mt-4">
              <Card className="border-border/50 shadow-sm">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm font-semibold">Benefits Utilization Alerts</CardTitle>
                  <p className="text-xs text-muted-foreground mt-1">
                    Automated checks for unused benefits, screening gaps, and upcoming deadlines.
                  </p>
                </CardHeader>
                <CardContent>
                  {alertsLoading ? (
                    <div className="flex items-center justify-center py-8">
                      <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
                    </div>
                  ) : !alertsLoaded ? (
                    <div className="text-center py-8">
                      <AlertTriangle className="mx-auto h-8 w-8 text-muted-foreground/40" />
                      <p className="mt-2 text-sm text-muted-foreground">Click to load alerts</p>
                    </div>
                  ) : utilAlerts.length === 0 ? (
                    <div className="text-center py-8">
                      <Check className="mx-auto h-8 w-8 text-success/60" />
                      <p className="mt-2 text-sm text-success font-medium">No alerts — member is on track!</p>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {utilAlerts.map((alert, i) => (
                        <div
                          key={i}
                          className={`rounded-lg border p-4 ${
                            alert.severity === 'warning'
                              ? 'border-warning/30 bg-warning/5'
                              : alert.severity === 'info'
                                ? 'border-primary/30 bg-primary/5'
                                : 'border-border'
                          }`}
                        >
                          <div className="flex items-start gap-3">
                            <div className={`h-8 w-8 rounded-lg flex items-center justify-center shrink-0 ${
                              alert.severity === 'warning' ? 'bg-warning/10' : 'bg-primary/10'
                            }`}>
                              {alert.type === 'screening_gap' ? (
                                <ClipboardCheck className={`h-4 w-4 ${alert.severity === 'warning' ? 'text-warning' : 'text-primary'}`} />
                              ) : alert.type === 'sdoh_risk' ? (
                                <Heart className="h-4 w-4 text-warning" />
                              ) : alert.type === 'otc_underuse' ? (
                                <FileText className="h-4 w-4 text-primary" />
                              ) : alert.type === 'flu_season' ? (
                                <AlertTriangle className="h-4 w-4 text-warning" />
                              ) : alert.type === 'refill_due' ? (
                                <Pill className="h-4 w-4 text-warning" />
                              ) : (
                                <AlertCircle className="h-4 w-4 text-primary" />
                              )}
                            </div>
                            <div className="flex-1">
                              <p className="text-sm font-semibold">{alert.title}</p>
                              <p className="text-xs text-muted-foreground mt-0.5">{alert.body}</p>
                              {alert.type === 'otc_underuse' && alert.cap && (
                                <div className="mt-2">
                                  <div className="flex items-center justify-between text-[10px] text-muted-foreground mb-1">
                                    <span>${alert.spent?.toFixed(0)} spent</span>
                                    <span>${alert.cap.toFixed(0)} / {alert.period?.toLowerCase()}</span>
                                  </div>
                                  <div className="h-2 rounded-full bg-muted overflow-hidden">
                                    <div
                                      className="h-full rounded-full bg-primary/60 transition-all"
                                      style={{ width: `${Math.min(100, ((alert.spent || 0) / alert.cap) * 100)}%` }}
                                    />
                                  </div>
                                </div>
                              )}
                              {alert.type === 'screening_gap' && alert.gaps && alert.gaps.length > 0 && (
                                <div className="flex flex-wrap gap-1 mt-2">
                                  {alert.gaps.map((g) => (
                                    <Badge key={g} variant="secondary" className="text-[10px] bg-warning/10 text-warning">{g}</Badge>
                                  ))}
                                </div>
                              )}
                            </div>
                            {/* Quick action: send notification about this alert */}
                            <Button
                              variant="outline"
                              size="sm"
                              className="h-7 text-[10px] shrink-0"
                              onClick={() => {
                                setNotifTitle(alert.title);
                                setNotifBody(alert.body);
                                setNotifCategory(
                                  alert.type === 'screening_gap' ? 'screening' :
                                  alert.type === 'otc_underuse' ? 'benefits_reminder' :
                                  alert.type === 'refill_due' ? 'medication' : 'general'
                                );
                                setNotifDialogOpen(true);
                              }}
                            >
                              <Bell className="mr-1 h-3 w-3" /> Notify
                            </Button>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            {/* L: Call Notes Tab */}
            <TabsContent value="call-notes" className="mt-4">
              <Card className="border-border/50 shadow-sm">
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <div>
                      <CardTitle className="text-sm font-semibold">Call Notes</CardTitle>
                      <p className="text-xs text-muted-foreground mt-1">
                        Log call interactions with {member.first_name}. Notes sync to Zoho CRM for a complete member record.
                      </p>
                    </div>
                    <Button size="sm" className="h-7 text-xs" onClick={() => { setCallNoteDialogOpen(true); setNoteResult(null); setNoteError(''); }}>
                      <Plus className="mr-1.5 h-3 w-3" /> Log Call
                    </Button>
                  </div>
                </CardHeader>
                <CardContent>
                  {!callNotesLoaded ? (
                    <div className="flex items-center justify-center py-8">
                      <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
                    </div>
                  ) : callNotes.length === 0 ? (
                    <div className="text-center py-8">
                      <NotebookPen className="mx-auto h-8 w-8 text-muted-foreground/40" />
                      <p className="mt-2 text-sm text-muted-foreground">No call notes yet</p>
                      <Button size="sm" className="mt-3 text-xs" onClick={() => { setCallNoteDialogOpen(true); setNoteResult(null); }}>
                        Log First Call
                      </Button>
                    </div>
                  ) : (
                    <div className="space-y-3">
                      {callNotes.map((note) => (
                        <div key={note.id} className="rounded-lg border border-border/50 p-3">
                          <div className="flex items-start justify-between gap-3">
                            <div className="flex items-start gap-3 flex-1">
                              <div className="h-8 w-8 rounded-lg bg-primary/10 flex items-center justify-center shrink-0 mt-0.5">
                                {note.call_type === 'inbound' ? (
                                  <PhoneIncoming className="h-4 w-4 text-primary" />
                                ) : note.call_type === 'follow_up' ? (
                                  <PhoneForwarded className="h-4 w-4 text-primary" />
                                ) : (
                                  <PhoneOutgoing className="h-4 w-4 text-primary" />
                                )}
                              </div>
                              <div className="flex-1 min-w-0">
                                <p className="text-sm font-semibold">{note.subject}</p>
                                <p className="text-xs text-muted-foreground mt-1 whitespace-pre-wrap">{note.body}</p>
                              </div>
                            </div>
                            <div className="flex flex-col items-end gap-1 shrink-0">
                              <Badge variant="secondary" className="text-[10px]">
                                {note.call_type === 'inbound' ? 'Inbound' : note.call_type === 'follow_up' ? 'Follow-up' : 'Outbound'}
                              </Badge>
                              {note.zoho_synced ? (
                                <Badge className="text-[10px] bg-success/10 text-success border-success/20">
                                  <RefreshCw className="mr-1 h-2.5 w-2.5" /> Zoho Synced
                                </Badge>
                              ) : (
                                <Badge variant="secondary" className="text-[10px] text-muted-foreground">
                                  Local Only
                                </Badge>
                              )}
                            </div>
                          </div>
                          <div className="flex items-center gap-3 mt-2 pl-11">
                            <span className="text-[10px] text-muted-foreground">{note.agent_name}</span>
                            {note.duration_minutes > 0 && (
                              <span className="text-[10px] text-muted-foreground">{note.duration_minutes} min</span>
                            )}
                            <span className="text-[10px] text-muted-foreground">{note.created_at}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            </TabsContent>

            {/* Notifications Tab */}
            <TabsContent value="notifications" className="mt-4">
              <Card className="border-border/50 shadow-sm">
                <CardHeader className="pb-3">
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-sm font-semibold">Notification History</CardTitle>
                    <Button size="sm" className="h-7 text-xs" onClick={() => setNotifDialogOpen(true)}>
                      <Plus className="mr-1.5 h-3 w-3" /> Send New
                    </Button>
                  </div>
                </CardHeader>
                <CardContent>
                  {!notifHistoryLoaded ? (
                    <div className="flex items-center justify-center py-8">
                      <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
                    </div>
                  ) : notifications.length === 0 ? (
                    <div className="text-center py-8">
                      <Bell className="mx-auto h-8 w-8 text-muted-foreground/40" />
                      <p className="mt-2 text-sm text-muted-foreground">No notifications sent yet</p>
                      <Button size="sm" className="mt-3 text-xs" onClick={() => setNotifDialogOpen(true)}>
                        Send First Notification
                      </Button>
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {notifications.map((n) => (
                        <div
                          key={n.id}
                          className={`rounded-lg border p-3 transition-colors ${
                            n.read ? 'border-border/50 bg-muted/10 opacity-70' : 'border-border bg-background'
                          }`}
                        >
                          <div className="flex items-start justify-between gap-3">
                            <div className="flex items-start gap-3 flex-1">
                              <div className="h-8 w-8 rounded-lg bg-primary/10 flex items-center justify-center shrink-0 mt-0.5">
                                <Bell className="h-4 w-4 text-primary" />
                              </div>
                              <div className="flex-1 min-w-0">
                                <p className="text-sm font-semibold">{n.title}</p>
                                <p className="text-xs text-muted-foreground mt-0.5">{n.body}</p>
                              </div>
                            </div>
                            <div className="flex items-center gap-2 shrink-0">
                              <Badge variant="secondary" className="text-[10px]">{n.category}</Badge>
                              <Badge variant="secondary" className={`text-[10px] ${n.read ? 'bg-success/10 text-success' : 'bg-chart-4/10 text-chart-4'}`}>
                                {n.read ? 'Read' : 'Unread'}
                              </Badge>
                            </div>
                          </div>
                          <p className="text-[10px] text-muted-foreground mt-2 pl-11">{n.created_at}</p>
                        </div>
                      ))}
                    </div>
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
          {reminderError && (
            <div className="flex items-center gap-2 text-sm text-destructive px-1">
              <AlertCircle className="h-4 w-4 shrink-0" />
              <span className="text-xs">{reminderError}</span>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => { setReminderDialogOpen(false); setReminderError(''); }} className="text-xs">Cancel</Button>
            <Button onClick={handleAddReminder} disabled={!newDrugName || !newDose || reminderSaving} className="text-xs">
              {reminderSaving ? (
                <><div className="mr-2 h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" /> Adding...</>
              ) : (
                <><Plus className="mr-1.5 h-3.5 w-3.5" /> Add Reminder</>
              )}
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
            {otpError && (
              <div className="mt-3 flex items-center gap-2 rounded-lg bg-destructive/5 border border-destructive/20 p-3">
                <AlertCircle className="h-4 w-4 text-destructive shrink-0" />
                <p className="text-xs font-medium text-destructive">{otpError}</p>
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

      {/* ── Send Notification Dialog ── */}
      <Dialog open={notifDialogOpen} onOpenChange={(open) => { if (!open) closeNotifDialog(); else setNotifDialogOpen(true); }}>
        <DialogContent className="sm:max-w-[520px]">
          <DialogHeader>
            <DialogTitle className="text-lg font-bold">Send Notification</DialogTitle>
            <DialogDescription className="text-sm">
              Push a notification to {member.first_name}'s device. They'll see it in the app and as a push alert.
            </DialogDescription>
          </DialogHeader>

          {!notifSent ? (
            <div className="space-y-4 py-2">
              {/* Quick templates */}
              <div className="space-y-2">
                <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Quick Templates</Label>
                <div className="flex flex-wrap gap-1.5">
                  {NOTIF_TEMPLATES.map((t) => (
                    <Button
                      key={t.label}
                      variant="outline"
                      size="sm"
                      className="h-7 text-[11px]"
                      onClick={() => { setNotifTitle(t.title); setNotifBody(t.body); }}
                    >
                      {t.label}
                    </Button>
                  ))}
                </div>
              </div>

              <div className="space-y-2">
                <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Category</Label>
                <Select value={notifCategory} onValueChange={setNotifCategory}>
                  <SelectTrigger className="h-9">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="general">General</SelectItem>
                    <SelectItem value="benefits_reminder">Benefits Reminder</SelectItem>
                    <SelectItem value="appointment">Appointment</SelectItem>
                    <SelectItem value="screening">Screening</SelectItem>
                    <SelectItem value="medication">Medication</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Title</Label>
                <Input
                  value={notifTitle}
                  onChange={(e) => setNotifTitle(e.target.value)}
                  placeholder="e.g. You still have $120 in OTC allowance!"
                  className="h-9"
                  maxLength={200}
                />
              </div>

              <div className="space-y-2">
                <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Message</Label>
                <textarea
                  value={notifBody}
                  onChange={(e) => setNotifBody(e.target.value)}
                  placeholder="Write a message for the member..."
                  className="flex w-full rounded-md border border-input bg-muted/30 px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring resize-none"
                  rows={3}
                  maxLength={1000}
                />
                <p className="text-[10px] text-muted-foreground text-right">{notifBody.length}/1000</p>
              </div>

              {notifError && (
                <div className="flex items-center gap-2 text-sm text-destructive">
                  <AlertCircle className="h-4 w-4 shrink-0" />
                  <span className="text-xs">{notifError}</span>
                </div>
              )}
            </div>
          ) : (
            <div className="py-6">
              <div className="rounded-lg border border-success/30 bg-success/5 p-4 text-center">
                <Check className="mx-auto h-8 w-8 text-success mb-2" />
                <p className="text-sm font-semibold text-success">Notification Sent!</p>
                {notifResult && (
                  <div className="mt-2 space-y-1">
                    <p className="text-xs text-muted-foreground">
                      Push delivery: {notifResult.push_delivered ? (
                        <span className="text-success font-medium">Delivered</span>
                      ) : notifResult.push_tokens_found === 0 ? (
                        <span className="text-warning font-medium">No push token registered (member hasn't enabled notifications)</span>
                      ) : (
                        <span className="text-warning font-medium">Failed — saved to inbox</span>
                      )}
                    </p>
                  </div>
                )}
              </div>
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={closeNotifDialog} className="text-xs">
              {notifSent ? 'Close' : 'Cancel'}
            </Button>
            {!notifSent && (
              <Button onClick={handleSendNotification} disabled={!notifTitle || !notifBody || notifSending} className="text-xs">
                {notifSending ? (
                  <><div className="mr-2 h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" /> Sending...</>
                ) : (
                  <><Bell className="mr-1.5 h-3.5 w-3.5" /> Send Notification</>
                )}
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
      {/* ── Call Note Dialog ── */}
      <Dialog open={callNoteDialogOpen} onOpenChange={(open) => { setCallNoteDialogOpen(open); if (!open) { setNoteError(''); setNoteResult(null); } }}>
        <DialogContent className="sm:max-w-[520px]">
          <DialogHeader>
            <DialogTitle className="text-lg font-bold">Log Call Note</DialogTitle>
            <DialogDescription className="text-sm">
              Record a call interaction with {member.first_name}. Notes will be saved locally and optionally synced to Zoho CRM.
            </DialogDescription>
          </DialogHeader>

          {!noteResult ? (
            <div className="space-y-4 py-2">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Call Type</Label>
                  <Select value={noteCallType} onValueChange={setNoteCallType}>
                    <SelectTrigger className="h-9">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="outbound">Outbound</SelectItem>
                      <SelectItem value="inbound">Inbound</SelectItem>
                      <SelectItem value="follow_up">Follow-up</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Duration (minutes)</Label>
                  <Input type="number" value={noteDuration} onChange={(e) => setNoteDuration(e.target.value)} placeholder="e.g. 15" className="h-9" />
                </div>
              </div>

              <div className="space-y-2">
                <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Subject</Label>
                <Input value={noteSubject} onChange={(e) => setNoteSubject(e.target.value)} placeholder="e.g. Benefits review, Appointment scheduling" className="h-9" maxLength={200} />
              </div>

              <div className="space-y-2">
                <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Notes</Label>
                <textarea
                  value={noteBody}
                  onChange={(e) => setNoteBody(e.target.value)}
                  placeholder="Describe the call interaction, topics discussed, action items..."
                  className="flex w-full rounded-md border border-input bg-muted/30 px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring resize-none"
                  rows={4}
                  maxLength={5000}
                />
                <p className="text-[10px] text-muted-foreground text-right">{noteBody.length}/5000</p>
              </div>

              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="syncZoho"
                  checked={noteSyncToZoho}
                  onChange={(e) => setNoteSyncToZoho(e.target.checked)}
                  className="h-4 w-4 rounded border-input"
                />
                <label htmlFor="syncZoho" className="text-xs text-muted-foreground">
                  Sync to Zoho CRM (add as note on contact record)
                </label>
              </div>

              {noteError && (
                <div className="flex items-center gap-2 text-sm text-destructive">
                  <AlertCircle className="h-4 w-4 shrink-0" />
                  <span className="text-xs">{noteError}</span>
                </div>
              )}
            </div>
          ) : (
            <div className="py-6">
              <div className="rounded-lg border border-success/30 bg-success/5 p-4 text-center">
                <Check className="mx-auto h-8 w-8 text-success mb-2" />
                <p className="text-sm font-semibold text-success">Call Note Saved</p>
                <div className="mt-2">
                  {noteResult.zoho_synced ? (
                    <p className="text-xs text-success flex items-center justify-center gap-1">
                      <RefreshCw className="h-3 w-3" /> Synced to Zoho CRM
                    </p>
                  ) : noteResult.zoho_error ? (
                    <p className="text-xs text-warning">
                      Zoho sync failed: {noteResult.zoho_error} (saved locally)
                    </p>
                  ) : (
                    <p className="text-xs text-muted-foreground">Saved locally (Zoho sync not requested)</p>
                  )}
                </div>
              </div>
            </div>
          )}

          <DialogFooter>
            <Button variant="outline" onClick={() => { setCallNoteDialogOpen(false); setNoteResult(null); setNoteError(''); }} className="text-xs">
              {noteResult ? 'Close' : 'Cancel'}
            </Button>
            {!noteResult && (
              <Button onClick={handleCreateCallNote} disabled={!noteSubject || !noteBody || noteSaving} className="text-xs">
                {noteSaving ? (
                  <><div className="mr-2 h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" /> Saving...</>
                ) : (
                  <><NotebookPen className="mr-1.5 h-3.5 w-3.5" /> Save Note</>
                )}
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
