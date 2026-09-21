import type { KeyValueStorage } from '../src/offline/queue.ts';

export class MemoryStorage implements KeyValueStorage {
  data = new Map<string, string>();
  async getItem(k: string) { return this.data.get(k) ?? null; }
  async setItem(k: string, v: string) { this.data.set(k, v); }
  async removeItem(k: string) { this.data.delete(k); }
}

export const SAMPLES = {
  kn: 'ನನ್ನ ರಸ್ತೆಯಲ್ಲಿ ದೊಡ್ಡ ಗುಂಡಿ ಇದೆ',
  hi: 'मेरे इलाके में सड़क खराब है',
  ta: 'எங்கள் பகுதியில் சாலை மிகவும் மோசமாக உள்ளது',
  te: 'మా ప్రాంతంలో రోడ్డు చాలా దారుణంగా ఉంది',
  en: 'My road has a large pothole',
} as const;
export const ENGLISH_TRANSLATION = 'There is a big pothole on my road.';

export function fakeResponse(status: number, body: unknown) {
  const text = body === undefined ? '' : typeof body === 'string' ? body : JSON.stringify(body);
  return { ok: status >= 200 && status < 300, status, text: async () => text };
}
