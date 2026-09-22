// WEB ONLY (Metro picks this over session.ts when platform === 'web'). Native keeps using the OS
// secure store; browsers have no Keychain/Keystore equivalent, so this falls back to localStorage.
// That is strictly weaker than native storage - the web build is for reviewing the UI, not for
// handling real citizen sessions on a shared machine.
const KEY = 'civiclens.session.token';

const safe = <T,>(fn: () => T, fallback: T): T => {
  try {
    return fn();
  } catch {
    return fallback; // private windows / blocked site data throw on access
  }
};

export const getToken = async (): Promise<string | null> => safe(() => window.localStorage.getItem(KEY), null);
export const setToken = async (t: string): Promise<void> => safe(() => window.localStorage.setItem(KEY, t), undefined);
export const clearToken = async (): Promise<void> => safe(() => window.localStorage.removeItem(KEY), undefined);
