import { useState } from 'react';
import { View, Text, TouchableOpacity, ScrollView, StyleSheet } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { COLORS, RADII, SPACING } from '../constants/theme';
import ProfileCard from '../components/ProfileCard';
import VoiceHelp from '../components/VoiceHelp';
import SOBModal from '../components/SOBModal';

const NAV_ITEMS = [
  { label: 'My Medications', icon: '💊', route: '/medications' },
  { label: 'Find a Doctor', icon: '👨‍⚕️', route: '/doctor-results' },
  { label: 'Pharmacy Finder', icon: '🏥', route: '/pharmacy-finder' },
];

export default function HomeScreen() {
  const [showSOB, setShowSOB] = useState(false);
  const router = useRouter();

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: COLORS.bg }} edges={['top', 'bottom']}>
      <ScrollView style={{ flex: 1 }} contentContainerStyle={{ flexGrow: 1 }}>
        <ProfileCard onViewSOB={() => setShowSOB(true)} />
        <View style={s.navRow}>
          {NAV_ITEMS.map((item, i) => (
            <TouchableOpacity key={i} style={s.navCard} onPress={() => router.push(item.route)} activeOpacity={0.7}>
              <Text style={{ fontSize: 28 }}>{item.icon}</Text>
              <Text style={s.navLabel}>{item.label}</Text>
            </TouchableOpacity>
          ))}
        </View>
      </ScrollView>
      <VoiceHelp />
      <SOBModal visible={showSOB} onClose={() => setShowSOB(false)} />
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  navRow: { flexDirection: 'row', paddingHorizontal: 20, gap: SPACING.sm, marginBottom: SPACING.md },
  navCard: { flex: 1, backgroundColor: COLORS.white, borderRadius: RADII.md, paddingVertical: 16, alignItems: 'center', borderWidth: 1, borderColor: COLORS.border, gap: 6 },
  navLabel: { fontSize: 13, fontWeight: '600', color: COLORS.text, textAlign: 'center' },
});
