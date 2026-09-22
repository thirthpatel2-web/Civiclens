import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import base from './translations.base.json';
import extra from './translations.extra.json';
import { createStrings } from './strings.ts';
import { isLanguageCode, UI_LANGUAGES } from './languages.ts';
import type { LanguageCode } from './languages.ts';
import { endpoints } from '../api/instance.ts';
import { getToken } from '../auth/session.ts';

const strings = createStrings(base as any, extra as any);
const KEY = 'civiclens.ui.language';
interface I18n { lang: LanguageCode; setLang(l: LanguageCode): Promise<void>; t(key: string, params?: Record<string, string | number>): string }
const Ctx = createContext<I18n | null>(null);
export const useI18n = () => { const c = useContext(Ctx); if (!c) throw new Error('I18nProvider missing'); return c; };

export function I18nProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = useState<LanguageCode>('en');
  useEffect(() => { AsyncStorage.getItem(KEY).then((v: string | null) => { if (isLanguageCode(v) && UI_LANGUAGES.includes(v)) setLangState(v); }); }, []);
  const setLang = useCallback(async (l: LanguageCode) => {
    setLangState(l);
    await AsyncStorage.setItem(KEY, l); // survives navigation and restarts
    if (await getToken()) endpoints.updateProfile({ language: l }).catch(() => undefined); // also persisted on the account (best effort)
  }, []);
  const value = useMemo(() => ({ lang, setLang, t: (k: string, p?: Record<string, string | number>) => strings.t(k, lang, p) }), [lang, setLang]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
