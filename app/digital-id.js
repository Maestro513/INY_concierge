import { useState, useRef, useEffect } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, Animated,
  SafeAreaView, Linking, ActivityIndicator, Image, Dimensions,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, RADII, SHADOWS, TYPE, MOTION } from '../constants/theme';
import { API_URL, authFetch } from '../constants/api';

const { width: SCREEN_WIDTH } = Dimensions.get('window');
const CARD_WIDTH = SCREEN_WIDTH - 48;
const CARD_HEIGHT = CARD_WIDTH / 1.59; // Real ID card aspect ratio

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
  const { firstName, lastName, planName, planNumber, medicareNumber } = useLocalSearchParams();

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
      const res = await authFetch(`${API_URL}/cms/id-card/${encodeURIComponent(planNumber)}`);
      if (!res.ok) throw new Error('Failed to load card data');
      const data = await res.json();
      setCardData(data);
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
        <TouchableOpacity onPress={() => router.back()} style={s.backBtn} activeOpacity={0.7}>
          <Ionicons name="chevron-back" size={24} color={COLORS.text} />
        </TouchableOpacity>
        <Text style={s.headerTitle}>Digital ID Card</Text>
        <View style={{ width: 40 }} />
      </View>

      {loading ? (
        <View style={s.center}>
          <ActivityIndicator size="large" color={COLORS.accent} />
          <Text style={s.loadingText}>Loading your ID card...</Text>
        </View>
      ) : error ? (
        <View style={s.center}>
          <Ionicons name="alert-circle-outline" size={48} color={COLORS.textTertiary} />
          <Text style={s.errorText}>{error}</Text>
          <TouchableOpacity style={s.retryBtn} onPress={loadCardData} activeOpacity={0.7}>
            <Text style={s.retryText}>Try Again</Text>
          </TouchableOpacity>
        </View>
      ) : (
        <View style={s.content}>
          <Text style={s.tapHint}>Tap card to flip</Text>

          <TouchableOpacity onPress={flipCard} activeOpacity={0.95} style={s.cardContainer}>
            {/* FRONT */}
            <Animated.View style={[s.card, s.cardFront, { transform: [{ perspective: 1000 }, { rotateY: frontRotation }] }]}>
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

              {medicareNumber ? (
                <View style={s.memberSection}>
                  <Text style={s.fieldLabel}>Medicare #</Text>
                  <Text style={s.fieldValue}>{medicareNumber}</Text>
                </View>
              ) : null}

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
              <Text style={s.backTitle}>Important Numbers</Text>

              {cardData?.customer_service ? (
                <TouchableOpacity style={s.phoneRow} onPress={() => callNumber(cardData.customer_service)} activeOpacity={0.7}>
                  <Ionicons name="call-outline" size={16} color={COLORS.accent} />
                  <View style={s.phoneInfo}>
                    <Text style={s.phoneLabel}>Customer Service</Text>
                    <Text style={s.phoneNumber}>{cardData.customer_service}</Text>
                  </View>
                  <Ionicons name="chevron-forward" size={14} color={COLORS.textTertiary} />
                </TouchableOpacity>
              ) : null}

              {cardData?.pharmacy_help ? (
                <TouchableOpacity style={s.phoneRow} onPress={() => callNumber(cardData.pharmacy_help)} activeOpacity={0.7}>
                  <Ionicons name="medkit-outline" size={16} color={COLORS.accent} />
                  <View style={s.phoneInfo}>
                    <Text style={s.phoneLabel}>Pharmacy Help</Text>
                    <Text style={s.phoneNumber}>{cardData.pharmacy_help}</Text>
                  </View>
                  <Ionicons name="chevron-forward" size={14} color={COLORS.textTertiary} />
                </TouchableOpacity>
              ) : null}

              {cardData?.prior_auth_phone ? (
                <TouchableOpacity style={s.phoneRow} onPress={() => callNumber(cardData.prior_auth_phone)} activeOpacity={0.7}>
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
  headerTitle: { ...TYPE.h3, color: COLORS.text },

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
  content: { flex: 1, alignItems: 'center', paddingTop: 8, paddingHorizontal: 24 },
  tapHint: { fontSize: 13, color: COLORS.textTertiary, marginBottom: 12, fontWeight: '500' },

  // Card container
  cardContainer: { width: CARD_WIDTH, height: CARD_HEIGHT },

  // Card shared
  card: {
    width: CARD_WIDTH, height: CARD_HEIGHT,
    borderRadius: 16, padding: 20,
    position: 'absolute', backfaceVisibility: 'hidden',
    ...SHADOWS.cardLifted,
  },

  // Front
  cardFront: { backgroundColor: '#FFFFFF' },
  cardTopRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 },
  cardLogo: { width: 90, height: 36 },
  cardOrgName: { fontSize: 14, fontWeight: '700', color: COLORS.accent, flex: 1 },
  planTypeBadge: {
    backgroundColor: COLORS.accentLight, borderRadius: RADII.full,
    paddingHorizontal: 10, paddingVertical: 4,
  },
  planTypeText: { fontSize: 10, fontWeight: '700', color: COLORS.accent, letterSpacing: 0.3 },
  cardPlanName: { fontSize: 13, fontWeight: '600', color: COLORS.textSecondary, marginBottom: 8, lineHeight: 18 },
  divider: { height: 1, backgroundColor: COLORS.borderLight, marginBottom: 10 },

  // Member info
  memberSection: { marginBottom: 6 },
  memberRow: { flexDirection: 'row', gap: 20, marginBottom: 6 },
  memberCol: { flex: 1 },
  fieldLabel: { fontSize: 10, fontWeight: '600', color: COLORS.textTertiary, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 1 },
  fieldValue: { fontSize: 15, fontWeight: '700', color: COLORS.text },

  // Rx strip
  rxStrip: {
    flexDirection: 'row', justifyContent: 'space-between',
    backgroundColor: COLORS.accentLight, borderRadius: RADII.sm,
    paddingHorizontal: 12, paddingVertical: 6, marginTop: 'auto',
  },
  rxItem: { fontSize: 11, fontWeight: '600', color: COLORS.accent },

  // Back
  cardBack: { backgroundColor: '#FFFFFF' },
  backTitle: { fontSize: 16, fontWeight: '700', color: COLORS.text, marginBottom: 10 },
  phoneRow: {
    flexDirection: 'row', alignItems: 'center', gap: 10,
    paddingVertical: 7, borderBottomWidth: 1, borderBottomColor: COLORS.borderLight,
  },
  phoneInfo: { flex: 1 },
  phoneLabel: { fontSize: 11, fontWeight: '600', color: COLORS.textTertiary, textTransform: 'uppercase', letterSpacing: 0.3 },
  phoneNumber: { fontSize: 14, fontWeight: '700', color: COLORS.text },

  // Back copays
  backDivider: { height: 1, backgroundColor: COLORS.borderLight, marginTop: 6, marginBottom: 8 },
  backSectionTitle: { fontSize: 12, fontWeight: '700', color: COLORS.textSecondary, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6 },
  copayGrid: { flexDirection: 'row', gap: 8, marginBottom: 8 },
  copayItem: {
    flex: 1, backgroundColor: COLORS.accentLighter, borderRadius: RADII.sm,
    paddingVertical: 6, paddingHorizontal: 4, alignItems: 'center',
  },
  copayValue: { fontSize: 16, fontWeight: '700', color: COLORS.accent },
  copayLabel: { fontSize: 10, fontWeight: '600', color: COLORS.textSecondary, marginTop: 1 },

  websiteText: { fontSize: 11, color: COLORS.textTertiary, textAlign: 'center', marginTop: 'auto' },

  // Disclaimer
  disclaimer: {
    fontSize: 12, color: COLORS.textTertiary, textAlign: 'center',
    marginTop: 20, paddingHorizontal: 16, lineHeight: 18,
  },
});
