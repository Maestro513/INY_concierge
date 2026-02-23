import { useState, useEffect } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, FlatList,
  ActivityIndicator, Linking,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { COLORS, RADII, SPACING } from '../constants/theme';
import { API_URL } from '../constants/api';

export default function DoctorResults() {
  const { specialty, zipCode, planName } = useLocalSearchParams();
  const router = useRouter();
  const [providers, setProviders] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [meta, setMeta] = useState({});

  useEffect(() => {
    searchProviders();
  }, []);

  const searchProviders = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await fetch(`${API_URL}/providers/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          plan_name: planName,
          specialty: specialty,
          zip_code: zipCode,
          radius_miles: 25,
          limit: 50,
          enrich_google: true,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Search failed');
      }
      setProviders(data.providers || []);
      setMeta({
        total: data.total,
        carrier: data.carrier,
        specialty: data.specialty,
      });
    } catch (err) {
      console.log('Provider search error:', err);
      if (err.message === 'Network request failed' || err.name === 'TypeError') {
        setError("Can't connect to the server right now. Check your connection and try again.");
      } else {
        setError(err.message || 'Something went wrong. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  };

  const callDoctor = (phone) => {
    if (!phone) return;
    const digits = phone.replace(/\D/g, '');
    Linking.openURL(`tel:${digits}`);
  };

  const renderStars = (rating) => {
    if (!rating) return null;
    const full = Math.floor(rating);
    const half = rating - full >= 0.5;
    let stars = '★'.repeat(full);
    if (half) stars += '½';
    return stars;
  };

  const renderProvider = ({ item }) => (
    <View style={s.card}>
      {/* Name + Credentials */}
      <Text style={s.name}>{item.name}</Text>
      <Text style={s.specialty}>{item.specialty}</Text>

      {/* Google Rating */}
      {item.google_rating && (
        <View style={s.ratingRow}>
          <Text style={s.stars}>{renderStars(item.google_rating)}</Text>
          <Text style={s.ratingNum}>{item.google_rating}</Text>
          {item.google_review_count ? (
            <Text style={s.reviewCount}>({item.google_review_count} reviews)</Text>
          ) : null}
        </View>
      )}

      {/* Address */}
      <Text style={s.address}>{item.address}</Text>

      {/* Distance */}
      {item.distance_miles != null && (
        <Text style={s.distance}>📍 {item.distance_miles.toFixed(1)} miles away</Text>
      )}

      {/* Accepting new patients */}
      {item.accepting_new_patients != null && (
        <Text style={[s.accepting, !item.accepting_new_patients && s.notAccepting]}>
          {item.accepting_new_patients ? '✓ Accepting new patients' : '✗ Not accepting new patients'}
        </Text>
      )}

      {/* Phone button */}
      {item.phone ? (
        <TouchableOpacity style={s.callBtn} onPress={() => callDoctor(item.phone)} activeOpacity={0.7}>
          <Text style={s.callText}>📞  {item.phone}</Text>
        </TouchableOpacity>
      ) : null}
    </View>
  );

  return (
    <SafeAreaView style={s.container} edges={['top']}>
      {/* Header */}
      <View style={s.header}>
        <TouchableOpacity onPress={() => router.back()} style={s.backBtn}>
          <Text style={s.backText}>← Back</Text>
        </TouchableOpacity>
        <Text style={s.headerTitle}>
          {meta.specialty || specialty || 'Doctors'} Near You
        </Text>
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
          <Text style={{ fontSize: 48, marginBottom: 12 }}>😔</Text>
          <Text style={s.errorText}>{error}</Text>
          <TouchableOpacity style={s.retryBtn} onPress={searchProviders}>
            <Text style={s.retryBtnText}>Try Again</Text>
          </TouchableOpacity>
        </View>
      )}

      {/* No results */}
      {!loading && !error && providers.length === 0 && (
        <View style={s.center}>
          <Text style={{ fontSize: 48, marginBottom: 12 }}>🔍</Text>
          <Text style={s.emptyText}>
            No {specialty || 'doctors'} found near {zipCode}.{'\n'}
            Try a different specialty or call us at (844) 463-2931.
          </Text>
        </View>
      )}

      {/* Results */}
      {!loading && providers.length > 0 && (
        <>
          <Text style={s.resultCount}>
            {meta.total || providers.length} {meta.specialty || specialty || 'doctor'}
            {(meta.total || providers.length) !== 1 ? 's' : ''} found
          </Text>
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
  header: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: 16, paddingVertical: 12,
    borderBottomWidth: 1, borderBottomColor: COLORS.border,
    backgroundColor: COLORS.white,
  },
  backBtn: { paddingRight: 12 },
  backText: { fontSize: 16, color: COLORS.accent, fontWeight: '600' },
  headerTitle: { fontSize: 18, fontWeight: '700', color: COLORS.text, flex: 1 },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center', padding: 24 },
  loadingText: { fontSize: 16, color: COLORS.textSecondary, marginTop: 16 },
  errorText: { fontSize: 16, color: '#D32F2F', textAlign: 'center', marginBottom: 16, lineHeight: 24 },
  retryBtn: { backgroundColor: COLORS.accent, borderRadius: RADII.md, paddingHorizontal: 28, paddingVertical: 12 },
  retryBtnText: { color: '#fff', fontSize: 16, fontWeight: '600' },
  emptyText: { fontSize: 16, color: COLORS.textSecondary, textAlign: 'center', lineHeight: 24 },
  resultCount: {
    fontSize: 14, fontWeight: '600', color: COLORS.textSecondary,
    paddingHorizontal: 20, paddingTop: 12, paddingBottom: 4,
  },
  list: { paddingHorizontal: 16, paddingBottom: 24 },
  card: {
    backgroundColor: COLORS.white, borderRadius: RADII.md,
    padding: 16, marginTop: 12,
    borderWidth: 1, borderColor: COLORS.border,
  },
  name: { fontSize: 18, fontWeight: '700', color: COLORS.text, marginBottom: 2 },
  specialty: { fontSize: 14, color: COLORS.textSecondary, marginBottom: 8 },
  ratingRow: { flexDirection: 'row', alignItems: 'center', marginBottom: 8 },
  stars: { fontSize: 16, color: '#F5A623', marginRight: 6 },
  ratingNum: { fontSize: 14, fontWeight: '700', color: COLORS.text, marginRight: 4 },
  reviewCount: { fontSize: 13, color: COLORS.textSecondary },
  address: { fontSize: 14, color: COLORS.text, lineHeight: 20, marginBottom: 4 },
  distance: { fontSize: 13, color: COLORS.textSecondary, marginBottom: 6 },
  accepting: { fontSize: 13, color: '#2E7D32', fontWeight: '600', marginBottom: 10 },
  notAccepting: { color: '#C62828' },
  callBtn: {
    backgroundColor: COLORS.accentLight || '#F3E8FF',
    borderRadius: RADII.sm, paddingVertical: 10, alignItems: 'center',
    borderWidth: 1, borderColor: 'rgba(123,63,191,0.2)',
  },
  callText: { fontSize: 15, fontWeight: '600', color: COLORS.accent },
});