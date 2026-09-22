// Language registry (mirror of backend app/i18n/languages.py). Codes are ISO 639-1 / BCP-47 primary subtags.
// The citizen's ORIGINAL text and language are never replaced: anything derived (translation) is a separate field.

export type LanguageCode = 'en' | 'hi' | 'mr' | 'bn' | 'gu' | 'pa' | 'ta' | 'te' | 'kn' | 'ml';

export interface Language {
  code: LanguageCode;
  name: string; // English name
  native: string; // name in its own script
  script: string; // ISO 15924
  ranges: Array<[number, number]>;
}

const LATN: Array<[number, number]> = [[0x41, 0x5a], [0x61, 0x7a], [0xc0, 0x24f]];

export const LANGUAGES: Record<LanguageCode, Language> = {
  en: { code: 'en', name: 'English', native: 'English', script: 'Latn', ranges: LATN },
  hi: { code: 'hi', name: 'Hindi', native: 'हिन्दी', script: 'Deva', ranges: [[0x900, 0x97f]] },
  mr: { code: 'mr', name: 'Marathi', native: 'मराठी', script: 'Deva', ranges: [[0x900, 0x97f]] },
  bn: { code: 'bn', name: 'Bengali', native: 'বাংলা', script: 'Beng', ranges: [[0x980, 0x9ff]] },
  gu: { code: 'gu', name: 'Gujarati', native: 'ગુજરાતી', script: 'Gujr', ranges: [[0xa80, 0xaff]] },
  pa: { code: 'pa', name: 'Punjabi', native: 'ਪੰਜਾਬੀ', script: 'Guru', ranges: [[0xa00, 0xa7f]] },
  ta: { code: 'ta', name: 'Tamil', native: 'தமிழ்', script: 'Taml', ranges: [[0xb80, 0xbff]] },
  te: { code: 'te', name: 'Telugu', native: 'తెలుగు', script: 'Telu', ranges: [[0xc00, 0xc7f]] },
  kn: { code: 'kn', name: 'Kannada', native: 'ಕನ್ನಡ', script: 'Knda', ranges: [[0xc80, 0xcff]] },
  ml: { code: 'ml', name: 'Malayalam', native: 'മലയാളം', script: 'Mlym', ranges: [[0xd00, 0xd7f]] },
};

export const UI_LANGUAGES: LanguageCode[] = ['en', 'hi', 'mr', 'bn', 'ta', 'te', 'kn']; // translated UI dictionaries exist

export function isLanguageCode(x: string | null | undefined): x is LanguageCode {
  return !!x && Object.prototype.hasOwnProperty.call(LANGUAGES, x);
}

export function scriptHistogram(text: string): Record<string, number> {
  const out: Record<string, number> = {};
  for (const ch of text ?? '') {
    const cp = ch.codePointAt(0)!;
    const letter = /\p{L}/u.test(ch) || (cp >= 0x900 && cp <= 0xd7f); // Indic vowel signs are marks, not letters
    if (!letter) continue;
    for (const lang of Object.values(LANGUAGES)) {
      if (lang.ranges.some(([lo, hi]) => cp >= lo && cp <= hi)) {
        out[lang.script] = (out[lang.script] ?? 0) + 1;
        break;
      }
    }
  }
  return out;
}

/** Does the text look like it is written in the script of `code`? Catches romanised/translated engine output. */
export function scriptMatches(code: LanguageCode, text: string, minRatio = 0.6): boolean {
  const h = scriptHistogram(text);
  const total = Object.values(h).reduce((a, b) => a + b, 0);
  return total === 0 || (h[LANGUAGES[code].script] ?? 0) / total >= minRatio;
}
