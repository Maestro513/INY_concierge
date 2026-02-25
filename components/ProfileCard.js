import { useState, useRef, useEffect } from 'react';
import {
  View, Text, TouchableOpacity, Image, StyleSheet, ActivityIndicator,
  Animated, Switch, TextInput, Modal,
} from 'react-native';
import { Ionicons, MaterialCommunityIcons } from '@expo/vector-icons';
import { COLORS, RADII, SPACING, SHADOWS, TYPE, MOTION, BENEFIT_ICON_MAP, DEFAULT_ICON } from '../constants/theme';

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
  if (name.includes('uhc') || name.includes('unitedhealthcare') || name.includes('aarp')) return 'uhc';
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
      />
      <TouchableOpacity
        onPress={() => onDelete(reminder.id)}
        hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
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

  const reset = () => { setDrugName(''); setDoseLabel(''); setHour(8); setMinute(0); setAmpm('AM'); setSaving(false); };

  const handleSave = async () => {
    if (!drugName.trim()) return;
    setSaving(true);
    const h24 = ampm === 'PM' ? (hour === 12 ? 12 : hour + 12) : (hour === 12 ? 0 : hour);
    await onSave({ drug_name: drugName.trim(), dose_label: doseLabel.trim(), time_hour: h24, time_minute: minute });
    reset();
    onClose();
  };

  const adjustHour = (d) => setHour((p) => { const n = p + d; return n > 12 ? 1 : n < 1 ? 12 : n; });
  const adjustMinute = (d) => setMinute((p) => { const n = p + d; return n >= 60 ? 0 : n < 0 ? 45 : n; });

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={styles.modalOverlay}>
        <View style={styles.modalContent}>
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>Add Reminder</Text>
            <TouchableOpacity onPress={() => { reset(); onClose(); }}>
              <Ionicons name="close" size={24} color={COLORS.textSecondary} />
            </TouchableOpacity>
          </View>
          <Text style={styles.fieldLabel}>Medication</Text>
          <TextInput style={styles.modalInput} value={drugName} onChangeText={setDrugName} placeholder="e.g. Metformin" placeholderTextColor={COLORS.textTertiary} autoFocus />
          <Text style={styles.fieldLabel}>Dose (optional)</Text>
          <TextInput style={styles.modalInput} value={doseLabel} onChangeText={setDoseLabel} placeholder="e.g. 500mg" placeholderTextColor={COLORS.textTertiary} />
          <Text style={styles.fieldLabel}>Reminder Time</Text>
          <View style={styles.timeRow}>
            <View style={styles.timeSpinner}>
              <TouchableOpacity onPress={() => adjustHour(1)} style={styles.spinBtn}><Ionicons name="chevron-up" size={20} color={COLORS.accent} /></TouchableOpacity>
              <Text style={styles.timeValue}>{String(hour).padStart(2, '0')}</Text>
              <TouchableOpacity onPress={() => adjustHour(-1)} style={styles.spinBtn}><Ionicons name="chevron-down" size={20} color={COLORS.accent} /></TouchableOpacity>
            </View>
            <Text style={styles.timeColon}>:</Text>
            <View style={styles.timeSpinner}>
              <TouchableOpacity onPress={() => adjustMinute(15)} style={styles.spinBtn}><Ionicons name="chevron-up" size={20} color={COLORS.accent} /></TouchableOpacity>
              <Text style={styles.timeValue}>{String(minute).padStart(2, '0')}</Text>
              <TouchableOpacity onPress={() => adjustMinute(-15)} style={styles.spinBtn}><Ionicons name="chevron-down" size={20} color={COLORS.accent} /></TouchableOpacity>
            </View>
            <View style={styles.ampmToggle}>
              <TouchableOpacity style={[styles.ampmBtn, ampm === 'AM' && styles.ampmActive]} onPress={() => setAmpm('AM')}>
                <Text style={[styles.ampmText, ampm === 'AM' && styles.ampmTextActive]}>AM</Text>
              </TouchableOpacity>
              <TouchableOpacity style={[styles.ampmBtn, ampm === 'PM' && styles.ampmActive]} onPress={() => setAmpm('PM')}>
                <Text style={[styles.ampmText, ampm === 'PM' && styles.ampmTextActive]}>PM</Text>
              </TouchableOpacity>
            </View>
          </View>
          <TouchableOpacity style={[styles.saveBtn, (!drugName.trim() || saving) && styles.saveBtnDisabled]} onPress={handleSave} disabled={!drugName.trim() || saving} activeOpacity={0.8}>
            {saving ? <ActivityIndicator color={COLORS.white} size="small" /> : <Text style={styles.saveBtnText}>Save Reminder</Text>}
          </TouchableOpacity>
        </View>
      </View>
    </Modal>
  );
}

// ── Main component ──────────────────────────────────────────────
export default function ProfileCard({ member, onViewSOB, benefits, loading, benefitsError, onRetryBenefits, reminders = [], onToggleReminder, onDeleteReminder, onAddReminder }) {
  const [remindersExpanded, setRemindersExpanded] = useState(false);
  const [showAddModal, setShowAddModal] = useState(false);

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

  const dateString = now.toLocaleDateString('en-US', {
    weekday: 'long', month: 'long', day: 'numeric',
  });

  const carrier = detectCarrier(member.planName);
  const carrierLogo = carrier ? CARRIER_LOGOS[carrier] : null;

  const row1 = (benefits || []).filter(b => b._row === 1);
  const row2 = (benefits || []).filter(b => b._row === 2);

  return (
    <View style={styles.container}>
      {/* Header: Greeting + Name + Agent | Carrier Logo + Plan Name */}
      <Animated.View style={[styles.header, { opacity: greetFade, transform: [{ translateY: greetSlide }] }]}>
        <View style={styles.headerLeft}>
          <Text style={styles.dateText}>{dateString}</Text>
          <Text style={styles.greeting}>{greeting()}</Text>
          <Text style={styles.name}>
            {member.firstName} {member.lastName}
          </Text>
        </View>
        <View style={styles.headerRight}>
          {carrierLogo ? (
            <View style={styles.logoBg} accessibilityLabel={`${carrier} insurance logo`}>
              <Image source={carrierLogo} style={styles.carrierLogo} resizeMode="contain" accessibilityRole="image" />
            </View>
          ) : null}
          <Text style={styles.planName} numberOfLines={2}>{member.planName}</Text>
        </View>
      </Animated.View>

      {/* Reminder Bar — tap to expand */}
      <TouchableOpacity
        style={styles.reminderBar}
        onPress={() => setRemindersExpanded(!remindersExpanded)}
        activeOpacity={0.7}
      >
        <Ionicons name="notifications-outline" size={16} color={COLORS.accent} />
        <Text style={styles.reminderText}>
          {reminders.length > 0 ? `${reminders.length} Reminder${reminders.length > 1 ? 's' : ''}` : 'Reminders'}
        </Text>
        {reminders.length > 0 ? (
          <View style={styles.remBadge}>
            <Text style={styles.remBadgeText}>{reminders.length}</Text>
          </View>
        ) : null}
        <Ionicons name={remindersExpanded ? 'chevron-up' : 'chevron-down'} size={16} color={COLORS.accentDark} />
      </TouchableOpacity>

      {/* Expanded reminder list */}
      {remindersExpanded ? (
        <View style={styles.remBody}>
          {reminders.length === 0 ? (
            <Text style={styles.remEmpty}>No reminders yet. Tap + or say "Remind me to take my medication at 8am"</Text>
          ) : (
            reminders.map((r) => (
              <ReminderRow key={String(r.id)} reminder={r} onToggle={onToggleReminder} onDelete={onDeleteReminder} />
            ))
          )}
          <TouchableOpacity style={styles.remAddBtn} onPress={() => setShowAddModal(true)} activeOpacity={0.7}>
            <Ionicons name="add-circle-outline" size={16} color={COLORS.accent} />
            <Text style={styles.remAddText}>Add Reminder</Text>
          </TouchableOpacity>
        </View>
      ) : null}

      <AddReminderModal visible={showAddModal} onClose={() => setShowAddModal(false)} onSave={onAddReminder} />

      {/* Agent + View More Benefits row — right above cards */}
      <View style={styles.aboveCardsRow}>
        {member.agent ? (
          <View style={styles.agentRow}>
            <Ionicons name="person-outline" size={14} color={COLORS.textSecondary} />
            <Text style={styles.agent}>Agent: {member.agent}</Text>
          </View>
        ) : <View />}
        <TouchableOpacity onPress={onViewSOB} style={styles.sobBtn} activeOpacity={0.7} accessibilityRole="button" accessibilityLabel="View summary of benefits">
          <Ionicons name="document-text-outline" size={16} color={COLORS.accent} />
          <Text style={styles.sobLink}>View More Benefits</Text>
          <Ionicons name="chevron-forward" size={14} color={COLORS.accent} />
        </TouchableOpacity>
      </View>

      {/* Benefits Grid */}
      {loading ? (
        <View style={styles.loadingWrap}>
          <ActivityIndicator size="small" color={COLORS.accent} />
          <Text style={styles.loadingText}>Loading benefits...</Text>
        </View>
      ) : row1.length > 0 ? (
        <View style={styles.benefitsWrap}>
          <View style={styles.benefitsRow}>
            {row1.map((b, i) => (
              <AnimatedCard key={'r1-' + String(i)} index={i} style={styles.benefitCard}>
                <BenefitIcon label={b.label} size={20} />
                <Text style={styles.benefitValue}>{b.in_network || ''}</Text>
                <Text style={styles.benefitLabel} numberOfLines={1}>{b.label}</Text>
              </AnimatedCard>
            ))}
          </View>
          {/* Row 2: Rx cost + supplementals (2-4 cards) */}
          {row2.length > 0 ? (
            <View style={styles.benefitsRow}>
              {row2.map((b, i) => (
                <AnimatedCard
                  key={'r2-' + String(i)}
                  index={row1.length + i}
                  style={row2.length <= 2 ? styles.benefitCardWide : styles.benefitCard}
                >
                  <BenefitIcon label={b.label} size={20} />
                  <Text style={styles.benefitValue}>{b.in_network || ''}</Text>
                  <Text style={styles.benefitLabel} numberOfLines={1}>{b.label}</Text>
                </AnimatedCard>
              ))}
            </View>
          ) : null}
        </View>
      ) : benefitsError ? (
        <View style={styles.errorWrap}>
          <Ionicons name="cloud-offline-outline" size={32} color={COLORS.textTertiary} />
          <Text style={styles.errorText}>Couldn't load your benefits</Text>
          {onRetryBenefits ? (
            <TouchableOpacity style={styles.retryBtn} onPress={onRetryBenefits} activeOpacity={0.7}>
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
  container: { paddingHorizontal: 20, paddingTop: SPACING.md, paddingBottom: SPACING.md },

  // Header
  header: {
    flexDirection: 'row', justifyContent: 'space-between',
    alignItems: 'flex-start', marginBottom: SPACING.sm,
  },
  headerLeft: { flex: 1, paddingTop: 4 },
  dateText: { fontSize: 13, fontWeight: '500', color: COLORS.textTertiary, marginBottom: 6 },
  headerRight: { alignItems: 'flex-end', flexShrink: 0, maxWidth: '48%' },
  greeting: { fontSize: 17, fontWeight: '600', letterSpacing: 0.2, color: COLORS.textSecondary, marginBottom: 2 },
  name: { ...TYPE.h1, color: COLORS.text },
  agentRow: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  agent: { fontSize: 16, fontWeight: '700', color: COLORS.textSecondary },
  logoBg: {
    backgroundColor: '#FFFFFF', borderRadius: RADII.sm,
    padding: 6, overflow: 'hidden',
    ...SHADOWS.soft,
  },
  carrierLogo: { width: 96, height: 48 },
  planName: { fontSize: 13, fontWeight: '600', color: COLORS.textSecondary, textAlign: 'right', marginTop: 6, lineHeight: 18 },

  // Reminder bar
  reminderBar: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    backgroundColor: COLORS.accentLight,
    borderRadius: RADII.md,
    paddingHorizontal: 14, paddingVertical: 10,
    marginBottom: 14,
    borderWidth: 1, borderColor: COLORS.accentSoft,
  },
  reminderText: { fontSize: 14, fontWeight: '600', color: COLORS.accentDark, flex: 1 },

  // Agent + View More Benefits row (right above cards)
  aboveCardsRow: {
    flexDirection: 'row', justifyContent: 'space-between',
    alignItems: 'center', marginBottom: 12,
  },
  sobBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    backgroundColor: COLORS.accentLight,
    borderRadius: RADII.full,
    paddingHorizontal: 16, paddingVertical: 10,
  },
  sobLink: { fontSize: 14, fontWeight: '700', color: COLORS.accent },

  // Loading
  loadingWrap: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    gap: 10, paddingVertical: 20,
  },
  loadingText: { ...TYPE.bodyMedium, color: COLORS.textSecondary },

  // Error state
  errorWrap: { alignItems: 'center', paddingVertical: 20, gap: 10 },
  errorText: { fontSize: 14, fontWeight: '500', color: COLORS.textSecondary, textAlign: 'center' },
  retryBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    backgroundColor: COLORS.accent, borderRadius: RADII.full,
    paddingHorizontal: 20, paddingVertical: 10, marginTop: 4,
    ...SHADOWS.button,
  },
  retryText: { color: COLORS.white, fontSize: 14, fontWeight: '600' },

  // Empty state
  emptyWrap: { alignItems: 'center', paddingVertical: 16 },
  emptyText: { fontSize: 14, fontWeight: '500', color: COLORS.textTertiary, textAlign: 'center' },

  // Section label
  sectionLabelRow: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    marginBottom: 10,
  },
  sectionDot: {
    width: 6, height: 6, borderRadius: 3,
    backgroundColor: COLORS.accent,
  },
  sectionLabel: { ...TYPE.labelSmall, color: COLORS.textSecondary, textTransform: 'uppercase', letterSpacing: 0.6 },

  // Benefits grid
  benefitsWrap: { gap: 10 },
  benefitsRow: { flexDirection: 'row', gap: 10 },

  benefitCard: {
    flex: 1, backgroundColor: COLORS.white, borderRadius: RADII.md,
    paddingVertical: 14, paddingHorizontal: 6, alignItems: 'center',
    gap: 6, ...SHADOWS.card,
    borderWidth: 1, borderColor: COLORS.borderLight,
  },
  benefitCardWide: {
    flex: 1, backgroundColor: COLORS.white, borderRadius: RADII.md,
    paddingVertical: 14, paddingHorizontal: 8, alignItems: 'center',
    gap: 6, ...SHADOWS.card,
    borderWidth: 1, borderColor: COLORS.borderLight,
  },

  // Icon circle
  iconCircle: {
    width: 36, height: 36, borderRadius: 12,
    justifyContent: 'center', alignItems: 'center',
  },

  benefitValue: {
    ...TYPE.cardValue, color: COLORS.text, textAlign: 'center',
  },
  benefitLabel: {
    ...TYPE.cardLabel, color: COLORS.textSecondary, textAlign: 'center', width: '100%',
  },

  // Reminder badge on bar
  remBadge: {
    backgroundColor: COLORS.accent, borderRadius: 10,
    minWidth: 20, height: 20, justifyContent: 'center', alignItems: 'center', paddingHorizontal: 5,
  },
  remBadgeText: { fontSize: 11, fontWeight: '700', color: COLORS.white },

  // Expanded reminder body
  remBody: {
    backgroundColor: COLORS.white, borderRadius: RADII.md,
    marginBottom: 14, paddingHorizontal: 14, paddingVertical: 10,
    borderWidth: 1, borderColor: COLORS.borderLight,
  },
  remEmpty: { fontSize: 13, color: COLORS.textTertiary, textAlign: 'center', paddingVertical: 10, lineHeight: 18 },

  // Reminder rows
  remRow: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    paddingVertical: 8, borderBottomWidth: 1, borderBottomColor: COLORS.borderLight,
  },
  remIcon: {
    width: 28, height: 28, borderRadius: 8,
    backgroundColor: COLORS.rxDrugBg || '#FDECEA',
    justifyContent: 'center', alignItems: 'center',
  },
  remInfo: { flex: 1 },
  remDrug: { fontSize: 14, fontWeight: '600', color: COLORS.text },
  remDose: { fontSize: 12, fontWeight: '400', color: COLORS.textSecondary },
  remTime: { fontSize: 12, fontWeight: '500', color: COLORS.textSecondary, marginTop: 1 },

  // Add reminder button
  remAddBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    gap: 6, paddingVertical: 8, marginTop: 4,
  },
  remAddText: { fontSize: 13, fontWeight: '600', color: COLORS.accent },

  // ── Add Reminder Modal ─────────────────────────────────────────
  modalOverlay: { flex: 1, backgroundColor: COLORS.overlay, justifyContent: 'flex-end' },
  modalContent: {
    backgroundColor: COLORS.white, borderTopLeftRadius: RADII.xl, borderTopRightRadius: RADII.xl,
    padding: 24, paddingBottom: 40, ...SHADOWS.modal,
  },
  modalHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 },
  modalTitle: { ...TYPE.h3, color: COLORS.text },
  fieldLabel: { ...TYPE.label, color: COLORS.textSecondary, marginBottom: 6, marginTop: 14 },
  modalInput: {
    backgroundColor: COLORS.bg, borderRadius: RADII.md,
    borderWidth: 1, borderColor: COLORS.borderLight,
    paddingHorizontal: 14, paddingVertical: 14,
    fontSize: 16, fontWeight: '500', color: COLORS.text,
  },
  timeRow: { flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 4 },
  timeSpinner: { alignItems: 'center' },
  spinBtn: { padding: 6 },
  timeValue: { fontSize: 28, fontWeight: '700', color: COLORS.text, minWidth: 48, textAlign: 'center' },
  timeColon: { fontSize: 28, fontWeight: '700', color: COLORS.textTertiary, marginBottom: 4 },
  ampmToggle: { flexDirection: 'column', gap: 4, marginLeft: 10 },
  ampmBtn: {
    paddingHorizontal: 14, paddingVertical: 6, borderRadius: RADII.sm,
    backgroundColor: COLORS.bg, borderWidth: 1, borderColor: COLORS.borderLight,
  },
  ampmActive: { backgroundColor: COLORS.accentLight, borderColor: COLORS.accentSoft },
  ampmText: { fontSize: 14, fontWeight: '600', color: COLORS.textTertiary, textAlign: 'center' },
  ampmTextActive: { color: COLORS.accent },
  saveBtn: {
    backgroundColor: COLORS.accent, borderRadius: RADII.md,
    paddingVertical: 16, alignItems: 'center', marginTop: 24, ...SHADOWS.button,
  },
  saveBtnDisabled: { opacity: 0.4 },
  saveBtnText: { fontSize: 16, fontWeight: '600', color: COLORS.white },
});
