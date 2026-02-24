import { View, Text, FlatList, TouchableOpacity, StyleSheet, Linking } from 'react-native';
import { useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { COLORS, RADII, SPACING } from '../constants/theme';

const SAMPLE_PHARMACIES = [
  { id: '1', name: 'CVS Pharmacy', address: '100 Broadway, New York, NY 10005', distance: '0.3 mi', phone: '2125551234', preferred: true, hours: 'Open until 9 PM' },
  { id: '2', name: 'Walgreens', address: '250 Fulton St, New York, NY 10007', distance: '0.5 mi', phone: '2125555678', preferred: true, hours: 'Open 24 hours' },
  { id: '3', name: 'Rite Aid', address: '55 Water St, New York, NY 10004', distance: '0.7 mi', phone: '2125559012', preferred: false, hours: 'Open until 8 PM' },
  { id: '4', name: 'Duane Reade', address: '44 Wall St, New York, NY 10005', distance: '0.9 mi', phone: '2125553456', preferred: true, hours: 'Open until 10 PM' },
];

export default function PharmacyFinderScreen() {
  const router = useRouter();

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
      <FlatList
        data={SAMPLE_PHARMACIES}
        keyExtractor={(item) => item.id}
        renderItem={renderPharmacy}
        contentContainerStyle={s.list}
        showsVerticalScrollIndicator={false}
      />
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
