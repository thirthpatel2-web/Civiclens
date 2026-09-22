// Typed HTTP client for the CivicLens FastAPI backend. No business logic lives here: it authenticates, sends, and normalises errors.
// Error body contract (backend): { error: { code, message, details?, correlation_id? } }

import { ApiError, NetworkError } from './errors.ts';

export type FetchLike = (input: string, init?: any) => Promise<any>;

export interface ClientOptions {
  baseUrl: string;
  getToken: () => Promise<string | null>;
  fetchImpl?: FetchLike;
  onUnauthorized?: () => void;
  timeoutMs?: number;
}

export interface RequestOptions {
  json?: unknown;
  form?: any; // FormData
  auth?: boolean;
  query?: Record<string, string | number | boolean | undefined | null>;
  timeoutMs?: number;
}

export interface ApiClient {
  request<T>(method: string, path: string, opts?: RequestOptions): Promise<T>;
  get<T>(path: string, query?: RequestOptions['query']): Promise<T>;
  post<T>(path: string, json?: unknown, opts?: RequestOptions): Promise<T>;
  put<T>(path: string, json?: unknown): Promise<T>;
  del<T>(path: string): Promise<T>;
  baseUrl: string;
}

export function buildUrl(baseUrl: string, path: string, query?: RequestOptions['query']): string {
  const base = baseUrl.replace(/\/+$/, '');
  const qs = Object.entries(query ?? {})
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
    .join('&');
  return `${base}/api/v1${path}${qs ? `?${qs}` : ''}`;
}

export function createApiClient(opts: ClientOptions): ApiClient {
  const doFetch: FetchLike = opts.fetchImpl ?? ((u, i) => (globalThis as any).fetch(u, i));

  async function request<T>(method: string, path: string, o: RequestOptions = {}): Promise<T> {
    const headers: Record<string, string> = { Accept: 'application/json' };
    if (o.auth !== false) {
      const token = await opts.getToken();
      if (token) headers.Authorization = `Bearer ${token}`;
    }
    let body: any;
    if (o.form) body = o.form; // let the runtime set the multipart boundary
    else if (o.json !== undefined) {
      headers['Content-Type'] = 'application/json';
      body = JSON.stringify(o.json);
    }
    const controller = typeof AbortController !== 'undefined' ? new AbortController() : undefined;
    const timer = controller ? setTimeout(() => controller.abort(), o.timeoutMs ?? opts.timeoutMs ?? 30000) : undefined;
    let res: any;
    try {
      res = await doFetch(buildUrl(opts.baseUrl, path, o.query), { method, headers, body, signal: controller?.signal });
    } catch (e: any) {
      throw new NetworkError(e?.name === 'AbortError' ? 'The request timed out' : e?.message ?? 'Network request failed');
    } finally {
      if (timer) clearTimeout(timer);
    }
    const text = await res.text();
    let parsed: any = undefined;
    if (text) {
      try { parsed = JSON.parse(text); } catch { parsed = undefined; }
    }
    if (!res.ok) {
      const err = parsed?.error;
      const apiErr = new ApiError(res.status, err?.code ?? 'http_error', err?.message ?? `Request failed (${res.status})`, err?.details, err?.correlation_id);
      if (apiErr.status === 401 && o.auth !== false) opts.onUnauthorized?.();
      throw apiErr;
    }
    return parsed as T;
  }

  return {
    baseUrl: opts.baseUrl,
    request,
    get: (path, query) => request('GET', path, { query }),
    post: (path, json, o) => request('POST', path, { ...o, json }),
    put: (path, json) => request('PUT', path, { json }),
    del: (path) => request('DELETE', path),
  };
}
