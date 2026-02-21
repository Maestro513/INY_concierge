import { useState, useRef } from 'react';
import { View, Text, TextInput, TouchableOpacity, StyleSheet, KeyboardAvoidingView, Platform } from 'react-native';
import { useRouter, useLocalSearchParams } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { COLORS, RADII, SPACING } from '../constants/theme';

export default function OTPScreen() {
  const { phone } = useLocalSearchParams();
  const [otp, setOtp] = useState(['', '', '', '', '', '']);
  const refs = useRef([]);
  const router = useRouter();

  const handleChange = (i, v) => {
    if (!/^\d?$/.test(v)) return;
    const n = [...otp]; n[i] = v; setOtp(n);
    if (v && i < 5) refs.current[i + 1]?.focus();
  };
  const handleKey = (i, k) => { if (k === 'Backspace' && !otp[i] && i > 0) refs.current[i - 1]?.focus(); };
  const filled = otp.every((d) => d !== '');

  return (
    <SafeAreaView style={s.container}>
      <KeyboardAvoidingView style={s.inner} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
        <View style={s.content}>
          <TouchableOpacity onPress={() => router.back()}><Text style={s.back}>← Back</Text></TouchableOpacity>
          <Text style={{ fontSize: 48, marginBottom: SPACING.md }}>✉️</Text>
          <Text style={s.title}>Check your phone</Text>
          <Text style={s.subtitle}>We sent a 6-digit code to{'\n'}<Text style={{ fontWeight: '700', color: COLORS.text }}>{phone}</Text></Text>
          <View style={s.otpRow}>
            {otp.map((d, i) => (
              <TextInput key={i} ref={(el) => (refs.current[i] = el)} style={[s.otpInput, d ? { borderColor: COLORS.accent } : null]} value={d} onChangeText={(v) => handleChange(i, v)} onKeyPress={({ nativeEvent }) => handleKey(i, nativeEvent.key)} keyboardType="number-pad" maxLength={1} selectTextOnFocus />
            ))}
          </View>
          <TouchableOpacity style={[s.button, !filled && { opacity: 0.4 }]} onPress={() => filled && router.replace('/home')} disabled={!filled} activeOpacity={0.8}>
            <Text style={s.buttonText}>Verify</Text>
          </TouchableOpacity>
          <TouchableOpacity style={{ marginTop: SPACING.lg, alignItems: 'center' }}>
            <Text style={{ fontSize: 15, color: COLORS.textSecondary }}>Didn't get it? <Text style={{ color: COLORS.accent, fontWeight: '600' }}>Resend code</Text></Text>
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.bg },
  inner: { flex: 1, justifyContent: 'center' },
  content: { paddingHorizontal: SPACING.xl },
  back: { fontSize: 16, fontWeight: '600', color: COLORS.accent, marginBottom: SPACING.lg },
  title: { fontSize: 30, fontWeight: '700', color: COLORS.text, marginBottom: SPACING.sm },
  subtitle: { fontSize: 17, color: COLORS.textSecondary, lineHeight: 26, marginBottom: 36 },
  otpRow: { flexDirection: 'row', justifyContent: 'center', gap: 10, marginBottom: SPACING.xl },
  otpInput: { width: 48, height: 56, borderWidth: 2, borderColor: COLORS.border, borderRadius: 12, backgroundColor: COLORS.white, textAlign: 'center', fontSize: 24, fontWeight: '600', color: COLORS.text },
  button: { backgroundColor: COLORS.accent, borderRadius: RADII.md, paddingVertical: 18, alignItems: 'center' },
  buttonText: { fontSize: 18, fontWeight: '600', color: COLORS.white },
});
