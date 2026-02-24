import { useState } from 'react';
import { View, Text, TextInput, TouchableOpacity, Image, StyleSheet, KeyboardAvoidingView, Platform } from 'react-native';
import { useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { COLORS, RADII, SPACING } from '../constants/theme';

const logo = require('../assets/images/logo.png');

export default function PhoneScreen() {
  const [phone, setPhone] = useState('');
  const router = useRouter();

  const formatPhone = (val) => {
    const digits = val.replace(/\D/g, '').slice(0, 10);
    if (digits.length <= 3) return digits;
    if (digits.length <= 6) return '(' + digits.slice(0, 3) + ') ' + digits.slice(3);
    return '(' + digits.slice(0, 3) + ') ' + digits.slice(3, 6) + '-' + digits.slice(6);
  };

  const rawDigits = phone.replace(/\D/g, '');
  const isValid = rawDigits.length === 10;

  return (
    <SafeAreaView style={s.container}>
      <KeyboardAvoidingView style={s.inner} behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
        <View style={s.content}>
          <Image source={logo} style={s.logo} resizeMode="contain" />
          <Text style={s.title}>InsuranceNYou</Text>
          <Text style={s.subtitle}>Your Medicare benefits,{'\n'}right at your fingertips.</Text>
          <View style={{ marginBottom: 28 }}>
            <Text style={s.label}>Enter your phone number</Text>
            <TextInput style={s.phoneInput} value={phone} onChangeText={(v) => setPhone(formatPhone(v))} placeholder="(555) 123-4567" placeholderTextColor={COLORS.border} keyboardType="phone-pad" autoFocus />
            <Text style={s.hint}>We'll text you a code to verify it's you.</Text>
          </View>
          <TouchableOpacity style={[s.button, !isValid && { opacity: 0.4 }]} onPress={() => isValid && router.push({ pathname: '/otp', params: { phone } })} disabled={!isValid} activeOpacity={0.8}>
            <Text style={s.buttonText}>Send me a code</Text>
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
  logo: { width: 110, height: 110, marginBottom: SPACING.lg },
  title: { fontSize: 30, fontWeight: '700', color: COLORS.text, marginBottom: SPACING.xs },
  subtitle: { fontSize: 17, color: COLORS.textSecondary, lineHeight: 26, marginBottom: 36 },
  label: { fontSize: 15, fontWeight: '600', color: COLORS.text, marginBottom: SPACING.sm },
  phoneInput: { backgroundColor: COLORS.white, borderWidth: 2, borderColor: COLORS.border, borderRadius: RADII.md, paddingHorizontal: 18, paddingVertical: 16, fontSize: 22, fontWeight: '500', color: COLORS.text },
  hint: { fontSize: 14, color: COLORS.textSecondary, marginTop: SPACING.sm },
  button: { backgroundColor: COLORS.accent, borderRadius: RADII.md, paddingVertical: 18, alignItems: 'center' },
  buttonText: { fontSize: 18, fontWeight: '600', color: COLORS.white },
});
