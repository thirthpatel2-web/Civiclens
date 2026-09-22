import React, { createContext, useCallback, useContext, useMemo, useState, useEffect } from 'react';
import { Appearance } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { DARK, LIGHT, statusColorFor } from '../theme.ts';
import type { ThemeColors } from '../theme.ts';

export type ThemeMode = 'light' | 'dark' | 'system';
const KEY = 'civiclens.ui.theme_mode';

interface ThemeCtx {
  colors: ThemeColors;
  statusColor: Record<string, string>;
  mode: ThemeMode;
  resolvedMode: 'light' | 'dark';
  setMode(m: ThemeMode): Promise<void>;
}
const Ctx = createContext<ThemeCtx | null>(null);
export const useTheme = () => { const c = useContext(Ctx); if (!c) throw new Error('ThemeProvider missing'); return c; };

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [system, setSystem] = useState(() => Appearance.getColorScheme());
  useEffect(() => { const sub = Appearance.addChangeListener(({ colorScheme }: { colorScheme: 'light' | 'dark' | null }) => setSystem(colorScheme)); return () => sub.remove(); }, []);
  const [mode, setModeState] = useState<ThemeMode>('system');
  useEffect(() => { AsyncStorage.getItem(KEY).then((v: string | null) => { if (v === 'light' || v === 'dark' || v === 'system') setModeState(v); }); }, []);
  const setMode = useCallback(async (m: ThemeMode) => { setModeState(m); await AsyncStorage.setItem(KEY, m); }, []);

  const resolvedMode: 'light' | 'dark' = mode === 'system' ? (system === 'dark' ? 'dark' : 'light') : mode;
  const colors = resolvedMode === 'dark' ? DARK : LIGHT;
  const value = useMemo(() => ({ colors, statusColor: statusColorFor(resolvedMode), mode, resolvedMode, setMode }), [colors, resolvedMode, mode, setMode]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
