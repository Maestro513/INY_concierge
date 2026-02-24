import { useState, useEffect } from 'react';
import { View, Text, TouchableOpacity, ActivityIndicator, StyleSheet } from 'react-native';
import { COLORS, RADII, SPACING } from '../constants/theme';
import { API_BASE } from '../constants/api';
import { SAMPLE_MEMBER, SAMPLE_BENEFITS } from '../constants/data';
import { useAuth } from '../constants/auth';

export default function ProfileCard({ onViewSOB }) {
  const { phone } = useAuth();
  const [member, setMember] = useState(SAMPLE_MEMBER);
  const [benefits, setBenefits] = useState(SAMPLE_BENEFITS);
  const [extras, setExtras] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const params = phone ? `?phone=${encodeURIComponent(phone)}` : '';
    fetch(`${API_BASE}/api/member/profile${params}`)
      .then((r) => r.json())
      .then((data) => {
        if (data.member) setMember(data.member);
        if (data.benefits) setBenefits(data.benefits);
        if (data.extraBenefits) setExtras(data.extraBenefits.filter((b) => b.has));
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const g = () => { const h = new Date().getHours(); return h < 12 ? 'Good morning,' : h < 17 ? 'Good afternoon,' : 'Good evening,'; };

  const ICON_MAP = { stethoscope: '🩺', doctor: '👨‍⚕️', pill: '💊', shield: '🛡️', tooth: '🦷', cart: '🛒', card: '💳', money: '💰' };

  if (loading) return <ActivityIndicator size="large" color={COLORS.accent} style={{ marginTop: 20 }} />;

  return (
    <View style={s.container}>
      <View style={s.header}>
        <View>
          <Text style={s.greeting}>{g()}</Text>
          <Text style={s.name}>{member.firstName} {member.lastName}</Text>
        </View>
        <View style={s.badge}><Text style={s.badgeText}>{member.carrier}</Text></View>
      </View>
      <View style={s.planRow}>
        <Text style={s.planName}>{member.planName}</Text>
        <TouchableOpacity onPress={onViewSOB}><Text style={s.sobLink}>View SOB →</Text></TouchableOpacity>
      </View>
      <View style={s.grid}>
        {benefits.map((b, i) => (
          <View key={i} style={s.card}>
            <Text style={{ fontSize: 22 }}>{ICON_MAP[b.icon] || b.icon}</Text>
            <Text style={s.val}>{b.value}</Text>
            <Text style={s.lbl}>{b.label}</Text>
          </View>
        ))}
      </View>
      {extras.length > 0 && (
        <View style={[s.grid, { marginTop: SPACING.sm }]}>
          {extras.map((b, i) => (
            <View key={i} style={s.card}>
              <Text style={{ fontSize: 22 }}>{ICON_MAP[b.icon] || b.icon}</Text>
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
