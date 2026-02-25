import { useState, useEffect, useCallback } from 'react';
import { View, StyleSheet } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useLocalSearchParams } from 'expo-router';
import { COLORS } from '../constants/theme';
import { API_URL, fetchWithTimeout } from '../constants/api';
import ProfileCard from '../components/ProfileCard';
import VoiceHelp from '../components/VoiceHelp';
import SOBModal from '../components/SOBModal';
import MedReminders from '../components/MedReminders';
import UsageTracker from '../components/UsageTracker';
import {
  syncAllReminders, scheduleReminder, cancelReminder,
  cacheReminders, getCachedReminders,
  cacheUsageSummary, getCachedUsageSummary,
  requestNotificationPermissions,
} from '../utils/notifications';

export default function HomeScreen() {
  const { firstName, lastName, planName, planNumber, agent, sessionId, zipCode } = useLocalSearchParams();
  const [showSOB, setShowSOB] = useState(false);
  const [benefits, setBenefits] = useState([]);
  const [loading, setLoading] = useState(true);
  const [sobData, setSobData] = useState(null);
  const [sobLoading, setSobLoading] = useState(false);

  // Reminders state
  const [reminders, setReminders] = useState([]);
  const [remindersLoading, setRemindersLoading] = useState(true);

  // Usage tracking state
  const [usageSummary, setUsageSummary] = useState([]);
  const [usageLoading, setUsageLoading] = useState(true);

  const member = {
    firstName: firstName || '',
    lastName: lastName || '',
    planName: planName || '',
    planNumber: planNumber || '',
    agent: agent || '',
  };

  useEffect(() => {
    // Reset all state when plan changes (e.g. user logs out and back in)
    setBenefits([]);
    setSobData(null);
    setReminders([]);
    setUsageSummary([]);
    if (!planNumber) {
      setLoading(false);
      setRemindersLoading(false);
      setUsageLoading(false);
      return;
    }
    loadAllBenefits();
    if (sessionId) {
      loadReminders();
      loadUsageSummary();
    }
  }, [planNumber]);

  // ── SOB ─────────────────────────────────────────────────────────

  const loadSOBData = useCallback(async () => {
    if (!planNumber) return;
    setSobLoading(true);
    try {
      const res = await fetchWithTimeout(`${API_URL}/sob/summary`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ plan_number: planNumber }),
      }, 30000);
      if (!res.ok) throw new Error('SOB fetch failed');
      const data = await res.json();
      setSobData(data);
    } catch (err) {
      console.log('SOB fetch error:', err);
      setSobData(null);
    } finally {
      setSobLoading(false);
    }
  }, [planNumber]);

  const handleOpenSOB = useCallback(() => {
    setShowSOB(true);
    loadSOBData();
  }, [loadSOBData]);

  // ── Benefits ────────────────────────────────────────────────────

  const loadAllBenefits = async () => {
    setLoading(true);
    try {
      const [benefitsRes, drugsRes] = await Promise.all([
        fetchWithTimeout(`${API_URL}/cms/benefits/${planNumber}`).then(r => r.json()).catch(() => null),
        sessionId
          ? fetchWithTimeout(`${API_URL}/cms/my-drugs-session/${sessionId}`).then(r => r.json()).catch(() => null)
          : Promise.resolve(null),
      ]);
      const cards = buildBenefitCards(benefitsRes, drugsRes);
      setBenefits(cards);
    } catch (err) {
      console.log('Benefits fetch error:', err);
      setBenefits([]);
    } finally {
      setLoading(false);
    }
  };

  // ── Reminders ───────────────────────────────────────────────────

  const loadReminders = async () => {
    setRemindersLoading(true);
    // Show cached data instantly
    const cached = await getCachedReminders();
    if (cached) setReminders(cached);

    try {
      const res = await fetchWithTimeout(`${API_URL}/reminders/${sessionId}`);
      if (!res.ok) throw new Error('Reminders fetch failed');
      const data = await res.json();
      setReminders(data.reminders);
      cacheReminders(data.reminders);
      // Sync local notifications
      syncAllReminders(data.reminders);
    } catch (err) {
      console.log('Reminders fetch error:', err);
    } finally {
      setRemindersLoading(false);
    }
  };

  const handleAddReminder = useCallback(async (reminderData) => {
    // Request notification permission on first reminder creation
    await requestNotificationPermissions();

    try {
      const res = await fetchWithTimeout(`${API_URL}/reminders/${sessionId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(reminderData),
      });
      if (!res.ok) throw new Error('Create reminder failed');
      const data = await res.json();
      const newReminder = data.reminder;

      setReminders((prev) => {
        const updated = [...prev, newReminder].sort(
          (a, b) => a.time_hour * 60 + a.time_minute - (b.time_hour * 60 + b.time_minute),
        );
        cacheReminders(updated);
        return updated;
      });
      // Schedule the local notification
      scheduleReminder(newReminder);
    } catch (err) {
      console.log('Create reminder error:', err);
    }
  }, [sessionId]);

  const handleToggleReminder = useCallback(async (reminderId, enabled) => {
    // Optimistic update
    setReminders((prev) => {
      const updated = prev.map((r) => (r.id === reminderId ? { ...r, enabled: enabled ? 1 : 0 } : r));
      cacheReminders(updated);
      return updated;
    });

    try {
      await fetchWithTimeout(`${API_URL}/reminders/${sessionId}/${reminderId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled }),
      });
      // Update local notification
      const reminder = reminders.find((r) => r.id === reminderId);
      if (reminder) {
        if (enabled) {
          scheduleReminder({ ...reminder, enabled: 1 });
        } else {
          cancelReminder(reminderId);
        }
      }
    } catch (err) {
      console.log('Toggle reminder error:', err);
      loadReminders(); // Revert on error
    }
  }, [sessionId, reminders]);

  const handleDeleteReminder = useCallback(async (reminderId) => {
    // Optimistic update
    setReminders((prev) => {
      const updated = prev.filter((r) => r.id !== reminderId);
      cacheReminders(updated);
      return updated;
    });
    cancelReminder(reminderId);

    try {
      await fetchWithTimeout(`${API_URL}/reminders/${sessionId}/${reminderId}`, {
        method: 'DELETE',
      });
    } catch (err) {
      console.log('Delete reminder error:', err);
      loadReminders(); // Revert on error
    }
  }, [sessionId]);

  // ── Usage Tracking ──────────────────────────────────────────────

  const loadUsageSummary = async () => {
    setUsageLoading(true);
    const cached = await getCachedUsageSummary();
    if (cached) setUsageSummary(cached);

    try {
      const res = await fetchWithTimeout(`${API_URL}/usage/${sessionId}/summary`);
      if (!res.ok) throw new Error('Usage summary fetch failed');
      const data = await res.json();
      setUsageSummary(data.summary);
      cacheUsageSummary(data.summary);
    } catch (err) {
      console.log('Usage summary fetch error:', err);
    } finally {
      setUsageLoading(false);
    }
  };

  const handleLogUsage = useCallback(async (usageData) => {
    try {
      const res = await fetchWithTimeout(`${API_URL}/usage/${sessionId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(usageData),
      });
      if (!res.ok) throw new Error('Log usage failed');
      // Refresh summary to get updated totals
      loadUsageSummary();
    } catch (err) {
      console.log('Log usage error:', err);
    }
  }, [sessionId]);

  // ── Render ──────────────────────────────────────────────────────

  return (
    <View style={styles.container}>
      <SafeAreaView style={styles.safe} edges={['top']}>
        <ProfileCard
          member={member}
          onViewSOB={handleOpenSOB}
          benefits={benefits}
          loading={loading}
        />
        <MedReminders
          reminders={reminders}
          loading={remindersLoading}
          onToggle={handleToggleReminder}
          onDelete={handleDeleteReminder}
          onAdd={handleAddReminder}
        />
        <UsageTracker
          summary={usageSummary}
          loading={usageLoading}
          onLogUsage={handleLogUsage}
        />
        <VoiceHelp
          planNumber={planNumber || ''}
          planName={planName || ''}
          zipCode={zipCode || '33434'}
          sessionId={sessionId || ''}
          onReminderCreated={loadReminders}
          onUsageLogged={loadUsageSummary}
        />
        <SOBModal
          visible={showSOB}
          onClose={() => setShowSOB(false)}
          member={member}
          sobData={sobData}
          loading={sobLoading}
          onRetry={loadSOBData}
        />
      </SafeAreaView>
    </View>
  );
}

/**
 * Build benefit cards from CMS data + drug costs.
 *
 * Row 1 (always 4): PCP, Specialist, Urgent Care, ER
 * Row 2 (flexible 2-4): Monthly Rx, Dental, Part B Giveback, OTC, Flex
 */
function buildBenefitCards(data, drugsData) {
  if (!data) return [];
  const row1 = [];
  const row2 = [];
  const med = data.medical || {};
  const dental = data.dental || {};
  const otc = data.otc || {};
  const flex = data.flex_ssbci || {};
  const giveback = data.part_b_giveback || {};

  // --- Row 1: Medical copays (always 4) ---
  if (med.pcp_copay) {
    row1.push({ label: 'PCP Visit', in_network: String(med.pcp_copay) });
  }
  if (med.specialist_copay) {
    row1.push({ label: 'Specialist', in_network: String(med.specialist_copay) });
  }
  if (med.urgent_care_copay) {
    row1.push({ label: 'Urgent Care', in_network: String(med.urgent_care_copay) });
  }
  if (med.er_copay) {
    row1.push({ label: 'Emergency', in_network: String(med.er_copay) });
  } else if (med.pcp_copay) {
    row1.push({ label: 'Emergency', in_network: '$0' });
  }

  // --- Row 2: Rx cost + supplementals ---
  if (drugsData && drugsData.has_medications) {
    row2.push({
      label: 'Est. Monthly Rx',
      in_network: String(drugsData.monthly_display) + '/mo',
    });
  }

  if (dental.has_preventive && dental.preventive) {
    const maxBenefit = dental.preventive.max_benefit;
    const dentalValue = maxBenefit ? `${maxBenefit}/yr max` : '$0 copay';
    row2.push({ label: 'Dental', in_network: dentalValue });
  }

  if (giveback.has_giveback && giveback.monthly_amount) {
    row2.push({
      label: 'Part B Giveback',
      in_network: '$' + String(giveback.monthly_amount) + '/mo',
    });
  }

  if (otc.has_otc && otc.amount) {
    const period = otc.period === 'Monthly' ? '/mo' : otc.period === 'Quarterly' ? '/qtr' : '/yr';
    const amt = String(otc.amount);
    const display = amt.startsWith('$') ? amt : '$' + amt;
    row2.push({
      label: 'OTC Allowance',
      in_network: display + period,
    });
  }

  if (!giveback.has_giveback && flex.has_ssbci && flex.benefits && flex.benefits.length > 0) {
    row2.push({ label: 'Flex Card', in_network: 'Included' });
  }

  row1.forEach(c => { c._row = 1; });
  row2.forEach(c => { c._row = 2; });

  return [...row1, ...row2];
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.bg },
  safe: { flex: 1 },
});
