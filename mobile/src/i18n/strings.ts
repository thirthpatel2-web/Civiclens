// UI strings: the ported 7-language dictionary + extras (English and Hindi). Missing keys fall back to English, then to the key.
import type { LanguageCode } from './languages.ts';

export type Dict = Record<string, Record<string, string>>;

export function createStrings(base: Dict, extra: Dict) {
  const lookup = (lang: string, key: string): string | undefined => extra[lang]?.[key] ?? base[lang]?.[key];
  return {
    t(key: string, lang: LanguageCode | string = 'en', params: Record<string, string | number> = {}): string {
      let text = lookup(lang, key) ?? lookup('en', key) ?? key;
      for (const [k, v] of Object.entries(params)) text = text.split(`{${k}}`).join(String(v));
      return text;
    },
    isTranslated: (key: string, lang: string) => lookup(lang, key) !== undefined,
    coverage(lang: string): { translated: number; total: number } {
      const keys = new Set([...Object.keys(base.en ?? {}), ...Object.keys(extra.en ?? {})]);
      return { translated: [...keys].filter((k) => lookup(lang, k) !== undefined).length, total: keys.size };
    },
  };
}
export type Strings = ReturnType<typeof createStrings>;
