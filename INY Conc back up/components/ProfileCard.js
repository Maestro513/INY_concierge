import { View, Text, TouchableOpacity, StyleSheet } from 'react-native';
import { COLORS, RADII, SPACING } from '../constants/theme';
import { SAMPLE_MEMBER, SAMPLE_BENEFITS } from '../constants/data';

const EXTRA_BENEFITS = [
  { label: 'Dental', value: '$1,500', icon: '🦷', has: true },
  { label: 'OTC', value: '$75/qtr', icon: '🛒', has: true },
  { label: 'Flex Card', value: '$200', icon: '💳', has: false },
  { label: 'Part B Giveback', value: '$100/mo', icon: '💰', has: true },
];

export default function ProfileCard({ onViewSOB }) {
  const g = () => { const h = new Date().getHours(); return h < 12 ? 'Good morning,' : h < 17 ? 'Good afternoon,' : 'Good evening,'; };
  const extras = EXTRA_BENEFITS.filter((b) => b.has);

  return (
    <View style={s.container}>
      <View style={s.header}>
        <View>
          <Text style={s.greeting}>{g()}</Text>
          <Text style={s.name}>{SAMPLE_MEMBER.firstName} {SAMPLE_MEMBER.lastName}</Text>
        </View>
        <View style={s.badge}><Text style={s.badgeText}>{SAMPLE_MEMBER.carrier}</Text></View>
      </View>
      <View style={s.planRow}>
        <Text style={s.planName}>{SAMPLE_MEMBER.planName}</Text>
        <TouchableOpacity onPress={onViewSOB}><Text style={s.sobLink}>View SOB →</Text></TouchableOpacity>
      </View>
      <View style={s.grid}>
        {SAMPLE_BENEFITS.map((b, i) => (
          <View key={i} style={s.card}>
            <Text style={{ fontSize: 22 }}>{b.icon}</Text>
            <Text style={s.val}>{b.value}</Text>
            <Text style={s.lbl}>{b.label}</Text>
          </View>
        ))}
      </View>
      {extras.length > 0 && (
        <View style={[s.grid, { marginTop: SPACING.sm }]}>
          {extras.map((b, i) => (
            <View key={i} style={s.card}>
              <Text style={{ fontSize: 22 }}>{b.icon}</Text>
              <Text style={s.val}>{b.value}</Text>
              <Text style={s.lbl}>{b.label}</Text>
            </View>
          ))}
        </View>
      )}
    </View>
  );
}
const s = StyleSheet.create({
  container: { paddingHorizontal: 20, paddingTop: SPACING.sm, paddingBottom: SPACING.md },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: SPACING.sm },
  greeting: { fontSize: 17, color: COLORS.textSecondary, marginBottom: 2 },
  name: { fontSize: 29, fontWeight: '700', color: COLORS.text },
  badge: { backgroundColor: '#002F6C', borderRadius: 10, paddingHorizontal: 14, paddingVertical: 6, marginTop: 4 },
  badgeText: { color: '#fff', fontWeight: '700', fontSize: 14, letterSpacing: 1 },
  planRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 },
  planName: { fontSize: 16, color: COLORS.textSecondary, fontWeight: '500', flex: 1 },
  sobLink: { fontSize: 16, color: COLORS.accent, fontWeight: '600' },
  grid: { flexDirection: 'row', gap: SPACING.sm },
  card: { flex: 1, backgroundColor: COLORS.white, borderRadius: RADII.md, paddingVertical: 12, paddingHorizontal: 8, alignItems: 'center', borderWidth: 1, borderColor: COLORS.border, gap: 4 },
  val: { fontSize: 19, fontWeight: '700', color: COLORS.text },
  lbl: { fontSize: 13, color: COLORS.textSecondary, textAlign: 'center', fontWeight: '500' },
});