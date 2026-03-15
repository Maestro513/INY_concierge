import { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ScrollView,
  ActivityIndicator,
  Alert,
} from 'react-native';
import { useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons, MaterialCommunityIcons } from '@expo/vector-icons';
import { COLORS, RADII, SHADOWS, BENEFIT_ICON_MAP, DEFAULT_ICON } from '../constants/theme';
import { API_URL, authFetch } from '../constants/api';
import { logout, clearCaregiverView } from '../constants/session';

function getIconForLabel(label) {
  const lower = (label || '').toLowerCase();
  for (const [key, icon] of Object.entries(BENEFIT_ICON_MAP)) {
    if (lower.includes(key)) return icon;
  }
  return DEFAULT_ICON;
}

function BenefitCard({ label, value, period }) {
  const icon = getIconForLabel(label);
  const IconFamily = icon.family === 'MaterialCommunityIcons' ? MaterialCommunityIcons : Ionicons;

  return (
    <View style={s.benefitCard}>
      <View style={[s.benefitIcon, { backgroundColor: icon.bg }]}>
        <IconFamily name={icon.name} size={18} color={icon.color} />
      </View>
      <Text style={s.benefitLabel} numberOfLines={1}>{label}</Text>
      <Text style={s.benefitValue}>{value}</Text>
      {period ? <Text style={s.benefitPeriod}>{period}</Text> : null}
    </View>
  );
}

export default function CaregiverHomeScreen() {
  const router = useRouter();
  const [members, setMembers] = useState([]);
  const [selectedMember, setSelectedMember] = useState(null);
  const [memberData, setMemberData] = useState(null);
  const [benefits, setBenefits] = useState([]);
  const [loading, setLoading] = useState(true);
  const [benefitsLoading, setBenefitsLoading] = useState(false);

  // Load members this caregiver has access to
  useEffect(() => {
    loadMembers();
  }, []);

  const loadMembers = async () => {
    setLoading(true);
    try {
      const res = await authFetch(`${API_URL}/caregiver/my-members`);
      if (res.ok) {
        const data = await res.json();
        setMembers(data.members || []);
        // Auto-select first member
        if (data.members && data.members.length > 0) {
          selectMember(data.members[0]);
        }
      }
    } catch (err) {
      if (__DEV__) console.log('Load members error:', err);
    } finally {
      setLoading(false);
    }
  };

  const selectMember = async (member) => {
    setSelectedMember(member);
    setBenefitsLoading(true);
    try {
      const res = await authFetch(`${API_URL}/caregiver/member-data/${member.invite_id}`);
      if (res.ok) {
        const data = await res.json();
        setMemberData(data);
        // Load benefits for this member
        if (data.plan_number) {
          loadBenefits(data.plan_number);
        } else {
          setBenefitsLoading(false);
        }
      } else {
        setMemberData(null);
        setBenefitsLoading(false);
      }
    } catch (err) {
      if (__DEV__) console.log('Load member data error:', err);
      setBenefitsLoading(false);
    }
  };

  const loadBenefits = async (planNumber) => {
    try {
      const res = await authFetch(`${API_URL}/benefits/${planNumber}`);
      if (res.ok) {
        const data = await res.json();
        setBenefits(buildBenefitCards(data));
      }
    } catch (err) {
      if (__DEV__) console.log('Load benefits error:', err);
    } finally {
      setBenefitsLoading(false);
    }
  };

  const handleLogout = () => {
    Alert.alert('Log Out', 'Are you sure you want to log out?', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Log Out',
        style: 'destructive',
        onPress: async () => {
          clearCaregiverView();
          await logout();
          router.replace('/');
        },
      },
    ]);
  };

  if (loading) {
    return (
      <View style={[s.container, { justifyContent: 'center', alignItems: 'center' }]}>
        <ActivityIndicator size="large" color={COLORS.accent} />
        <Text style={{ marginTop: 12, color: COLORS.textSecondary }}>Loading...</Text>
      </View>
    );
  }

  if (members.length === 0) {
    return (
      <View style={s.container}>
        <SafeAreaView style={s.safe} edges={['top']}>
          <View style={s.emptyContainer}>
            <Ionicons name="people-outline" size={64} color={COLORS.textTertiary} />
            <Text style={s.emptyTitle}>No Access Yet</Text>
            <Text style={s.emptyText}>
              You don't have access to any member's plan yet. Ask the member to send you an invite
              from their Settings.
            </Text>
            <TouchableOpacity style={s.logoutBtn} onPress={handleLogout} activeOpacity={0.7}>
              <Ionicons name="log-out-outline" size={18} color={COLORS.error} />
              <Text style={s.logoutText}>Log Out</Text>
            </TouchableOpacity>
          </View>
        </SafeAreaView>
      </View>
    );
  }

  return (
    <View style={s.container}>
      <SafeAreaView style={s.safe} edges={['top']}>
        {/* Header with read-only badge */}
        <View style={s.header}>
          <View style={s.headerLeft}>
            <View style={s.readOnlyBadge}>
              <Ionicons name="eye-outline" size={14} color={COLORS.accent} />
              <Text style={s.readOnlyText}>View Only</Text>
            </View>
          </View>
          <Text style={s.headerTitle}>Caregiver View</Text>
          <TouchableOpacity onPress={handleLogout} style={s.headerRight} activeOpacity={0.7}>
            <Ionicons name="log-out-outline" size={22} color={COLORS.textSecondary} />
          </TouchableOpacity>
        </View>

        <ScrollView style={s.body} contentContainerStyle={s.bodyContent}>
          {/* Member selector (if multiple) */}
          {members.length > 1 && (
            <ScrollView
              horizontal
              showsHorizontalScrollIndicator={false}
              style={s.memberPicker}
              contentContainerStyle={s.memberPickerContent}
            >
              {members.map((m) => (
                <TouchableOpacity
                  key={m.invite_id}
                  style={[
                    s.memberChip,
                    selectedMember?.invite_id === m.invite_id && s.memberChipActive,
                  ]}
                  onPress={() => selectMember(m)}
                  activeOpacity={0.7}
                >
                  <Text
                    style={[
                      s.memberChipText,
                      selectedMember?.invite_id === m.invite_id && s.memberChipTextActive,
                    ]}
                  >
                    {m.first_name} {m.last_name}
                  </Text>
                </TouchableOpacity>
              ))}
            </ScrollView>
          )}

          {/* Member info card */}
          {memberData && (
            <View style={s.memberCard}>
              <View style={s.memberAvatar}>
                <Text style={s.memberAvatarText}>
                  {(memberData.first_name || '?')[0]}
                  {(memberData.last_name || '?')[0]}
                </Text>
              </View>
              <Text style={s.memberName}>
                {memberData.first_name} {memberData.last_name}
              </Text>
              <Text style={s.memberPlan}>{memberData.plan_name || 'No plan'}</Text>
              <View style={s.memberBadge}>
                <Ionicons name="lock-closed-outline" size={12} color={COLORS.textTertiary} />
                <Text style={s.memberBadgeText}>Medicare # {memberData.medicare_number}</Text>
              </View>
            </View>
          )}

          {/* Benefits */}
          {benefitsLoading ? (
            <View style={s.loadingWrap}>
              <ActivityIndicator color={COLORS.accent} />
              <Text style={s.loadingText}>Loading benefits...</Text>
            </View>
          ) : benefits.length > 0 ? (
            <>
              <Text style={s.sectionLabel}>PLAN BENEFITS</Text>
              <View style={s.benefitsGrid}>
                {benefits.map((b, i) => (
                  <BenefitCard key={i} label={b.label} value={b.in_network} period={b._period} />
                ))}
              </View>
            </>
          ) : null}

          {/* Quick actions */}
          {memberData && memberData.plan_number && (
            <>
              <Text style={s.sectionLabel}>QUICK ACTIONS</Text>
              <View style={s.actionsRow}>
                <TouchableOpacity
                  style={s.actionCard}
                  onPress={() => router.push('/digital-id')}
                  activeOpacity={0.7}
                >
                  <Ionicons name="card-outline" size={24} color={COLORS.accent} />
                  <Text style={s.actionLabel}>ID Card</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={s.actionCard}
                  onPress={() => router.push('/pharmacy-results')}
                  activeOpacity={0.7}
                >
                  <MaterialCommunityIcons name="pill" size={24} color={COLORS.accent} />
                  <Text style={s.actionLabel}>Pharmacies</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={s.actionCard}
                  onPress={() => router.push('/doctor-results')}
                  activeOpacity={0.7}
                >
                  <MaterialCommunityIcons name="stethoscope" size={24} color={COLORS.accent} />
                  <Text style={s.actionLabel}>Doctors</Text>
                </TouchableOpacity>
              </View>
            </>
          )}

          {/* Caregiver notice */}
          <View style={s.noticeBox}>
            <Ionicons name="information-circle-outline" size={20} color={COLORS.accent} />
            <Text style={s.noticeText}>
              You're viewing this plan as a caregiver. You have read-only access. The member can
              revoke your access at any time from their Settings.
            </Text>
          </View>
        </ScrollView>
      </SafeAreaView>
    </View>
  );
}

function buildBenefitCards(data) {
  if (!data || typeof data !== 'object') return [];
  const cards = [];
  const med = data.medical && typeof data.medical === 'object' ? data.medical : {};
  const dental = data.dental && typeof data.dental === 'object' ? data.dental : {};
  const otc = data.otc && typeof data.otc === 'object' ? data.otc : {};
  const giveback = data.part_b_giveback && typeof data.part_b_giveback === 'object' ? data.part_b_giveback : {};

  if (med.pcp_copay) cards.push({ label: 'PCP Visit', in_network: String(med.pcp_copay) });
  if (med.specialist_copay) cards.push({ label: 'Specialist', in_network: String(med.specialist_copay) });
  if (med.urgent_care_copay) cards.push({ label: 'Urgent Care', in_network: String(med.urgent_care_copay) });
  if (med.er_copay) cards.push({ label: 'Emergency Room', in_network: String(med.er_copay) });

  if (dental.has_preventive && dental.preventive) {
    cards.push({ label: 'Dental Max', in_network: dental.preventive.max_benefit || '$0 copay', _period: 'Per year' });
  }
  if (giveback.has_giveback && giveback.monthly_amount) {
    const amt = String(giveback.monthly_amount);
    cards.push({ label: 'Part B Giveback', in_network: (amt.startsWith('$') ? amt : '$' + amt) + '/mo' });
  }
  if (otc.has_otc && otc.amount) {
    const amt = String(otc.amount);
    const period = otc.period === 'Monthly' ? 'Per month' : otc.period === 'Quarterly' ? 'Per quarter' : 'Per year';
    cards.push({ label: 'OTC Allowance', in_network: amt.startsWith('$') ? amt : '$' + amt, _period: period });
  }

  return cards;
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
  headerLeft: { width: 90 },
  headerTitle: { fontSize: 18, fontWeight: '700', color: COLORS.text },
  headerRight: { width: 90, alignItems: 'flex-end' },

  readOnlyBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    backgroundColor: COLORS.accentLight,
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
  },
  readOnlyText: { fontSize: 12, fontWeight: '600', color: COLORS.accent },

  // Body
  body: { flex: 1 },
  bodyContent: { padding: 18, paddingBottom: 40 },

  // Member picker
  memberPicker: { marginBottom: 16 },
  memberPickerContent: { gap: 8 },
  memberChip: {
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 20,
    backgroundColor: COLORS.white,
    borderWidth: 1,
    borderColor: COLORS.borderLight,
  },
  memberChipActive: {
    backgroundColor: COLORS.accent,
    borderColor: COLORS.accent,
  },
  memberChipText: { fontSize: 14, fontWeight: '600', color: COLORS.text },
  memberChipTextActive: { color: '#fff' },

  // Member card
  memberCard: {
    alignItems: 'center',
    backgroundColor: COLORS.white,
    borderRadius: RADII.lg,
    padding: 24,
    ...SHADOWS.card,
    borderWidth: 1,
    borderColor: COLORS.borderLight,
    marginBottom: 20,
  },
  memberAvatar: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: COLORS.accentLight,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 12,
  },
  memberAvatarText: { fontSize: 24, fontWeight: '700', color: COLORS.accent },
  memberName: { fontSize: 22, fontWeight: '700', color: COLORS.text },
  memberPlan: { fontSize: 14, color: COLORS.textSecondary, marginTop: 4 },
  memberBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    marginTop: 8,
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 8,
    backgroundColor: COLORS.cardTinted,
  },
  memberBadgeText: { fontSize: 12, color: COLORS.textTertiary },

  // Section
  sectionLabel: {
    fontSize: 12,
    fontWeight: '600',
    color: COLORS.textTertiary,
    letterSpacing: 0.5,
    marginBottom: 8,
    marginTop: 8,
    marginLeft: 4,
  },

  // Benefits grid
  benefitsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
    marginBottom: 20,
  },
  benefitCard: {
    width: '48%',
    backgroundColor: COLORS.white,
    borderRadius: RADII.md,
    padding: 14,
    ...SHADOWS.soft,
    borderWidth: 1,
    borderColor: COLORS.borderLight,
  },
  benefitIcon: {
    width: 32,
    height: 32,
    borderRadius: 10,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 8,
  },
  benefitLabel: { fontSize: 12, fontWeight: '600', color: COLORS.textSecondary },
  benefitValue: { fontSize: 18, fontWeight: '700', color: COLORS.text, marginTop: 2 },
  benefitPeriod: { fontSize: 11, color: COLORS.textTertiary, marginTop: 2 },

  // Actions
  actionsRow: {
    flexDirection: 'row',
    gap: 10,
    marginBottom: 20,
  },
  actionCard: {
    flex: 1,
    alignItems: 'center',
    backgroundColor: COLORS.white,
    borderRadius: RADII.md,
    paddingVertical: 16,
    gap: 6,
    ...SHADOWS.soft,
    borderWidth: 1,
    borderColor: COLORS.borderLight,
  },
  actionLabel: { fontSize: 12, fontWeight: '600', color: COLORS.text },

  // Notice
  noticeBox: {
    flexDirection: 'row',
    gap: 10,
    padding: 14,
    backgroundColor: COLORS.accentLighter,
    borderRadius: RADII.md,
    borderWidth: 1,
    borderColor: COLORS.accentLight,
    marginTop: 8,
  },
  noticeText: { fontSize: 13, color: COLORS.textSecondary, flex: 1, lineHeight: 19 },

  // Empty
  emptyContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 40,
    gap: 12,
  },
  emptyTitle: { fontSize: 22, fontWeight: '700', color: COLORS.text },
  emptyText: {
    fontSize: 15,
    color: COLORS.textSecondary,
    textAlign: 'center',
    lineHeight: 22,
  },
  logoutBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginTop: 20,
    paddingHorizontal: 20,
    paddingVertical: 12,
    borderRadius: RADII.sm,
    backgroundColor: COLORS.errorBg,
  },
  logoutText: { fontSize: 15, fontWeight: '600', color: COLORS.error },

  // Loading
  loadingWrap: { padding: 30, alignItems: 'center', gap: 8 },
  loadingText: { fontSize: 14, color: COLORS.textSecondary },
});
