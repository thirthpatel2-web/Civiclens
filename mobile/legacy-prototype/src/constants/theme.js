// CivicLens - Design System
//
// DESIGN DIRECTION ("Rajmudra" — official seal):
// The previous palette was Tailwind's default blue-600 on slate — the same
// colors any generic admin dashboard ships with, with no connection to
// what this product actually is. CivicLens sits between a citizen and the
// machinery of Indian civic administration and law, so the palette is
// drawn from that world instead: the deep indigo of an official seal and
// judicial robes, the warm sandstone/terracotta of government sandstone
// buildings (secretariats, courts), and the ochre of turmeric/saffron used
// in official ceremony — rather than a generic SaaS blue-and-slate kit.
//
// Typography: Fraunces (an editorial serif with real character) carries
// headlines and hero moments — the kind of weight you'd expect on a
// statute or a formal notice. Manrope carries all UI/body text — clean
// and legible at small sizes on a phone screen. See App.js for how these
// are loaded and applied as the app-wide default.

export const FONT_FAMILY = {
  display: 'Fraunces_600SemiBold',
  displayBold: 'Fraunces_700Bold',
  displayItalic: 'Fraunces_600SemiBold_Italic',
  body: 'Manrope_400Regular',
  bodyMedium: 'Manrope_500Medium',
  bodySemiBold: 'Manrope_600SemiBold',
  bodyBold: 'Manrope_700Bold',
  bodyExtraBold: 'Manrope_800ExtraBold',
};

export const DARK_THEME = {
  mode: 'dark',
  background: '#0B0E1A',        // indigo-charcoal, not generic slate
  surface: '#12162A',
  surfaceElevated: '#1B2140',
  card: '#151A32',
  cardBorder: '#262E52',
  border: '#1E2542',
  borderLight: '#3A4470',

  // Brand & Institutional Colors
  primary: '#3547A8',           // Seal Indigo
  primaryLight: '#5568D6',
  primaryDark: '#232F73',
  primaryGlow: 'rgba(53, 71, 168, 0.28)',

  accent: '#2E9E8F',            // Verdigris (copper-seal patina) — links/info
  accentSaffron: '#BF6B3D',     // Sandstone Terracotta — "official" badges
  accentEmerald: '#2E9E63',     // Resolution Green (deeper, less generic)
  accentRose: '#B0435C',        // Seal Red — alerts, urgent
  accentAmber: '#BE8A2E',       // Turmeric Ochre — pending
  accentPurple: '#7A5FB0',      // Legal Plum — judiciary/legal content

  // Text Colors — warm off-whites (ledger paper), not clinical slate-white
  text: '#F2EFE6',
  textSecondary: '#C7C2AF',
  textMuted: '#8D8874',
  textInverse: '#0B0E1A',

  // Statuses
  success: '#2E9E63',
  warning: '#BE8A2E',
  danger: '#C24545',
  info: '#3B8FA8',

  // Inputs
  inputBg: '#10142A',
  inputBorder: '#262E52',
  inputFocusBorder: '#5568D6',
};

export const LIGHT_THEME = {
  mode: 'light',
  background: '#FAF7EF',        // warm paper, not clinical #F8FAFC
  surface: '#FFFFFF',
  surfaceElevated: '#F3EEE1',
  card: '#FFFFFF',
  cardBorder: '#E7DFC9',
  border: '#E7DFC9',
  borderLight: '#D6CCAE',

  // Brand & Institutional Colors
  primary: '#2A3785',           // Seal Indigo, deepened for light contrast
  primaryLight: '#3547A8',
  primaryDark: '#1D2760',
  primaryGlow: 'rgba(42, 55, 133, 0.12)',

  accent: '#1F7A6D',
  accentSaffron: '#A85A30',
  accentEmerald: '#1F7A4C',
  accentRose: '#9C3A50',
  accentAmber: '#9C7025',
  accentPurple: '#654A96',

  // Text Colors
  text: '#201E13',
  textSecondary: '#4A4632',
  textMuted: '#79735A',
  textInverse: '#FAF7EF',

  // Statuses
  success: '#1F7A4C',
  warning: '#9C7025',
  danger: '#B23A3A',
  info: '#28728A',

  // Inputs
  inputBg: '#FFFFFF',
  inputBorder: '#D6CCAE',
  inputFocusBorder: '#2A3785',
};

export const SPACING = {
  xs: 4,
  sm: 8,
  md: 16,
  lg: 24,
  xl: 32,
  xxl: 40,
};

export const RADIUS = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  full: 9999,
};

export const FONT_SIZE = {
  xs: 11,
  sm: 13,
  md: 15,
  lg: 18,
  xl: 22,
  xxl: 28,
  hero: 34,
};

export const SHADOWS = {
  sm: {
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 2,
    elevation: 2,
  },
  md: {
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.15,
    shadowRadius: 6,
    elevation: 4,
  },
  lg: {
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.2,
    shadowRadius: 12,
    elevation: 8,
  },
};
