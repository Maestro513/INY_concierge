import { useState, useRef, useEffect } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, TextInput,
  Modal, Animated, ActivityIndicator,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, RADII, SPACING, SHADOWS, TYPE, MOTION } from '../constants/theme';

// ── Category config ─────────────────────────────────────────────
const CATEGORY_CONFIG = {
  otc:     { label: 'OTC Allowance', icon: 'cart-outline',  color: COLORS.clinical,  bg: COLORS.clinicalBg },
  dental:  { label: 'Dental',        icon: 'medical-outline', color: COLORS.clinical, bg: COLORS.clinicalBg },
  flex:    { label: 'Flex Card',     icon: 'card-outline',   color: COLORS.clinical,  bg: COLORS.clinicalBg },
  vision:  { label: 'Vision',        icon: 'eye-outline',    color: COLORS.clinical,  bg: COLORS.clinicalBg },
  hearing: { label: 'Hearing',       icon: 'ear-outline',    color: COLORS.clinical,  bg: COLORS.clinicalBg },
};

const PERIOD_LABELS = {
  Monthly: 'monthly',
  Quarterly: 'quarterly',
  Yearly: 'yearly',
};

// ── Progress bar ────────────────────────────────────────────────
function ProgressBar({ pct, color }) {
  const widthAnim = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    Animated.timing(widthAnim, {
      toValue: Math.min(pct, 100),
      duration: MOTION.slow,
      useNativeDriver: false,
    }).start();
  }, [pct]);

  const barColor = pct >= 90 ? COLORS.error : pct >= 70 ? COLORS.warning : color;

  return (
    <View style={styles.progressTrack}>
      <Animated.View
        style={[
          styles.progressFill,
          {
            backgroundColor: barColor,
            width: widthAnim.interpolate({
              inputRange: [0, 100],
              outputRange: ['0%', '100%'],
            }),
          },
        ]}
      />
    </View>
  );
}

// ── Usage row ───────────────────────────────────────────────────
function UsageRow({ item }) {
  const config = CATEGORY_CONFIG[item.category] || CATEGORY_CONFIG.otc;
  const periodLabel = PERIOD_LABELS[item.period] || item.period;

  return (
    <View style={styles.usageRow}>
      <View style={styles.usageTop}>
        <View style={[styles.usageIcon, { backgroundColor: config.bg }]}>
          <Ionicons name={config.icon} size={16} color={config.color} />
        </View>
        <View style={styles.usageInfo}>
          <Text style={styles.usageLabel}>{item.label || config.label}</Text>
          <Text style={styles.usageAmounts}>
            ${item.spent.toFixed(0)} / ${item.cap.toFixed(0)} {periodLabel}
          </Text>
        </View>
        <Text style={styles.usageRemaining}>
          ${item.remaining.toFixed(0)} left
        </Text>
      </View>
      <ProgressBar pct={item.pct_used} color={config.color} />
    </View>
  );
}

// ── Log usage modal ─────────────────────────────────────────────
function LogUsageModal({ visible, onClose, onSave, categories }) {
  const [category, setCategory] = useState('');
  const [amount, setAmount] = useState('');
  const [description, setDescription] = useState('');
  const [saving, setSaving] = useState(false);

  const reset = () => {
    setCategory('');
    setAmount('');
    setDescription('');
    setSaving(false);
  };

  const handleSave = async () => {
    const parsedAmt = parseFloat(amount);
    if (!category || !amount || isNaN(parsedAmt) || parsedAmt <= 0 || parsedAmt > 10000) return;
    setSaving(true);
    await onSave({
      category,
      amount: parseFloat(amount),
      description: description.trim(),
      benefit_period: categories.find(c => c.category === category)?.period || 'Monthly',
    });
    reset();
    onClose();
  };

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <View style={styles.modalOverlay}>
        <View style={styles.modalContent}>
          <View style={styles.modalHeader}>
            <Text style={styles.modalTitle}>Log Spending</Text>
            <TouchableOpacity onPress={() => { reset(); onClose(); }}>
              <Ionicons name="close" size={24} color={COLORS.textSecondary} />
            </TouchableOpacity>
          </View>

          {/* Category picker */}
          <Text style={styles.fieldLabel}>Category</Text>
          <View style={styles.categoryGrid}>
            {categories.map((c) => {
              const config = CATEGORY_CONFIG[c.category] || CATEGORY_CONFIG.otc;
              const selected = category === c.category;
              return (
                <TouchableOpacity
                  key={c.category}
                  style={[styles.categoryChip, selected && styles.categoryChipActive]}
                  onPress={() => setCategory(c.category)}
                  activeOpacity={0.7}
                >
                  <Ionicons name={config.icon} size={16} color={selected ? COLORS.accent : COLORS.textSecondary} />
                  <Text style={[styles.categoryChipText, selected && styles.categoryChipTextActive]}>
                    {c.label || config.label}
                  </Text>
                </TouchableOpacity>
              );
            })}
          </View>

          {/* Amount */}
          <Text style={styles.fieldLabel}>Amount</Text>
          <View style={styles.amountRow}>
            <Text style={styles.dollarSign}>$</Text>
            <TextInput
              style={styles.amountInput}
              value={amount}
              onChangeText={setAmount}
              placeholder="0.00"
              placeholderTextColor={COLORS.textTertiary}
              keyboardType="decimal-pad"
            />
          </View>

          {/* Description (optional) */}
          <Text style={styles.fieldLabel}>Note (optional)</Text>
          <TextInput
            style={styles.textInput}
            value={description}
            onChangeText={setDescription}
            placeholder="e.g. CVS OTC purchase"
            placeholderTextColor={COLORS.textTertiary}
          />

          {/* Save button */}
          <TouchableOpacity
            style={[styles.saveBtn, (!category || !amount || saving) && styles.saveBtnDisabled]}
            onPress={handleSave}
            disabled={!category || !amount || saving}
            activeOpacity={0.8}
          >
            {saving ? (
              <ActivityIndicator color={COLORS.white} size="small" />
            ) : (
              <Text style={styles.saveBtnText}>Log Spending</Text>
            )}
          </TouchableOpacity>
        </View>
      </View>
    </Modal>
  );
}

// ── Main component ──────────────────────────────────────────────
export default function UsageTracker({ summary, loading, onLogUsage }) {
  const [expanded, setExpanded] = useState(true);
  const [showLog, setShowLog] = useState(false);

  const fadeIn = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    Animated.timing(fadeIn, { toValue: 1, duration: MOTION.normal, useNativeDriver: true }).start();
  }, []);

  // Don't render if no trackable benefits
  if (!loading && (!summary || summary.length === 0)) return null;

  if (loading && (!summary || summary.length === 0)) {
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
            <Ionicons name="pie-chart-outline" size={16} color={COLORS.accent} />
          </View>
          <Text style={styles.sectionTitle}>Benefits Usage</Text>
        </View>
        <Ionicons
          name={expanded ? 'chevron-up' : 'chevron-down'}
          size={18}
          color={COLORS.textSecondary}
        />
      </TouchableOpacity>

      {expanded ? (
        <View style={styles.body}>
          {summary.map((item) => (
            <UsageRow key={item.category} item={item} />
          ))}

          {/* Log button */}
          <TouchableOpacity
            style={styles.addBtn}
            onPress={() => setShowLog(true)}
            activeOpacity={0.7}
          >
            <Ionicons name="add-circle-outline" size={18} color={COLORS.accent} />
            <Text style={styles.addBtnText}>Log Spending</Text>
          </TouchableOpacity>
        </View>
      ) : null}

      <LogUsageModal
        visible={showLog}
        onClose={() => setShowLog(false)}
        onSave={onLogUsage}
        categories={summary}
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

  // Body
  body: { paddingHorizontal: 16, paddingBottom: 14 },

  // Usage row
  usageRow: { marginBottom: 14 },
  usageTop: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 6 },
  usageIcon: {
    width: 28, height: 28, borderRadius: 8,
    justifyContent: 'center', alignItems: 'center',
  },
  usageInfo: { flex: 1 },
  usageLabel: { fontSize: 14, fontWeight: '600', color: COLORS.text },
  usageAmounts: { fontSize: 12, fontWeight: '500', color: COLORS.textSecondary },
  usageRemaining: { fontSize: 13, fontWeight: '700', color: COLORS.accent },

  // Progress bar
  progressTrack: {
    height: 6, borderRadius: 3,
    backgroundColor: COLORS.borderLight,
    overflow: 'hidden',
  },
  progressFill: {
    height: '100%', borderRadius: 3,
  },

  // Add button
  addBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    gap: 6, paddingVertical: 10, marginTop: 2,
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
    marginBottom: 16,
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

  // Category chips
  categoryGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  categoryChip: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    paddingHorizontal: 14, paddingVertical: 10,
    borderRadius: RADII.full,
    backgroundColor: COLORS.bg,
    borderWidth: 1, borderColor: COLORS.borderLight,
  },
  categoryChipActive: {
    backgroundColor: COLORS.accentLight,
    borderColor: COLORS.accentSoft,
  },
  categoryChipText: { fontSize: 13, fontWeight: '600', color: COLORS.textSecondary },
  categoryChipTextActive: { color: COLORS.accent },

  // Amount input
  amountRow: { flexDirection: 'row', alignItems: 'center' },
  dollarSign: {
    fontSize: 24, fontWeight: '700', color: COLORS.text,
    marginRight: 4,
  },
  amountInput: {
    flex: 1,
    backgroundColor: COLORS.bg,
    borderRadius: RADII.md,
    borderWidth: 1, borderColor: COLORS.borderLight,
    paddingHorizontal: 14, paddingVertical: 14,
    fontSize: 24, fontWeight: '700', color: COLORS.text,
  },

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
