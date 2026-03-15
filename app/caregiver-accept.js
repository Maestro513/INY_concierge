import { useState } from 'react';
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  Alert,
} from 'react-native';
import { useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, RADII, SHADOWS } from '../constants/theme';
import { API_URL, authFetch } from '../constants/api';
import { setCaregiverInfo } from '../constants/session';

export default function CaregiverAcceptScreen() {
  const router = useRouter();
  const [code, setCode] = useState(['', '', '', '', '', '']);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const refs = [];

  const handleChange = (i, v) => {
    if (!/^\d?$/.test(v)) return;
    const n = [...code];
    n[i] = v;
    setCode(n);
    if (v && i < 5) refs[i + 1]?.focus();
    setError('');
  };

  const handleKey = (i, k) => {
    if (k === 'Backspace' && !code[i] && i > 0) refs[i - 1]?.focus();
  };

  const filled = code.every((d) => d !== '');

  const handleAccept = async () => {
    if (!filled) return;
    setLoading(true);
    setError('');

    try {
      const res = await authFetch(`${API_URL}/caregiver/accept`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ invite_code: code.join('') }),
      });

      const data = await res.json();
      if (res.ok) {
        setCaregiverInfo({ isCaregiverOnly: true, accepted: true });
        router.replace('/caregiver-home');
      } else {
        setError(data.detail || 'Invalid code. Please try again.');
        setCode(['', '', '', '', '', '']);
        refs[0]?.focus();
      }
    } catch (err) {
      setError("Couldn't connect. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <View style={s.container}>
      <SafeAreaView style={s.safe} edges={['top', 'bottom']}>
        <View style={s.content}>
          {/* Icon */}
          <View style={s.iconWrap}>
            <Ionicons name="people" size={48} color={COLORS.accent} />
          </View>

          <Text style={s.title}>You've Been Invited</Text>
          <Text style={s.subtitle}>
            Someone has invited you to view their health plan details. Enter the 6-digit code from
            the text message you received.
          </Text>

          {/* Code input */}
          <Text style={s.fieldLabel}>INVITE CODE</Text>
          <View style={s.codeRow}>
            {code.map((d, i) => (
              <TextInput
                key={i}
                ref={(el) => (refs[i] = el)}
                style={[s.codeInput, d ? s.codeInputFilled : null]}
                value={d}
                onChangeText={(v) => handleChange(i, v)}
                onKeyPress={({ nativeEvent }) => handleKey(i, nativeEvent.key)}
                keyboardType="number-pad"
                maxLength={1}
                selectTextOnFocus
                editable={!loading}
                accessibilityLabel={`Invite code digit ${i + 1} of 6`}
              />
            ))}
          </View>

          {error ? (
            <View style={s.errorWrap}>
              <Ionicons name="alert-circle-outline" size={16} color={COLORS.error} />
              <Text style={s.errorText}>{error}</Text>
            </View>
          ) : null}

          <TouchableOpacity
            style={[s.btn, filled && !loading && s.btnActive]}
            onPress={handleAccept}
            disabled={!filled || loading}
            activeOpacity={0.8}
            accessibilityRole="button"
            accessibilityLabel="Accept invite"
          >
            {loading ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <>
                <Text style={s.btnText}>Accept Invite</Text>
                <Ionicons name="checkmark" size={20} color="#fff" style={{ marginLeft: 6 }} />
              </>
            )}
          </TouchableOpacity>

          <View style={s.infoBox}>
            <Ionicons name="eye-outline" size={18} color={COLORS.accent} />
            <Text style={s.infoText}>
              You'll get read-only access to view their plan benefits, copays, and medication
              reminders. You won't be able to make any changes.
            </Text>
          </View>

          <TouchableOpacity
            style={s.skipBtn}
            onPress={() => {
              Alert.alert(
                'Skip for Now',
                'You can accept the invite later by logging in again with your phone number.',
                [
                  { text: 'Cancel', style: 'cancel' },
                  {
                    text: 'Skip',
                    onPress: () => router.replace('/'),
                  },
                ],
              );
            }}
            activeOpacity={0.7}
          >
            <Text style={s.skipText}>Skip for now</Text>
          </TouchableOpacity>
        </View>
      </SafeAreaView>
    </View>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.bg },
  safe: { flex: 1 },
  content: {
    flex: 1,
    paddingHorizontal: 28,
    paddingTop: 40,
    alignItems: 'center',
  },

  iconWrap: {
    width: 80,
    height: 80,
    borderRadius: 24,
    backgroundColor: COLORS.accentLight,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 20,
  },

  title: { fontSize: 24, fontWeight: '700', color: COLORS.text, marginBottom: 8 },
  subtitle: {
    fontSize: 15,
    color: COLORS.textSecondary,
    textAlign: 'center',
    lineHeight: 22,
    marginBottom: 28,
    paddingHorizontal: 10,
  },

  fieldLabel: {
    fontSize: 12,
    fontWeight: '600',
    color: COLORS.textTertiary,
    letterSpacing: 0.5,
    marginBottom: 10,
    alignSelf: 'flex-start',
  },

  codeRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 20,
    width: '100%',
  },
  codeInput: {
    flex: 1,
    marginHorizontal: 4,
    height: 56,
    borderWidth: 2,
    borderColor: COLORS.borderLight,
    borderRadius: RADII.md,
    backgroundColor: COLORS.white,
    textAlign: 'center',
    fontSize: 24,
    fontWeight: '700',
    color: COLORS.text,
  },
  codeInputFilled: {
    borderColor: COLORS.accent,
    backgroundColor: COLORS.accentLighter,
  },

  errorWrap: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: COLORS.errorBg,
    borderRadius: RADII.sm,
    paddingHorizontal: 14,
    paddingVertical: 10,
    marginBottom: 16,
    width: '100%',
  },
  errorText: { fontSize: 14, color: COLORS.error, flex: 1 },

  btn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: RADII.md,
    paddingVertical: 18,
    width: '100%',
    backgroundColor: COLORS.textTertiary,
    ...SHADOWS.button,
  },
  btnActive: { backgroundColor: COLORS.accent },
  btnText: { fontSize: 17, fontWeight: '700', color: '#fff' },

  infoBox: {
    flexDirection: 'row',
    gap: 10,
    padding: 14,
    backgroundColor: COLORS.accentLighter,
    borderRadius: RADII.sm,
    marginTop: 24,
    borderWidth: 1,
    borderColor: COLORS.accentLight,
    width: '100%',
  },
  infoText: { fontSize: 13, color: COLORS.textSecondary, flex: 1, lineHeight: 19 },

  skipBtn: { marginTop: 20, padding: 12 },
  skipText: { fontSize: 15, color: COLORS.textSecondary, fontWeight: '500' },
});
