import { useState, useEffect } from 'react';
import { View, Text, FlatList, TouchableOpacity, ActivityIndicator, StyleSheet } from 'react-native';
import { useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { COLORS, RADII, SPACING } from '../constants/theme';
import { API_BASE } from '../constants/api';

const TIER_COLORS = {
  'Tier 1': '#4CAF50',
  'Tier 2': '#2196F3',
  'Tier 3': '#FF9800',
  'Tier 4': '#F44336',
};

export default function MedicationsScreen() {
  const router = useRouter();
  const [meds, setMeds] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API_BASE}/api/medications`)
      .then((r) => r.json())
      .then((data) => setMeds(data.medications || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const renderMed = ({ item }) => (
    <View style={s.card}>
      <View style={s.cardHeader}>
        <Text style={s.medName}>{item.name}</Text>
        <View style={[s.tierBadge, { backgroundColor: TIER_COLORS[item.tier] || COLORS.accent }]}>
          <Text style={s.tierText}>{item.tier}</Text>
        </View>
      </View>
      <View style={s.detailRow}>
        <Text style={s.detailLabel}>Copay</Text>
        <Text style={s.detailValue}>{item.copay}</Text>
      </View>
      <View style={s.detailRow}>
        <Text style={s.detailLabel}>Supply</Text>
        <Text style={s.detailValue}>{item.daysSupply}</Text>
      </View>
      <View style={[s.detailRow, { borderBottomWidth: 0 }]}>
        <Text style={s.detailLabel}>Pharmacy</Text>
        <Text style={s.detailValue}>{item.pharmacy}</Text>
      </View>
    </View>
  );

  return (
    <SafeAreaView style={s.container}>
      <View style={s.topBar}>
        <TouchableOpacity onPress={() => router.back()}>
          <Text style={s.back}>← Back</Text>
        </TouchableOpacity>
        <Text style={s.title}>My Medications</Text>
      </View>
      {loading ? (
        <ActivityIndicator size="large" color={COLORS.accent} style={{ marginTop: 40 }} />
      ) : (
        <FlatList
          data={meds}
          keyExtractor={(item) => item.id}
          renderItem={renderMed}
          contentContainerStyle={s.list}
          showsVerticalScrollIndicator={false}
        />
      )}
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.bg },
  topBar: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 20, paddingVertical: SPACING.md, gap: SPACING.md },
  back: { fontSize: 16, fontWeight: '600', color: COLORS.accent },
  title: { fontSize: 20, fontWeight: '700', color: COLORS.text },
  list: { paddingHorizontal: 20, paddingBottom: 32 },
  card: { backgroundColor: COLORS.white, borderRadius: RADII.md, padding: SPACING.md, marginBottom: SPACING.sm, borderWidth: 1, borderColor: COLORS.border },
  cardHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: SPACING.sm },
  medName: { fontSize: 16, fontWeight: '700', color: COLORS.text, flex: 1 },
  tierBadge: { borderRadius: 8, paddingHorizontal: 10, paddingVertical: 4 },
  tierText: { color: '#fff', fontSize: 12, fontWeight: '700' },
  detailRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: COLORS.border },
  detailLabel: { fontSize: 14, color: COLORS.textSecondary },
  detailValue: { fontSize: 14, fontWeight: '600', color: COLORS.text },
});
