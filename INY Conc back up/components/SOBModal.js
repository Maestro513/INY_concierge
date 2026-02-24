import { View, Text, TouchableOpacity, Modal, ScrollView, StyleSheet } from 'react-native';
import { COLORS, RADII, SPACING } from '../constants/theme';
import { SAMPLE_MEMBER, SAMPLE_SOB } from '../constants/data';

export default function SOBModal({ visible, onClose }) {
  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <TouchableOpacity style={s.overlay} activeOpacity={1} onPress={onClose}>
        <View style={s.sheet} onStartShouldSetResponder={() => true}>
          <View style={s.header}>
            <Text style={s.title}>Summary of Benefits</Text>
            <TouchableOpacity onPress={onClose} style={s.closeBtn}><Text style={s.closeX}>✕</Text></TouchableOpacity>
          </View>
          <ScrollView style={s.body} showsVerticalScrollIndicator={false}>
            <View style={s.preview}>
              <Text style={{ fontSize: 48, marginBottom: SPACING.sm }}>📄</Text>
              <Text style={s.docTitle}>2026 Summary of Benefits</Text>
              <Text style={s.docSub}>{SAMPLE_MEMBER.planName} — {SAMPLE_MEMBER.planId}</Text>
              <TouchableOpacity style={s.dlBtn}><Text style={s.dlText}>⬇ Download PDF</Text></TouchableOpacity>
            </View>
            <Section title="Medical Benefits" items={SAMPLE_SOB.medical} />
            <Section title="Prescription Drugs" items={SAMPLE_SOB.drugs} />
          </ScrollView>
        </View>
      </TouchableOpacity>
    </Modal>
  );
}

function Section({ title, items }) {
  return (
    <View style={{ marginBottom: SPACING.md }}>
      <Text style={s.secTitle}>{title}</Text>
      {items.map((item, i) => (
        <View key={i} style={s.row}>
          <Text style={s.rowLabel}>{item.label}</Text>
          <Text style={s.rowVal}>{item.value}</Text>
        </View>
      ))}
    </View>
  );
}

const s = StyleSheet.create({
  overlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.4)', justifyContent: 'flex-end' },
  sheet: { backgroundColor: COLORS.white, borderTopLeftRadius: RADII.xl, borderTopRightRadius: RADII.xl, maxHeight: '80%' },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 20, paddingTop: 20, paddingBottom: 12, borderBottomWidth: 1, borderBottomColor: COLORS.border },
  title: { fontSize: 19, fontWeight: '700', color: COLORS.text },
  closeBtn: { width: 32, height: 32, borderRadius: 16, backgroundColor: COLORS.inputBg, justifyContent: 'center', alignItems: 'center' },
  closeX: { fontSize: 16, color: COLORS.textSecondary },
  body: { paddingHorizontal: 20, paddingBottom: 32 },
  preview: { alignItems: 'center', paddingVertical: 20, marginBottom: SPACING.md },
  docTitle: { fontSize: 17, fontWeight: '600', color: COLORS.text, marginBottom: 4 },
  docSub: { fontSize: 13, color: COLORS.textSecondary, marginBottom: SPACING.md },
  dlBtn: { backgroundColor: COLORS.accentLight, borderRadius: RADII.sm, paddingHorizontal: 24, paddingVertical: 10, borderWidth: 1, borderColor: 'rgba(123,63,191,0.2)' },
  dlText: { fontSize: 15, fontWeight: '600', color: COLORS.accent },
  secTitle: { fontSize: 14, fontWeight: '700', color: COLORS.textSecondary, textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 10 },
  row: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: COLORS.border },
  rowLabel: { fontSize: 15, color: COLORS.text, flex: 1 },
  rowVal: { fontSize: 15, fontWeight: '600', color: COLORS.accent },
});
