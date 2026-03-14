import { useState, useRef, useEffect } from 'react';
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  Animated,
  ActivityIndicator,
} from 'react-native';
import { Ionicons, MaterialCommunityIcons } from '@expo/vector-icons';
import { COLORS, RADII, SHADOWS, TYPE, MOTION } from '../constants/theme';

// ── Progress ring (simple bar for each med) ─────────────────────
function AdherenceBar({ pct }) {
  const widthAnim = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    Animated.timing(widthAnim, {
      toValue: Math.min(pct, 100),
      duration: MOTION.slow,
      useNativeDriver: false,
    }).start();
  }, [pct]);

  const color = pct >= 80 ? '#4CAF50' : pct >= 50 ? '#FF9800' : COLORS.error;

  return (
    <View style={styles.barTrack}>
      <Animated.View
        style={[
          styles.barFill,
          {
            backgroundColor: color,
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

// ── Single med adherence row ────────────────────────────────────
function AdherenceRow({ item }) {
  const pctColor =
    item.adherence_pct >= 80 ? '#4CAF50' : item.adherence_pct >= 50 ? '#FF9800' : COLORS.error;
  return (
    <View style={styles.medRow}>
      <View style={styles.medIcon}>
        <MaterialCommunityIcons name="pill" size={16} color={COLORS.rxDrug} />
      </View>
      <View style={styles.medInfo}>
        <Text style={styles.medName} numberOfLines={1}>
          {item.drug_name}
        </Text>
        <AdherenceBar pct={item.adherence_pct} />
        <Text style={styles.medDetail}>
          {item.doses_taken}/{item.total_days} doses · {item.doses_missed} missed
        </Text>
      </View>
      <Text style={[styles.pctText, { color: pctColor }]}>{item.adherence_pct}%</Text>
    </View>
  );
}

// ── Refill alert row ────────────────────────────────────────────
function RefillAlertRow({ alert }) {
  const urgent = alert.days_until_refill !== null && alert.days_until_refill <= 0;
  return (
    <View style={[styles.alertRow, urgent && styles.alertRowUrgent]}>
      <View style={[styles.alertIcon, urgent && styles.alertIconUrgent]}>
        <Ionicons
          name={urgent ? 'warning' : 'time-outline'}
          size={16}
          color={urgent ? COLORS.error : '#FF9800'}
        />
      </View>
      <View style={styles.alertInfo}>
        <Text style={styles.alertDrug} numberOfLines={1}>
          {alert.drug_name}
        </Text>
        <Text style={styles.alertDetail}>
          {alert.days_until_refill !== null
            ? alert.days_until_refill <= 0
              ? 'Refill overdue!'
              : `Refill due in ${alert.days_until_refill} day${alert.days_until_refill === 1 ? '' : 's'}`
            : 'Refill reminder enabled'}
        </Text>
      </View>
      <Text style={[styles.alertDays, urgent && { color: COLORS.error }]}>
        {alert.days_until_refill !== null
          ? alert.days_until_refill <= 0
            ? 'NOW'
            : `${alert.days_until_refill}d`
          : '—'}
      </Text>
    </View>
  );
}

// ── Main component ──────────────────────────────────────────────
export default function MedAdherence({ summary, refillAlerts, loading, onLogDose }) {
  const [expanded, setExpanded] = useState(true);
  const fadeIn = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    Animated.timing(fadeIn, { toValue: 1, duration: MOTION.normal, useNativeDriver: true }).start();
  }, []);

  const hasData = (summary && summary.length > 0) || (refillAlerts && refillAlerts.length > 0);
  if (!loading && !hasData) return null;

  if (loading && !hasData) {
    return (
      <View style={styles.container}>
        <ActivityIndicator size="small" color={COLORS.accent} />
      </View>
    );
  }

  // Overall adherence
  const overallPct =
    summary && summary.length > 0
      ? Math.round(summary.reduce((sum, s) => sum + s.adherence_pct, 0) / summary.length)
      : 0;
  const overallColor = overallPct >= 80 ? '#4CAF50' : overallPct >= 50 ? '#FF9800' : COLORS.error;

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
            <Ionicons name="fitness-outline" size={16} color={COLORS.accent} />
          </View>
          <Text style={styles.sectionTitle}>Medication Adherence</Text>
          {summary && summary.length > 0 && (
            <View style={[styles.badge, { backgroundColor: overallColor }]}>
              <Text style={styles.badgeText}>{overallPct}%</Text>
            </View>
          )}
        </View>
        <Ionicons
          name={expanded ? 'chevron-up' : 'chevron-down'}
          size={18}
          color={COLORS.textSecondary}
        />
      </TouchableOpacity>

      {expanded && (
        <View style={styles.body}>
          {/* Refill alerts */}
          {refillAlerts && refillAlerts.length > 0 && (
            <View style={styles.alertsSection}>
              <Text style={styles.subHeader}>Refill Alerts</Text>
              {refillAlerts.map((a) => (
                <RefillAlertRow key={String(a.id)} alert={a} />
              ))}
            </View>
          )}

          {/* Per-med adherence */}
          {summary && summary.length > 0 && (
            <>
              <Text style={styles.subHeader}>30-Day Adherence</Text>
              {summary.map((item) => (
                <AdherenceRow key={`${item.reminder_id}-${item.drug_name}`} item={item} />
              ))}
            </>
          )}

          {/* Log dose button */}
          {onLogDose && (
            <TouchableOpacity style={styles.logBtn} onPress={onLogDose} activeOpacity={0.7}>
              <Ionicons name="checkmark-circle-outline" size={18} color={COLORS.accent} />
              <Text style={styles.logBtnText}>Log Dose Taken</Text>
            </TouchableOpacity>
          )}
        </View>
      )}
    </Animated.View>
  );
}

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
  sectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 14,
  },
  sectionLeft: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  sectionIcon: {
    width: 28,
    height: 28,
    borderRadius: 8,
    backgroundColor: COLORS.accentLight,
    justifyContent: 'center',
    alignItems: 'center',
  },
  sectionTitle: { ...TYPE.label, fontSize: 14, color: COLORS.text },
  badge: {
    borderRadius: 10,
    minWidth: 38,
    height: 20,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 6,
  },
  badgeText: { fontSize: 11, fontWeight: '700', color: COLORS.white },
  body: { paddingHorizontal: 16, paddingBottom: 14 },
  subHeader: {
    fontSize: 12,
    fontWeight: '700',
    color: COLORS.textTertiary,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: 8,
    marginTop: 4,
  },

  // Adherence rows
  medRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.borderLight,
  },
  medIcon: {
    width: 28,
    height: 28,
    borderRadius: 8,
    backgroundColor: COLORS.rxDrugBg || '#FDECEA',
    justifyContent: 'center',
    alignItems: 'center',
  },
  medInfo: { flex: 1 },
  medName: { fontSize: 14, fontWeight: '600', color: COLORS.text, marginBottom: 4 },
  medDetail: { fontSize: 11, fontWeight: '500', color: COLORS.textTertiary, marginTop: 3 },
  pctText: { fontSize: 16, fontWeight: '700', minWidth: 44, textAlign: 'right' },

  // Progress bar
  barTrack: {
    height: 6,
    borderRadius: 3,
    backgroundColor: COLORS.borderLight,
    overflow: 'hidden',
  },
  barFill: { height: '100%', borderRadius: 3 },

  // Refill alerts
  alertsSection: { marginBottom: 12 },
  alertRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingVertical: 10,
    paddingHorizontal: 10,
    borderRadius: RADII.sm,
    backgroundColor: '#FFF8E1',
    marginBottom: 6,
  },
  alertRowUrgent: { backgroundColor: '#FFEBEE' },
  alertIcon: {
    width: 28,
    height: 28,
    borderRadius: 8,
    backgroundColor: '#FFF3E0',
    justifyContent: 'center',
    alignItems: 'center',
  },
  alertIconUrgent: { backgroundColor: '#FFCDD2' },
  alertInfo: { flex: 1 },
  alertDrug: { fontSize: 14, fontWeight: '600', color: COLORS.text },
  alertDetail: { fontSize: 12, fontWeight: '500', color: COLORS.textSecondary, marginTop: 1 },
  alertDays: { fontSize: 14, fontWeight: '700', color: '#FF9800' },

  // Log button
  logBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    paddingVertical: 10,
    marginTop: 6,
  },
  logBtnText: { fontSize: 14, fontWeight: '600', color: COLORS.accent },
});
