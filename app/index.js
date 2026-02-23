import { useState } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, Image,
  StyleSheet, KeyboardAvoidingView, Platform, ActivityIndicator,
} from 'react-native';
import { useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { COLORS, RADII, SPACING } from '../constants/theme';
import { API_URL } from '../constants/api';

const logo = require('../assets/images/logo.png');

export default function PhoneScreen() {
  const [phone, setPhone] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const router = useRouter();

  const formatPhone = (val) => {
    const digits = val.replace(/\D/g, '').slice(0, 10);
    if (digits.length <= 3) return digits;
    if (digits.length <= 6) return '(' + digits.slice(0, 3) + ') ' + digits.slice(3);
    return '(' + digits.slice(0, 3) + ') ' + digits.slice(3, 6) + '-' + digits.slice(6);
  };

  const rawDigits = phone.replace(/\D/g, '');
  const isValid = rawDigits.length === 10;

  const handleSubmit = async () => {
    if (!isValid) return;
    setLoading(true);
    setError('');

    try {
      const res = await fetch(`${API_URL}/auth/lookup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone: rawDigits }),
      });
      const data = await res.json();

      if (data.found) {
        router.push({
          pathname: '/home',
          params: {
            firstName: data.first_name,
            lastName: data.last_name,
            planName: data.plan_name,
            planNumber: data.plan_number,
            agent: data.agent,
            phone: rawDigits,
            zipCode: data.zip_code || '',
          },
        });
      } else {
        setError("We couldn't find an account with that number. Please call us at (844) 463-2931.");
      }
    } catch (err) {
      console.log('Lookup error:', err);
      setError("Can't connect right now. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <KeyboardAvoidingView
        style={styles.inner}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      >
        <View style={styles.content}>
          <Image source={logo} style={styles.logo} resizeMode="contain" />
          <Text style={styles.title}>Med Concierge</Text>
          <Text style={styles.subtitle}>
            Powered by{'\n'}<Text style={styles.brandName}>Insurance 'n You</Text>
        </Text>

          <View style={styles.inputGroup}>
            <Text style={styles.label}>Enter your phone number</Text>
            <TextInput
              style={styles.phoneInput}
              value={phone}
              onChangeText={(val) => { setPhone(formatPhone(val)); setError(''); }}
              placeholder="(555) 123-4567"
              placeholderTextColor={COLORS.border}
              keyboardType="phone-pad"
              autoFocus
              editable={!loading}
            />
            <Text style={styles.hint}>We'll look up your account.</Text>
          </View>

          {error ? <Text style={styles.errorText}>{error}</Text> : null}

          <TouchableOpacity
            style={[styles.button, (!isValid || loading) && styles.buttonDisabled]}
            onPress={handleSubmit}
            disabled={!isValid || loading}
            activeOpacity={0.8}
          >
            {loading ? (
              <ActivityIndicator color={COLORS.white} />
            ) : (
              <Text style={styles.buttonText}>Look up my plan</Text>
            )}
          </TouchableOpacity>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.bg },
  inner: { flex: 1, justifyContent: 'center' },
  content: { paddingHorizontal: SPACING.xl },
  logo: { width: 110, height: 110, marginBottom: SPACING.lg },
  title: { fontSize: 30, fontWeight: '700', color: COLORS.text, marginBottom: SPACING.xs },
  subtitle: { fontSize: 17, color: COLORS.textSecondary, lineHeight: 26, marginBottom: 36 },
  brandName: { fontSize: 20, fontWeight: '700', color: COLORS.text },  inputGroup: { marginBottom: 28 },
  label: { fontSize: 15, fontWeight: '600', color: COLORS.text, marginBottom: SPACING.sm },
  phoneInput: {
    backgroundColor: COLORS.white, borderWidth: 2, borderColor: COLORS.border,
    borderRadius: RADII.md, paddingHorizontal: 18, paddingVertical: 16,
    fontSize: 22, fontWeight: '500', color: COLORS.text, letterSpacing: 0.5,
  },
  hint: { fontSize: 14, color: COLORS.textSecondary, marginTop: SPACING.sm },
  errorText: { fontSize: 14, color: '#D32F2F', marginBottom: 16, lineHeight: 20 },
  button: {
    backgroundColor: COLORS.accent, borderRadius: RADII.md,
    paddingVertical: 18, alignItems: 'center',
  },
  buttonDisabled: { opacity: 0.4 },
  buttonText: { fontSize: 18, fontWeight: '600', color: COLORS.white },
});