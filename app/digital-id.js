import { useState, useRef, useEffect } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, Animated,
  SafeAreaView, Linking, ActivityIndicator, Image, Dimensions,
} from 'react-native';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, RADII, SHADOWS, TYPE, MOTION } from '../constants/theme';
import { API_URL, authFetch } from '../constants/api';
import { cachedFetch } from '../utils/offlineCache';
import { getMemberSession } from '../constants/session';

const { width: SCREEN_WIDTH } = Dimensions.get('window');
const CARD_WIDTH = SCREEN_WIDTH - 16;
const CARD_HEIGHT = CARD_WIDTH / 1.25; // Extra tall for bigger content

// Carrier logo map (same as ProfileCard)
const CARRIER_LOGOS = {
  humana: require('../assets/carriers/humana.png'),
  uhc: require('../assets/carriers/uhc.png'),
  aetna: require('../assets/carriers/aetna.png'),
  devoted: require('../assets/carriers/devoted.png'),
  wellcare: require('../assets/carriers/wellcare.png'),
  zing: require('../assets/carriers/zing.png'),
  healthspring: require('../assets/carriers/healthspring.png'),
};

export default function DigitalIDScreen() {
  const router = useRouter();
  const { member: _mem } = getMemberSession();
  const { firstName, lastName, planName, planNumber, medicareNumber } = _mem || {};

  const [cardData, setCardData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [flipped, setFlipped] = useState(false);
  const flipAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    loadCardData();
  }, [planNumber]);

  const loadCardData = async () => {
    setLoading(true);
    setError(null);
    try {
      const url = `${API_URL}/cms/id-card/${encodeURIComponent(planNumber)}`;
      const result = await cachedFetch(authFetch, url);
      setCardData(result.data);
    } catch (e) {
      console.log('ID Card load error:', e);
      setError('Could not load card details');
    } finally {
      setLoading(false);
    }
  };

  const flipCard = () => {
    Animated.spring(flipAnim, {
      toValue: flipped ? 0 : 1,
      friction: 8,
      tension: 10,
      useNativeDriver: true,
    }).start();
    setFlipped(!flipped);
  };

  const frontRotation = flipAnim.interpolate({
    inputRange: [0, 1],
    outputRange: ['0deg', '180deg'],
  });
  const backRotation = flipAnim.interpolate({
    inputRange: [0, 1],
    outputRange: ['180deg', '360deg'],
  });

  const callNumber = (num) => {
    if (num) Linking.openURL(`tel:${num.replace(/[^0-9+]/g, '')}`);
  };

  const carrier = cardData?.carrier || null;
  const carrierLogo = carrier ? CARRIER_LOGOS[carrier] : null;

  return (
    <SafeAreaView style={s.safe}>
      {/* Header */}
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} style={s.backBtn} activeOpacity={0.7} accessibilityRole="button" accessibilityLabel="Go back">
          <Ionicons name="chevron-back" size={24} color={COLORS.text} />
        </TouchableOpacity>
        <Text style={s.headerTitle} accessibilityRole="header">Digital ID Card</Text>
        <View style={{ width: 40 }} />
      </View>

      {loading ? (
        <View style={s.center}>
          <ActivityIndicator size="large" color={COLORS.accent} accessibilityLabel="Loading" />
          <Text style={s.loadingText} accessibilityLiveRegion="polite">Loading your ID card...</Text>
        </View>
      ) : error ? (
        <View style={s.center}>
          <Ionicons name="alert-circle-outline" size={48} color={COLORS.textTertiary} />
          <Text style={s.errorText} accessibilityLiveRegion="assertive">{error}</Text>
          <TouchableOpacity style={s.retryBtn} onPress={loadCardData} activeOpacity={0.7} accessibilityRole="button" accessibilityLabel="Try again to load ID card">
            <Text style={s.retryText}>Try Again</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <View style={s.content}>
          <Text style={s.tapHint} accessibilityElementsHidden>Tap card to flip</Text>

          <TouchableOpacity onPress={flipCard} activeOpacity={0.95} style={s.cardContainer} accessibilityRole="button" accessibilityLabel={flipped ? 'ID card back side showing phone numbers. Tap to flip to front' : 'ID card front side showing member info. Tap to flip to back'} accessibilityHint="Double tap to flip the card">
            {/* FRONT */}
            <Animated.View style={[s.card, s.cardFront, { transform: [{ perspective: 1000 }, { rotateY: frontRotation }] }]}>
              {/* Premium accent stripe */}
              <View style={s.accentStripe} />

              {/* Top row: Carrier logo + Plan type */}
              <View style={s.cardTopRow}>
                {carrierLogo ? (
                  <Image source={carrierLogo} style={s.cardLogo} resizeMode="contain" />
                ) : (
                  <Text style={s.cardOrgName}>{cardData?.org_name || ''}</Text>
                )}
                <View style={s.planTypeBadge}>
                  <Text style={s.planTypeText}>Medicare Advantage</Text>
                </View>
              </View>

              {/* Plan name */}
              <Text style={s.cardPlanName} numberOfLines={2}>{planName || cardData?.plan_name || ''}</Text>

              {/* Divider */}
              <View style={s.divider} />

              {/* Member info */}
              <View style={s.memberSection}>
                <Text style={s.fieldLabel}>Member Name</Text>
                <Text style={s.fieldValue}>{firstName} {lastName}</Text>
              </View>

              <View style={s.memberRow}>
                <View style={s.memberCol}>
                  <Text style={s.fieldLabel}>Member ID</Text>
                  <Text style={s.fieldValue}>{planNumber}</Text>
                </View>
                <View style={s.memberCol}>
                  <Text style={s.fieldLabel}>Effective Date</Text>
                  <Text style={s.fieldValue}>{cardData?.effective_date || '01/01/2026'}</Text>
                </View>
              </View>

              {/* Rx info strip at bottom */}
              {cardData?.rx_bin ? (
                <View style={s.rxStrip}>
                  <Text style={s.rxItem}>RxBIN: {cardData.rx_bin}</Text>
                  <Text style={s.rxItem}>RxPCN: {cardData.rx_pcn}</Text>
                  <Text style={s.rxItem}>RxGrp: {cardData.rx_group}</Text>
                </View>
              ) : null}
            </Animated.View>

            {/* BACK */}
            <Animated.View style={[s.card, s.cardBack, { transform: [{ perspective: 1000 }, { rotateY: backRotation }] }]}>
              {/* Premium accent stripe */}
              <View style={s.accentStripe} />
              <Text style={s.backTitle}>Important Numbers</Text>

              {cardData?.customer_service ? (
                <TouchableOpacity style={s.phoneRow} onPress={() => callNumber(cardData.customer_service)} activeOpacity={0.7} accessibilityRole="button" accessibilityLabel={`Call customer service at ${cardData.customer_service}`}>
                  <Ionicons name="call-outline" size={16} color={COLORS.accent} />
                  <View style={s.phoneInfo}>
                    <Text style={s.phoneLabel}>Customer Service</Text>
                    <Text style={s.phoneNumber}>{cardData.customer_service}</Text>
                  </View>
                  <Ionicons name="chevron-forward" size={14} color={COLORS.textTertiary} />
                </TouchableOpacity>
              ) : null}

              {cardData?.pharmacy_help ? (
                <TouchableOpacity style={s.phoneRow} onPress={() => callNumber(cardData.pharmacy_help)} activeOpacity={0.7} accessibilityRole="button" accessibilityLabel={`Call pharmacy help at ${cardData.pharmacy_help}`}>
                  <Ionicons name="medkit-outline" size={16} color={COLORS.accent} />
                  <View style={s.phoneInfo}>
                    <Text style={s.phoneLabel}>Pharmacy Help</Text>
                    <Text style={s.phoneNumber}>{cardData.pharmacy_help}</Text>
                  </View>
                  <Ionicons name="chevron-forward" size={14} color={COLORS.textTertiary} />
                </TouchableOpacity>
              ) : null}

              {cardData?.prior_auth_phone ? (
                <TouchableOpacity style={s.phoneRow} onPress={() => callNumber(cardData.prior_auth_phone)} activeOpacity={0.7} accessibilityRole="button" accessibilityLabel={`Call prior authorization at ${cardData.prior_auth_phone}`}>
                  <Ionicons name="document-text-outline" size={16} color={COLORS.accent} />
                  <View style={s.phoneInfo}>
                    <Text style={s.phoneLabel}>Prior Authorization</Text>
                    <Text style={s.phoneNumber}>{cardData.prior_auth_phone}</Text>
                  </View>
                  <Ionicons name="chevron-forward" size={14} color={COLORS.textTertiary} />
                </TouchableOpacity>
              ) : null}

              <View style={s.phoneRow}>
                <Ionicons name="ear-outline" size={16} color={COLORS.accent} />
                <View style={s.phoneInfo}>
                  <Text style={s.phoneLabel}>TTY</Text>
                  <Text style={s.phoneNumber}>{cardData?.customer_service_tty || '711'}</Text>
                </View>
              </View>

              {/* Copays section */}
              <View style={s.backDivider} />
              <Text style={s.backSectionTitle}>Your Copays</Text>
              <View style={s.copayGrid}>
                {cardData?.pcp_copay ? (
                  <View style={s.copayItem}>
                    <Text style={s.copayValue}>{cardData.pcp_copay}</Text>
                    <Text style={s.copayLabel}>PCP</Text>
                  </View>
                ) : null}
                {cardData?.specialist_copay ? (
                  <View style={s.copayItem}>
                    <Text style={s.copayValue}>{cardData.specialist_copay}</Text>
                    <Text style={s.copayLabel}>Specialist</Text>
                  </View>
                ) : null}
                {cardData?.urgent_care_copay ? (
                  <View style={s.copayItem}>
                    <Text style={s.copayValue}>{cardData.urgent_care_copay}</Text>
                    <Text style={s.copayLabel}>Urgent</Text>
                  </View>
                ) : null}
                {cardData?.er_copay ? (
                  <View style={s.copayItem}>
                    <Text style={s.copayValue}>{cardData.er_copay}</Text>
                    <Text style={s.copayLabel}>ER</Text>
                  </View>
                ) : null}
              </View>

              {cardData?.website ? (
                <Text style={s.websiteText}>{cardData.website}</Text>
              ) : null}
            </Animated.View>
          </TouchableOpacity>

          <Text style={s.disclaimer}>
            This digital card is for reference only. Present your physical card at appointments.
          </Text>
        </View>
      )}
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: COLORS.bg },

  // Header
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 16, paddingVertical: 12,
  },
  backBtn: { width: 40, height: 40, justifyContent: 'center', alignItems: 'center' },
  headerTitle: { ...TYPE.h2, color: COLORS.text },

  // Center states
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', paddingHorizontal: 24 },
  loadingText: { fontSize: 15, color: COLORS.textSecondary, marginTop: 12 },
  errorText: { fontSize: 15, color: COLORS.textSecondary, marginTop: 12, textAlign: 'center' },
  retryBtn: {
    marginTop: 16, backgroundColor: COLORS.accent, borderRadius: RADII.full,
    paddingHorizontal: 24, paddingVertical: 12, ...SHADOWS.button,
  },
  retryText: { color: '#fff', fontSize: 14, fontWeight: '600' },

  // Content
  content: { flex: 1, alignItems: 'center', paddingTop: 8, paddingHorizontal: 12 },
  tapHint: { fontSize: 13, color: COLORS.textTertiary, marginBottom: 12, fontWeight: '500' },

  // Card container
  cardContainer: { width: CARD_WIDTH, height: CARD_HEIGHT },

  // Card shared
  card: {
    width: CARD_WIDTH, height: CARD_HEIGHT,
    borderRadius: 20, padding: 26, paddingTop: 32,
    position: 'absolute', backfaceVisibility: 'hidden',
    overflow: 'hidden',
    ...SHADOWS.container,
  },

  // Premium accent stripe at top of card
  accentStripe: {
    position: 'absolute', top: 0, left: 0, right: 0,
    height: 6, borderTopLeftRadius: 20, borderTopRightRadius: 20,
    backgroundColor: COLORS.accent,
  },

  // Front
  cardFront: { backgroundColor: '#FFFFFF' },
  cardTopRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 },
  cardLogo: { width: 120, height: 50 },
  cardOrgName: { fontSize: 19, fontWeight: '700', color: COLORS.accent, flex: 1 },
  planTypeBadge: {
    backgroundColor: COLORS.accentLight, borderRadius: RADII.full,
    paddingHorizontal: 14, paddingVertical: 6,
  },
  planTypeText: { fontSize: 13, fontWeight: '700', color: COLORS.accent, letterSpacing: 0.4 },
  cardPlanName: { fontSize: 17, fontWeight: '600', color: COLORS.textSecondary, marginBottom: 14, lineHeight: 23 },
  divider: { height: 1, backgroundColor: COLORS.borderLight, marginBottom: 16 },

  // Member info
  memberSection: { marginBottom: 12 },
  memberRow: { flexDirection: 'row', gap: 28, marginBottom: 12 },
  memberCol: { flex: 1 },
  fieldLabel: { fontSize: 13, fontWeight: '700', color: COLORS.textTertiary, textTransform: 'uppercase', letterSpacing: 0.6, marginBottom: 3 },
  fieldValue: { fontSize: 20, fontWeight: '700', color: COLORS.text, letterSpacing: 0.1 },

  // Rx strip
  rxStrip: {
    flexDirection: 'row', justifyContent: 'space-between',
    backgroundColor: COLORS.accentLight, borderRadius: RADII.sm,
    paddingHorizontal: 16, paddingVertical: 12, marginTop: 'auto',
  },
  rxItem: { fontSize: 15, fontWeight: '600', color: COLORS.accent },

  // Back
  cardBack: { backgroundColor: '#FFFFFF' },
  backTitle: { fontSize: 22, fontWeight: '700', color: COLORS.text, marginBottom: 14 },
  phoneRow: {
    flexDirection: 'row', alignItems: 'center', gap: 14,
    paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: COLORS.borderLight,
  },
  phoneInfo: { flex: 1 },
  phoneLabel: { fontSize: 14, fontWeight: '600', color: COLORS.textTertiary, textTransform: 'uppercase', letterSpacing: 0.4 },
  phoneNumber: { fontSize: 19, fontWeight: '700', color: COLORS.text },

  // Back copays
  backDivider: { height: 1, backgroundColor: COLORS.borderLight, marginTop: 10, marginBottom: 12 },
  backSectionTitle: { fontSize: 15, fontWeight: '700', color: COLORS.textSecondary, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 10 },
  copayGrid: { flexDirection: 'row', gap: 12, marginBottom: 10 },
  copayItem: {
    flex: 1, backgroundColor: COLORS.accentLighter, borderRadius: RADII.sm,
    paddingVertical: 10, paddingHorizontal: 8, alignItems: 'center',
  },
  copayValue: { fontSize: 22, fontWeight: '700', color: COLORS.accent },
  copayLabel: { fontSize: 13, fontWeight: '600', color: COLORS.textSecondary, marginTop: 2 },

  websiteText: { fontSize: 14, color: COLORS.textTertiary, textAlign: 'center', marginTop: 'auto' },

  // Disclaimer
  disclaimer: {
    fontSize: 12, color: COLORS.textTertiary, textAlign: 'center',
    marginTop: 20, paddingHorizontal: 16, lineHeight: 18,
  },
});
