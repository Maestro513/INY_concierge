import { useState, useRef, useEffect } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, Switch, TextInput,
  Modal, Animated, ActivityIndicator, Platform, ScrollView,
} from 'react-native';
import { Ionicons, MaterialCommunityIcons } from '@expo/vector-icons';
import { COLORS, RADII, SPACING, SHADOWS, TYPE, MOTION } from '../constants/theme';

// ── Time formatting helper ──────────────────────────────────────
function formatTime(hour, minute) {
  const ampm = hour >= 12 ? 'PM' : 'AM';
  const h = hour === 0 ? 12 : hour > 12 ? hour - 12 : hour;
  const m = String(minute).padStart(2, '0');
  return `${h}:${m} ${ampm}`;
}

// ── Reminder row ────────────────────────────────────────────────
function ReminderRow({ reminder, onToggle, onDelete }) {
  return (
    <View style={styles.reminderRow}>
      <View style={styles.reminderIcon}>
        <MaterialCommunityIcons name="pill" size={18} color={COLORS.rxDrug} />
      </View>
      <View style={styles.reminderInfo}>
        <Text style={styles.reminderDrug} numberOfLines={1}>
          {reminder.drug_name}
          {reminder.dose_label ? <Text style={styles.reminderDose}> {reminder.dose_label}</Text> : null}
        </Text>
        <Text style={styles.reminderTime}>{formatTime(reminder.time_hour, reminder.time_minute)}</Text>
      </View>
      <Switch
        value={!!reminder.enabled}
        onValueChange={(val) => onToggle(reminder.id, val)}
        trackColor={{ false: COLORS.border, true: COLORS.accentSoft }}
        thumbColor={reminder.enabled ? COLORS.accent : COLORS.textTertiary}
        style={{ transform: [{ scale: 0.85 }] }}
      />
      <TouchableOpacity
        onPress={() => onDelete(reminder.id)}
        hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
        accessibilityLabel={`Delete ${reminder.drug_name} reminder`}
      >
        <Ionicons name="trash-outline" size={18} color={COLORS.textTertiary} />
      </TouchableOpacity>
    </View>
  );
}

// ── Add reminder modal ──────────────────────────────────────────
function AddReminderModal({ visible, onClose, onSave, existingMeds }) {
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
    const h24 = ampm === 'PM' ? (hour === 12 ? 12 : hour + 12) : (hour === 12 ? 0 : hour);
    await onSave({
      drug_name: drugName.trim(),
      dose_label: doseLabel.trim(),
      time_hour: h24,
      time_minute: minute,
    });
    reset();
    onClose();
  };

  const adjustHour = (delta) => setHour((prev) => {
    const next = prev + delta;
    if (next > 12) return 1;
    if (next < 1) return 12;
    return next;
  });

  const adjustMinute = (delta) => setMinute((prev) => {
    const next = prev + delta;
    if (next >= 60) return 0;
    if (next < 0) return 45;
    return next;
  });

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

          {/* Medication name */}
          <Text style={styles.fieldLabel}>Medication</Text>
          <TextInput
            style={styles.textInput}
            value={drugName}
            onChangeText={setDrugName}
            placeholder="e.g. Metformin"
            placeholderTextColor={COLORS.textTertiary}
            autoFocus
          />

          {/* Dose (optional) */}
          <Text style={styles.fieldLabel}>Dose (optional)</Text>
          <TextInput
            style={styles.textInput}
            value={doseLabel}
            onChangeText={setDoseLabel}
            placeholder="e.g. 500mg"
            placeholderTextColor={COLORS.textTertiary}
          />

          {/* Time picker */}
          <Text style={styles.fieldLabel}>Reminder Time</Text>
          <View style={styles.timeRow}>
            <View style={styles.timeSpinner}>
              <TouchableOpacity onPress={() => adjustHour(1)} style={styles.spinBtn}>
                <Ionicons name="chevron-up" size={20} color={COLORS.accent} />
              </TouchableOpacity>
              <Text style={styles.timeValue}>{String(hour).padStart(2, '0')}</Text>
              <TouchableOpacity onPress={() => adjustHour(-1)} style={styles.spinBtn}>
                <Ionicons name="chevron-down" size={20} color={COLORS.accent} />
              </TouchableOpacity>
            </View>
            <Text style={styles.timeColon}>:</Text>
            <View style={styles.timeSpinner}>
              <TouchableOpacity onPress={() => adjustMinute(15)} style={styles.spinBtn}>
                <Ionicons name="chevron-up" size={20} color={COLORS.accent} />
              </TouchableOpacity>
              <Text style={styles.timeValue}>{String(minute).padStart(2, '0')}</Text>
              <TouchableOpacity onPress={() => adjustMinute(-15)} style={styles.spinBtn}>
                <Ionicons name="chevron-down" size={20} color={COLORS.accent} />
              </TouchableOpacity>
            </View>
            <View style={styles.ampmToggle}>
              <TouchableOpacity
                style={[styles.ampmBtn, ampm === 'AM' && styles.ampmActive]}
                onPress={() => setAmpm('AM')}
              >
                <Text style={[styles.ampmText, ampm === 'AM' && styles.ampmTextActive]}>AM</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.ampmBtn, ampm === 'PM' && styles.ampmActive]}
                onPress={() => setAmpm('PM')}
              >
                <Text style={[styles.ampmText, ampm === 'PM' && styles.ampmTextActive]}>PM</Text>
              </TouchableOpacity>
            </View>
          </View>

          {/* Save button */}
          <TouchableOpacity
            style={[styles.saveBtn, (!drugName.trim() || saving) && styles.saveBtnDisabled]}
            onPress={handleSave}
            disabled={!drugName.trim() || saving}
            activeOpacity={0.8}
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
export default function MedReminders({ reminders, loading, onToggle, onDelete, onAdd }) {
  const [expanded, setExpanded] = useState(true);
  const [showAdd, setShowAdd] = useState(false);

  // Entrance animation
  const fadeIn = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    Animated.timing(fadeIn, { toValue: 1, duration: MOTION.normal, useNativeDriver: true }).start();
  }, []);

  if (loading) {
    return (
      <View style={styles.container}>
        <ActivityIndicator size="small" color={COLORS.accent} />
      </View>
    );
  }

  return (
    <Animated.View style={[styles.container, { opacity: fadeIn }]}>
      {/* Header */}
      <TouchableOpacity
        style={styles.sectionHeader}
        onPress={() => setExpanded(!expanded)}
        activeOpacity={0.7}
      >
        <View style={styles.sectionLeft}>
          <View style={styles.sectionIcon}>
            <MaterialCommunityIcons name="pill" size={16} color={COLORS.accent} />
          </View>
          <Text style={styles.sectionTitle}>Medication Reminders</Text>
          {reminders.length > 0 ? (
            <View style={styles.badge}>
              <Text style={styles.badgeText}>{reminders.length}</Text>
            </View>
          ) : null}
        </View>
        <Ionicons
          name={expanded ? 'chevron-up' : 'chevron-down'}
          size={18}
          color={COLORS.textSecondary}
        />
      </TouchableOpacity>

      {expanded ? (
        <View style={styles.body}>
          {reminders.length === 0 ? (
            <Text style={styles.emptyText}>
              No reminders yet. Tap + or say "Remind me to take my medication at 8am"
            </Text>
          ) : (
            reminders.map((r) => (
              <ReminderRow
                key={String(r.id)}
                reminder={r}
                onToggle={onToggle}
                onDelete={onDelete}
              />
            ))
          )}

          {/* Add button */}
          <TouchableOpacity
            style={styles.addBtn}
            onPress={() => setShowAdd(true)}
            activeOpacity={0.7}
          >
            <Ionicons name="add-circle-outline" size={18} color={COLORS.accent} />
            <Text style={styles.addBtnText}>Add Reminder</Text>
          </TouchableOpacity>
        </View>
      ) : null}

      <AddReminderModal
        visible={showAdd}
        onClose={() => setShowAdd(false)}
        onSave={onAdd}
      />
    </Animated.View>
  );
}

// ── Styles ──────────────────────────────────────────────────────
const styles = StyleSheet.create({
  container: {
    marginHorizontal: 20,
    marginBottom: 12,
    backgroundColor: COLORS.white,
    borderRadius: RADII.lg,
    ...SHADOWS.card,
    borderWidth: 1,
    borderColor: COLORS.borderLight,
    overflow: 'hidden',
  },

  // Section header
  sectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 14,
  },
  sectionLeft: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  sectionIcon: {
    width: 28, height: 28, borderRadius: 8,
    backgroundColor: COLORS.accentLight,
    justifyContent: 'center', alignItems: 'center',
  },
  sectionTitle: { ...TYPE.label, fontSize: 14, color: COLORS.text },
  badge: {
    backgroundColor: COLORS.accent,
    borderRadius: 10,
    minWidth: 20, height: 20,
    justifyContent: 'center', alignItems: 'center',
    paddingHorizontal: 6,
  },
  badgeText: { fontSize: 11, fontWeight: '700', color: COLORS.white },

  // Body
  body: { paddingHorizontal: 16, paddingBottom: 14 },

  // Reminder row
  reminderRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.borderLight,
  },
  reminderIcon: {
    width: 32, height: 32, borderRadius: 10,
    backgroundColor: COLORS.rxDrugBg,
    justifyContent: 'center', alignItems: 'center',
  },
  reminderInfo: { flex: 1 },
  reminderDrug: { fontSize: 15, fontWeight: '600', color: COLORS.text },
  reminderDose: { fontSize: 13, fontWeight: '400', color: COLORS.textSecondary },
  reminderTime: { fontSize: 13, fontWeight: '500', color: COLORS.textSecondary, marginTop: 2 },

  // Empty state
  emptyText: { ...TYPE.caption, color: COLORS.textTertiary, textAlign: 'center', paddingVertical: 12, lineHeight: 18 },

  // Add button
  addBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    gap: 6, paddingVertical: 10, marginTop: 6,
  },
  addBtnText: { fontSize: 14, fontWeight: '600', color: COLORS.accent },

  // ── Modal ─────────────────────────────────────────────────────
  modalOverlay: {
    flex: 1,
    backgroundColor: COLORS.overlay,
    justifyContent: 'flex-end',
  },
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

  // Fields
  fieldLabel: { ...TYPE.label, color: COLORS.textSecondary, marginBottom: 6, marginTop: 14 },
  textInput: {
    backgroundColor: COLORS.bg,
    borderRadius: RADII.md,
    borderWidth: 1, borderColor: COLORS.borderLight,
    paddingHorizontal: 14, paddingVertical: 14,
    fontSize: 16, fontWeight: '500', color: COLORS.text,
  },

  // Time picker
  timeRow: { flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 4 },
  timeSpinner: { alignItems: 'center' },
  spinBtn: { padding: 6 },
  timeValue: {
    fontSize: 28, fontWeight: '700', color: COLORS.text,
    minWidth: 48, textAlign: 'center',
  },
  timeColon: { fontSize: 28, fontWeight: '700', color: COLORS.textTertiary, marginBottom: 4 },
  ampmToggle: {
    flexDirection: 'column', gap: 4, marginLeft: 10,
  },
  ampmBtn: {
    paddingHorizontal: 14, paddingVertical: 6,
    borderRadius: RADII.sm,
    backgroundColor: COLORS.bg,
    borderWidth: 1, borderColor: COLORS.borderLight,
  },
  ampmActive: {
    backgroundColor: COLORS.accentLight,
    borderColor: COLORS.accentSoft,
  },
  ampmText: { fontSize: 14, fontWeight: '600', color: COLORS.textTertiary, textAlign: 'center' },
  ampmTextActive: { color: COLORS.accent },

  // Save button
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
