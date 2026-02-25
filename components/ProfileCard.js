import { useRef, useEffect } from 'react';
import { View, Text, TouchableOpacity, Image, StyleSheet, ActivityIndicator, Animated } from 'react-native';
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

// ── Main component ──────────────────────────────────────────────
export default function ProfileCard({ member, onViewSOB, benefits, loading }) {
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

      {/* Reminder Bar */}
      <View style={styles.reminderBar}>
        <Ionicons name="notifications-outline" size={16} color={COLORS.accent} />
        <Text style={styles.reminderText}>Annual Enrollment: Oct 15 – Dec 7</Text>
      </View>

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
      ) : null}
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
});
