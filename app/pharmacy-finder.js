import { useState, useEffect } from 'react';
import { View, Text, FlatList, TouchableOpacity, ActivityIndicator, Linking, StyleSheet } from 'react-native';
import { useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { COLORS, RADII, SPACING } from '../constants/theme';
import { API_BASE } from '../constants/api';

export default function PharmacyFinderScreen() {
  const router = useRouter();
  const [pharmacies, setPharmacies] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API_BASE}/api/pharmacies`)
      .then((r) => r.json())
      .then((data) => setPharmacies(data.pharmacies || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const renderPharmacy = ({ item }) => (
    <View style={s.card}>
      <View style={s.cardHeader}>
        <View style={{ flex: 1 }}>
          <Text style={s.pharmaName}>{item.name}</Text>
          {item.preferred && <Text style={s.preferred}>Preferred Pharmacy</Text>}
        </View>
        <Text style={s.distance}>{item.distance}</Text>
      </View>
      <Text style={s.address}>{item.address}</Text>
      <Text style={s.hours}>{item.hours}</Text>
      <View style={s.actions}>
        <TouchableOpacity style={s.actionBtn} onPress={() => Linking.openURL('tel:' + item.phone)}>
          <Text style={s.actionText}>Call</Text>
        </TouchableOpacity>
        <TouchableOpacity style={[s.actionBtn, s.actionBtnSecondary]} onPress={() => Linking.openURL('https://maps.google.com/?q=' + encodeURIComponent(item.address))}>
          <Text style={[s.actionText, { color: COLORS.accent }]}>Directions</Text>
        </TouchableOpacity>
      </View>
    </View>
  );

  return (
    <SafeAreaView style={s.container}>
      <View style={s.topBar}>
        <TouchableOpacity onPress={() => router.back()}>
          <Text style={s.back}>← Back</Text>
        </TouchableOpacity>
        <Text style={s.title}>Pharmacy Finder</Text>
      </View>
      {loading ? (
        <ActivityIndicator size="large" color={COLORS.accent} style={{ marginTop: 40 }} />
      ) : (
        <FlatList
          data={pharmacies}
          keyExtractor={(item) => item.id}
          renderItem={renderPharmacy}
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
  cardHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 4 },
  pharmaName: { fontSize: 17, fontWeight: '700', color: COLORS.text },
  preferred: { fontSize: 12, fontWeight: '600', color: '#4CAF50', marginTop: 2 },
  distance: { fontSize: 14, fontWeight: '600', color: COLORS.accent },
  address: { fontSize: 14, color: COLORS.textSecondary, marginBottom: 4 },
  hours: { fontSize: 13, color: COLORS.textSecondary, marginBottom: SPACING.sm },
  actions: { flexDirection: 'row', gap: SPACING.sm },
  actionBtn: { flex: 1, backgroundColor: COLORS.accent, borderRadius: RADII.sm, paddingVertical: 10, alignItems: 'center' },
  actionBtnSecondary: { backgroundColor: COLORS.accentLight, borderWidth: 1, borderColor: 'rgba(123,63,191,0.2)' },
  actionText: { fontSize: 14, fontWeight: '600', color: COLORS.white },
});
