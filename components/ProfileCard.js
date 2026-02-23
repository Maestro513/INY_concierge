import { View, Text, TouchableOpacity, Image, StyleSheet, ActivityIndicator } from 'react-native';
import { COLORS, RADII, SPACING } from '../constants/theme';

// Carrier logo map — filenames must match assets/carriers/
const CARRIER_LOGOS = {
  humana: require('../assets/carriers/humana.png'),
  uhc: require('../assets/carriers/uhc.png'),
  aetna: require('../assets/carriers/aetna.png'),
  devoted: require('../assets/carriers/devoted.png'),
  wellcare: require('../assets/carriers/wellcare.png'),
  zing: require('../assets/carriers/zing.png'),
  healthspring: require('../assets/carriers/healthspring.png'),
};

function detectCarrier(planName) {
  if (!planName) return null;
  const name = planName.toLowerCase();
  if (name.includes('humana')) return 'humana';
  if (name.includes('uhc') || name.includes('unitedhealthcare') || name.includes('aarp')) return 'uhc';
  if (name.includes('aetna')) return 'aetna';
  if (name.includes('devoted')) return 'devoted';
  if (name.includes('wellcare')) return 'wellcare';
  if (name.includes('zing')) return 'zing';
  if (name.includes('healthspring')) return 'healthspring';
  return null;
}

const BENEFIT_ICONS = {
  'pcp': '🩺', 'primary': '🩺', 'doctor': '🩺',
  'specialist': '👨\u200D⚕️',
  'emergency': '🚑', 'er ': '🚑',
  'urgent': '🏥',
  'dental': '🦷',
  'vision': '👁', 'eye': '👁',
  'hearing': '👂',
  'hospital': '🏨', 'inpatient': '🏨',
  'mental': '🧠',
  'lab': '🔬', 'x-ray': '🔬',
  'drug': '💊', 'prescription': '💊', 'rx': '💊',
  'preventive': '✅',
  'telehealth': '📱',
  'otc': '🛒',
  'flex': '💳',
  'part b': '💰', 'giveback': '💰',
};

function pickIcon(label) {
  const lower = label.toLowerCase();
  for (const [key, icon] of Object.entries(BENEFIT_ICONS)) {
    if (lower.includes(key)) return icon;
  }
  return '📋';
}

export default function ProfileCard({ member, onViewSOB, benefits, loading }) {
  const greeting = () => {
    const hour = new Date().getHours();
    if (hour < 12) return 'Good morning,';
    if (hour < 17) return 'Good afternoon,';
    return 'Good evening,';
  };

  const carrier = detectCarrier(member.planName);
  const carrierLogo = carrier ? CARRIER_LOGOS[carrier] : null;

  // Split into row 1 (medical, always 4) and row 2 (supplementals, 2-4)
  const row1 = (benefits || []).filter(b => b._row === 1);
  const row2 = (benefits || []).filter(b => b._row === 2);

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <View style={{ flex: 1 }}>
          <Text style={styles.greeting}>{greeting()}</Text>
          <Text style={styles.name}>
            {member.firstName} {member.lastName}
          </Text>
          {member.agent ? (
            <Text style={styles.agent}>{'Agent: ' + member.agent}</Text>
          ) : null}
        </View>
        {carrierLogo ? (
          <Image source={carrierLogo} style={styles.carrierLogo} resizeMode="contain" />
        ) : null}
      </View>

      <View style={styles.planRow}>
        <Text style={styles.planName}>{member.planName}</Text>
        <TouchableOpacity onPress={onViewSOB}>
          <Text style={styles.sobLink}>{'View SOB \u2192'}</Text>
        </TouchableOpacity>
      </View>

      {loading ? (
        <View style={styles.loadingWrap}>
          <ActivityIndicator size="small" color={COLORS.accent} />
        </View>
      ) : row1.length > 0 ? (
        <View style={styles.benefitsWrap}>
          {/* Row 1: Medical copays (4 cards) */}
          <View style={styles.benefitsRow}>
            {row1.map((b, i) => (
              <View key={'r1-' + String(i)} style={styles.benefitCard}>
                <Text style={styles.benefitIcon}>{pickIcon(b.label)}</Text>
                <Text style={styles.benefitValue}>{b.in_network || ''}</Text>
                <Text style={styles.benefitLabel}>{b.label}</Text>
              </View>
            ))}
          </View>
          {/* Row 2: Rx cost + supplementals (2-4 cards, flex layout) */}
          {row2.length > 0 ? (
            <View style={styles.benefitsRow}>
              {row2.map((b, i) => (
                <View key={'r2-' + String(i)} style={row2.length <= 2 ? styles.benefitCardWide : styles.benefitCard}>
                  <Text style={styles.benefitIcon}>{pickIcon(b.label)}</Text>
                  <Text style={styles.benefitValue}>{b.in_network || ''}</Text>
                  <Text style={styles.benefitLabel}>{b.label}</Text>
                </View>
              ))}
            </View>
          ) : null}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { paddingHorizontal: 20, paddingTop: SPACING.sm, paddingBottom: SPACING.md },
  header: {
    flexDirection: 'row', justifyContent: 'space-between',
    alignItems: 'flex-start', marginBottom: SPACING.sm,
  },
  greeting: { fontSize: 14, color: COLORS.textSecondary, marginBottom: 2 },
  name: { fontSize: 24, fontWeight: '700', color: COLORS.text },
  agent: { fontSize: 13, color: COLORS.textSecondary, marginTop: 4 },
  carrierLogo: { width: 80, height: 40, marginTop: 4 },
  planRow: {
    flexDirection: 'row', justifyContent: 'space-between',
    alignItems: 'center', marginBottom: 14,
  },
  planName: { fontSize: 13, color: COLORS.textSecondary, fontWeight: '500', flex: 1 },
  sobLink: { fontSize: 13, color: COLORS.accent, fontWeight: '600' },
  loadingWrap: { paddingVertical: 16, alignItems: 'center' },
  benefitsWrap: { gap: SPACING.sm },
  benefitsRow: { flexDirection: 'row', gap: SPACING.sm },
  benefitCard: {
    flex: 1, backgroundColor: COLORS.white, borderRadius: RADII.md,
    paddingVertical: 10, paddingHorizontal: 6, alignItems: 'center',
    borderWidth: 1, borderColor: COLORS.border, gap: 3,
  },
  benefitCardWide: {
    flex: 1, backgroundColor: COLORS.white, borderRadius: RADII.md,
    paddingVertical: 10, paddingHorizontal: 8, alignItems: 'center',
    borderWidth: 1, borderColor: COLORS.border, gap: 3,
  },
  benefitIcon: { fontSize: 18 },
  benefitValue: { fontSize: 15, fontWeight: '700', color: COLORS.text },
  benefitLabel: { fontSize: 10, color: COLORS.textSecondary, textAlign: 'center', fontWeight: '500' },
});