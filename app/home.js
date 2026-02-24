import { useState } from 'react';
import { StyleSheet } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { COLORS } from '../constants/theme';
import ProfileCard from '../components/ProfileCard';
import VoiceHelp from '../components/VoiceHelp';
import SOBModal from '../components/SOBModal';

export default function HomeScreen() {
  const [showSOB, setShowSOB] = useState(false);
  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: COLORS.bg }} edges={['top', 'bottom']}>
      <ProfileCard onViewSOB={() => setShowSOB(true)} />
      <VoiceHelp />
      <SOBModal visible={showSOB} onClose={() => setShowSOB(false)} />
    </SafeAreaView>
  );
}
