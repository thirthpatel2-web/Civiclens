import React, { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { endpoints, onUnauthorized } from '../api/instance.ts';
import { ApiError } from '../api/errors.ts';
import type { SessionUser } from '../api/types.ts';
import { clearToken, getToken, setToken } from './session.ts';

interface AuthState { user: SessionUser | null; loading: boolean; signIn(email: string, password: string, otp?: string): Promise<void>; signOut(): Promise<void>; refresh(): Promise<void> }
const Ctx = createContext<AuthState | null>(null);
export const useAuth = () => { const c = useContext(Ctx); if (!c) throw new Error('AuthProvider missing'); return c; };

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<SessionUser | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    if (!(await getToken())) { setUser(null); return; }
    try { setUser((await endpoints.me()).user); }
    catch (e) { if (e instanceof ApiError && e.isAuth) { await clearToken(); setUser(null); } /* network error: keep the cached session */ }
  }, []);

  useEffect(() => { onUnauthorized(() => { clearToken().then(() => setUser(null)); }); refresh().finally(() => setLoading(false)); }, [refresh]);

  const signIn = useCallback(async (email: string, password: string, otp?: string) => {
    const r = await endpoints.login(email, password, otp); // throws ApiError (mfa_required => the screen asks for the code)
    await setToken(r.session_token);
    setUser(r.user);
  }, []);

  const signOut = useCallback(async () => {
    try { await endpoints.logout(); } catch { /* offline: the token is still discarded locally; the server session expires by itself */ }
    await clearToken();
    setUser(null);
  }, []);

  const value = useMemo(() => ({ user, loading, signIn, signOut, refresh }), [user, loading, signIn, signOut, refresh]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
