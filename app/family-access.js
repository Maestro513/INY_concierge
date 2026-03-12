import { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  TextInput,
  Alert,
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, RADII, SHADOWS, TYPE, SPACING } from '../constants/theme';
import { API_URL, authFetch } from '../constants/api';
import { getMemberSession } from '../constants/session';

export default function FamilyAccessScreen() {
  const router = useRouter();
  const { sessionId } = getMemberSession();
  const [members, setMembers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [familyName, setFamilyName] = useState('');
  const [familyPhone, setFamilyPhone] = useState('');
  const [saving, setSaving] = useState(false);

  const loadMembers = useCallback(async () => {
    if (!sessionId) return;
    setLoading(true);
    try {
      const res = await authFetch(`${API_URL}/family-access/${sessionId}`);
      if (res.ok) {
        const data = await res.json();
        setMembers(data.family_members || []);
      }
    } catch (err) {
      if (__DEV__) console.log('Family access fetch error:', err);
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    loadMembers();
  }, [loadMembers]);

  const formatPhone = (text) => {
    const digits = text.replace(/\D/g, '').slice(0, 10);
    if (digits.length <= 3) return digits;
    if (digits.length <= 6) return `(${digits.slice(0, 3)}) ${digits.slice(3)}`;
    return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`;
  };

  const rawPhone = familyPhone.replace(/\D/g, '');

  const handleAdd = async () => {
    if (!familyName.trim() || rawPhone.length !== 10) return;
    setSaving(true);
    try {
      const res = await authFetch(`${API_URL}/family-access/${sessionId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          family_phone: rawPhone,
          family_name: familyName.trim(),
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        Alert.alert('Error', err.detail || 'Could not grant access.');
        return;
      }
      setFamilyName('');
      setFamilyPhone('');
      setShowAdd(false);
      loadMembers();
    } catch (err) {
      Alert.alert('Error', 'Something went wrong. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  const handleRevoke = (id, name) => {
    Alert.alert('Remove Access', `Remove ${name}'s access to your health info?`, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Remove',
        style: 'destructive',
        onPress: async () => {
          try {
            await authFetch(`${API_URL}/family-access/${sessionId}/${id}`, {
              method: 'DELETE',
            });
            setMembers((prev) => prev.filter((m) => m.id !== id));
          } catch (err) {
            if (__DEV__) console.log('Revoke error:', err);
          }
        },
      },
    ]);
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        {/* Header */}
        <View style={styles.header}>
          <TouchableOpacity
            onPress={() => router.back()}
            hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
            accessibilityRole="button"
            accessibilityLabel="Go back"
          >
            <Ionicons name="arrow-back" size={24} color={COLORS.text} />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>Family Access</Text>
          <View style={{ width: 24 }} />
        </View>

        <ScrollView style={styles.flex} contentContainerStyle={styles.content}>
          {/* Explainer */}
          <View style={styles.infoCard}>
            <Ionicons name="shield-checkmark-outline" size={24} color={COLORS.accent} />
            <Text style={styles.infoText}>
              Give a family member or caregiver read-only access to your medication reminders,
              benefits, and health screenings. They'll need to log in with their own phone number.
            </Text>
          </View>

          {/* Members list */}
          {loading ? (
            <ActivityIndicator size="small" color={COLORS.accent} style={{ marginTop: 30 }} />
          ) : members.length === 0 && !showAdd ? (
            <View style={styles.emptyState}>
              <Ionicons name="people-outline" size={48} color={COLORS.textTertiary} />
              <Text style={styles.emptyText}>No family members added yet</Text>
              <Text style={styles.emptySubtext}>
                Tap the button below to grant someone access
              </Text>
            </View>
          ) : (
            members.map((m) => (
              <View key={String(m.id)} style={styles.memberCard}>
                <View style={styles.memberAvatar}>
                  <Ionicons name="person" size={20} color={COLORS.accent} />
                </View>
                <View style={styles.memberInfo}>
                  <Text style={styles.memberName}>{m.family_name}</Text>
                  <Text style={styles.memberPhone}>
                    Phone ending in {m.family_phone_display}
                  </Text>
                </View>
                <TouchableOpacity
                  onPress={() => handleRevoke(m.id, m.family_name)}
                  hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
                  accessibilityRole="button"
                  accessibilityLabel={`Remove ${m.family_name}`}
                >
                  <Ionicons name="close-circle" size={22} color={COLORS.error} />
                </TouchableOpacity>
              </View>
            ))
          )}

          {/* Add form */}
          {showAdd && (
            <View style={styles.addForm}>
              <Text style={styles.addTitle}>Add Family Member</Text>
              <Text style={styles.fieldLabel}>Name</Text>
              <TextInput
                style={styles.input}
                value={familyName}
                onChangeText={setFamilyName}
                placeholder="e.g. Maria (daughter)"
                placeholderTextColor={COLORS.textTertiary}
                maxLength={100}
                accessibilityLabel="Family member name"
              />
              <Text style={styles.fieldLabel}>Phone Number</Text>
              <TextInput
                style={styles.input}
                value={familyPhone}
                onChangeText={(t) => setFamilyPhone(formatPhone(t))}
                placeholder="(555) 123-4567"
                placeholderTextColor={COLORS.textTertiary}
                keyboardType="phone-pad"
                maxLength={14}
                accessibilityLabel="Family member phone number"
              />
              <View style={styles.addActions}>
                <TouchableOpacity
                  style={styles.cancelBtn}
                  onPress={() => {
                    setShowAdd(false);
                    setFamilyName('');
                    setFamilyPhone('');
                  }}
                  accessibilityRole="button"
                >
                  <Text style={styles.cancelBtnText}>Cancel</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[
                    styles.grantBtn,
                    (!familyName.trim() || rawPhone.length !== 10 || saving) &&
                      styles.grantBtnDisabled,
                  ]}
                  onPress={handleAdd}
                  disabled={!familyName.trim() || rawPhone.length !== 10 || saving}
                  accessibilityRole="button"
                  accessibilityLabel="Grant access"
                >
                  {saving ? (
                    <ActivityIndicator color={COLORS.white} size="small" />
                  ) : (
                    <Text style={styles.grantBtnText}>Grant Access</Text>
                  )}
                </TouchableOpacity>
              </View>
            </View>
          )}
        </ScrollView>

        {/* Add button */}
        {!showAdd && (
          <View style={styles.bottomBar}>
            <TouchableOpacity
              style={styles.addBtn}
              onPress={() => setShowAdd(true)}
              activeOpacity={0.8}
              accessibilityRole="button"
              accessibilityLabel="Add a family member"
            >
              <Ionicons name="person-add" size={20} color={COLORS.white} />
              <Text style={styles.addBtnText}>Add Family Member</Text>
            </TouchableOpacity>
          </View>
        )}
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: COLORS.bg },
  flex: { flex: 1 },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 18,
    paddingVertical: 14,
  },
  headerTitle: { ...TYPE.h3, color: COLORS.text },
  content: { paddingHorizontal: 18, paddingBottom: 100 },

  // Info card
  infoCard: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 12,
    backgroundColor: COLORS.accentLight || '#F0E8F8',
    borderRadius: RADII.md,
    padding: 14,
    marginBottom: 20,
  },
  infoText: {
    flex: 1,
    fontSize: 13,
    fontWeight: '500',
    color: COLORS.textSecondary,
    lineHeight: 19,
  },

  // Empty state
  emptyState: { alignItems: 'center', paddingTop: 40, gap: 8 },
  emptyText: { fontSize: 16, fontWeight: '600', color: COLORS.textSecondary },
  emptySubtext: { fontSize: 13, color: COLORS.textTertiary, textAlign: 'center' },

  // Member cards
  memberCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: COLORS.white,
    borderRadius: RADII.md,
    padding: 14,
    marginBottom: 10,
    gap: 12,
    ...SHADOWS.card,
    borderWidth: 1,
    borderColor: COLORS.borderLight,
  },
  memberAvatar: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: COLORS.accentLight || '#F0E8F8',
    justifyContent: 'center',
    alignItems: 'center',
  },
  memberInfo: { flex: 1 },
  memberName: { fontSize: 15, fontWeight: '600', color: COLORS.text },
  memberPhone: { fontSize: 12, fontWeight: '500', color: COLORS.textSecondary, marginTop: 2 },

  // Add form
  addForm: {
    backgroundColor: COLORS.white,
    borderRadius: RADII.lg,
    padding: 18,
    marginTop: 16,
    ...SHADOWS.card,
    borderWidth: 1,
    borderColor: COLORS.borderLight,
  },
  addTitle: { ...TYPE.h3, color: COLORS.text, marginBottom: 12 },
  fieldLabel: { fontSize: 13, fontWeight: '600', color: COLORS.textSecondary, marginBottom: 6, marginTop: 10 },
  input: {
    backgroundColor: COLORS.bg,
    borderRadius: RADII.md,
    borderWidth: 1,
    borderColor: COLORS.borderLight,
    paddingHorizontal: 14,
    paddingVertical: 14,
    fontSize: 16,
    fontWeight: '500',
    color: COLORS.text,
  },
  addActions: {
    flexDirection: 'row',
    gap: 10,
    marginTop: 18,
  },
  cancelBtn: {
    flex: 1,
    paddingVertical: 14,
    alignItems: 'center',
    borderRadius: RADII.md,
    borderWidth: 1.5,
    borderColor: COLORS.borderLight,
  },
  cancelBtnText: { fontSize: 15, fontWeight: '600', color: COLORS.textSecondary },
  grantBtn: {
    flex: 1,
    paddingVertical: 14,
    alignItems: 'center',
    borderRadius: RADII.md,
    backgroundColor: COLORS.accent,
    ...SHADOWS.button,
  },
  grantBtnDisabled: { opacity: 0.4 },
  grantBtnText: { fontSize: 15, fontWeight: '600', color: COLORS.white },

  // Bottom bar
  bottomBar: {
    paddingHorizontal: 18,
    paddingBottom: 20,
  },
  addBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    backgroundColor: COLORS.accent,
    borderRadius: RADII.md,
    paddingVertical: 16,
    ...SHADOWS.button,
  },
  addBtnText: { fontSize: 16, fontWeight: '600', color: COLORS.white },
});
