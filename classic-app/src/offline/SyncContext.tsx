import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { AppState } from 'react-native';
import NetInfo from '@react-native-community/netinfo';
import { draftStore } from './storage.ts';
import { syncAll } from './sync.ts';
import type { SyncSummary } from './sync.ts';
import { endpoints } from '../api/instance.ts';
import { useAuth } from '../auth/AuthContext.tsx';

interface SyncState { online: boolean; syncing: boolean; pending: number; needsAttention: number; last: SyncSummary | null; syncNow(): Promise<SyncSummary | null>; reload(): Promise<void> }
const Ctx = createContext<SyncState | null>(null);
export const useSync = () => { const c = useContext(Ctx); if (!c) throw new Error('SyncProvider missing'); return c; };

export const isOnline = async () => { const s = await NetInfo.fetch(); return !!s.isConnected && s.isInternetReachable !== false; };

export function SyncProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth();
  const [online, setOnline] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [counts, setCounts] = useState({ pending: 0, needsAttention: 0 });
  const [last, setLast] = useState<SyncSummary | null>(null);
  const busy = useRef(false);

  const reload = useCallback(async () => {
    const c = await draftStore.counts();
    setCounts({ pending: c.pending + c.syncing, needsAttention: c.failed + c.needs_review });
  }, []);

  const syncNow = useCallback(async () => {
    if (!user || busy.current) return null;
    busy.current = true; setSyncing(true);
    try {
      const summary = await syncAll({ store: draftStore, api: { uploadEvidence: endpoints.uploadEvidence, transcribe: endpoints.transcribe, createComplaint: endpoints.createComplaint }, isOnline, now: () => new Date() });
      setLast(summary);
      return summary;
    } finally { busy.current = false; setSyncing(false); await reload(); }
  }, [user, reload]);

  useEffect(() => { reload(); }, [reload]);
  useEffect(() => NetInfo.addEventListener((s: { isConnected: boolean | null; isInternetReachable: boolean | null }) => { const on = !!s.isConnected && s.isInternetReachable !== false; setOnline(on); if (on) syncNow(); }), [syncNow]); // reconnect => sync
  useEffect(() => { const sub = AppState.addEventListener('change', (st: string) => { if (st === 'active') syncNow(); }); return () => sub.remove(); }, [syncNow]); // foreground => sync

  const value = useMemo(() => ({ online, syncing, ...counts, last, syncNow, reload }), [online, syncing, counts, last, syncNow, reload]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
