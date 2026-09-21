import { createApiClient } from './client.ts';
import { createEndpoints } from './endpoints.ts';
import { API_BASE_URL } from '../config.ts';
import { getToken } from '../auth/session.ts';

let unauthorizedHandler: (() => void) | undefined;
export const onUnauthorized = (fn: () => void) => { unauthorizedHandler = fn; };

export const api = createApiClient({ baseUrl: API_BASE_URL, getToken, onUnauthorized: () => unauthorizedHandler?.() });
export const endpoints = createEndpoints(api);
