import { useRef, useEffect } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, Animated, Linking } from 'react-native';
import { Ionicons, MaterialCommunityIcons } from '@expo/vector-icons';
import { COLORS, RADII, SHADOWS, MOTION } from '../constants/theme';

/**
 * MTM (Medication Therapy Management) eligibility prompt.
 * Shows when a member has 5+ active medications.
 *
 * Props:
 *   eligible: boolean
 *   medicationCount: number
 *   message: string
 *   onDismiss: () => void (optional)
 */
export default function MTMPrompt({ eligible, medicationCount, _message, onDismiss }) {
  const fadeIn = useRef(new Animated.Value(0)).current;
  const slideUp = useRef(new Animated.Value(10)).current;

  useEffect(() => {
    if (eligible) {
      Animated.parallel([
        Animated.timing(fadeIn, { toValue: 1, duration: MOTION.slow, useNativeDriver: true }),
        Animated.timing(slideUp, { toValue: 0, duration: MOTION.slow, useNativeDriver: true }),
      ]).start();
    }
  }, [eligible]);

  if (!eligible) return null;

  return (
    <Animated.View
      style={[styles.container, { opacity: fadeIn, transform: [{ translateY: slideUp }] }]}
    >
      <View style={styles.iconRow}>
        <View style={styles.iconWrap}>
          <MaterialCommunityIcons name="medical-bag" size={20} color="#3D6B99" />
        </View>
        <View style={styles.content}>
          <Text style={styles.title}>Free Medication Review Available</Text>
          <Text style={styles.subtitle}>
            You're on {medicationCount} medications — you may qualify for a free Medication Therapy
            Management (MTM) consultation with your pharmacist.
          </Text>
        </View>
        {onDismiss && (
          <TouchableOpacity
            onPress={onDismiss}
            hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
            accessibilityLabel="Dismiss MTM prompt"
          >
            <Ionicons name="close" size={18} color={COLORS.textTertiary} />
          </TouchableOpacity>
        )}
      </View>

      <View style={styles.infoBox}>
        <Ionicons name="information-circle-outline" size={16} color="#3D6B99" />
        <Text style={styles.infoText}>
          MTM is a covered Medicare benefit — a pharmacist reviews all your medications for
          interactions, duplicates, and cost savings at no extra charge.
        </Text>
      </View>

      <TouchableOpacity
        style={styles.ctaBtn}
        activeOpacity={0.7}
        accessibilityRole="button"
        accessibilityLabel="Learn about medication therapy management"
        onPress={() => {
          Linking.openURL(
            'https://www.medicare.gov/drug-coverage-part-d/what-drug-plans-cover/medication-therapy-management-programs-for-complex-health-needs',
          ).catch(() => {});
        }}
      >
        <Ionicons name="open-outline" size={16} color={COLORS.white} />
        <Text style={styles.ctaBtnText}>Learn More About MTM</Text>
      </TouchableOpacity>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  container: {
    marginHorizontal: 20,
    marginBottom: 12,
    backgroundColor: '#EDF4FB',
    borderRadius: RADII.lg,
    padding: 16,
    borderWidth: 1,
    borderColor: '#C5D9ED',
    ...SHADOWS.card,
  },
  iconRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 12,
  },
  iconWrap: {
    width: 36,
    height: 36,
    borderRadius: 10,
    backgroundColor: '#D6E8F7',
    justifyContent: 'center',
    alignItems: 'center',
  },
  content: { flex: 1 },
  title: {
    fontSize: 15,
    fontWeight: '700',
    color: '#2C5282',
    marginBottom: 4,
  },
  subtitle: {
    fontSize: 13,
    fontWeight: '500',
    color: '#4A6A8A',
    lineHeight: 18,
  },
  infoBox: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 8,
    marginTop: 12,
    backgroundColor: '#D6E8F7',
    borderRadius: RADII.sm,
    padding: 10,
  },
  infoText: {
    flex: 1,
    fontSize: 12,
    fontWeight: '500',
    color: '#3D6B99',
    lineHeight: 17,
  },
  ctaBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    backgroundColor: '#3D6B99',
    borderRadius: RADII.full,
    paddingVertical: 12,
    marginTop: 12,
    ...SHADOWS.button,
  },
  ctaBtnText: {
    fontSize: 14,
    fontWeight: '600',
    color: COLORS.white,
  },
});
