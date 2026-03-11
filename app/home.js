import { useState, useEffect, useCallback } from 'react';
import { View, StyleSheet, Platform, Alert } from 'react-native';
import { SafeAreaView, useSafeAreaInsets } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { COLORS } from '../constants/theme';
import { API_URL, authFetch } from '../constants/api';
import { cachedFetch } from '../utils/offlineCache';
import { getMemberSession, logout } from '../constants/session';
import ProfileCard from '../components/ProfileCard';
import VoiceHelp from '../components/VoiceHelp';
import SOBModal from '../components/SOBModal';
import {
  syncAllReminders, scheduleReminder, cancelReminder,
  cacheReminders, getCachedReminders,
  cacheUsageSummary, getCachedUsageSummary,
  requestNotificationPermissions,
} from '../utils/notifications';

export default function HomeScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { member: _mem, sessionId } = getMemberSession();
  const { firstName, lastName, planName, planNumber, agent, medicareNumber, zipCode } = _mem || {};
  const [showSOB, setShowSOB] = useState(false);
  const [benefits, setBenefits] = useState([]);
  const [loading, setLoading] = useState(true);
  const [benefitsError, setBenefitsError] = useState('');
  const [sobData, setSobData] = useState(null);
  const [sobLoading, setSobLoading] = useState(false);

  // Reminders state
  const [reminders, setReminders] = useState([]);
  const [remindersLoading, setRemindersLoading] = useState(true);

  // Drug data (for Rx card tap detail)
  const [drugsData, setDrugsData] = useState(null);

  // Usage tracking state
  const [usageSummary, setUsageSummary] = useState([]);
  const [usageLoading, setUsageLoading] = useState(true);

  const member = {
    firstName: firstName || '',
    lastName: lastName || '',
    planName: planName || '',
    planNumber: planNumber || '',
    agent: agent || '',
    medicareNumber: medicareNumber || '',
  };

  useEffect(() => {
    // Reset all state when plan changes (e.g. user logs out and back in)
    setBenefits([]);
    setBenefitsError(false);
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
      const res = await authFetch(`${API_URL}/sob/summary`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ plan_number: planNumber }),
      }, 30000);
      if (!res.ok) throw new Error('SOB fetch failed');
      const data = await res.json();
      setSobData(data);
    } catch (err) {
      if (__DEV__) console.log('SOB fetch error:', err);
      setSobData(null);
    } finally {
      setSobLoading(false);
    }
  }, [planNumber]);

  const handleOpenSOB = useCallback(() => {
    setShowSOB(true);
    loadSOBData();
  }, [loadSOBData]);

  const handleViewIDCard = () => {
    router.push('/digital-id');
  };

  const handleFindPharmacy = () => {
    router.push('/pharmacy-results');
  };

  // ── Benefits ────────────────────────────────────────────────────

  const loadAllBenefits = async () => {
    setLoading(true);
    setBenefitsError('');
    try {
      const benefitsUrl = `${API_URL}/benefits/${planNumber}`;
      const [benefitsResult, drugsRes] = await Promise.all([
        cachedFetch(authFetch, benefitsUrl)
          .then(r => r.data)
          .catch((err) => { if (__DEV__) console.warn('Benefits fetch error:', err); return null; }),
        sessionId
          ? authFetch(`${API_URL}/cms/my-drugs-session/${sessionId}`)
              .then(r => {
                if (!r.ok) {
                  if (__DEV__) {
                    const errBody = await r.text().catch(() => '');
                    console.warn(`Drugs fetch failed: ${r.status} ${errBody}`);
                  }
                  return null;
                }
                return r.json();
              })
              .catch((err) => { if (__DEV__) console.warn('Drugs fetch error:', err); return null; })
          : Promise.resolve(null),
      ]);
      if (!benefitsResult) {
        setBenefitsError('server');
        setBenefits([]);
      } else {
        const cards = buildBenefitCards(benefitsResult, drugsRes);
        setBenefits(cards);
      }
      if (drugsRes) setDrugsData(drugsRes);
    } catch (err) {
      if (__DEV__) console.warn('Benefits load error:', err);
      const errType = (err.name === 'AbortError') ? 'timeout'
        : (err.message === 'Network request failed' || err.name === 'TypeError') ? 'network'
        : 'server';
      setBenefitsError(errType);
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
      const res = await authFetch(`${API_URL}/reminders/${sessionId}`);
      if (!res.ok) throw new Error('Reminders fetch failed');
      const data = await res.json();
      setReminders(data.reminders);
      cacheReminders(data.reminders);
      // Sync local notifications
      syncAllReminders(data.reminders);
    } catch (err) {
      if (__DEV__) console.log('Reminders fetch error:', err);
    } finally {
      setRemindersLoading(false);
    }
  };

  const handleAddReminder = useCallback(async (reminderData) => {
    // Request notification permission on first reminder creation
    await requestNotificationPermissions();

    try {
      const res = await authFetch(`${API_URL}/reminders/${sessionId}`, {
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
      if (__DEV__) console.log('Create reminder error:', err);
    }
  }, [sessionId]);

  const handleToggleReminder = useCallback(async (reminderId, enabled) => {
    // Optimistic update — use functional setter to avoid stale closure (H13)
    setReminders((prev) => {
      const updated = prev.map((r) => (r.id === reminderId ? { ...r, enabled: enabled ? 1 : 0 } : r));
      cacheReminders(updated);
      // Schedule/cancel notification from the fresh state
      const reminder = updated.find((r) => r.id === reminderId);
      if (reminder) {
        if (enabled) {
          scheduleReminder(reminder);
        } else {
          cancelReminder(reminderId);
        }
      }
      return updated;
    });

    try {
      await authFetch(`${API_URL}/reminders/${sessionId}/${reminderId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled }),
      });
    } catch (err) {
      if (__DEV__) console.log('Toggle reminder error:', err);
      loadReminders(); // Revert on error
    }
  }, [sessionId]);

  const handleDeleteReminder = useCallback(async (reminderId) => {
    // Optimistic update
    setReminders((prev) => {
      const updated = prev.filter((r) => r.id !== reminderId);
      cacheReminders(updated);
      return updated;
    });
    cancelReminder(reminderId);

    try {
      await authFetch(`${API_URL}/reminders/${sessionId}/${reminderId}`, {
        method: 'DELETE',
      });
    } catch (err) {
      if (__DEV__) console.log('Delete reminder error:', err);
      loadReminders(); // Revert on error
    }
  }, [sessionId]);

  // ── Usage Tracking ──────────────────────────────────────────────

  const loadUsageSummary = async () => {
    setUsageLoading(true);
    const cached = await getCachedUsageSummary();
    if (cached) setUsageSummary(cached);

    try {
      const res = await authFetch(`${API_URL}/usage/${sessionId}/summary`);
      if (!res.ok) throw new Error('Usage summary fetch failed');
      const data = await res.json();
      setUsageSummary(data.summary);
      cacheUsageSummary(data.summary);
    } catch (err) {
      if (__DEV__) console.log('Usage summary fetch error:', err);
    } finally {
      setUsageLoading(false);
    }
  };

  const handleLogUsage = useCallback(async (usageData) => {
    try {
      const res = await authFetch(`${API_URL}/usage/${sessionId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(usageData),
      });
      if (!res.ok) throw new Error('Log usage failed');
      // Refresh summary to get updated totals
      loadUsageSummary();
    } catch (err) {
      if (__DEV__) console.log('Log usage error:', err);
    }
  }, [sessionId]);

  // ── Logout ─────────────────────────────────────────────────────

  const handleLogout = useCallback(() => {
    Alert.alert(
      'Log Out',
      'Are you sure you want to log out? Your cached data will be cleared.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Log Out',
          style: 'destructive',
          onPress: async () => {
            await logout();
            router.replace('/');
          },
        },
      ],
    );
  }, [router]);

  // ── Render ──────────────────────────────────────────────────────

  return (
    <View style={[styles.container, { paddingBottom: Platform.OS === 'android' ? Math.max(insets.bottom, 24) : 0 }]}>
      <SafeAreaView style={styles.safe} edges={['top']}>
        <ProfileCard
          member={member}
          onViewSOB={handleOpenSOB}
          onViewIDCard={handleViewIDCard}
          benefits={benefits}
          loading={loading}
          benefitsError={benefitsError}
          onRetryBenefits={loadAllBenefits}
          reminders={reminders}
          onToggleReminder={handleToggleReminder}
          onDeleteReminder={handleDeleteReminder}
          onAddReminder={handleAddReminder}
          drugsData={drugsData}
          onLogout={handleLogout}
        />
        <VoiceHelp
          planNumber={planNumber || ''}
          planName={planName || ''}
          zipCode={zipCode || ''}
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
  if (!data || typeof data !== 'object') return [];
  const row1 = [];
  const row2 = [];
  const med = (data.medical && typeof data.medical === 'object') ? data.medical : {};
  const dental = (data.dental && typeof data.dental === 'object') ? data.dental : {};
  const otc = (data.otc && typeof data.otc === 'object') ? data.otc : {};
  const flex = (data.flex_ssbci && typeof data.flex_ssbci === 'object') ? data.flex_ssbci : {};
  const giveback = (data.part_b_giveback && typeof data.part_b_giveback === 'object') ? data.part_b_giveback : {};

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
    row1.push({ label: 'Emergency Room', in_network: String(med.er_copay) });
  } else if (med.pcp_copay) {
    row1.push({ label: 'Emergency Room', in_network: '$0' });
  }

  // --- Row 2: Rx cost + supplementals ---
  if (drugsData && drugsData.has_medications) {
    row2.push({
      label: 'Est. Annual Rx',
      in_network: String(drugsData.annual_display),
      _period: 'Per year',
    });
  }

  if (dental.has_preventive && dental.preventive) {
    const maxBenefit = dental.preventive.max_benefit;
    const dentalValue = maxBenefit || '$0 copay';
    row2.push({ label: 'Dental Max', in_network: dentalValue, _period: 'Per year' });
  }

  if (giveback.has_giveback && giveback.monthly_amount) {
    const amt = String(giveback.monthly_amount);
    const display = amt.startsWith('$') ? amt : '$' + amt;
    row2.push({
      label: 'Part B Giveback',
      in_network: display + '/mo',
    });
  }

  if (otc.has_otc && otc.amount) {
    const periodLabel = otc.period === 'Monthly' ? 'Per month' : otc.period === 'Quarterly' ? 'Per quarter' : 'Per year';
    const amt = String(otc.amount);
    const display = amt.startsWith('$') ? amt : '$' + amt;
    row2.push({
      label: 'OTC Allowance',
      in_network: display,
      _period: periodLabel,
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
  container: { flex: 1, backgroundColor: COLORS.white },
  safe: { flex: 1, backgroundColor: COLORS.bg },
});
