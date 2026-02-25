// ── Color Palette ─────────────────────────────────────────────
export const COLORS = {
  // Backgrounds
  bg: '#F7F5FA',              // warm purple-tinted gray (was flat gray)
  bgGradientTop: '#EDE7F6',   // top of header gradient
  bgGradientBottom: '#F7F5FA', // blends into main bg
  card: '#FFFFFF',
  cardTinted: '#FAFAFD',       // very subtle purple tint for alternating

  // Brand
  accent: '#7B3FBF',
  accentSoft: '#9B6BD4',       // lighter purple for secondary elements
  accentLight: '#F0E8F8',
  accentLighter: '#F8F4FC',    // barely-there purple for card backgrounds
  accentDark: '#5A2D8C',
  accentGlow: 'rgba(123, 63, 191, 0.25)',

  // Category accent colors (for benefit card icon backgrounds)
  careVisit: '#7B3FBF',       // purple - care visits
  careBg: 'rgba(123, 63, 191, 0.08)',
  clinical: '#3D6B99',        // slate blue - clinical
  clinicalBg: 'rgba(61, 107, 153, 0.08)',
  savings: '#3A7D5C',         // sage green - savings
  savingsBg: 'rgba(58, 125, 92, 0.08)',

  // Text
  text: '#1E1B2E',
  textSecondary: '#7A7585',
  textTertiary: '#A49EB0',

  // UI
  border: '#E4E2E8',
  borderLight: '#F0EDF4',
  inputBg: '#EEEDF1',
  white: '#FFFFFF',
  shadow: 'rgba(123, 63, 191, 0.08)',
  overlay: 'rgba(30, 27, 46, 0.5)',

  // Mic
  micRing1: 'rgba(123, 63, 191, 0.15)',
  micRing2: 'rgba(123, 63, 191, 0.08)',
  micRing3: 'rgba(123, 63, 191, 0.04)',

  // Status
  success: '#2E7D32',
  successBg: 'rgba(46, 125, 50, 0.08)',
  error: '#C62828',
  errorBg: 'rgba(198, 40, 40, 0.08)',
  warning: '#F5A623',
  warningBg: 'rgba(245, 166, 35, 0.08)',
};

// ── Spacing ──────────────────────────────────────────────────
export const SPACING = { xs: 4, sm: 8, md: 16, lg: 24, xl: 32, xxl: 48 };

// ── Radii ────────────────────────────────────────────────────
export const RADII = { xs: 6, sm: 10, md: 14, lg: 20, xl: 24, xxl: 32, full: 999 };

// ── Shadow Presets ───────────────────────────────────────────
export const SHADOWS = {
  card: {
    shadowColor: '#7B3FBF',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.06,
    shadowRadius: 8,
    elevation: 2,
  },
  cardLifted: {
    shadowColor: '#7B3FBF',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.10,
    shadowRadius: 12,
    elevation: 4,
  },
  container: {
    shadowColor: '#7B3FBF',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.10,
    shadowRadius: 16,
    elevation: 6,
  },
  modal: {
    shadowColor: '#000000',
    shadowOffset: { width: 0, height: -4 },
    shadowOpacity: 0.15,
    shadowRadius: 24,
    elevation: 12,
  },
  button: {
    shadowColor: '#7B3FBF',
    shadowOffset: { width: 0, height: 3 },
    shadowOpacity: 0.20,
    shadowRadius: 8,
    elevation: 4,
  },
  glow: {
    shadowColor: '#7B3FBF',
    shadowOffset: { width: 0, height: 0 },
    shadowOpacity: 0.35,
    shadowRadius: 20,
    elevation: 8,
  },
  soft: {
    shadowColor: '#7B3FBF',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.04,
    shadowRadius: 4,
    elevation: 1,
  },
};

// ── Typography Scale ─────────────────────────────────────────
export const TYPE = {
  hero:          { fontSize: 34, fontWeight: '700', letterSpacing: -0.5 },
  h1:            { fontSize: 30, fontWeight: '700', letterSpacing: -0.3 },
  h2:            { fontSize: 24, fontWeight: '700', letterSpacing: -0.2 },
  h3:            { fontSize: 19, fontWeight: '700', letterSpacing: 0 },
  body:          { fontSize: 16, fontWeight: '400', letterSpacing: 0.1 },
  bodyMedium:    { fontSize: 15, fontWeight: '500', letterSpacing: 0.1 },
  label:         { fontSize: 13, fontWeight: '600', letterSpacing: 0.3 },
  labelSmall:    { fontSize: 11, fontWeight: '500', letterSpacing: 0.4 },
  caption:       { fontSize: 12, fontWeight: '500', letterSpacing: 0.3 },
  cardValue:     { fontSize: 18, fontWeight: '700', letterSpacing: 0.1 },
  cardLabel:     { fontSize: 11, fontWeight: '600', letterSpacing: 0.3 },
  sectionHeader: { fontSize: 13, fontWeight: '700', letterSpacing: 0.8, textTransform: 'uppercase' },
};

// ── Animation Timing ─────────────────────────────────────────
export const MOTION = {
  fast: 150,
  normal: 250,
  slow: 400,
  staggerDelay: 60,
  springConfig: { tension: 40, friction: 7 },
};

// ── Benefit Icon Map ─────────────────────────────────────────
// Maps label keywords → { family, name, color, bg } for @expo/vector-icons
// 3-tone palette: purple (care visits), slate blue (clinical), sage green (savings)
export const BENEFIT_ICON_MAP = {
  'pcp':          { family: 'MaterialCommunityIcons', name: 'stethoscope',              color: COLORS.careVisit,  bg: COLORS.careBg },
  'primary':      { family: 'MaterialCommunityIcons', name: 'stethoscope',              color: COLORS.careVisit,  bg: COLORS.careBg },
  'doctor':       { family: 'MaterialCommunityIcons', name: 'stethoscope',              color: COLORS.careVisit,  bg: COLORS.careBg },
  'specialist':   { family: 'MaterialCommunityIcons', name: 'account-tie',              color: COLORS.clinical,   bg: COLORS.clinicalBg },
  'emergency':    { family: 'MaterialCommunityIcons', name: 'ambulance',                color: COLORS.careVisit,  bg: COLORS.careBg },
  'er ':          { family: 'MaterialCommunityIcons', name: 'ambulance',                color: COLORS.careVisit,  bg: COLORS.careBg },
  'urgent':       { family: 'MaterialCommunityIcons', name: 'medical-bag',              color: COLORS.careVisit,  bg: COLORS.careBg },
  'dental':       { family: 'MaterialCommunityIcons', name: 'tooth-outline',            color: COLORS.clinical,   bg: COLORS.clinicalBg },
  'vision':       { family: 'Ionicons',               name: 'eye-outline',              color: COLORS.clinical,   bg: COLORS.clinicalBg },
  'eye':          { family: 'Ionicons',               name: 'eye-outline',              color: COLORS.clinical,   bg: COLORS.clinicalBg },
  'hearing':      { family: 'MaterialCommunityIcons', name: 'ear-hearing',              color: COLORS.clinical,   bg: COLORS.clinicalBg },
  'hospital':     { family: 'Ionicons',               name: 'bed-outline',              color: COLORS.careVisit,  bg: COLORS.careBg },
  'inpatient':    { family: 'Ionicons',               name: 'bed-outline',              color: COLORS.careVisit,  bg: COLORS.careBg },
  'mental':       { family: 'MaterialCommunityIcons', name: 'head-heart-outline',       color: COLORS.clinical,   bg: COLORS.clinicalBg },
  'lab':          { family: 'MaterialCommunityIcons', name: 'flask-outline',            color: COLORS.clinical,   bg: COLORS.clinicalBg },
  'x-ray':        { family: 'MaterialCommunityIcons', name: 'flask-outline',            color: COLORS.clinical,   bg: COLORS.clinicalBg },
  'drug':         { family: 'MaterialCommunityIcons', name: 'pill',                     color: COLORS.clinical,   bg: COLORS.clinicalBg },
  'prescription': { family: 'MaterialCommunityIcons', name: 'pill',                     color: COLORS.clinical,   bg: COLORS.clinicalBg },
  'rx':           { family: 'MaterialCommunityIcons', name: 'pill',                     color: COLORS.clinical,   bg: COLORS.clinicalBg },
  'estimated':    { family: 'MaterialCommunityIcons', name: 'pill',                     color: COLORS.clinical,   bg: COLORS.clinicalBg },
  'preventive':   { family: 'Ionicons',               name: 'checkmark-circle-outline', color: COLORS.savings,    bg: COLORS.savingsBg },
  'telehealth':   { family: 'Ionicons',               name: 'videocam-outline',         color: COLORS.clinical,   bg: COLORS.clinicalBg },
  'otc':          { family: 'Ionicons',               name: 'cart-outline',             color: COLORS.savings,    bg: COLORS.savingsBg },
  'flex':         { family: 'Ionicons',               name: 'card-outline',             color: COLORS.savings,    bg: COLORS.savingsBg },
  'part b':       { family: 'Ionicons',               name: 'cash-outline',             color: COLORS.savings,    bg: COLORS.savingsBg },
  'giveback':     { family: 'Ionicons',               name: 'cash-outline',             color: COLORS.savings,    bg: COLORS.savingsBg },
};
export const DEFAULT_ICON = { family: 'Ionicons', name: 'document-text-outline', color: COLORS.careVisit, bg: COLORS.careBg };
