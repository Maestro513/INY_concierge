import { useState } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  Alert,
  Platform,
  ScrollView,
} from 'react-native';
import { useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, RADII, SHADOWS, SPACING } from '../constants/theme';
import { getMemberSession, logout, fullLogout } from '../constants/session';

export default function SettingsScreen() {
  const router = useRouter();
  const { member } = getMemberSession();
  const [loggingOut, setLoggingOut] = useState(false);

  const handleLogout = () => {
    Alert.alert(
      'Log Out',
      'You can unlock again with Face ID, fingerprint, or your phone passcode.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Log Out',
          style: 'destructive',
          onPress: async () => {
            setLoggingOut(true);
            await logout();
            router.replace('/');
          },
        },
      ],
    );
  };

  const handleFullLogout = () => {
    Alert.alert(
      'Sign Out of Device',
      'This will remove all data from this device. You will need to verify your phone number again with a new code.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Sign Out',
          style: 'destructive',
          onPress: async () => {
            setLoggingOut(true);
            await fullLogout();
            router.replace('/');
          },
        },
      ],
    );
  };

  const handleFamilyAccess = () => {
    Alert.alert(
      'Family Access',
      'Family Access lets a trusted family member or caregiver view your plan details and help manage your benefits.\n\nThis feature is coming soon!',
      [{ text: 'OK' }],
    );
  };

  return (
    <View style={s.container}>
      <SafeAreaView style={s.safe} edges={['top']}>
        {/* Header */}
        <View style={s.header}>
          <TouchableOpacity
            onPress={() => router.back()}
            style={s.backBtn}
            activeOpacity={0.7}
            accessibilityRole="button"
            accessibilityLabel="Go back"
          >
            <Ionicons name="chevron-back" size={22} color={COLORS.accent} />
            <Text style={s.backText}>Home</Text>
          </TouchableOpacity>
          <Text style={s.title}>Setup</Text>
          <View style={{ width: 70 }} />
        </View>

        <ScrollView style={s.body} contentContainerStyle={s.bodyContent}>
          {/* Account section */}
          <Text style={s.sectionLabel}>ACCOUNT</Text>
          <View style={s.card}>
            {member && (
              <View style={s.memberRow}>
                <View style={s.avatarCircle}>
                  <Text style={s.avatarText}>
                    {(member.firstName || '?')[0]}
                    {(member.lastName || '?')[0]}
                  </Text>
                </View>
                <View style={s.memberInfo}>
                  <Text style={s.memberName}>
                    {member.firstName} {member.lastName}
                  </Text>
                  <Text style={s.memberPlan} numberOfLines={1}>
                    {member.planName || 'No plan'}
                  </Text>
                </View>
              </View>
            )}
          </View>

          {/* Features section */}
          <Text style={s.sectionLabel}>FEATURES</Text>
          <View style={s.card}>
            <TouchableOpacity
              style={s.menuRow}
              onPress={handleFamilyAccess}
              activeOpacity={0.7}
              accessibilityRole="button"
              accessibilityLabel="Family Access"
            >
              <View style={[s.menuIcon, { backgroundColor: COLORS.accentLight }]}>
                <Ionicons name="people-outline" size={20} color={COLORS.accent} />
              </View>
              <View style={s.menuInfo}>
                <Text style={s.menuLabel}>Family Access</Text>
                <Text style={s.menuSub}>Let a caregiver view your plan</Text>
              </View>
              <Ionicons name="chevron-forward" size={18} color={COLORS.textTertiary} />
            </TouchableOpacity>
          </View>

          {/* Actions section */}
          <Text style={s.sectionLabel}>ACTIONS</Text>
          <View style={s.card}>
            <TouchableOpacity
              style={s.menuRow}
              onPress={handleLogout}
              disabled={loggingOut}
              activeOpacity={0.7}
              accessibilityRole="button"
              accessibilityLabel="Log out"
            >
              <View style={[s.menuIcon, { backgroundColor: COLORS.accentLight }]}>
                <Ionicons name="lock-closed-outline" size={20} color={COLORS.accent} />
              </View>
              <View style={s.menuInfo}>
                <Text style={s.menuLabel}>Lock App</Text>
                <Text style={s.menuSub}>Unlock later with Face ID or passcode</Text>
              </View>
            </TouchableOpacity>
            <TouchableOpacity
              style={[s.menuRow, s.menuRowLast]}
              onPress={handleFullLogout}
              disabled={loggingOut}
              activeOpacity={0.7}
              accessibilityRole="button"
              accessibilityLabel="Sign out of this device"
            >
              <View style={[s.menuIcon, { backgroundColor: '#FDECEA' }]}>
                <Ionicons name="log-out-outline" size={20} color="#C0392B" />
              </View>
              <View style={s.menuInfo}>
                <Text style={[s.menuLabel, { color: '#C0392B' }]}>
                  {loggingOut ? 'Signing out...' : 'Sign Out of Device'}
                </Text>
                <Text style={s.menuSub}>Requires phone verification to log back in</Text>
              </View>
            </TouchableOpacity>
          </View>
        </ScrollView>
      </SafeAreaView>
    </View>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.bg },
  safe: { flex: 1 },

  // Header
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 12,
    backgroundColor: COLORS.white,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.borderLight,
  },
  backBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 2,
    width: 70,
  },
  backText: {
    fontSize: 16,
    fontWeight: '500',
    color: COLORS.accent,
  },
  title: {
    fontSize: 18,
    fontWeight: '700',
    color: COLORS.text,
    textAlign: 'center',
  },

  // Body
  body: { flex: 1 },
  bodyContent: { padding: 18, paddingBottom: 40 },

  // Section label
  sectionLabel: {
    fontSize: 12,
    fontWeight: '600',
    color: COLORS.textTertiary,
    letterSpacing: 0.5,
    marginBottom: 8,
    marginTop: 20,
    marginLeft: 4,
  },

  // Card
  card: {
    backgroundColor: COLORS.white,
    borderRadius: RADII.md,
    ...SHADOWS.card,
    borderWidth: 1,
    borderColor: COLORS.borderLight,
    overflow: 'hidden',
  },

  // Member row
  memberRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
    padding: 16,
  },
  avatarCircle: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: COLORS.accentLight,
    justifyContent: 'center',
    alignItems: 'center',
  },
  avatarText: {
    fontSize: 18,
    fontWeight: '700',
    color: COLORS.accent,
  },
  memberInfo: { flex: 1 },
  memberName: {
    fontSize: 17,
    fontWeight: '600',
    color: COLORS.text,
  },
  memberPlan: {
    fontSize: 13,
    fontWeight: '500',
    color: COLORS.textSecondary,
    marginTop: 2,
  },

  // Menu rows
  menuRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
    padding: 16,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.borderLight,
  },
  menuRowLast: {
    borderBottomWidth: 0,
  },
  menuIcon: {
    width: 40,
    height: 40,
    borderRadius: 12,
    justifyContent: 'center',
    alignItems: 'center',
  },
  menuInfo: { flex: 1 },
  menuLabel: {
    fontSize: 16,
    fontWeight: '600',
    color: COLORS.text,
  },
  menuSub: {
    fontSize: 13,
    fontWeight: '400',
    color: COLORS.textSecondary,
    marginTop: 2,
  },
});
