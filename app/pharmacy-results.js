import { useState, useEffect } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, FlatList,
  ActivityIndicator, Linking, Platform,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, RADII, SPACING, SHADOWS, TYPE } from '../constants/theme';
import { API_URL, authFetch } from '../constants/api';

export default function PharmacyResults() {
  const { zipCode, planNumber, planName } = useLocalSearchParams();
  const router = useRouter();
  const [pharmacies, setPharmacies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [meta, setMeta] = useState({});

  useEffect(() => { searchPharmacies(); }, []);

  const searchPharmacies = async () => {
    setLoading(true); setError('');
    try {
      const res = await authFetch(`${API_URL}/pharmacies/search`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          plan_number: planNumber || '',
          zip_code: zipCode || '',
          radius_miles: 10,
          limit: 30,
        }),
      }, 30000);
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Search failed');
      setPharmacies(data.pharmacies || []);
      setMeta({ total: data.total, has_network_data: data.has_network_data });
    } catch (err) {
      console.log('Pharmacy search error:', err);
      if (err.name === 'AbortError') {
        setError('Search is taking too long. Check your connection and try again.');
      } else if (err.message === 'Network request failed' || err.name === 'TypeError') {
        setError("Can't connect to the server right now. Check your connection and try again.");
      } else { setError(err.message || 'Something went wrong. Please try again.'); }
    } finally { setLoading(false); }
  };

  const callPharmacy = (phone) => {
    if (!phone) return;
    Linking.openURL(`tel:${phone.replace(/\D/g, '')}`);
  };

  const getDirections = (pharmacy) => {
    const { lat, lng, name, address } = pharmacy;
    let url;
    if (lat && lng) {
      url = Platform.select({
        ios: `maps://app?daddr=${lat},${lng}&q=${encodeURIComponent(name)}`,
        android: `google.navigation:q=${lat},${lng}`,
        default: `https://www.google.com/maps/dir/?api=1&destination=${lat},${lng}&destination_place_id=${pharmacy.place_id || ''}`,
      });
    } else {
      const query = encodeURIComponent(`${name} ${address}`);
      url = `https://www.google.com/maps/search/?api=1&query=${query}`;
    }
    Linking.openURL(url);
  };

  const renderStars = (rating) => {
    if (!rating) return null;
    const full = Math.floor(rating);
    const half = rating - full >= 0.5;
    const stars = [];
    for (let i = 0; i < full; i++) stars.push(<Ionicons key={'f'+i} name="star" size={13} color={COLORS.warning} />);
    if (half) stars.push(<Ionicons key="h" name="star-half" size={13} color={COLORS.warning} />);
    return stars;
  };

  const renderPharmacy = ({ item }) => (
    <View style={s.card}>
      <View style={s.cardHeader}>
        {/* Pharmacy icon */}
        <View style={[s.avatar, item.preferred && s.avatarPreferred]}>
          <Ionicons
            name="storefront"
            size={20}
            color={item.preferred ? '#fff' : COLORS.accent}
          />
        </View>
        <View style={s.nameWrap}>
          <Text style={s.name} numberOfLines={2}>{item.name}</Text>
          {item.open_now != null && (
            <Text style={[s.openStatus, item.open_now ? s.openNow : s.closedNow]}>
              {item.open_now ? 'Open now' : 'Closed'}
            </Text>
          )}
        </View>
        {/* Badge: Preferred or In-Network (all results are in-network) */}
        {item.preferred ? (
          <View style={s.preferredBadge}>
            <Ionicons name="star" size={10} color="#fff" />
            <Text style={s.preferredText}>Preferred</Text>
          </View>
        ) : (
          <View style={s.networkBadge}>
            <Ionicons name="checkmark-circle" size={11} color={COLORS.success} />
            <Text style={s.networkText}>In-Network</Text>
          </View>
        )}
      </View>

      {/* Google Rating */}
      {item.google_rating ? (
        <View style={s.ratingRow}>
          <View style={s.starsRow}>{renderStars(item.google_rating)}</View>
          <Text style={s.ratingNum}>{item.google_rating}</Text>
          {item.google_review_count ? (
            <Text style={s.reviewCount}>({item.google_review_count})</Text>
          ) : null}
        </View>
      ) : null}

      {/* Address */}
      <View style={s.infoRow}>
        <Ionicons name="location-outline" size={15} color={COLORS.textSecondary} />
        <Text style={s.address}>{item.address}</Text>
      </View>

      {/* Distance */}
      {item.distance_miles != null && (
        <View style={s.distanceBadge}>
          <Ionicons name="navigate-outline" size={12} color={COLORS.accent} />
          <Text style={s.distanceText}>{item.distance_miles.toFixed(1)} mi</Text>
        </View>
      )}

      {/* Action buttons */}
      <View style={s.actionsRow}>
        <TouchableOpacity
          style={s.directionsBtn}
          onPress={() => getDirections(item)}
          activeOpacity={0.7}
          accessibilityRole="button"
          accessibilityLabel={`Get directions to ${item.name}`}
        >
          <Ionicons name="navigate" size={15} color={COLORS.accent} />
          <Text style={s.directionsBtnText}>Directions</Text>
        </TouchableOpacity>

        {item.phone ? (
          <TouchableOpacity
            style={s.callBtn}
            onPress={() => callPharmacy(item.phone)}
            activeOpacity={0.7}
            accessibilityRole="button"
            accessibilityLabel={`Call ${item.name}`}
          >
            <Ionicons name="call" size={15} color={COLORS.accent} />
            <Text style={s.callBtnText}>Call</Text>
          </TouchableOpacity>
        ) : null}
      </View>
    </View>
  );

  return (
    <SafeAreaView style={s.container} edges={['top']}>
      {/* Header */}
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} style={s.backBtn} activeOpacity={0.7} accessibilityRole="button" accessibilityLabel="Go back">
          <Ionicons name="chevron-back" size={22} color={COLORS.accent} />
        </TouchableOpacity>
        <View style={s.headerCenter}>
          <Text style={s.headerTitle}>Pharmacies</Text>
          <Text style={s.headerSub}>Near {zipCode || ''}</Text>
        </View>
        <View style={{ width: 36 }} />
      </View>

      {/* Loading */}
      {loading && (
        <View style={s.center}>
          <ActivityIndicator size="large" color={COLORS.accent} />
          <Text style={s.loadingText}>Searching for pharmacies...</Text>
        </View>
      )}

      {/* Error */}
      {error !== '' && !loading && (
        <View style={s.center}>
          <View style={s.errorIcon}>
            <Ionicons name="cloud-offline-outline" size={36} color={COLORS.textTertiary} />
          </View>
          <Text style={s.errorText}>{error}</Text>
          <TouchableOpacity style={s.retryBtn} onPress={searchPharmacies} activeOpacity={0.7} accessibilityRole="button" accessibilityLabel="Try search again">
            <Text style={s.retryBtnText}>Try Again</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* No results */}
      {!loading && !error && pharmacies.length === 0 && (
        <View style={s.center}>
          <View style={s.errorIcon}>
            <Ionicons name="search-outline" size={36} color={COLORS.textTertiary} />
          </View>
          <Text style={s.emptyText}>
            No pharmacies found near {zipCode || ''}.{'\n'}
            Try a different zip code or call us at (844) 463-2931.
          </Text>
        </View>
      )}

      {/* Results */}
      {!loading && pharmacies.length > 0 && (
        <>
          <View style={s.countRow}>
            <View style={s.countBadge}>
              <Text style={s.countBadgeText}>{meta.total || pharmacies.length}</Text>
            </View>
            <Text style={s.resultCount}>
              pharmac{(meta.total || pharmacies.length) !== 1 ? 'ies' : 'y'} found
            </Text>
          </View>
          <FlatList
            data={pharmacies}
            keyExtractor={(item, i) => item.place_id || `${item.name}-${i}`}
            renderItem={renderPharmacy}
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

  // Avatar
  avatar: {
    width: 42, height: 42, borderRadius: 12,
    backgroundColor: COLORS.accentLight,
    justifyContent: 'center', alignItems: 'center',
    marginRight: 12,
  },
  avatarPreferred: {
    backgroundColor: COLORS.accent,
  },
  nameWrap: { flex: 1, marginRight: 10 },
  name: { fontSize: 16, fontWeight: '700', color: COLORS.text, letterSpacing: 0.1 },
  openStatus: { fontSize: 12, fontWeight: '600', marginTop: 2 },
  openNow: { color: COLORS.success },
  closedNow: { color: COLORS.textTertiary },

  // Badges
  preferredBadge: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    backgroundColor: COLORS.accent,
    borderRadius: RADII.full,
    paddingHorizontal: 10, paddingVertical: 4,
  },
  preferredText: { fontSize: 11, fontWeight: '700', color: '#fff' },
  networkBadge: {
    flexDirection: 'row', alignItems: 'center', gap: 4,
    backgroundColor: COLORS.successBg,
    borderRadius: RADII.full,
    paddingHorizontal: 10, paddingVertical: 4,
  },
  networkText: { fontSize: 11, fontWeight: '600', color: COLORS.success },

  // Rating
  ratingRow: { flexDirection: 'row', alignItems: 'center', marginBottom: 8, gap: 4 },
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

  // Action buttons
  actionsRow: {
    flexDirection: 'row', gap: 10, marginTop: 10,
  },
  directionsBtn: {
    flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6,
    backgroundColor: COLORS.accentLighter, borderRadius: RADII.md,
    paddingVertical: 11,
    borderWidth: 1.5, borderColor: COLORS.accentLight,
  },
  directionsBtnText: { fontSize: 14, fontWeight: '600', color: COLORS.accent },
  callBtn: {
    flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6,
    backgroundColor: COLORS.accentLighter, borderRadius: RADII.md,
    paddingVertical: 11,
    borderWidth: 1.5, borderColor: COLORS.accentLight,
  },
  callBtnText: { fontSize: 14, fontWeight: '600', color: COLORS.accent },
});
