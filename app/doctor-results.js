import { useState, useEffect } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, FlatList,
  ActivityIndicator, Linking,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, RADII, SPACING, SHADOWS, TYPE } from '../constants/theme';
import { API_URL } from '../constants/api';

export default function DoctorResults() {
  const { specialty, zipCode, planName } = useLocalSearchParams();
  const router = useRouter();
  const [providers, setProviders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [meta, setMeta] = useState({});

  useEffect(() => { searchProviders(); }, []);

  const searchProviders = async () => {
    setLoading(true); setError('');
    try {
      const res = await fetch(`${API_URL}/providers/search`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ plan_name: planName, specialty, zip_code: zipCode, radius_miles: 25, limit: 50, enrich_google: true }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Search failed');
      setProviders(data.providers || []);
      setMeta({ total: data.total, carrier: data.carrier, specialty: data.specialty });
    } catch (err) {
      console.log('Provider search error:', err);
      if (err.message === 'Network request failed' || err.name === 'TypeError') {
        setError("Can't connect to the server right now. Check your connection and try again.");
      } else { setError(err.message || 'Something went wrong. Please try again.'); }
    } finally { setLoading(false); }
  };

  const callDoctor = (phone) => {
    if (!phone) return;
    Linking.openURL(`tel:${phone.replace(/\D/g, '')}`);
  };

  const renderStars = (rating) => {
    if (!rating) return null;
    const full = Math.floor(rating);
    const half = rating - full >= 0.5;
    const stars = [];
    for (let i = 0; i < full; i++) stars.push(<Ionicons key={'f'+i} name="star" size={14} color={COLORS.warning} />);
    if (half) stars.push(<Ionicons key="h" name="star-half" size={14} color={COLORS.warning} />);
    return stars;
  };

  const getInitials = (name) => {
    if (!name) return '?';
    const parts = name.replace(/^Dr\.?\s*/i, '').split(' ').filter(Boolean);
    if (parts.length >= 2) return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
    return (parts[0] || '?')[0].toUpperCase();
  };

  const renderProvider = ({ item, index }) => (
    <View style={s.card}>
      <View style={s.cardHeader}>
        {/* Avatar with initials */}
        <View style={s.avatar}>
          <Text style={s.avatarText}>{getInitials(item.name)}</Text>
        </View>
        <View style={s.nameWrap}>
          <Text style={s.name}>{item.name}</Text>
          <Text style={s.specialty}>{item.specialty}</Text>
        </View>
        {item.accepting_new_patients != null && (
          <View style={[s.statusPill, !item.accepting_new_patients && s.statusPillClosed]}>
            <View style={[s.statusDot, !item.accepting_new_patients && s.statusDotClosed]} />
            <Text style={[s.statusText, !item.accepting_new_patients && s.statusTextClosed]}>
              {item.accepting_new_patients ? 'Accepting' : 'Not Accepting'}
            </Text>
          </View>
        )}
      </View>

      {/* Google Rating */}
      {item.google_rating && (
        <View style={s.ratingRow}>
          <View style={s.starsRow}>{renderStars(item.google_rating)}</View>
          <Text style={s.ratingNum}>{item.google_rating}</Text>
          {item.google_review_count ? (
            <Text style={s.reviewCount}>({item.google_review_count})</Text>
          ) : null}
        </View>
      )}

      {/* Address + distance inline */}
      <View style={s.infoRow}>
        <Ionicons name="location-outline" size={15} color={COLORS.textSecondary} />
        <Text style={s.address}>{item.address}</Text>
      </View>
      {item.distance_miles != null && (
        <View style={s.distanceBadge}>
          <Ionicons name="navigate-outline" size={12} color={COLORS.accent} />
          <Text style={s.distanceText}>{item.distance_miles.toFixed(1)} mi</Text>
        </View>
      )}

      {/* Phone button */}
      {item.phone ? (
        <TouchableOpacity style={s.callDocBtn} onPress={() => callDoctor(item.phone)} activeOpacity={0.7}>
          <Ionicons name="call" size={15} color={COLORS.accent} />
          <Text style={s.callDocText}>{item.phone}</Text>
        </TouchableOpacity>
      ) : null}
    </View>
  );

  return (
    <SafeAreaView style={s.container} edges={['top']}>
      {/* Header */}
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} style={s.backBtn} activeOpacity={0.7}>
          <Ionicons name="chevron-back" size={22} color={COLORS.accent} />
        </TouchableOpacity>
        <View style={s.headerCenter}>
          <Text style={s.headerTitle} numberOfLines={1}>
            {meta.specialty || specialty || 'Doctors'}
          </Text>
          <Text style={s.headerSub}>Near {zipCode}</Text>
        </View>
        <View style={{ width: 36 }} />
      </View>

      {/* Loading */}
      {loading && (
        <View style={s.center}>
          <ActivityIndicator size="large" color={COLORS.accent} />
          <Text style={s.loadingText}>Searching for {specialty || 'doctors'}...</Text>
        </View>
      )}

      {/* Error */}
      {error !== '' && !loading && (
        <View style={s.center}>
          <View style={s.errorIcon}>
            <Ionicons name="cloud-offline-outline" size={36} color={COLORS.textTertiary} />
          </View>
          <Text style={s.errorText}>{error}</Text>
          <TouchableOpacity style={s.retryBtn} onPress={searchProviders} activeOpacity={0.7}>
            <Text style={s.retryBtnText}>Try Again</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* No results */}
      {!loading && !error && providers.length === 0 && (
        <View style={s.center}>
          <View style={s.errorIcon}>
            <Ionicons name="search-outline" size={36} color={COLORS.textTertiary} />
          </View>
          <Text style={s.emptyText}>
            No {specialty || 'doctors'} found near {zipCode}.{'\n'}
            Try a different specialty or call us at (844) 463-2931.
          </Text>
        </View>
      )}

      {/* Results */}
      {!loading && providers.length > 0 && (
        <>
          <View style={s.countRow}>
            <View style={s.countBadge}>
              <Text style={s.countBadgeText}>{meta.total || providers.length}</Text>
            </View>
            <Text style={s.resultCount}>
              result{(meta.total || providers.length) !== 1 ? 's' : ''} found
            </Text>
          </View>
          <FlatList
            data={providers}
            keyExtractor={(item, i) => item.npi || `${item.name}-${i}`}
            renderItem={renderProvider}
            contentContainerStyle={s.list}
            showsVerticalScrollIndicator={false}
          />
        </>
      )}
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.bg },

  // Header
  header: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: 16, paddingVertical: 12,
    backgroundColor: COLORS.white,
    borderBottomWidth: 1, borderBottomColor: COLORS.borderLight,
  },
  backBtn: {
    width: 36, height: 36, borderRadius: 12,
    backgroundColor: COLORS.accentLight,
    justifyContent: 'center', alignItems: 'center',
  },
  headerCenter: { flex: 1, alignItems: 'center' },
  headerTitle: { ...TYPE.h3, color: COLORS.text },
  headerSub: { ...TYPE.caption, color: COLORS.textSecondary, marginTop: 1 },

  // States
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 24 },
  loadingText: { ...TYPE.body, color: COLORS.textSecondary, marginTop: 16 },
  errorIcon: {
    width: 72, height: 72, borderRadius: 22,
    backgroundColor: COLORS.bg,
    justifyContent: 'center', alignItems: 'center',
    marginBottom: 16,
  },
  errorText: { ...TYPE.body, color: COLORS.textSecondary, textAlign: 'center', marginBottom: 20, lineHeight: 24 },
  retryBtn: {
    backgroundColor: COLORS.accent, borderRadius: RADII.md,
    paddingHorizontal: 28, paddingVertical: 12,
    ...SHADOWS.button,
  },
  retryBtnText: { color: '#fff', fontSize: 16, fontWeight: '600' },
  emptyText: { ...TYPE.body, color: COLORS.textSecondary, textAlign: 'center', lineHeight: 24 },

  // Results
  countRow: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
    paddingHorizontal: 20, paddingTop: 14, paddingBottom: 4,
  },
  countBadge: {
    backgroundColor: COLORS.accentLight, borderRadius: RADII.xs,
    paddingHorizontal: 8, paddingVertical: 3,
  },
  countBadgeText: { ...TYPE.label, color: COLORS.accent, fontSize: 12 },
  resultCount: { ...TYPE.label, color: COLORS.textSecondary },
  list: { paddingHorizontal: 16, paddingBottom: 24 },

  // Card
  card: {
    backgroundColor: COLORS.white, borderRadius: RADII.lg,
    padding: 18, marginTop: 12,
    ...SHADOWS.card,
    borderWidth: 1, borderColor: COLORS.borderLight,
  },
  cardHeader: {
    flexDirection: 'row', alignItems: 'flex-start', marginBottom: 8,
  },
  avatar: {
    width: 40, height: 40, borderRadius: 12,
    backgroundColor: COLORS.accentLight,
    justifyContent: 'center', alignItems: 'center',
    marginRight: 12,
  },
  avatarText: { fontSize: 15, fontWeight: '700', color: COLORS.accent },
  nameWrap: { flex: 1, marginRight: 10 },
  name: { fontSize: 17, fontWeight: '700', color: COLORS.text, letterSpacing: 0.1 },
  specialty: { ...TYPE.caption, color: COLORS.textSecondary, marginTop: 2 },

  // Status pill
  statusPill: {
    flexDirection: 'row', alignItems: 'center', gap: 5,
    backgroundColor: COLORS.successBg,
    borderRadius: RADII.full,
    paddingHorizontal: 10, paddingVertical: 4,
  },
  statusPillClosed: { backgroundColor: COLORS.errorBg },
  statusDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: COLORS.success },
  statusDotClosed: { backgroundColor: COLORS.error },
  statusText: { fontSize: 11, fontWeight: '600', color: COLORS.success },
  statusTextClosed: { color: COLORS.error },

  // Rating
  ratingRow: { flexDirection: 'row', alignItems: 'center', marginBottom: 10, gap: 4 },
  starsRow: { flexDirection: 'row', gap: 1 },
  ratingNum: { fontSize: 14, fontWeight: '700', color: COLORS.text, marginLeft: 4 },
  reviewCount: { ...TYPE.caption, color: COLORS.textTertiary },

  // Info rows
  infoRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 6, marginBottom: 6 },
  address: { fontSize: 14, color: COLORS.text, lineHeight: 20, flex: 1 },
  distanceBadge: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    backgroundColor: COLORS.accentLighter, borderRadius: RADII.xs,
    paddingHorizontal: 8, paddingVertical: 4,
    alignSelf: 'flex-start', marginBottom: 4,
  },
  distanceText: { fontSize: 12, fontWeight: '600', color: COLORS.accent },

  // Call button
  callDocBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8,
    backgroundColor: COLORS.accentLighter, borderRadius: RADII.md,
    paddingVertical: 12, marginTop: 8,
    borderWidth: 1.5, borderColor: COLORS.accentLight,
  },
  callDocText: { fontSize: 15, fontWeight: '600', color: COLORS.accent },
});
