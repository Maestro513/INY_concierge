import { useState } from 'react';
import {
  View,
  Text,
  Pressable,
  TouchableOpacity,
  Modal,
  ScrollView,
  StyleSheet,
  ActivityIndicator,
  Alert,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { COLORS, RADII, SHADOWS, TYPE } from '../constants/theme';
import { API_URL, getAccessToken } from '../constants/api';
import * as FileSystem from 'expo-file-system/legacy';
import * as Sharing from 'expo-sharing';

export default function SOBModal({ visible, onClose, member, sobData, loading, onRetry }) {
  const [downloading, setDownloading] = useState(false);

  if (!visible) return null;

  const planName = member?.planName || 'Your Plan';
  const planNumber = member?.planNumber || '';
  const isLoading = loading === true;
  const hasData = sobData != null;
  const medical = sobData?.medical || [];
  const drugs = sobData?.drugs || [];
  const isPPO = (sobData?.plan_type || planName || '').toUpperCase().includes('PPO');
  const hasOutOfNetwork =
    isPPO || medical.some((b) => b.out_of_network && b.out_of_network !== b.in_network);

  const handleDownload = async () => {
    if (!planNumber || downloading) return;
    setDownloading(true);
    const url = `${API_URL}/sob/pdf/${encodeURIComponent(planNumber)}`;
    const fileName = `SOB_${planNumber.replace(/[^a-zA-Z0-9-]/g, '')}.pdf`;
    try {
      const token = getAccessToken();
      const fileUri = FileSystem.cacheDirectory + fileName;
      const download = await FileSystem.downloadAsync(url, fileUri, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (download.status !== 200) {
        Alert.alert('Not Available', 'Summary of Benefits PDF is not available for this plan.');
        return;
      }
      const base64 = await FileSystem.readAsStringAsync(fileUri, {
        encoding: FileSystem.EncodingType.Base64,
      });

      // Show options: Save to device or Share
      Alert.alert('PDF Ready', 'Summary of Benefits downloaded.', [
        {
          text: 'Save to Device',
          onPress: async () => {
            try {
              const perms =
                await FileSystem.StorageAccessFramework.requestDirectoryPermissionsAsync();
              if (perms.granted) {
                const safUri = await FileSystem.StorageAccessFramework.createFileAsync(
                  perms.directoryUri,
                  fileName,
                  'application/pdf',
                );
                await FileSystem.writeAsStringAsync(safUri, base64, {
                  encoding: FileSystem.EncodingType.Base64,
                });
                Alert.alert('Saved', 'PDF saved successfully.');
              }
            } catch {
              Alert.alert('Error', 'Could not save to device.');
            }
          },
        },
        {
          text: 'Share',
          onPress: () =>
            Sharing.shareAsync(fileUri, {
              mimeType: 'application/pdf',
              dialogTitle: 'Summary of Benefits',
            }),
        },
        { text: 'Cancel', style: 'cancel' },
      ]);
    } catch (err) {
      if (__DEV__) console.log('SOB download error:', err);
      Alert.alert('Error', 'Could not download the document. Please try again.');
    } finally {
      setDownloading(false);
    }
  };

  return (
    <Modal visible={true} transparent animationType="slide" onRequestClose={onClose}>
      <View style={s.overlay}>
        <Pressable
          style={s.backdrop}
          onPress={onClose}
          accessibilityRole="button"
          accessibilityLabel="Close benefits sheet"
        />
        <View style={s.sheet}>
          {/* Drag handle */}
          <View style={s.handleWrap}>
            <View style={s.handle} />
          </View>

          {/* Header */}
          <View style={s.header}>
            <View style={s.headerLeft}>
              <View style={s.headerIcon}>
                <Ionicons name="document-text" size={16} color={COLORS.accent} />
              </View>
              <Text style={s.title}>Summary of Benefits</Text>
            </View>
            <View style={s.headerRight}>
              {hasData && !isLoading ? (
                <TouchableOpacity
                  onPress={handleDownload}
                  style={s.downloadBtn}
                  activeOpacity={0.7}
                  accessibilityRole="button"
                  accessibilityLabel="Download benefits PDF"
                >
                  <Ionicons name="download-outline" size={14} color="#fff" />
                  <Text style={s.downloadText}>PDF</Text>
                </TouchableOpacity>
              ) : null}
              <TouchableOpacity
                onPress={onClose}
                style={s.closeBtn}
                activeOpacity={0.7}
                accessibilityRole="button"
                accessibilityLabel="Close"
              >
                <Ionicons name="close" size={18} color={COLORS.textSecondary} />
              </TouchableOpacity>
            </View>
          </View>

          <ScrollView
            style={s.body}
            contentContainerStyle={s.bodyContent}
            showsVerticalScrollIndicator={true}
            nestedScrollEnabled={true}
          >
            {/* Plan info */}
            <View style={s.planInfo}>
              <Text style={s.planName}>{sobData?.plan_name || planName}</Text>
              <Text style={s.planId}>{planNumber}</Text>
            </View>

            {/* Plan snapshot: premium, deductible, MOOP */}
            {!isLoading && hasData && (
              <View style={s.snapshotRow}>
                {sobData.monthly_premium ? (
                  <View style={[s.snapshotCard, { backgroundColor: COLORS.accentLighter }]}>
                    <View
                      style={[s.snapIconCircle, { backgroundColor: 'rgba(123, 63, 191, 0.12)' }]}
                    >
                      <Ionicons name="wallet-outline" size={16} color={COLORS.accent} />
                    </View>
                    <Text style={[s.snapValue, { color: COLORS.accent }]}>
                      {sobData.monthly_premium}
                    </Text>
                    <Text style={s.snapLabel}>Premium</Text>
                  </View>
                ) : null}
                {sobData.annual_deductible_in ? (
                  <View style={[s.snapshotCard, { backgroundColor: COLORS.clinicalBg }]}>
                    <View
                      style={[s.snapIconCircle, { backgroundColor: 'rgba(61, 107, 153, 0.12)' }]}
                    >
                      <Ionicons name="shield-outline" size={16} color={COLORS.clinical} />
                    </View>
                    <Text style={[s.snapValue, { color: COLORS.clinical }]}>
                      {sobData.annual_deductible_in}
                    </Text>
                    <Text style={s.snapLabel}>Deductible</Text>
                  </View>
                ) : null}
                {sobData.moop_in ? (
                  <View style={[s.snapshotCard, { backgroundColor: COLORS.savingsBg }]}>
                    <View
                      style={[s.snapIconCircle, { backgroundColor: 'rgba(58, 125, 92, 0.12)' }]}
                    >
                      <Ionicons name="trending-down-outline" size={16} color={COLORS.savings} />
                    </View>
                    <Text style={[s.snapValue, { color: COLORS.savings }]}>{sobData.moop_in}</Text>
                    <Text style={s.snapLabel}>MOOP</Text>
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
                <Ionicons
                  name="cloud-offline-outline"
                  size={40}
                  color={COLORS.textTertiary}
                  style={{ marginBottom: 12 }}
                />
                <Text style={s.errorText}>{"Couldn't load benefits for this plan."}</Text>
                {onRetry ? (
                  <TouchableOpacity
                    style={s.retryBtn}
                    onPress={onRetry}
                    activeOpacity={0.7}
                    accessibilityRole="button"
                    accessibilityLabel="Retry loading benefits"
                  >
                    <Text style={s.retryText}>Try Again</Text>
                  </TouchableOpacity>
                ) : null}
              </View>
            ) : (
              <View>
                {/* Medical Benefits Table */}
                {medical.length > 0 ? (
                  <View style={s.section}>
                    <View style={s.secTitleRow}>
                      <Ionicons name="medkit-outline" size={14} color={COLORS.accent} />
                      <Text style={s.secTitle}>Medical Benefits</Text>
                    </View>
                    <View style={s.tableCard}>
                      <View style={s.tableHeader}>
                        <Text style={s.thLabel}>Benefit</Text>
                        <Text style={s.thValue}>In-Network</Text>
                        {hasOutOfNetwork ? <Text style={s.thValue}>Out-of-Network</Text> : null}
                      </View>
                      {medical.map((item, i) => (
                        <View key={i} style={[s.tableRow, i % 2 === 0 && s.tableRowAlt]}>
                          <Text style={s.tdLabel}>{item.label || ''}</Text>
                          <Text style={s.tdValue}>{item.in_network || item.value || ''}</Text>
                          {hasOutOfNetwork ? (
                            <Text style={[s.tdValue, s.tdOut]}>
                              {item.out_of_network || '\u2014'}
                            </Text>
                          ) : null}
                        </View>
                      ))}
                    </View>
                  </View>
                ) : null}

                {/* Divider between sections */}
                {medical.length > 0 && drugs.length > 0 ? <View style={s.sectionDivider} /> : null}

                {/* Prescription Drugs */}
                {drugs.length > 0 ? (
                  <View style={s.section}>
                    <View style={s.secTitleRow}>
                      <Ionicons name="medical-outline" size={14} color={COLORS.clinical} />
                      <Text style={[s.secTitle, { color: COLORS.clinical }]}>
                        Prescription Drugs
                      </Text>
                    </View>
                    <View style={s.tableCard}>
                      <View style={s.tableHeader}>
                        <Text style={s.thLabel}>Tier / Phase</Text>
                        <Text style={s.thValue}>You Pay</Text>
                      </View>
                      {drugs.map((item, i) => (
                        <View key={i} style={[s.tableRow, i % 2 === 0 && s.tableRowAlt]}>
                          <Text style={s.tdLabel}>{item.label || ''}</Text>
                          <Text style={s.tdValue}>{item.value || item.in_network || ''}</Text>
                        </View>
                      ))}
                    </View>
                  </View>
                ) : null}

                {/* Out-of-network footer */}
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
                  style={s.downloadBtnLarge}
                  onPress={handleDownload}
                  activeOpacity={0.7}
                  accessibilityRole="button"
                  accessibilityLabel="Download full summary of benefits PDF"
                >
                  <Ionicons name="document-text-outline" size={16} color={COLORS.accent} />
                  <Text style={s.downloadTextLarge}>Download Full SOB (PDF)</Text>
                </TouchableOpacity>
              </View>
            )}

            <View style={{ height: 40 }} />
          </ScrollView>
        </View>
      </View>
    </Modal>
  );
}

const s = StyleSheet.create({
  overlay: { flex: 1, backgroundColor: COLORS.overlay, justifyContent: 'flex-end' },
  backdrop: { flex: 1 },
  sheet: {
    backgroundColor: COLORS.white,
    borderTopLeftRadius: RADII.xxl,
    borderTopRightRadius: RADII.xxl,
    height: '85%',
    ...SHADOWS.modal,
  },

  // Handle
  handleWrap: { alignItems: 'center', paddingTop: 10, paddingBottom: 4 },
  handle: { width: 36, height: 4, borderRadius: 2, backgroundColor: COLORS.border },

  // Header
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingTop: 8,
    paddingBottom: 14,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.borderLight,
  },
  headerLeft: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  headerIcon: {
    width: 30,
    height: 30,
    borderRadius: 10,
    backgroundColor: COLORS.accentLight,
    justifyContent: 'center',
    alignItems: 'center',
  },
  headerRight: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  title: { ...TYPE.h3, color: COLORS.text },
  downloadBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    backgroundColor: COLORS.accent,
    borderRadius: RADII.full,
    paddingHorizontal: 14,
    paddingVertical: 7,
    ...SHADOWS.button,
  },
  downloadText: { color: '#fff', fontSize: 13, fontWeight: '600' },
  closeBtn: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: COLORS.bg,
    justifyContent: 'center',
    alignItems: 'center',
  },
  body: { flex: 1 },
  bodyContent: { paddingBottom: 80 },

  // Plan info
  planInfo: { alignItems: 'center', paddingVertical: 16, paddingHorizontal: 20 },
  planName: {
    fontSize: 16,
    fontWeight: '700',
    color: COLORS.text,
    textAlign: 'center',
    letterSpacing: 0.1,
  },
  planId: { ...TYPE.caption, color: COLORS.textTertiary, marginTop: 2 },

  // Snapshot cards
  snapshotRow: { flexDirection: 'row', paddingHorizontal: 16, marginBottom: 20, gap: 8 },
  snapshotCard: {
    flex: 1,
    borderRadius: RADII.md,
    paddingVertical: 14,
    paddingHorizontal: 8,
    alignItems: 'center',
    gap: 4,
  },
  snapIconCircle: {
    width: 32,
    height: 32,
    borderRadius: 10,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 2,
  },
  snapValue: { ...TYPE.cardValue, fontSize: 20 },
  snapLabel: { ...TYPE.cardLabel, color: COLORS.textSecondary, marginTop: 2, textAlign: 'center' },

  // Loading / error
  center: { alignItems: 'center', paddingVertical: 30 },
  loadingText: { fontSize: 15, color: COLORS.textSecondary, marginTop: 12 },
  errorText: { fontSize: 15, color: COLORS.textSecondary, textAlign: 'center', marginBottom: 12 },
  retryBtn: {
    backgroundColor: COLORS.accent,
    borderRadius: RADII.md,
    paddingHorizontal: 24,
    paddingVertical: 10,
    ...SHADOWS.button,
  },
  retryText: { color: '#fff', fontSize: 15, fontWeight: '600' },

  // Section divider
  sectionDivider: {
    height: 1,
    backgroundColor: COLORS.borderLight,
    marginHorizontal: 24,
    marginBottom: 8,
  },

  // Section
  section: { marginBottom: 20, paddingHorizontal: 16 },
  secTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginBottom: 10,
    marginTop: 4,
  },
  secTitle: { ...TYPE.sectionHeader, color: COLORS.accent },

  // Table card
  tableCard: {
    backgroundColor: COLORS.white,
    borderRadius: RADII.md,
    borderWidth: 1,
    borderColor: COLORS.borderLight,
    overflow: 'hidden',
  },
  tableHeader: {
    flexDirection: 'row',
    paddingVertical: 10,
    paddingHorizontal: 12,
    backgroundColor: COLORS.bg,
  },
  thLabel: {
    flex: 2,
    fontSize: 11,
    fontWeight: '700',
    color: COLORS.textSecondary,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  thValue: {
    flex: 1.5,
    fontSize: 11,
    fontWeight: '700',
    color: COLORS.textSecondary,
    textTransform: 'uppercase',
    textAlign: 'right',
    letterSpacing: 0.5,
  },

  // Table rows
  tableRow: {
    flexDirection: 'row',
    paddingVertical: 12,
    paddingHorizontal: 12,
    alignItems: 'flex-start',
  },
  tableRowAlt: { backgroundColor: COLORS.cardTinted },
  tdLabel: { flex: 2, fontSize: 14, color: COLORS.text, lineHeight: 20 },
  tdValue: { flex: 1.5, fontSize: 13, fontWeight: '600', color: COLORS.text, textAlign: 'right' },
  tdOut: { color: COLORS.textSecondary },

  // Footer
  footer: {
    paddingHorizontal: 20,
    paddingTop: 8,
    paddingBottom: 16,
    backgroundColor: COLORS.bg,
    borderRadius: RADII.sm,
    marginHorizontal: 16,
  },
  footerText: { fontSize: 12, color: COLORS.textSecondary, marginBottom: 4 },

  // Download (large, inside scroll)
  downloadBtnLarge: {
    marginHorizontal: 16,
    marginTop: 12,
    marginBottom: 8,
    backgroundColor: COLORS.accentLighter,
    borderRadius: RADII.md,
    paddingVertical: 14,
    alignItems: 'center',
    flexDirection: 'row',
    justifyContent: 'center',
    gap: 8,
    borderWidth: 1,
    borderColor: COLORS.accentLight,
  },
  downloadTextLarge: { fontSize: 15, fontWeight: '600', color: COLORS.accent },
});
