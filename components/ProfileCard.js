import { useState, useRef, useEffect } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  Image,
  StyleSheet,
  ActivityIndicator,
  Animated,
  Switch,
  TextInput,
  Modal,
  ScrollView,
} from 'react-native';
import { Ionicons, MaterialCommunityIcons } from '@expo/vector-icons';
import {
  COLORS,
  RADII,
  SPACING,
  SHADOWS,
  TYPE,
  MOTION,
  BENEFIT_ICON_MAP,
  DEFAULT_ICON,
} from '../constants/theme';

// Carrier logo map — filenames must match assets/carriers/
const CARRIER_LOGOS = {
  humana: require('../assets/carriers/humana.png'),
  uhc: require('../assets/carriers/uhc.png'),
  aetna: require('../assets/carriers/aetna.png'),
  devoted: require('../assets/carriers/devoted.png'),
  wellcare: require('../assets/carriers/wellcare.png'),
  zing: require('../assets/carriers/zing.png'),
  healthspring: require('../assets/carriers/healthspring.png'),
};

function detectCarrier(planName) {
  if (!planName) return null;
  const name = planName.toLowerCase();
  if (name.includes('humana')) return 'humana';
  if (name.includes('uhc') || name.includes('unitedhealthcare') || name.includes('aarp'))
    return 'uhc';
  if (name.includes('aetna')) return 'aetna';
  if (name.includes('devoted')) return 'devoted';
  if (name.includes('wellcare')) return 'wellcare';
  if (name.includes('zing')) return 'zing';
  if (name.includes('healthspring')) return 'healthspring';
  return null;
}

// ── Icon resolver using BENEFIT_ICON_MAP from theme ───────────
const ICON_FAMILIES = { Ionicons, MaterialCommunityIcons };

function resolveIcon(label) {
  const lower = label.toLowerCase();
  for (const [key, config] of Object.entries(BENEFIT_ICON_MAP)) {
    if (lower.includes(key)) return config;
  }
  return DEFAULT_ICON;
}

function BenefitIcon({ label, size = 20 }) {
  const config = resolveIcon(label);
  const IconComponent = ICON_FAMILIES[config.family];
  if (!IconComponent) return null;
  return (
    <View style={[styles.iconCircle, { backgroundColor: config.bg }]}>
      <IconComponent name={config.name} size={size} color={config.color} />
    </View>
  );
}

// ── Animated card wrapper (staggered fade-in + slide-up) ──────
function AnimatedCard({ children, index, style }) {
  const opacity = useRef(new Animated.Value(0)).current;
  const translateY = useRef(new Animated.Value(12)).current;

  useEffect(() => {
    Animated.parallel([
      Animated.timing(opacity, {
        toValue: 1,
        duration: MOTION.normal,
        delay: index * MOTION.staggerDelay,
        useNativeDriver: true,
      }),
      Animated.timing(translateY, {
        toValue: 0,
        duration: MOTION.normal,
        delay: index * MOTION.staggerDelay,
        useNativeDriver: true,
      }),
    ]).start();
  }, []);

  return (
    <Animated.View style={[style, { opacity, transform: [{ translateY }] }]}>
      {children}
    </Animated.View>
  );
}

// ── Reminder helpers ────────────────────────────────────────────
function formatTime(hour, minute) {
  const ampm = hour >= 12 ? 'PM' : 'AM';
  const h = hour === 0 ? 12 : hour > 12 ? hour - 12 : hour;
  const m = String(minute).padStart(2, '0');
  return `${h}:${m} ${ampm}`;
}

function ReminderRow({ reminder, onToggle, onDelete }) {
  return (
    <View style={styles.remRow}>
      <View style={styles.remIcon}>
        <MaterialCommunityIcons name="pill" size={16} color={COLORS.rxDrug} />
      </View>
      <View style={styles.remInfo}>
        <Text style={styles.remDrug} numberOfLines={1}>
          {reminder.drug_name}
          {reminder.dose_label ? <Text style={styles.remDose}> {reminder.dose_label}</Text> : null}
        </Text>
        <Text style={styles.remTime}>{formatTime(reminder.time_hour, reminder.time_minute)}</Text>
      </View>
      <Switch
        value={!!reminder.enabled}
        onValueChange={(val) => onToggle(reminder.id, val)}
        trackColor={{ false: COLORS.border, true: COLORS.accentSoft }}
        thumbColor={reminder.enabled ? COLORS.accent : COLORS.textTertiary}
        style={{ transform: [{ scale: 0.8 }] }}
        accessibilityLabel={`${reminder.drug_name} reminder ${reminder.enabled ? 'enabled' : 'disabled'}`}
        accessibilityRole="switch"
      />
      <TouchableOpacity
        onPress={() => onDelete(reminder.id)}
        hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
        accessibilityRole="button"
        accessibilityLabel={`Delete ${reminder.drug_name} reminder`}
      >
        <Ionicons name="trash-outline" size={16} color={COLORS.textTertiary} />
      </TouchableOpacity>
    </View>
  );
}

function AddReminderModal({ visible, onClose, onSave }) {
  const [drugName, setDrugName] = useState('');
  const [doseLabel, setDoseLabel] = useState('');
  const [hour, setHour] = useState(8);
  const [minute, setMinute] = useState(0);
  const [ampm, setAmpm] = useState('AM');
  const [saving, setSaving] = useState(false);

  const reset = () => {
    setDrugName('');
    setDoseLabel('');
    setHour(8);
    setMinute(0);
    setAmpm('AM');
    setSaving(false);
  };

  const handleSave = async () => {
    if (!drugName.trim()) return;
    setSaving(true);
    const h24 = ampm === 'PM' ? (hour === 12 ? 12 : hour + 12) : hour === 12 ? 0 : hour;
    await onSave({
      drug_name: drugName.trim(),
      dose_label: doseLabel.trim(),
      time_hour: h24,
      time_minute: minute,
    });
    reset();
    onClose();
  };

  const adjustHour = (d) =>
    setHour((p) => {
      const n = p + d;
      return n > 12 ? 1 : n < 1 ? 12 : n;
    });
  const adjustMinute = (d) =>
    setMinute((p) => {
      const n = p + d;
      return n >= 60 ? 0 : n < 0 ? 45 : n;
    });

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={styles.modalOverlay}>
        <View style={styles.modalContent}>
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>Add Reminder</Text>
            <TouchableOpacity
              onPress={() => {
                reset();
                onClose();
              }}
              accessibilityRole="button"
              accessibilityLabel="Close add reminder"
            >
              <Ionicons name="close" size={24} color={COLORS.textSecondary} />
            </TouchableOpacity>
          </View>
          <Text style={styles.fieldLabel}>Medication</Text>
          <TextInput
            style={styles.modalInput}
            value={drugName}
            onChangeText={setDrugName}
            placeholder="e.g. Metformin"
            placeholderTextColor={COLORS.textTertiary}
            autoFocus
            maxLength={200}
            accessibilityLabel="Medication name"
          />
          <Text style={styles.fieldLabel}>Dose (optional)</Text>
          <TextInput
            style={styles.modalInput}
            value={doseLabel}
            onChangeText={setDoseLabel}
            placeholder="e.g. 500mg"
            placeholderTextColor={COLORS.textTertiary}
            maxLength={200}
            accessibilityLabel="Dose, optional"
          />
          <Text style={styles.fieldLabel}>Reminder Time</Text>
          <View style={styles.timeRow}>
            <View style={styles.timeSpinner}>
              <TouchableOpacity
                onPress={() => adjustHour(1)}
                style={styles.spinBtn}
                accessibilityRole="button"
                accessibilityLabel="Increase hour"
              >
                <Ionicons name="chevron-up" size={20} color={COLORS.accent} />
              </TouchableOpacity>
              <Text style={styles.timeValue} accessibilityLabel={`Hour: ${hour}`}>
                {String(hour).padStart(2, '0')}
              </Text>
              <TouchableOpacity
                onPress={() => adjustHour(-1)}
                style={styles.spinBtn}
                accessibilityRole="button"
                accessibilityLabel="Decrease hour"
              >
                <Ionicons name="chevron-down" size={20} color={COLORS.accent} />
              </TouchableOpacity>
            </View>
            <Text style={styles.timeColon} accessibilityElementsHidden>
              :
            </Text>
            <View style={styles.timeSpinner}>
              <TouchableOpacity
                onPress={() => adjustMinute(15)}
                style={styles.spinBtn}
                accessibilityRole="button"
                accessibilityLabel="Increase minutes"
              >
                <Ionicons name="chevron-up" size={20} color={COLORS.accent} />
              </TouchableOpacity>
              <Text style={styles.timeValue} accessibilityLabel={`Minutes: ${minute}`}>
                {String(minute).padStart(2, '0')}
              </Text>
              <TouchableOpacity
                onPress={() => adjustMinute(-15)}
                style={styles.spinBtn}
                accessibilityRole="button"
                accessibilityLabel="Decrease minutes"
              >
                <Ionicons name="chevron-down" size={20} color={COLORS.accent} />
              </TouchableOpacity>
            </View>
            <View style={styles.ampmToggle}>
              <TouchableOpacity
                style={[styles.ampmBtn, ampm === 'AM' && styles.ampmActive]}
                onPress={() => setAmpm('AM')}
                accessibilityRole="button"
                accessibilityLabel="AM"
                accessibilityState={{ selected: ampm === 'AM' }}
              >
                <Text style={[styles.ampmText, ampm === 'AM' && styles.ampmTextActive]}>AM</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.ampmBtn, ampm === 'PM' && styles.ampmActive]}
                onPress={() => setAmpm('PM')}
                accessibilityRole="button"
                accessibilityLabel="PM"
                accessibilityState={{ selected: ampm === 'PM' }}
              >
                <Text style={[styles.ampmText, ampm === 'PM' && styles.ampmTextActive]}>PM</Text>
              </TouchableOpacity>
            </View>
          </View>
          <TouchableOpacity
            style={[styles.saveBtn, (!drugName.trim() || saving) && styles.saveBtnDisabled]}
            onPress={handleSave}
            disabled={!drugName.trim() || saving}
            activeOpacity={0.8}
            accessibilityRole="button"
            accessibilityLabel="Save reminder"
            accessibilityState={{ disabled: !drugName.trim() || saving }}
          >
            {saving ? (
              <ActivityIndicator color={COLORS.white} size="small" />
            ) : (
              <Text style={styles.saveBtnText}>Save Reminder</Text>
            )}
          </TouchableOpacity>
        </View>
      </View>
    </Modal>
  );
}

// ── Main component ──────────────────────────────────────────────
export default function ProfileCard({
  member,
  onViewSOB,
  benefits,
  loading,
  benefitsError,
  onRetryBenefits,
  reminders = [],
  onToggleReminder,
  onDeleteReminder,
  onAddReminder,
  drugsData,
  _onLogout,
  onOpenSettings,
  onBookTransportation,
  onOpenMessages,
}) {
  const [remindersExpanded, setRemindersExpanded] = useState(false);
  const [showAddModal, setShowAddModal] = useState(false);
  const [showMedsModal, setShowMedsModal] = useState(false);

  // Greeting entrance animation
  const greetFade = useRef(new Animated.Value(0)).current;
  const greetSlide = useRef(new Animated.Value(10)).current;

  useEffect(() => {
    Animated.parallel([
      Animated.timing(greetFade, { toValue: 1, duration: MOTION.slow, useNativeDriver: true }),
      Animated.timing(greetSlide, { toValue: 0, duration: MOTION.slow, useNativeDriver: true }),
    ]).start();
  }, []);

  const now = new Date();
  const greeting = () => {
    const hour = now.getHours();
    if (hour < 12) return 'Good morning,';
    if (hour < 17) return 'Good afternoon,';
    return 'Good evening,';
  };

  const carrier = detectCarrier(member.planName);
  const carrierLogo = carrier ? CARRIER_LOGOS[carrier] : null;

  const row1 = (benefits || []).filter((b) => b._row === 1);
  const row2 = (benefits || []).filter((b) => b._row === 2);

  return (
    <View style={styles.container}>
      {/* Header: Greeting + Name + Agent | Carrier Logo + Plan Name */}
      <Animated.View
        style={[styles.header, { opacity: greetFade, transform: [{ translateY: greetSlide }] }]}
      >
        <View style={styles.headerLeft}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Text style={styles.greeting}>{greeting()}</Text>
          </View>
          <Text style={styles.name}>
            {member.firstName} {member.lastName}
          </Text>
        </View>
        <View style={styles.headerRight}>
          <View style={styles.logoBg} accessibilityLabel={`${carrier || 'insurance'} plan`}>
            {carrierLogo ? (
              <Image
                source={carrierLogo}
                style={styles.carrierLogo}
                resizeMode="contain"
                accessibilityRole="image"
              />
            ) : (
              <Text style={styles.carrierFallbackText} numberOfLines={1}>
                {member.planName}
              </Text>
            )}
            {member.planNumber ? (
              <Text style={styles.planNumberInLogo}>{member.planNumber}</Text>
            ) : null}
          </View>
        </View>
      </Animated.View>

      <AddReminderModal
        visible={showAddModal}
        onClose={() => setShowAddModal(false)}
        onSave={onAddReminder}
      />

      {/* Medications detail modal */}
      <Modal
        visible={showMedsModal}
        transparent
        animationType="slide"
        onRequestClose={() => setShowMedsModal(false)}
      >
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Your Medications</Text>
              <TouchableOpacity
                onPress={() => setShowMedsModal(false)}
                accessibilityRole="button"
                accessibilityLabel="Close medications list"
              >
                <Ionicons name="close" size={24} color={COLORS.textSecondary} />
              </TouchableOpacity>
            </View>
            {drugsData && drugsData.medications ? (
              drugsData.medications.map((med, i) => (
                <View key={String(i)} style={styles.medRow}>
                  <View style={styles.medIconWrap}>
                    <MaterialCommunityIcons name="pill" size={18} color={COLORS.rxDrug} />
                  </View>
                  <View style={styles.medInfo}>
                    <Text style={styles.medName}>{med.drug_name}</Text>
                    <Text style={styles.medDetail}>
                      {med.tier_label}
                      {med.copay_display ? ` · ${med.copay_display}/mo` : ''}
                    </Text>
                  </View>
                  <Text style={styles.medCost}>{med.copay_display || '—'}</Text>
                </View>
              ))
            ) : (
              <Text style={styles.remEmpty}>No medication data available.</Text>
            )}
            {drugsData && drugsData.annual_display ? (
              <View style={styles.medTotalRow}>
                <Text style={styles.medTotalLabel}>Est. Annual Total</Text>
                <Text style={styles.medTotalValue}>{drugsData.annual_display}/yr</Text>
              </View>
            ) : null}
          </View>
        </View>
      </Modal>

      {/* Quick Actions — pill style */}
      <View style={styles.quickActionsRow}>
        <TouchableOpacity
          onPress={onBookTransportation}
          style={styles.quickPill}
          activeOpacity={0.7}
          accessibilityRole="button"
          accessibilityLabel="Book transportation"
        >
          <Ionicons name="bus-outline" size={18} color={COLORS.accent} />
          <Text style={styles.quickPillText}>Book Ride</Text>
        </TouchableOpacity>
        <TouchableOpacity
          onPress={() => setRemindersExpanded(!remindersExpanded)}
          style={styles.quickPill}
          activeOpacity={0.7}
          accessibilityRole="button"
          accessibilityLabel="Medication reminders"
        >
          <Ionicons name="alarm-outline" size={18} color={COLORS.accent} />
          <Text style={styles.quickPillText}>Reminders</Text>
          {reminders.length > 0 ? (
            <View style={styles.quickPillBadge}>
              <Text style={styles.quickPillBadgeText}>{reminders.length}</Text>
            </View>
          ) : null}
        </TouchableOpacity>
        <TouchableOpacity
          onPress={onOpenMessages}
          style={styles.quickPill}
          activeOpacity={0.7}
          accessibilityRole="button"
          accessibilityLabel="Send a message to your agent"
        >
          <Ionicons name="chatbubble-outline" size={18} color={COLORS.accent} />
          <Text style={styles.quickPillText}>Messages</Text>
        </TouchableOpacity>
        <TouchableOpacity
          onPress={onViewSOB}
          style={styles.quickPill}
          activeOpacity={0.7}
          accessibilityRole="button"
          accessibilityLabel="View benefits and ID card"
        >
          <Ionicons name="document-text-outline" size={18} color={COLORS.accent} />
          <Text style={styles.quickPillText}>Benefits</Text>
        </TouchableOpacity>
      </View>

      {/* Expanded reminders section */}
      {remindersExpanded ? (
        <View style={styles.remBody}>
          {reminders.length === 0 ? (
            <Text style={styles.remEmpty}>
              No reminders yet. Tap + or say "Remind me to take my medication at 8am"
            </Text>
          ) : (
            reminders.map((r) => (
              <ReminderRow
                key={String(r.id)}
                reminder={r}
                onToggle={onToggleReminder}
                onDelete={onDeleteReminder}
              />
            ))
          )}
          <TouchableOpacity
            style={styles.remAddBtn}
            onPress={() => setShowAddModal(true)}
            activeOpacity={0.7}
            accessibilityRole="button"
            accessibilityLabel="Add medication reminder"
          >
            <Ionicons name="add-circle-outline" size={16} color={COLORS.accent} />
            <Text style={styles.remAddText}>Add Reminder</Text>
          </TouchableOpacity>
        </View>
      ) : null}

      {/* Agent + Settings gear — right above cards */}
      <View style={styles.aboveCardsRow}>
        {member.agent ? (
          <View style={styles.agentRow}>
            <Ionicons name="person-outline" size={14} color={COLORS.textSecondary} />
            <Text style={styles.agent}>Agent: {member.agent}</Text>
          </View>
        ) : (
          <View />
        )}
        <TouchableOpacity
          onPress={onOpenSettings}
          style={styles.settingsGear}
          activeOpacity={0.7}
          accessibilityRole="button"
          accessibilityLabel="Open settings"
        >
          <Ionicons name="settings-outline" size={22} color={COLORS.textSecondary} />
        </TouchableOpacity>
      </View>

      {/* Benefits */}
      {loading ? (
        <View style={styles.loadingWrap}>
          <ActivityIndicator size="small" color={COLORS.accent} />
          <Text style={styles.loadingText}>Loading benefits...</Text>
        </View>
      ) : row1.length > 0 ? (
        <>
          {/* Copays — 2x2 grid */}
          <Text style={styles.sectionLabel}>Your Copays</Text>
          <View style={styles.copayGrid}>
            {row1.map((b, i) => {
              const value = b.in_network || '';
              const isFree = value === '$0' || value.toLowerCase().includes('no cost');
              return (
                <AnimatedCard key={'c-' + String(i)} index={i} style={styles.copayCard}>
                  <BenefitIcon label={b.label} size={20} />
                  <View style={styles.copayInfo}>
                    <Text style={styles.copayLabel} numberOfLines={1}>
                      {b.label}
                    </Text>
                    <Text style={styles.copayValue}>{value}</Text>
                    {isFree ? (
                      <View style={styles.badgeFree}>
                        <Text style={styles.badgeFreeText}>No Cost</Text>
                      </View>
                    ) : b._highlight ? (
                      <View style={styles.badgeHighlight}>
                        <Text style={styles.badgeHighlightText}>{b._highlight}</Text>
                      </View>
                    ) : null}
                  </View>
                </AnimatedCard>
              );
            })}
          </View>

          {/* Allowances — horizontal scroll */}
          {row2.length > 0 ? (
            <>
              <View style={styles.sectionLabelRow}>
                <Text style={[styles.sectionLabel, { marginBottom: 0, marginTop: 0 }]}>
                  Your Allowances
                </Text>
                <View style={styles.scrollHint}>
                  <Ionicons name="chevron-back" size={16} color={COLORS.textSecondary} />
                  <Text style={styles.scrollHintText}>Scroll</Text>
                  <Ionicons name="chevron-forward" size={16} color={COLORS.textSecondary} />
                </View>
              </View>
              <ScrollView
                horizontal
                showsHorizontalScrollIndicator
                style={styles.allowanceScroll}
                contentContainerStyle={styles.allowanceScrollContent}
              >
                {row2.map((b, i) => {
                  const isRx = b.label.toLowerCase().includes('rx');
                  const cardInner = (
                    <>
                      <View style={styles.allowanceBar} />
                      <View style={styles.allowanceBody}>
                        <BenefitIcon label={b.label} size={22} />
                        <Text style={styles.allowanceValue}>{b.in_network || ''}</Text>
                        <Text style={styles.allowanceLabel} numberOfLines={1}>
                          {b.label}
                        </Text>
                        {b._period ? <Text style={styles.allowancePeriod}>{b._period}</Text> : null}
                        {b._highlight ? (
                          <View style={styles.badgeHighlight}>
                            <Text style={styles.badgeHighlightText}>{b._highlight}</Text>
                          </View>
                        ) : null}
                      </View>
                    </>
                  );
                  return (
                    <AnimatedCard
                      key={'a-' + String(i)}
                      index={row1.length + i}
                      style={styles.allowanceCard}
                    >
                      {isRx && drugsData ? (
                        <TouchableOpacity
                          onPress={() => setShowMedsModal(true)}
                          activeOpacity={0.7}
                        >
                          {cardInner}
                        </TouchableOpacity>
                      ) : (
                        cardInner
                      )}
                    </AnimatedCard>
                  );
                })}
              </ScrollView>
            </>
          ) : null}
        </>
      ) : benefitsError ? (
        <View style={styles.errorWrap}>
          <Ionicons name="cloud-offline-outline" size={32} color={COLORS.textTertiary} />
          <Text style={styles.errorText}>Couldn't load your benefits</Text>
          {onRetryBenefits ? (
            <TouchableOpacity
              style={styles.retryBtn}
              onPress={onRetryBenefits}
              activeOpacity={0.7}
              accessibilityRole="button"
              accessibilityLabel="Retry loading benefits"
            >
              <Ionicons name="refresh-outline" size={16} color={COLORS.white} />
              <Text style={styles.retryText}>Try Again</Text>
            </TouchableOpacity>
          ) : null}
        </View>
      ) : (
        <View style={styles.emptyWrap}>
          <Text style={styles.emptyText}>No benefit details available for this plan.</Text>
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { paddingHorizontal: 18, paddingTop: SPACING.sm, paddingBottom: SPACING.sm },

  // Header
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: SPACING.sm,
  },
  headerLeft: { flex: 1, paddingTop: 4 },
  headerRight: { alignItems: 'flex-end', flexShrink: 0, maxWidth: '48%' },
  greeting: {
    fontSize: 17,
    fontWeight: '600',
    letterSpacing: 0.3,
    color: COLORS.textSecondary,
    marginBottom: 2,
  },
  name: { ...TYPE.h1, color: COLORS.text, letterSpacing: -0.5 },
  medicareNumber: {
    fontSize: 18,
    fontWeight: '700',
    color: COLORS.text,
    marginTop: 6,
    letterSpacing: 0.2,
  },
  agentRow: { flexDirection: 'row', alignItems: 'center', gap: 6, flex: 1 },
  settingsGear: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: COLORS.quickPillBg,
    borderWidth: 1,
    borderColor: COLORS.quickPillBorder,
    justifyContent: 'center',
    alignItems: 'center',
  },
  agent: { fontSize: 16, fontWeight: '700', color: COLORS.textSecondary },
  logoBg: {
    backgroundColor: '#FFFFFF',
    borderRadius: RADII.md,
    padding: 8,
    alignItems: 'center',
    overflow: 'hidden',
    ...SHADOWS.card,
  },
  carrierLogo: { width: 125, height: 36 },
  carrierFallbackText: {
    fontSize: 14,
    fontWeight: '700',
    color: COLORS.accent,
    textAlign: 'center',
  },
  planNumberInLogo: { fontSize: 11, fontWeight: '600', color: COLORS.textSecondary, marginTop: 2 },

  // Quick action pills
  quickActionsRow: {
    flexDirection: 'row',
    gap: 10,
    marginBottom: 14,
  },
  quickPill: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    backgroundColor: COLORS.quickPillBg,
    borderWidth: 1.5,
    borderColor: COLORS.quickPillBorder,
    borderRadius: RADII.md,
    paddingVertical: 12,
    paddingHorizontal: 10,
  },
  quickPillText: { fontSize: 13, fontWeight: '600', color: COLORS.text },
  quickPillBadge: {
    backgroundColor: COLORS.accent,
    borderRadius: 10,
    minWidth: 18,
    height: 18,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 4,
  },
  quickPillBadgeText: { fontSize: 10, fontWeight: '700', color: COLORS.white },

  // Agent row (right above cards)
  aboveCardsRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
  },

  // Loading
  loadingWrap: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
    paddingVertical: 20,
  },
  loadingText: { ...TYPE.bodyMedium, color: COLORS.textSecondary },

  // Error state
  errorWrap: { alignItems: 'center', paddingVertical: 20, gap: 10 },
  errorText: { fontSize: 14, fontWeight: '500', color: COLORS.textSecondary, textAlign: 'center' },
  retryBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: COLORS.accent,
    borderRadius: RADII.full,
    paddingHorizontal: 20,
    paddingVertical: 10,
    marginTop: 4,
    ...SHADOWS.button,
  },
  retryText: { color: COLORS.white, fontSize: 14, fontWeight: '600' },

  // Empty state
  emptyWrap: { alignItems: 'center', paddingVertical: 16 },
  emptyText: { fontSize: 14, fontWeight: '500', color: COLORS.textTertiary, textAlign: 'center' },

  // Section label
  sectionLabel: {
    ...TYPE.sectionHeader,
    color: COLORS.textTertiary,
    marginBottom: 10,
    marginTop: 4,
  },
  sectionLabelRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 10,
    marginTop: 4,
  },
  scrollHint: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: COLORS.accentLight || '#F0E8F8',
    borderRadius: RADII.full,
    paddingHorizontal: 20,
    paddingVertical: 4,
  },
  scrollHintText: {
    fontSize: 12,
    fontWeight: '600',
    color: COLORS.accent,
  },

  // Copay grid — 2x2
  copayGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    marginBottom: 12,
  },
  copayCard: {
    width: '48%',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: COLORS.white,
    borderRadius: 14,
    padding: 10,
    ...SHADOWS.card,
    borderWidth: 1,
    borderColor: COLORS.borderLight,
  },
  copayInfo: { flex: 1 },
  copayLabel: { fontSize: 12, fontWeight: '500', color: COLORS.textSecondary, marginBottom: 1 },
  copayValue: { fontSize: 22, fontWeight: '700', color: COLORS.text },

  // Badges
  badgeFree: {
    backgroundColor: COLORS.badgeFree,
    borderRadius: 6,
    paddingHorizontal: 8,
    paddingVertical: 2,
    alignSelf: 'flex-start',
    marginTop: 3,
  },
  badgeFreeText: { fontSize: 10, fontWeight: '600', color: COLORS.white },
  badgeHighlight: {
    backgroundColor: COLORS.badgeHighlightBg,
    borderRadius: 5,
    paddingHorizontal: 7,
    paddingVertical: 2,
    alignSelf: 'flex-start',
    marginTop: 3,
  },
  badgeHighlightText: { fontSize: 9, fontWeight: '600', color: COLORS.badgeHighlight },

  // Allowance cards — horizontal scroll
  allowanceScroll: {
    marginBottom: 10,
  },
  allowanceScrollContent: {
    flexDirection: 'row',
    gap: 12,
    paddingRight: 4,
  },
  allowanceCard: {
    width: 115,
    backgroundColor: COLORS.white,
    borderRadius: 13,
    overflow: 'hidden',
    ...SHADOWS.card,
    borderWidth: 1,
    borderColor: COLORS.borderLight,
  },
  allowanceBar: { height: 2, backgroundColor: COLORS.allowanceBar },
  allowanceBody: { padding: 9, alignItems: 'flex-start', gap: 2 },
  allowanceValue: { fontSize: 18, fontWeight: '700', color: COLORS.text, marginTop: 3 },
  allowanceLabel: { fontSize: 11, fontWeight: '500', color: COLORS.textSecondary },
  allowancePeriod: {
    fontSize: 10,
    fontWeight: '400',
    color: COLORS.textTertiary,
    fontStyle: 'italic',
    marginTop: 1,
  },

  // Icon circle
  iconCircle: {
    width: 36,
    height: 36,
    borderRadius: 12,
    justifyContent: 'center',
    alignItems: 'center',
  },

  // Expanded reminder body
  remBody: {
    backgroundColor: COLORS.white,
    borderRadius: RADII.md,
    marginBottom: 14,
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderWidth: 1,
    borderColor: COLORS.borderLight,
  },
  remEmpty: {
    fontSize: 13,
    color: COLORS.textTertiary,
    textAlign: 'center',
    paddingVertical: 10,
    lineHeight: 18,
  },

  // Reminder rows
  remRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.borderLight,
  },
  remIcon: {
    width: 28,
    height: 28,
    borderRadius: 8,
    backgroundColor: COLORS.rxDrugBg || '#FDECEA',
    justifyContent: 'center',
    alignItems: 'center',
  },
  remInfo: { flex: 1 },
  remDrug: { fontSize: 14, fontWeight: '600', color: COLORS.text },
  remDose: { fontSize: 12, fontWeight: '400', color: COLORS.textSecondary },
  remTime: { fontSize: 12, fontWeight: '500', color: COLORS.textSecondary, marginTop: 1 },

  // Add reminder button
  remAddBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    paddingVertical: 8,
    marginTop: 4,
  },
  remAddText: { fontSize: 13, fontWeight: '600', color: COLORS.accent },

  // Tappable benefit card inner wrapper
  benefitCardTap: { alignItems: 'center', gap: 6, width: '100%' },

  // Medications modal rows
  medRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.borderLight,
  },
  medIconWrap: {
    width: 32,
    height: 32,
    borderRadius: 10,
    backgroundColor: COLORS.rxDrugBg || '#FDECEA',
    justifyContent: 'center',
    alignItems: 'center',
  },
  medInfo: { flex: 1 },
  medName: { fontSize: 15, fontWeight: '600', color: COLORS.text },
  medDetail: { fontSize: 12, fontWeight: '500', color: COLORS.textSecondary, marginTop: 2 },
  medCost: { fontSize: 16, fontWeight: '700', color: COLORS.text },
  medTotalRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingTop: 14,
    marginTop: 4,
    borderTopWidth: 2,
    borderTopColor: COLORS.accent,
  },
  medTotalLabel: { fontSize: 14, fontWeight: '600', color: COLORS.textSecondary },
  medTotalValue: { fontSize: 18, fontWeight: '700', color: COLORS.accent },

  // ── Add Reminder Modal ─────────────────────────────────────────
  modalOverlay: { flex: 1, backgroundColor: COLORS.overlay, justifyContent: 'flex-end' },
  modalContent: {
    backgroundColor: COLORS.white,
    borderTopLeftRadius: RADII.xl,
    borderTopRightRadius: RADII.xl,
    padding: 24,
    paddingBottom: 40,
    ...SHADOWS.modal,
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 20,
  },
  modalTitle: { ...TYPE.h3, color: COLORS.text },
  fieldLabel: { ...TYPE.label, color: COLORS.textSecondary, marginBottom: 6, marginTop: 14 },
  modalInput: {
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
  timeRow: { flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 4 },
  timeSpinner: { alignItems: 'center' },
  spinBtn: { padding: 6 },
  timeValue: {
    fontSize: 28,
    fontWeight: '700',
    color: COLORS.text,
    minWidth: 48,
    textAlign: 'center',
  },
  timeColon: { fontSize: 28, fontWeight: '700', color: COLORS.textTertiary, marginBottom: 4 },
  ampmToggle: { flexDirection: 'column', gap: 4, marginLeft: 10 },
  ampmBtn: {
    paddingHorizontal: 14,
    paddingVertical: 6,
    borderRadius: RADII.sm,
    backgroundColor: COLORS.bg,
    borderWidth: 1,
    borderColor: COLORS.borderLight,
  },
  ampmActive: { backgroundColor: COLORS.accentLight, borderColor: COLORS.accentSoft },
  ampmText: { fontSize: 14, fontWeight: '600', color: COLORS.textTertiary, textAlign: 'center' },
  ampmTextActive: { color: COLORS.accent },
  saveBtn: {
    backgroundColor: COLORS.accent,
    borderRadius: RADII.md,
    paddingVertical: 16,
    alignItems: 'center',
    marginTop: 24,
    ...SHADOWS.button,
  },
  saveBtnDisabled: { opacity: 0.4 },
  saveBtnText: { fontSize: 16, fontWeight: '600', color: COLORS.white },
});
