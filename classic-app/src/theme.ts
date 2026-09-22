// "Rajmudra" (official seal) palette — deep indigo of an official seal and judicial robes, warm
// sandstone/terracotta of government buildings, and turmeric/saffron ochre used in official ceremony.
// Chosen deliberately over a generic SaaS blue-and-slate kit, since this app sits between a citizen
// and the machinery of Indian civic administration and law. LIGHT is "ledger paper", DARK is
// "indigo-charcoal, not generic slate" - see ThemeContext.tsx for how a screen picks one live.
export interface ThemeColors {
  mode: 'light' | 'dark';
  primary: string; primaryLight: string; primaryDark: string; primaryGlow: string;
  accent: string; accentSaffron: string; accentEmerald: string; accentRose: string; accentAmber: string; accentPurple: string;
  ok: string; warn: string; bad: string; info: string; muted: string;
  bg: string; card: string; surfaceElevated: string; border: string; borderLight: string;
  text: string; textSoft: string; textMuted: string; textInverse: string;
  inputBg: string; inputBorder: string; inputFocusBorder: string;
}
export const LIGHT: ThemeColors = {
  mode: 'light',
  primary: '#2A3785', primaryLight: '#3547A8', primaryDark: '#1D2760', primaryGlow: 'rgba(42, 55, 133, 0.12)',
  accent: '#1F7A6D', accentSaffron: '#A85A30', accentEmerald: '#1F7A4C', accentRose: '#9C3A50', accentAmber: '#9C7025', accentPurple: '#654A96',
  ok: '#1F7A4C', warn: '#9C7025', bad: '#B23A3A', info: '#28728A', muted: '#79735A',
  bg: '#FAF7EF', card: '#FFFFFF', surfaceElevated: '#F3EEE1', border: '#E7DFC9', borderLight: '#D6CCAE',
  text: '#201E13', textSoft: '#4A4632', textMuted: '#79735A', textInverse: '#FAF7EF',
  inputBg: '#FFFFFF', inputBorder: '#D6CCAE', inputFocusBorder: '#2A3785',
};
export const DARK: ThemeColors = {
  mode: 'dark',
  primary: '#3547A8', primaryLight: '#5568D6', primaryDark: '#232F73', primaryGlow: 'rgba(53, 71, 168, 0.28)',
  accent: '#2E9E8F', accentSaffron: '#BF6B3D', accentEmerald: '#2E9E63', accentRose: '#B0435C', accentAmber: '#BE8A2E', accentPurple: '#7A5FB0',
  ok: '#2E9E63', warn: '#BE8A2E', bad: '#C24545', info: '#3B8FA8', muted: '#8D8874',
  bg: '#0B0E1A', card: '#151A32', surfaceElevated: '#1B2140', border: '#1E2542', borderLight: '#3A4470',
  text: '#F2EFE6', textSoft: '#C7C2AF', textMuted: '#8D8874', textInverse: '#0B0E1A',
  inputBg: '#10142A', inputBorder: '#262E52', inputFocusBorder: '#5568D6',
};

// Back-compat default (light) for any file not yet migrated to useTheme() - never add new usages of this.
export const colors: ThemeColors = LIGHT;

// Ported 1:1 from legacy-prototype/src/constants/theme.js (SPACING/RADIUS/FONT_SIZE/SHADOWS) - this
// is the zip's actual scale, not a re-derived approximation, so density/type-size match exactly.
export const spacing = { xs: 4, sm: 8, md: 16, lg: 24, xl: 32, xxl: 40 };
export const radius = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24, full: 9999 };
export const fontSize = { xs: 11, sm: 13, md: 15, lg: 18, xl: 22, xxl: 28, hero: 34 };
export const MIN_TOUCH = 48; // accessible touch target

// Fraunces (headlines/hero) + Manrope (UI/body) - see ClassicFontProvider in app/_layout.tsx for
// how these are loaded; falls back to the system font until the async load resolves.
export const fontFamily = {
  display: 'Fraunces_600SemiBold', displayBold: 'Fraunces_700Bold', displayItalic: 'Fraunces_600SemiBold_Italic',
  body: 'Manrope_400Regular', bodyMedium: 'Manrope_500Medium', bodySemiBold: 'Manrope_600SemiBold', bodyBold: 'Manrope_700Bold', bodyExtraBold: 'Manrope_800ExtraBold',
};

// Cross-platform elevation (shadow* for iOS/web, elevation for Android) - shared so cards, the hero
// banner and dashboard tiles all read as lifted surfaces instead of flat, bordered rectangles.
export const shadow = {
  sm: { shadowColor: '#000', shadowOffset: { width: 0, height: 1 }, shadowOpacity: 0.1, shadowRadius: 2, elevation: 2 },
  md: { shadowColor: '#000', shadowOffset: { width: 0, height: 4 }, shadowOpacity: 0.15, shadowRadius: 6, elevation: 4 },
  lg: { shadowColor: '#000', shadowOffset: { width: 0, height: 8 }, shadowOpacity: 0.2, shadowRadius: 12, elevation: 8 },
} as const;

const STATUS_LIGHT: Record<string, string> = {
  submitted: '#79735A', ai_routed: '#654A96', assigned: '#3547A8', under_review: '#9C7025', inspection_scheduled: '#A85A30',
  in_progress: '#28728A', resolved: '#1F7A4C', closed: '#1D2760', rejected: '#B23A3A',
};
const STATUS_DARK: Record<string, string> = {
  submitted: '#8D8874', ai_routed: '#7A5FB0', assigned: '#5568D6', under_review: '#BE8A2E', inspection_scheduled: '#BF6B3D',
  in_progress: '#3B8FA8', resolved: '#2E9E63', closed: '#5568D6', rejected: '#C24545',
};
export const statusColor = STATUS_LIGHT; // back-compat default; use statusColorFor(mode) in theme-aware code
export const statusColorFor = (mode: 'light' | 'dark'): Record<string, string> => (mode === 'dark' ? STATUS_DARK : STATUS_LIGHT);

/** "#RRGGBB" -> "rgba(r,g,b,alpha)", so a banner tint stays legible on both a light-paper and a dark-charcoal background. */
export function withAlpha(hex: string, alpha: number): string {
  const h = hex.replace('#', '');
  const r = parseInt(h.substring(0, 2), 16), g = parseInt(h.substring(2, 4), 16), b = parseInt(h.substring(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

