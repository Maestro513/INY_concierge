import { View, Text, FlatList, TouchableOpacity, StyleSheet } from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { COLORS, RADII, SPACING } from '../constants/theme';

const SAMPLE_DOCTORS = [
  { id: '1', name: 'Dr. Sarah Chen', specialty: 'Primary Care', distance: '0.8 mi', address: '123 Main St, Suite 200', rating: 4.8, accepting: true },
  { id: '2', name: 'Dr. Marcus Johnson', specialty: 'Primary Care', distance: '1.2 mi', address: '456 Oak Ave, Floor 3', rating: 4.6, accepting: true },
  { id: '3', name: 'Dr. Priya Patel', specialty: 'Internal Medicine', distance: '2.1 mi', address: '789 Elm Blvd', rating: 4.9, accepting: false },
  { id: '4', name: 'Dr. Robert Kim', specialty: 'Family Medicine', distance: '2.5 mi', address: '321 Pine Rd, Suite 100', rating: 4.7, accepting: true },
];

export default function DoctorResultsScreen() {
  const router = useRouter();
  const { query } = useLocalSearchParams();

  const renderDoctor = ({ item }) => (
    <View style={s.card}>
      <View style={s.cardHeader}>
        <Text style={s.docName}>{item.name}</Text>
        <Text style={s.distance}>{item.distance}</Text>
      </View>
      <Text style={s.specialty}>{item.specialty}</Text>
      <Text style={s.address}>{item.address}</Text>
      <View style={s.cardFooter}>
        <Text style={s.rating}>{'★'} {item.rating}</Text>
        <Text style={[s.accepting, !item.accepting && { color: COLORS.textSecondary }]}>
          {item.accepting ? 'Accepting patients' : 'Not accepting'}
        </Text>
      </View>
    </View>
  );

  return (
    <SafeAreaView style={s.container}>
      <View style={s.topBar}>
        <TouchableOpacity onPress={() => router.back()}>
          <Text style={s.back}>← Back</Text>
        </TouchableOpacity>
        <Text style={s.title}>Doctors Near You</Text>
      </View>
      {query ? <Text style={s.queryText}>Results for "{query}"</Text> : null}
      <FlatList
        data={SAMPLE_DOCTORS}
        keyExtractor={(item) => item.id}
        renderItem={renderDoctor}
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
  queryText: { fontSize: 14, color: COLORS.textSecondary, paddingHorizontal: 20, marginBottom: SPACING.sm },
  list: { paddingHorizontal: 20, paddingBottom: 32 },
  card: { backgroundColor: COLORS.white, borderRadius: RADII.md, padding: SPACING.md, marginBottom: SPACING.sm, borderWidth: 1, borderColor: COLORS.border },
  cardHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 },
  docName: { fontSize: 17, fontWeight: '700', color: COLORS.text },
  distance: { fontSize: 14, fontWeight: '600', color: COLORS.accent },
  specialty: { fontSize: 14, color: COLORS.textSecondary, marginBottom: 4 },
  address: { fontSize: 14, color: COLORS.textSecondary, marginBottom: SPACING.sm },
  cardFooter: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  rating: { fontSize: 14, fontWeight: '600', color: '#F5A623' },
  accepting: { fontSize: 13, fontWeight: '600', color: '#4CAF50' },
});
