import { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  Modal,
  TextInput,
  ActivityIndicator,
  Alert,
} from 'react-native';
import { useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, RADII, SHADOWS } from '../constants/theme';
import { API_URL, authFetch } from '../constants/api';
import { getMemberSession } from '../constants/session';

// ── HIPAA Consent Step ──────────────────────────────────────────

function ConsentScreen({ consentText, onApprove, loading }) {
  const [scrolledToEnd, setScrolledToEnd] = useState(false);

  return (
    <View style={s.consentContainer}>
      <View style={s.consentHeader}>
        <Ionicons name="shield-checkmark" size={32} color={COLORS.accent} />
        <Text style={s.consentTitle}>HIPAA Authorization</Text>
        <Text style={s.consentSub}>
          Please read and approve this authorization before inviting a caregiver.
        </Text>
      </View>

      <ScrollView
        style={s.consentScroll}
        contentContainerStyle={s.consentScrollContent}
        onScroll={({ nativeEvent }) => {
          const { layoutMeasurement, contentOffset, contentSize } = nativeEvent;
          if (contentOffset.y + layoutMeasurement.height >= contentSize.height - 40) {
            setScrolledToEnd(true);
          }
        }}
        scrollEventThrottle={200}
      >
        <Text style={s.consentBody}>{consentText}</Text>
      </ScrollView>

      <View style={s.consentFooter}>
        {!scrolledToEnd && (
          <Text style={s.scrollHint}>Scroll to the bottom to continue</Text>
        )}
        <TouchableOpacity
          style={[s.approveBtn, !scrolledToEnd && s.approveBtnDisabled]}
          onPress={onApprove}
          disabled={!scrolledToEnd || loading}
          activeOpacity={0.8}
          accessibilityRole="button"
          accessibilityLabel="I authorize caregiver access"
        >
          {loading ? (
            <ActivityIndicator color="#fff" />
          ) : (
            <>
              <Ionicons name="checkmark-circle" size={20} color="#fff" style={{ marginRight: 8 }} />
              <Text style={s.approveBtnText}>I Authorize This Access</Text>
            </>
          )}
        </TouchableOpacity>
      </View>
    </View>
  );
}

// ── Invite Form Step ────────────────────────────────────────────

function InviteForm({ onSend, loading, consentId }) {
  const [phone, setPhone] = useState('');
  const [error, setError] = useState('');

  const formatPhone = (val) => {
    const digits = val.replace(/\D/g, '').slice(0, 10);
    if (digits.length <= 3) return digits;
    if (digits.length <= 6) return '(' + digits.slice(0, 3) + ') ' + digits.slice(3);
    return '(' + digits.slice(0, 3) + ') ' + digits.slice(3, 6) + '-' + digits.slice(6);
  };

  const rawDigits = phone.replace(/\D/g, '');
  const isValid =
    rawDigits.length === 10 &&
    !/^(\d)\1{9}$/.test(rawDigits) &&
    !rawDigits.startsWith('000') &&
    !rawDigits.startsWith('1');

  const handleSend = () => {
    if (!isValid) return;
    setError('');
    onSend(rawDigits);
  };

  return (
    <View style={s.inviteContainer}>
      <View style={s.inviteHeader}>
        <Ionicons name="person-add" size={32} color={COLORS.accent} />
        <Text style={s.inviteTitle}>Invite Caregiver</Text>
        <Text style={s.inviteSub}>
          Enter your caregiver's phone number. They'll receive a text with instructions to download
          the app and a verification code.
        </Text>
      </View>

      <Text style={s.fieldLabel}>CAREGIVER'S PHONE NUMBER</Text>
      <View style={[s.inputWrap, phone ? s.inputWrapFocused : null]}>
        <Ionicons name="call-outline" size={20} color={COLORS.textSecondary} />
        <TextInput
          style={s.phoneInput}
          value={phone}
          onChangeText={(val) => {
            setPhone(formatPhone(val));
            setError('');
          }}
          placeholder="(555) 123-4567"
          placeholderTextColor={COLORS.textTertiary}
          keyboardType="phone-pad"
          autoFocus
          editable={!loading}
          accessibilityLabel="Caregiver phone number"
        />
        {isValid && !loading ? (
          <Ionicons name="checkmark-circle" size={22} color={COLORS.success} />
        ) : null}
      </View>

      {error ? (
        <View style={s.errorWrap}>
          <Ionicons name="alert-circle-outline" size={16} color={COLORS.error} />
          <Text style={s.errorText}>{error}</Text>
        </View>
      ) : null}

      <TouchableOpacity
        style={[s.sendBtn, isValid && !loading && s.sendBtnActive]}
        onPress={handleSend}
        disabled={!isValid || loading}
        activeOpacity={0.8}
        accessibilityRole="button"
        accessibilityLabel="Send invite"
      >
        {loading ? (
          <ActivityIndicator color="#fff" />
        ) : (
          <>
            <Text style={s.sendBtnText}>Send Invite</Text>
            <Ionicons name="send" size={18} color="#fff" style={{ marginLeft: 8 }} />
          </>
        )}
      </TouchableOpacity>

      <View style={s.noteBox}>
        <Ionicons name="time-outline" size={16} color={COLORS.textSecondary} />
        <Text style={s.noteText}>
          The invite code expires in 48 hours. Your caregiver will get read-only access to your plan
          details.
        </Text>
      </View>
    </View>
  );
}

// ── Main Family Access Screen ───────────────────────────────────

export default function FamilyAccessScreen() {
  const router = useRouter();
  const { member } = getMemberSession();

  // Flow state: 'manage' | 'consent' | 'invite' | 'success'
  const [step, setStep] = useState('manage');
  const [consentText, setConsentText] = useState('');
  const [consentId, setConsentId] = useState(null);
  const [loading, setLoading] = useState(false);
  const [inviteMessage, setInviteMessage] = useState('');

  // Existing caregivers/invites
  const [activeCaregivers, setActiveCaregivers] = useState([]);
  const [pendingInvites, setPendingInvites] = useState([]);
  const [listLoading, setListLoading] = useState(true);

  const loadCaregivers = useCallback(async () => {
    setListLoading(true);
    try {
      const res = await authFetch(`${API_URL}/caregiver/my-caregivers`);
      if (res.ok) {
        const data = await res.json();
        setActiveCaregivers(data.active_caregivers || []);
        setPendingInvites(data.pending_invites || []);
      }
    } catch (err) {
      if (__DEV__) console.log('Load caregivers error:', err);
    } finally {
      setListLoading(false);
    }
  }, []);

  useEffect(() => {
    loadCaregivers();
  }, []);

  // Load consent text
  const loadConsent = async () => {
    setLoading(true);
    try {
      const res = await authFetch(`${API_URL}/caregiver/consent-text`);
      if (res.ok) {
        const data = await res.json();
        setConsentText(data.consent_text);
        setStep('consent');
      }
    } catch (err) {
      Alert.alert('Error', 'Unable to load consent form. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  // Approve consent
  const handleApproveConsent = async () => {
    setLoading(true);
    try {
      const res = await authFetch(`${API_URL}/caregiver/consent`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ consent_acknowledged: true }),
      });
      if (res.ok) {
        const data = await res.json();
        setConsentId(data.consent_id);
        setStep('invite');
      } else {
        Alert.alert('Error', 'Unable to record consent. Please try again.');
      }
    } catch (err) {
      Alert.alert('Error', 'Something went wrong. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  // Send invite
  const handleSendInvite = async (caregiverPhone) => {
    setLoading(true);
    try {
      const res = await authFetch(`${API_URL}/caregiver/invite`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ caregiver_phone: caregiverPhone, consent_id: consentId }),
      });
      const data = await res.json();
      if (res.ok) {
        setInviteMessage(data.message || 'Invite sent!');
        setStep('success');
        loadCaregivers();
      } else {
        Alert.alert('Unable to Send', data.detail || 'Something went wrong.');
      }
    } catch (err) {
      Alert.alert('Error', 'Unable to send invite. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  // Revoke access
  const handleRevoke = (inviteId) => {
    Alert.alert(
      'Remove Access',
      'This caregiver will no longer be able to view your plan details. Are you sure?',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Remove',
          style: 'destructive',
          onPress: async () => {
            try {
              const res = await authFetch(`${API_URL}/caregiver/revoke`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ invite_id: inviteId }),
              });
              if (res.ok) {
                loadCaregivers();
              }
            } catch (err) {
              Alert.alert('Error', 'Unable to revoke access.');
            }
          },
        },
      ],
    );
  };

  return (
    <View style={s.container}>
      <SafeAreaView style={s.safe} edges={['top']}>
        {/* Header */}
        <View style={s.header}>
          <TouchableOpacity
            onPress={() => {
              if (step === 'manage') router.back();
              else if (step === 'consent') setStep('manage');
              else if (step === 'invite') setStep('consent');
              else setStep('manage');
            }}
            style={s.backBtn}
            activeOpacity={0.7}
            accessibilityRole="button"
            accessibilityLabel="Go back"
          >
            <Ionicons name="chevron-back" size={22} color={COLORS.accent} />
            <Text style={s.backText}>
              {step === 'manage' ? 'Settings' : 'Back'}
            </Text>
          </TouchableOpacity>
          <Text style={s.title}>Family Access</Text>
          <View style={{ width: 70 }} />
        </View>

        <ScrollView style={s.body} contentContainerStyle={s.bodyContent}>
          {step === 'manage' && (
            <>
              {/* Invite button */}
              <TouchableOpacity
                style={s.inviteCard}
                onPress={loadConsent}
                activeOpacity={0.7}
                accessibilityRole="button"
                accessibilityLabel="Invite a caregiver"
              >
                <View style={s.inviteCardIcon}>
                  <Ionicons name="person-add" size={24} color={COLORS.accent} />
                </View>
                <View style={s.inviteCardInfo}>
                  <Text style={s.inviteCardLabel}>Invite a Caregiver</Text>
                  <Text style={s.inviteCardSub}>
                    Let a family member view your plan details
                  </Text>
                </View>
                <Ionicons name="chevron-forward" size={18} color={COLORS.textTertiary} />
              </TouchableOpacity>

              {/* Active Caregivers */}
              {activeCaregivers.length > 0 && (
                <>
                  <Text style={s.sectionLabel}>ACTIVE CAREGIVERS</Text>
                  <View style={s.card}>
                    {activeCaregivers.map((cg, i) => (
                      <View
                        key={cg.invite_id}
                        style={[
                          s.caregiverRow,
                          i === activeCaregivers.length - 1 && s.caregiverRowLast,
                        ]}
                      >
                        <View style={s.caregiverIcon}>
                          <Ionicons name="person" size={20} color={COLORS.accent} />
                        </View>
                        <View style={s.caregiverInfo}>
                          <Text style={s.caregiverLabel}>Caregiver</Text>
                          <Text style={s.caregiverSub}>
                            Active since{' '}
                            {new Date(cg.accepted_at * 1000).toLocaleDateString()}
                          </Text>
                        </View>
                        <TouchableOpacity
                          onPress={() => handleRevoke(cg.invite_id)}
                          style={s.revokeBtn}
                          activeOpacity={0.7}
                          accessibilityRole="button"
                          accessibilityLabel="Remove caregiver access"
                        >
                          <Text style={s.revokeText}>Remove</Text>
                        </TouchableOpacity>
                      </View>
                    ))}
                  </View>
                </>
              )}

              {/* Pending Invites */}
              {pendingInvites.length > 0 && (
                <>
                  <Text style={s.sectionLabel}>PENDING INVITES</Text>
                  <View style={s.card}>
                    {pendingInvites.map((inv, i) => (
                      <View
                        key={inv.invite_id}
                        style={[
                          s.caregiverRow,
                          i === pendingInvites.length - 1 && s.caregiverRowLast,
                        ]}
                      >
                        <View style={[s.caregiverIcon, { backgroundColor: COLORS.warningBg }]}>
                          <Ionicons name="time" size={20} color={COLORS.warning} />
                        </View>
                        <View style={s.caregiverInfo}>
                          <Text style={s.caregiverLabel}>Pending</Text>
                          <Text style={s.caregiverSub}>
                            Expires{' '}
                            {new Date(inv.expires_at * 1000).toLocaleDateString()}
                          </Text>
                        </View>
                        <TouchableOpacity
                          onPress={() => handleRevoke(inv.invite_id)}
                          style={s.revokeBtn}
                          activeOpacity={0.7}
                        >
                          <Text style={s.revokeText}>Cancel</Text>
                        </TouchableOpacity>
                      </View>
                    ))}
                  </View>
                </>
              )}

              {/* Empty state */}
              {!listLoading && activeCaregivers.length === 0 && pendingInvites.length === 0 && (
                <View style={s.emptyState}>
                  <Ionicons name="people-outline" size={48} color={COLORS.textTertiary} />
                  <Text style={s.emptyTitle}>No Caregivers Yet</Text>
                  <Text style={s.emptySub}>
                    Invite a trusted family member or caregiver to view your plan details and help
                    manage your benefits.
                  </Text>
                </View>
              )}

              {listLoading && (
                <View style={s.loadingWrap}>
                  <ActivityIndicator color={COLORS.accent} />
                </View>
              )}

              {/* Info box */}
              <View style={s.infoBox}>
                <Ionicons name="shield-checkmark-outline" size={20} color={COLORS.accent} />
                <View style={{ flex: 1 }}>
                  <Text style={s.infoTitle}>HIPAA Protected</Text>
                  <Text style={s.infoText}>
                    Caregivers can only view your plan details. They cannot change anything or see
                    your Medicare number. You can remove access at any time.
                  </Text>
                </View>
              </View>
            </>
          )}

          {step === 'consent' && (
            <ConsentScreen
              consentText={consentText}
              onApprove={handleApproveConsent}
              loading={loading}
            />
          )}

          {step === 'invite' && (
            <InviteForm onSend={handleSendInvite} loading={loading} consentId={consentId} />
          )}

          {step === 'success' && (
            <View style={s.successContainer}>
              <View style={s.successIcon}>
                <Ionicons name="checkmark-circle" size={64} color={COLORS.success} />
              </View>
              <Text style={s.successTitle}>Invite Sent!</Text>
              <Text style={s.successMessage}>{inviteMessage}</Text>
              <Text style={s.successSub}>
                They'll receive a text message with instructions to download the app and a
                verification code. The code expires in 48 hours.
              </Text>
              <TouchableOpacity
                style={s.doneBtn}
                onPress={() => setStep('manage')}
                activeOpacity={0.8}
                accessibilityRole="button"
                accessibilityLabel="Done"
              >
                <Text style={s.doneBtnText}>Done</Text>
              </TouchableOpacity>
            </View>
          )}
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
  backText: { fontSize: 16, fontWeight: '500', color: COLORS.accent },
  title: { fontSize: 18, fontWeight: '700', color: COLORS.text, textAlign: 'center' },

  // Body
  body: { flex: 1 },
  bodyContent: { padding: 18, paddingBottom: 40 },

  // Section
  sectionLabel: {
    fontSize: 12,
    fontWeight: '600',
    color: COLORS.textTertiary,
    letterSpacing: 0.5,
    marginBottom: 8,
    marginTop: 24,
    marginLeft: 4,
  },

  // Invite button card
  inviteCard: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: COLORS.white,
    borderRadius: RADII.md,
    padding: 16,
    gap: 14,
    ...SHADOWS.card,
    borderWidth: 1,
    borderColor: COLORS.borderLight,
  },
  inviteCardIcon: {
    width: 48,
    height: 48,
    borderRadius: 14,
    backgroundColor: COLORS.accentLight,
    justifyContent: 'center',
    alignItems: 'center',
  },
  inviteCardInfo: { flex: 1 },
  inviteCardLabel: { fontSize: 16, fontWeight: '600', color: COLORS.text },
  inviteCardSub: { fontSize: 13, color: COLORS.textSecondary, marginTop: 2 },

  // Card
  card: {
    backgroundColor: COLORS.white,
    borderRadius: RADII.md,
    ...SHADOWS.card,
    borderWidth: 1,
    borderColor: COLORS.borderLight,
    overflow: 'hidden',
  },

  // Caregiver rows
  caregiverRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 14,
    padding: 16,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.borderLight,
  },
  caregiverRowLast: { borderBottomWidth: 0 },
  caregiverIcon: {
    width: 40,
    height: 40,
    borderRadius: 12,
    backgroundColor: COLORS.accentLight,
    justifyContent: 'center',
    alignItems: 'center',
  },
  caregiverInfo: { flex: 1 },
  caregiverLabel: { fontSize: 15, fontWeight: '600', color: COLORS.text },
  caregiverSub: { fontSize: 13, color: COLORS.textSecondary, marginTop: 2 },
  revokeBtn: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 8,
    backgroundColor: COLORS.errorBg,
  },
  revokeText: { fontSize: 13, fontWeight: '600', color: COLORS.error },

  // Empty state
  emptyState: {
    alignItems: 'center',
    paddingVertical: 40,
    paddingHorizontal: 20,
    gap: 8,
  },
  emptyTitle: { fontSize: 18, fontWeight: '700', color: COLORS.text },
  emptySub: {
    fontSize: 14,
    color: COLORS.textSecondary,
    textAlign: 'center',
    lineHeight: 20,
  },

  // Loading
  loadingWrap: { padding: 40, alignItems: 'center' },

  // Info box
  infoBox: {
    flexDirection: 'row',
    gap: 12,
    padding: 16,
    backgroundColor: COLORS.accentLighter,
    borderRadius: RADII.md,
    marginTop: 24,
    borderWidth: 1,
    borderColor: COLORS.accentLight,
  },
  infoTitle: {
    fontSize: 13,
    fontWeight: '700',
    color: COLORS.accent,
    marginBottom: 4,
  },
  infoText: { fontSize: 13, color: COLORS.textSecondary, lineHeight: 19 },

  // ── Consent step ─────────────────────────────

  consentContainer: { flex: 1 },
  consentHeader: { alignItems: 'center', paddingBottom: 16, gap: 8 },
  consentTitle: { fontSize: 22, fontWeight: '700', color: COLORS.text },
  consentSub: { fontSize: 14, color: COLORS.textSecondary, textAlign: 'center' },

  consentScroll: {
    maxHeight: 380,
    backgroundColor: COLORS.white,
    borderRadius: RADII.md,
    borderWidth: 1,
    borderColor: COLORS.borderLight,
  },
  consentScrollContent: { padding: 16 },
  consentBody: {
    fontSize: 14,
    color: COLORS.text,
    lineHeight: 22,
  },

  consentFooter: { marginTop: 16, gap: 8 },
  scrollHint: {
    fontSize: 13,
    color: COLORS.textTertiary,
    textAlign: 'center',
    fontStyle: 'italic',
  },
  approveBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: COLORS.accent,
    borderRadius: RADII.md,
    paddingVertical: 18,
    ...SHADOWS.button,
  },
  approveBtnDisabled: { opacity: 0.4 },
  approveBtnText: { fontSize: 16, fontWeight: '700', color: '#fff' },

  // ── Invite step ──────────────────────────────

  inviteContainer: { flex: 1, gap: 16 },
  inviteHeader: { alignItems: 'center', paddingBottom: 8, gap: 8 },
  inviteTitle: { fontSize: 22, fontWeight: '700', color: COLORS.text },
  inviteSub: { fontSize: 14, color: COLORS.textSecondary, textAlign: 'center', lineHeight: 20 },

  fieldLabel: {
    fontSize: 12,
    fontWeight: '600',
    color: COLORS.textTertiary,
    letterSpacing: 0.5,
    marginBottom: 4,
    marginLeft: 4,
  },
  inputWrap: {
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: RADII.md,
    borderWidth: 2,
    borderColor: COLORS.borderLight,
    backgroundColor: COLORS.white,
    paddingHorizontal: 16,
    gap: 10,
  },
  inputWrapFocused: { borderColor: COLORS.accent },
  phoneInput: {
    flex: 1,
    paddingVertical: 16,
    fontSize: 20,
    fontWeight: '600',
    color: COLORS.text,
    letterSpacing: 1,
  },

  errorWrap: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: COLORS.errorBg,
    borderRadius: RADII.sm,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  errorText: { fontSize: 14, color: COLORS.error, flex: 1 },

  sendBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: COLORS.textTertiary,
    borderRadius: RADII.md,
    paddingVertical: 18,
    ...SHADOWS.button,
  },
  sendBtnActive: { backgroundColor: COLORS.accent },
  sendBtnText: { fontSize: 16, fontWeight: '700', color: '#fff' },

  noteBox: {
    flexDirection: 'row',
    gap: 8,
    padding: 14,
    backgroundColor: COLORS.cardTinted,
    borderRadius: RADII.sm,
    borderWidth: 1,
    borderColor: COLORS.borderLight,
  },
  noteText: { fontSize: 13, color: COLORS.textSecondary, flex: 1, lineHeight: 19 },

  // ── Success step ─────────────────────────────

  successContainer: { alignItems: 'center', paddingVertical: 40, gap: 12 },
  successIcon: { marginBottom: 8 },
  successTitle: { fontSize: 24, fontWeight: '700', color: COLORS.text },
  successMessage: { fontSize: 16, fontWeight: '600', color: COLORS.accent },
  successSub: {
    fontSize: 14,
    color: COLORS.textSecondary,
    textAlign: 'center',
    lineHeight: 20,
    paddingHorizontal: 20,
  },
  doneBtn: {
    backgroundColor: COLORS.accent,
    borderRadius: RADII.md,
    paddingVertical: 16,
    paddingHorizontal: 48,
    marginTop: 16,
    ...SHADOWS.button,
  },
  doneBtnText: { fontSize: 16, fontWeight: '700', color: '#fff' },
});
