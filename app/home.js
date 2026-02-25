import { useState, useEffect, useCallback } from 'react';
import { View, StyleSheet } from 'react-native';
// import GradientBg from '../components/GradientBg';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useLocalSearchParams } from 'expo-router';
import { COLORS } from '../constants/theme';
import { API_URL } from '../constants/api';
import ProfileCard from '../components/ProfileCard';
import VoiceHelp from '../components/VoiceHelp';
import SOBModal from '../components/SOBModal';

export default function HomeScreen() {
  const { firstName, lastName, planName, planNumber, agent, phone, zipCode } = useLocalSearchParams();
  const [showSOB, setShowSOB] = useState(false);
  const [benefits, setBenefits] = useState([]);
  const [loading, setLoading] = useState(true);
  const [sobData, setSobData] = useState(null);
  const [sobLoading, setSobLoading] = useState(false);

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
    if (!planNumber) {
      setLoading(false);
      return;
    }
    loadAllBenefits();
  }, [planNumber]);

  const loadSOBData = useCallback(async () => {
    if (!planNumber) return;
    setSobLoading(true);
    try {
      const res = await fetch(`${API_URL}/sob/summary`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ plan_number: planNumber }),
      });
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
    loadSOBData();          // always fetch fresh — no stale cache
  }, [loadSOBData]);

  const loadAllBenefits = async () => {
    setLoading(true);
    try {
      // Fetch CMS benefits and my-drugs in parallel
      const [benefitsRes, drugsRes] = await Promise.all([
        fetch(`${API_URL}/cms/benefits/${planNumber}`).then(r => r.json()).catch(() => null),
        phone
          ? fetch(`${API_URL}/cms/my-drugs/${phone}`).then(r => r.json()).catch(() => null)
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

  return (
    <View style={styles.container}>
      <SafeAreaView style={styles.safe} edges={['top']}>
        <ProfileCard
          member={member}
          onViewSOB={handleOpenSOB}
          benefits={benefits}
          loading={loading}
        />
        <VoiceHelp planNumber={planNumber || ''} planName={planName || ''} zipCode={zipCode || '33434'} />
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
 *
 * Row 2 combos:
 *   Rx + Dental + Part B + OTC  (4 cards)
 *   Rx + Dental + OTC + Flex    (4 cards)
 *   Rx + Dental + OTC           (3 cards)
 *   Rx + Dental                 (2 cards)
 *   etc.
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

  // Monthly Rx cost (always first in row 2 if member has meds)
  if (drugsData && drugsData.has_medications) {
    row2.push({
      label: 'Est. Monthly Rx',
      in_network: String(drugsData.monthly_display) + '/mo',
    });
  }

  // Dental — show annual max if available, otherwise $0 copay
  if (dental.has_preventive && dental.preventive) {
    const maxBenefit = dental.preventive.max_benefit;
    const dentalValue = maxBenefit ? `${maxBenefit}/yr max` : '$0 copay';
    row2.push({ label: 'Dental', in_network: dentalValue });
  }

  // Part B Giveback
  if (giveback.has_giveback && giveback.monthly_amount) {
    row2.push({
      label: 'Part B Giveback',
      in_network: '$' + String(giveback.monthly_amount) + '/mo',
    });
  }

  // OTC Allowance
  if (otc.has_otc && otc.amount) {
    const period = otc.period === 'Monthly' ? '/mo' : otc.period === 'Quarterly' ? '/qtr' : '/yr';
    // amount may already include $ from backend (e.g. "$50")
    const amt = String(otc.amount);
    const display = amt.startsWith('$') ? amt : '$' + amt;
    row2.push({
      label: 'OTC Allowance',
      in_network: display + period,
    });
  }

  // Flex Card (only if no Part B Giveback — plans have either Giveback+OTC or OTC+Flex)
  if (!giveback.has_giveback && flex.has_ssbci && flex.benefits && flex.benefits.length > 0) {
    row2.push({ label: 'Flex Card', in_network: 'Included' });
  }

  // Tag rows so ProfileCard knows how to lay them out
  row1.forEach(c => { c._row = 1; });
  row2.forEach(c => { c._row = 2; });

  return [...row1, ...row2];
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.bg },
  safe: { flex: 1 },
});