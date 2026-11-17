export interface ErrorBody {
  code: string;
  message: string;
  details?: Record<string, string> | null;
}

export interface ErrorResponseEnvelope {
  error: ErrorBody;
}

export class ApiClientError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, string> | null;

  constructor(options: {
    status: number;
    code: string;
    message: string;
    details?: Record<string, string> | null;
  }) {
    super(options.message);
    this.name = 'ApiClientError';
    this.status = options.status;
    this.code = options.code;
    this.details = options.details ?? null;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function parseDetailsRecord(value: unknown): Record<string, string> | null {
  if (!isRecord(value)) {
    return null;
  }
  const entries: Array<[string, string]> = [];
  for (const [key, item] of Object.entries(value)) {
    if (typeof item === 'string') {
      entries.push([key, item]);
    } else if (item != null) {
      entries.push([key, String(item)]);
    }
  }
  return entries.length > 0 ? Object.fromEntries(entries) : null;
}

export function isErrorResponseEnvelope(value: unknown): value is ErrorResponseEnvelope {
  if (!isRecord(value) || !('error' in value)) {
    return false;
  }
  const body = value.error;
  return isRecord(body) && typeof body.code === 'string' && typeof body.message === 'string';
}

export function buildApiClientErrorFromPayload(
  status: number,
  statusText: string,
  payload: unknown,
): ApiClientError {
  if (isErrorResponseEnvelope(payload)) {
    return new ApiClientError({
      status,
      code: payload.error.code,
      message: payload.error.message,
      details: parseDetailsRecord(payload.error.details),
    });
  }

  if (isRecord(payload) && typeof payload.detail === 'string') {
    return new ApiClientError({
      status,
      code: `HTTP_${status}`,
      message: payload.detail,
    });
  }

  return new ApiClientError({
    status,
    code: `HTTP_${status}`,
    message: statusText ? `Request failed (${status} ${statusText})` : `Request failed (${status})`,
  });
}

export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError';
}

export function extractErrorInfo(
  error: unknown,
  fallback = 'An unexpected error occurred.',
): { message: string; code?: string; details?: Record<string, string> | null } {
  if (error instanceof ApiClientError) {
    return {
      message: error.message,
      code: `${error.status > 0 ? `${error.status} · ` : ''}${error.code}`,
      details: error.details,
    };
  }
  if (error instanceof Error) {
    return { message: error.message };
  }
  return { message: fallback };
}
