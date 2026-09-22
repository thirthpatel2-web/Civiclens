export class ApiError extends Error {
  status: number;
  code: string;
  details: unknown;
  correlationId?: string;
  constructor(status: number, code: string, message: string, details?: unknown, correlationId?: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.details = details;
    this.correlationId = correlationId;
  }
  get isAuth(): boolean { return this.status === 401; }
  get isValidation(): boolean { return this.status === 422; }
  get isMfaRequired(): boolean { return this.code === 'mfa_required'; }
  get isNotConfigured(): boolean { return this.code === 'not_configured' || this.status === 501; }
}

/** The request never reached a server response (offline, DNS, timeout). Distinct from ApiError so callers can queue and retry. */
export class NetworkError extends Error {
  constructor(message = 'Network request failed') {
    super(message);
    this.name = 'NetworkError';
  }
}
