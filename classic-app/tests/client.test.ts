import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildUrl, createApiClient } from '../src/api/client.ts';
import { ApiError, NetworkError } from '../src/api/errors.ts';
import { fakeResponse } from './helpers.ts';

function client(handler: (url: string, init: any) => any, token: string | null = 'tok-123', onUnauthorized?: () => void) {
  const calls: Array<{ url: string; init: any }> = [];
  const api = createApiClient({ baseUrl: 'https://api.example.org/', getToken: async () => token, onUnauthorized,
    fetchImpl: async (url, init) => { calls.push({ url, init }); return handler(url, init); } });
  return { api, calls };
}

test('buildUrl versions the path, trims slashes and encodes/omits query values', () => {
  assert.equal(buildUrl('https://a.org/', '/complaints', { filter: 'all', q: 'a b', x: undefined, y: '' }), 'https://a.org/api/v1/complaints?filter=all&q=a%20b');
});

test('sends the bearer token and JSON body; parses the response', async () => {
  const { api, calls } = client(() => fakeResponse(200, { ok: true }));
  const r = await api.post<{ ok: boolean }>('/x', { a: 1 });
  assert.equal(r.ok, true);
  assert.equal(calls[0].init.headers.Authorization, 'Bearer tok-123');
  assert.equal(calls[0].init.headers['Content-Type'], 'application/json');
  assert.equal(calls[0].init.body, '{"a":1}');
  assert.equal(calls[0].url, 'https://api.example.org/api/v1/x');
});

test('auth:false sends no Authorization header; multipart bodies are passed through without a JSON content type', async () => {
  const { api, calls } = client(() => fakeResponse(200, {}));
  await api.request('POST', '/auth/mobile/login', { json: {}, auth: false });
  assert.equal(calls[0].init.headers.Authorization, undefined);
  const form = new FormData();
  form.append('k', 'v');
  await api.request('POST', '/complaints/evidence', { form });
  assert.equal(calls[1].init.body, form);
  assert.equal(calls[1].init.headers['Content-Type'], undefined);
});

test('backend error contract becomes ApiError with code, message, details and correlation id', async () => {
  const { api } = client(() => fakeResponse(422, { error: { code: 'validation_failed', message: 'The complaint has errors.', details: { title: 'too short' }, correlation_id: 'abc12345' } }));
  await assert.rejects(api.post('/complaints', {}), (e: any) => {
    assert.ok(e instanceof ApiError);
    assert.deepEqual([e.status, e.code, e.message, e.details, e.correlationId, e.isValidation], [422, 'validation_failed', 'The complaint has errors.', { title: 'too short' }, 'abc12345', true]);
    return true;
  });
});

test('401 calls onUnauthorized (once per failing call) and mfa_required is recognisable', async () => {
  let n = 0;
  const { api } = client(() => fakeResponse(401, { error: { code: 'mfa_required', message: 'code needed' } }), 't', () => { n += 1; });
  await assert.rejects(api.get('/complaints'), (e: any) => e.isAuth && e.isMfaRequired);
  assert.equal(n, 1);
  const noAuth = client(() => fakeResponse(401, { error: { code: 'mfa_required', message: 'm' } }), 't', () => { n += 10; });
  await assert.rejects(noAuth.api.request('POST', '/auth/mobile/login', { json: {}, auth: false }));
  assert.equal(n, 1); // a failed LOGIN must not trigger the "session expired" handler
});

test('non-JSON error bodies and network failures are normalised', async () => {
  const bad = client(() => fakeResponse(502, '<html>bad gateway</html>'));
  await assert.rejects(bad.api.get('/x'), (e: any) => e instanceof ApiError && e.status === 502 && e.code === 'http_error');
  const down = client(() => { throw new TypeError('Network request failed'); });
  await assert.rejects(down.api.get('/x'), (e: any) => e instanceof NetworkError);
  const ok204 = client(() => fakeResponse(204, undefined));
  assert.equal(await ok204.api.del('/x'), undefined);
});

test('not_configured backend responses are recognisable (501)', async () => {
  const { api } = client(() => fakeResponse(501, { error: { code: 'not_configured', message: 'No translation provider is configured.' } }));
  await assert.rejects(api.post('/voice/translate', {}), (e: any) => e.isNotConfigured);
});
