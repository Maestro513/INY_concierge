import { View, Text, TouchableOpacity, Modal, ScrollView, StyleSheet, ActivityIndicator, Linking, Platform } from 'react-native';
import { COLORS, RADII, SPACING } from '../constants/theme';
import { API_URL } from '../constants/api';

export default function SOBModal({ visible, onClose, member, sobData, loading, onRetry }) {
  if (!visible) return null;

  const planName = member?.planName || 'Your Plan';
  const planNumber = member?.planNumber || '';
  const isLoading = loading === true;
  const hasData = sobData != null;
  const medical = sobData?.medical || [];
  const drugs = sobData?.drugs || [];
  const isPPO = (sobData?.plan_type || planName || '').toUpperCase().includes('PPO');
  const hasOutOfNetwork = isPPO || medical.some(b => b.out_of_network && b.out_of_network !== b.in_network);

  return (
    <Modal visible={true} transparent animationType="slide" onRequestClose={onClose}>
      <TouchableOpacity style={s.overlay} activeOpacity={1} onPress={onClose}>
        <View style={s.sheet} onStartShouldSetResponder={() => true}>
          {/* Header */}
          <View style={s.header}>
            <Text style={s.title}>Summary of Benefits</Text>
            <TouchableOpacity onPress={onClose} style={s.closeBtn}>
              <Text style={s.closeX}>✕</Text>
            </TouchableOpacity>
          </View>

          <ScrollView style={s.body} contentContainerStyle={s.bodyContent} showsVerticalScrollIndicator={true}>
            {/* Plan info */}
            <View style={s.planInfo}>
              <Text style={s.planName}>{sobData?.plan_name || planName}</Text>
              <Text style={s.planId}>{planNumber}</Text>
            </View>

            {/* Plan snapshot: premium, deductible, MOOP */}
            {!isLoading && hasData && (
              <View style={s.snapshotRow}>
                {sobData.monthly_premium ? (
                  <View style={s.snapshotCard}>
                    <Text style={s.snapValue}>{sobData.monthly_premium}</Text>
                    <Text style={s.snapLabel}>Monthly Premium</Text>
                  </View>
                ) : null}
                {sobData.annual_deductible_in ? (
                  <View style={s.snapshotCard}>
                    <Text style={s.snapValue}>{sobData.annual_deductible_in}</Text>
                    <Text style={s.snapLabel}>Deductible (In)</Text>
                  </View>
                ) : null}
                {sobData.moop_in ? (
                  <View style={s.snapshotCard}>
                    <Text style={s.snapValue}>{sobData.moop_in}</Text>
                    <Text style={s.snapLabel}>Max Out of Pocket</Text>
                  </View>
                ) : null}
              </View>
            )}

            {/* Loading */}
            {isLoading ? (
              <View style={s.center}>
                <ActivityIndicator size="large" color={COLORS.accent} />
                <Text style={s.loadingText}>Loading your benefits...</Text>
              </View>
            ) : !hasData ? (
              <View style={s.center}>
                <Text style={s.errorText}>{"Couldn't load benefits for this plan."}</Text>
                {onRetry ? (
                  <TouchableOpacity style={s.retryBtn} onPress={onRetry}>
                    <Text style={s.retryText}>Try Again</Text>
                  </TouchableOpacity>
                ) : null}
              </View>
            ) : (
              <View>
                {/* Medical Benefits Table */}
                {medical.length > 0 ? (
                  <View style={s.section}>
                    <Text style={s.secTitle}>Medical Benefits</Text>
                    {/* Column headers */}
                    <View style={s.tableHeader}>
                      <Text style={s.thLabel}>Benefit</Text>
                      <Text style={s.thValue}>In-Network</Text>
                      {hasOutOfNetwork ? (
                        <Text style={s.thValue}>Out-of-Network</Text>
                      ) : null}
                    </View>
                    {medical.map((item, i) => (
                      <View key={i} style={s.tableRow}>
                        <Text style={s.tdLabel}>{item.label || ''}</Text>
                        <Text style={s.tdValue}>{item.in_network || item.value || ''}</Text>
                        {hasOutOfNetwork ? (
                          <Text style={[s.tdValue, s.tdOut]}>
                            {item.out_of_network || '—'}
                          </Text>
                        ) : null}
                      </View>
                    ))}
                  </View>
                ) : null}

                {/* Prescription Drugs */}
                {drugs.length > 0 ? (
                  <View style={s.section}>
                    <Text style={s.secTitle}>Prescription Drugs</Text>
                    <View style={s.tableHeader}>
                      <Text style={s.thLabel}>Tier / Phase</Text>
                      <Text style={s.thValue}>You Pay</Text>
                    </View>
                    {drugs.map((item, i) => (
                      <View key={i} style={s.tableRow}>
                        <Text style={s.tdLabel}>{item.label || ''}</Text>
                        <Text style={s.tdValue}>{item.value || item.in_network || ''}</Text>
                      </View>
                    ))}
                  </View>
                ) : null}

                {/* Out-of-network deductible / MOOP footer */}
                {hasOutOfNetwork && (sobData.annual_deductible_out || sobData.moop_out) ? (
                  <View style={s.footer}>
                    {sobData.annual_deductible_out ? (
                      <Text style={s.footerText}>
                        Out-of-Network Deductible: {sobData.annual_deductible_out}
                      </Text>
                    ) : null}
                    {sobData.moop_out ? (
                      <Text style={s.footerText}>
                        Out-of-Network Max Out of Pocket: {sobData.moop_out}
                      </Text>
                    ) : null}
                  </View>
                ) : null}

                {/* Download PDF */}
                <TouchableOpacity
                  style={s.downloadBtn}
                  onPress={() => Linking.openURL(`${API_URL}/sob/pdf/${encodeURIComponent(planNumber)}`)}
                  activeOpacity={0.7}
                >
                  <Text style={s.downloadText}>📄  Download Full SOB (PDF)</Text>
                </TouchableOpacity>
              </View>
            )}
          </ScrollView>
        </View>
      </TouchableOpacity>
    </Modal>
  );
}

const s = StyleSheet.create({
  overlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.4)', justifyContent: 'flex-end' },
  sheet: { backgroundColor: COLORS.white, borderTopLeftRadius: RADII.xl, borderTopRightRadius: RADII.xl, height: '85%' },
  header: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    paddingHorizontal: 20, paddingTop: 20, paddingBottom: 12,
    borderBottomWidth: 1, borderBottomColor: COLORS.border,
  },
  title: { fontSize: 19, fontWeight: '700', color: COLORS.text },
  closeBtn: { width: 32, height: 32, borderRadius: 16, backgroundColor: COLORS.border, justifyContent: 'center', alignItems: 'center' },
  closeX: { fontSize: 16, color: COLORS.textSecondary },
  body: { flex: 1 },
  bodyContent: { paddingBottom: 80 },

  // Plan info
  planInfo: { alignItems: 'center', paddingVertical: 16, paddingHorizontal: 20 },
  planName: { fontSize: 16, fontWeight: '700', color: COLORS.text, textAlign: 'center' },
  planId: { fontSize: 13, color: COLORS.textSecondary, marginTop: 2 },

  // Snapshot cards (premium, deductible, MOOP)
  snapshotRow: { flexDirection: 'row', paddingHorizontal: 16, marginBottom: 16, gap: 8 },
  snapshotCard: {
    flex: 1, backgroundColor: COLORS.bg, borderRadius: RADII.sm,
    paddingVertical: 10, paddingHorizontal: 8, alignItems: 'center',
    borderWidth: 1, borderColor: COLORS.border,
  },
  snapValue: { fontSize: 15, fontWeight: '700', color: COLORS.accent },
  snapLabel: { fontSize: 10, color: COLORS.textSecondary, marginTop: 2, textAlign: 'center' },

  // Loading / error
  center: { alignItems: 'center', paddingVertical: 30 },
  loadingText: { fontSize: 15, color: COLORS.textSecondary, marginTop: 12 },
  errorText: { fontSize: 15, color: '#D32F2F', textAlign: 'center', marginBottom: 12 },
  retryBtn: { backgroundColor: COLORS.accent, borderRadius: RADII.sm, paddingHorizontal: 24, paddingVertical: 10 },
  retryText: { color: '#fff', fontSize: 15, fontWeight: '600' },

  // Section
  section: { marginBottom: 20, paddingHorizontal: 16 },
  secTitle: {
    fontSize: 14, fontWeight: '700', color: COLORS.accent,
    textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 8, marginTop: 4,
  },

  // Table header
  tableHeader: {
    flexDirection: 'row', paddingVertical: 8, paddingHorizontal: 4,
    backgroundColor: COLORS.bg, borderRadius: 4, marginBottom: 2,
  },
  thLabel: { flex: 2, fontSize: 11, fontWeight: '700', color: COLORS.textSecondary, textTransform: 'uppercase' },
  thValue: { flex: 1.5, fontSize: 11, fontWeight: '700', color: COLORS.textSecondary, textTransform: 'uppercase', textAlign: 'right' },

  // Table rows
  tableRow: {
    flexDirection: 'row', paddingVertical: 10, paddingHorizontal: 4,
    borderBottomWidth: 1, borderBottomColor: COLORS.border,
    alignItems: 'flex-start',
  },
  tdLabel: { flex: 2, fontSize: 14, color: COLORS.text },
  tdValue: { flex: 1.5, fontSize: 13, fontWeight: '600', color: COLORS.text, textAlign: 'right' },
  tdOut: { color: COLORS.textSecondary },

  // Footer
  footer: { paddingHorizontal: 20, paddingTop: 8, paddingBottom: 16 },
  footerText: { fontSize: 12, color: COLORS.textSecondary, marginBottom: 4 },

  // Download
  downloadBtn: {
    marginHorizontal: 16, marginTop: 12, marginBottom: 8,
    backgroundColor: COLORS.accentLight || '#F3E8FF', borderRadius: RADII.sm,
    paddingVertical: 14, alignItems: 'center',
    borderWidth: 1, borderColor: 'rgba(123,63,191,0.2)',
  },
  downloadText: { fontSize: 15, fontWeight: '600', color: COLORS.accent },
});