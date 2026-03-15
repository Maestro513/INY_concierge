import { useState, useEffect } from 'react';
import {
  Megaphone, Plus, Send, Users, Clock, CheckCircle,
  XCircle, AlertCircle, Eye,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import client from '@/api/client';
import { ENDPOINTS } from '@/config/api';

interface Campaign {
  id: number;
  name: string;
  cohort_type: string;
  cohort_filter: Record<string, unknown>;
  message_template: string;
  status: string;
  total_recipients: number;
  sent_count: number;
  failed_count: number;
  created_by: string;
  created_at: string;
  sent_at: string | null;
}

const COHORT_LABELS: Record<string, string> = {
  screening_gap: 'Screening Gaps',
  otc_underuse: 'Unused OTC Allowance',
  sdoh_flag: 'SDoH Risk Flags',
  custom: 'Custom Phone List',
};

const GAP_TYPES = [
  { value: 'colonoscopy', label: 'Colonoscopy' },
  { value: 'flu', label: 'Flu Shot' },
  { value: 'awv', label: 'Annual Wellness Visit' },
  { value: 'cholesterol', label: 'Cholesterol Screening' },
  { value: 'a1c', label: 'Diabetes (A1C)' },
  { value: 'mammogram', label: 'Mammogram' },
  { value: 'prostate', label: 'Prostate Screening' },
  { value: 'bone_density', label: 'Bone Density' },
];

const SDOH_FLAG_TYPES = [
  { value: 'transportation', label: 'Transportation Issues' },
  { value: 'food_insecurity', label: 'Food Insecurity' },
  { value: 'social_isolation', label: 'Social Isolation' },
  { value: 'housing_stability', label: 'Housing Instability' },
];

const SMS_TEMPLATES = [
  {
    label: 'Screening Reminder',
    message: 'Hi {name}, this is your Insurance NY concierge team. Our records show you may be due for a health screening. Call us at (XXX) XXX-XXXX to schedule — it\'s covered by your plan at no cost!',
  },
  {
    label: 'OTC Allowance',
    message: 'Hi {name}, don\'t forget — you have unused OTC allowance on your plan! Use it for vitamins, first aid, and more. Call your concierge at (XXX) XXX-XXXX for help.',
  },
  {
    label: 'Wellness Check-in',
    message: 'Hi {name}, your Insurance NY concierge team is checking in. We\'re here to help with appointments, prescriptions, or any questions about your plan. Reply or call (XXX) XXX-XXXX.',
  },
];

export default function CampaignsPage() {
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [sendingId, setSendingId] = useState<number | null>(null);
  const [previewData, setPreviewData] = useState<{ total: number; sample: { phone_last4: string }[] } | null>(null);
  const [previewingId, setPreviewingId] = useState<number | null>(null);

  // Create form state
  const [name, setName] = useState('');
  const [cohortType, setCohortType] = useState('screening_gap');
  const [gapType, setGapType] = useState('');
  const [sdohFlag, setSdohFlag] = useState('');
  const [minUnused, setMinUnused] = useState('100');
  const [messageTemplate, setMessageTemplate] = useState('');
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState('');

  // Send result
  const [sendResult, setSendResult] = useState<{ sent: number; failed: number; total: number } | null>(null);

  useEffect(() => {
    loadCampaigns();
  }, []);

  async function loadCampaigns() {
    try {
      const res = await client.get(ENDPOINTS.CAMPAIGNS);
      setCampaigns(res.data?.campaigns || []);
    } catch {
      // Handle error silently
    } finally {
      setLoading(false);
    }
  }

  async function handleCreate() {
    setCreating(true);
    setCreateError('');
    try {
      const cohortFilter: Record<string, unknown> = {};
      if (cohortType === 'screening_gap' && gapType) cohortFilter.gap_type = gapType;
      if (cohortType === 'sdoh_flag' && sdohFlag) cohortFilter.flag_type = sdohFlag;
      if (cohortType === 'otc_underuse') cohortFilter.min_unused = parseFloat(minUnused) || 100;

      await client.post(ENDPOINTS.CAMPAIGNS, {
        name,
        cohort_type: cohortType,
        cohort_filter: cohortFilter,
        message_template: messageTemplate,
      });
      setCreateOpen(false);
      resetForm();
      loadCampaigns();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to create campaign';
      setCreateError(msg);
    } finally {
      setCreating(false);
    }
  }

  async function handlePreview(campaignId: number) {
    setPreviewingId(campaignId);
    try {
      const res = await client.get(ENDPOINTS.CAMPAIGN_PREVIEW(campaignId));
      setPreviewData(res.data);
    } catch {
      setPreviewData(null);
    } finally {
      setPreviewingId(null);
    }
  }

  async function handleSend(campaignId: number) {
    if (!confirm('Are you sure you want to send this campaign? SMS messages will be sent to all matching members.')) {
      return;
    }
    setSendingId(campaignId);
    setSendResult(null);
    try {
      const res = await client.post(ENDPOINTS.CAMPAIGN_SEND(campaignId));
      setSendResult({
        sent: res.data.sent,
        failed: res.data.failed,
        total: res.data.total_recipients,
      });
      loadCampaigns();
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'Send failed';
      alert(detail);
    } finally {
      setSendingId(null);
    }
  }

  function resetForm() {
    setName('');
    setCohortType('screening_gap');
    setGapType('');
    setSdohFlag('');
    setMinUnused('100');
    setMessageTemplate('');
    setCreateError('');
  }

  function statusBadge(status: string) {
    switch (status) {
      case 'draft':
        return <Badge variant="secondary" className="text-[10px]">Draft</Badge>;
      case 'sent':
        return <Badge className="text-[10px] bg-success/10 text-success border-success/20">Sent</Badge>;
      case 'sending':
        return <Badge className="text-[10px] bg-chart-4/10 text-chart-4 border-chart-4/20">Sending</Badge>;
      default:
        return <Badge variant="secondary" className="text-[10px]">{status}</Badge>;
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Campaigns</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Create and send bulk SMS outreach to targeted member cohorts.
          </p>
        </div>
        <Button onClick={() => setCreateOpen(true)} className="text-xs">
          <Plus className="mr-1.5 h-3.5 w-3.5" /> New Campaign
        </Button>
      </div>

      {/* Send Result Banner */}
      {sendResult && (
        <Card className="border-success/30 bg-success/5">
          <CardContent className="pt-4 pb-4">
            <div className="flex items-center gap-3">
              <CheckCircle className="h-5 w-5 text-success shrink-0" />
              <div>
                <p className="text-sm font-semibold">Campaign Sent</p>
                <p className="text-xs text-muted-foreground">
                  {sendResult.sent} delivered, {sendResult.failed} failed out of {sendResult.total} recipients
                </p>
              </div>
              <Button variant="ghost" size="sm" className="ml-auto text-xs" onClick={() => setSendResult(null)}>
                Dismiss
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Campaigns List */}
      <Card className="border-border/50 shadow-sm">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-semibold">All Campaigns</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="space-y-3">
              {[1, 2, 3].map((i) => <Skeleton key={i} className="h-20 w-full rounded-lg" />)}
            </div>
          ) : campaigns.length === 0 ? (
            <div className="text-center py-12">
              <Megaphone className="mx-auto h-10 w-10 text-muted-foreground/40" />
              <p className="mt-3 text-sm text-muted-foreground">No campaigns yet</p>
              <Button size="sm" className="mt-3 text-xs" onClick={() => setCreateOpen(true)}>
                Create First Campaign
              </Button>
            </div>
          ) : (
            <div className="space-y-3">
              {campaigns.map((c) => (
                <div key={c.id} className="rounded-lg border border-border/50 p-4 transition-colors hover:bg-muted/20">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <p className="text-sm font-semibold">{c.name}</p>
                        {statusBadge(c.status)}
                      </div>
                      <div className="flex items-center gap-4 mt-1.5">
                        <span className="text-[11px] text-muted-foreground flex items-center gap-1">
                          <Users className="h-3 w-3" /> {COHORT_LABELS[c.cohort_type] || c.cohort_type}
                        </span>
                        <span className="text-[11px] text-muted-foreground flex items-center gap-1">
                          <Clock className="h-3 w-3" /> {c.created_at}
                        </span>
                        {c.status === 'sent' && (
                          <>
                            <span className="text-[11px] text-success flex items-center gap-1">
                              <CheckCircle className="h-3 w-3" /> {c.sent_count} sent
                            </span>
                            {c.failed_count > 0 && (
                              <span className="text-[11px] text-destructive flex items-center gap-1">
                                <XCircle className="h-3 w-3" /> {c.failed_count} failed
                              </span>
                            )}
                          </>
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground mt-2 line-clamp-2">{c.message_template}</p>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      {c.status === 'draft' && (
                        <>
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-7 text-[11px]"
                            onClick={() => handlePreview(c.id)}
                            disabled={previewingId === c.id}
                          >
                            <Eye className="mr-1 h-3 w-3" />
                            {previewingId === c.id ? 'Loading...' : 'Preview'}
                          </Button>
                          <Button
                            size="sm"
                            className="h-7 text-[11px]"
                            onClick={() => handleSend(c.id)}
                            disabled={sendingId === c.id}
                          >
                            {sendingId === c.id ? (
                              <div className="h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent mr-1" />
                            ) : (
                              <Send className="mr-1 h-3 w-3" />
                            )}
                            Send
                          </Button>
                        </>
                      )}
                    </div>
                  </div>

                  {/* Inline preview */}
                  {previewData && previewingId === null && c.status === 'draft' && (
                    <div className="mt-3 rounded-md bg-muted/30 border border-border/50 p-3">
                      <p className="text-xs font-semibold">
                        Cohort Preview: {previewData.total} recipient{previewData.total !== 1 ? 's' : ''}
                      </p>
                      {previewData.sample.length > 0 && (
                        <p className="text-[11px] text-muted-foreground mt-1">
                          Sample: {previewData.sample.map((s) => `...${s.phone_last4}`).join(', ')}
                          {previewData.total > 10 && ` and ${previewData.total - 10} more`}
                        </p>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Create Campaign Dialog */}
      <Dialog open={createOpen} onOpenChange={(open) => { if (!open) resetForm(); setCreateOpen(open); }}>
        <DialogContent className="sm:max-w-[560px]">
          <DialogHeader>
            <DialogTitle className="text-lg font-bold">New Campaign</DialogTitle>
            <DialogDescription className="text-sm">
              Target a specific cohort and compose an SMS message. Campaign will be saved as draft first.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-2">
            <div className="space-y-2">
              <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Campaign Name</Label>
              <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Q1 Colonoscopy Reminder" className="h-9" maxLength={200} />
            </div>

            <div className="space-y-2">
              <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Target Cohort</Label>
              <Select value={cohortType} onValueChange={setCohortType}>
                <SelectTrigger className="h-9">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="screening_gap">Members with Screening Gaps</SelectItem>
                  <SelectItem value="otc_underuse">Members with Unused OTC Allowance</SelectItem>
                  <SelectItem value="sdoh_flag">Members with SDoH Risk Flags</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Dynamic filter based on cohort type */}
            {cohortType === 'screening_gap' && (
              <div className="space-y-2">
                <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Screening Type (optional)</Label>
                <Select value={gapType} onValueChange={setGapType}>
                  <SelectTrigger className="h-9">
                    <SelectValue placeholder="All gaps" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="">All gaps</SelectItem>
                    {GAP_TYPES.map((g) => (
                      <SelectItem key={g.value} value={g.value}>{g.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}

            {cohortType === 'otc_underuse' && (
              <div className="space-y-2">
                <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Minimum Unused Amount ($)</Label>
                <Input type="number" value={minUnused} onChange={(e) => setMinUnused(e.target.value)} placeholder="100" className="h-9" />
              </div>
            )}

            {cohortType === 'sdoh_flag' && (
              <div className="space-y-2">
                <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">Risk Flag (optional)</Label>
                <Select value={sdohFlag} onValueChange={setSdohFlag}>
                  <SelectTrigger className="h-9">
                    <SelectValue placeholder="All flags" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="">All flags</SelectItem>
                    {SDOH_FLAG_TYPES.map((f) => (
                      <SelectItem key={f.value} value={f.value}>{f.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}

            <div className="space-y-2">
              <Label className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">SMS Message</Label>
              <div className="flex flex-wrap gap-1.5 mb-2">
                {SMS_TEMPLATES.map((t) => (
                  <Button
                    key={t.label}
                    variant="outline"
                    size="sm"
                    className="h-6 text-[10px]"
                    onClick={() => setMessageTemplate(t.message)}
                  >
                    {t.label}
                  </Button>
                ))}
              </div>
              <textarea
                value={messageTemplate}
                onChange={(e) => setMessageTemplate(e.target.value)}
                placeholder="Type your SMS message..."
                className="flex w-full rounded-md border border-input bg-muted/30 px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring resize-none"
                rows={4}
                maxLength={1600}
              />
              <p className="text-[10px] text-muted-foreground text-right">{messageTemplate.length}/1600</p>
            </div>

            {createError && (
              <div className="flex items-center gap-2 text-sm text-destructive">
                <AlertCircle className="h-4 w-4 shrink-0" />
                <span className="text-xs">{createError}</span>
              </div>
            )}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => { setCreateOpen(false); resetForm(); }} className="text-xs">Cancel</Button>
            <Button onClick={handleCreate} disabled={!name || !messageTemplate || creating} className="text-xs">
              {creating ? (
                <><div className="mr-2 h-3 w-3 animate-spin rounded-full border-2 border-current border-t-transparent" /> Creating...</>
              ) : (
                <><Plus className="mr-1.5 h-3.5 w-3.5" /> Create Draft</>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
