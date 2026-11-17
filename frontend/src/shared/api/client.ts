import { env } from '../config/env';
import { ApiClientError, buildApiClientErrorFromPayload, isAbortError } from './errors';
import type { components, paths } from './schema';

export type ApiPaths = paths;
export type ApiSchemas = components['schemas'];

export interface ApiRequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  body?: unknown;
  headers?: HeadersInit;
  signal?: AbortSignal;
}

function resolveUrl(endpoint: string): string {
  const baseUrl = env.VITE_API_BASE_URL.replace(/\/$/, '');
  const normalizedPath = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
  return `${baseUrl}${normalizedPath}`;
}

async function parseJsonSafely(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) {
    return null;
  }
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return null;
  }
}

export async function apiRequest<TResponse>(
  endpoint: string,
  options: ApiRequestOptions = {},
): Promise<TResponse> {
  const { method = 'GET', body, headers, signal } = options;
  const requestHeaders = new Headers(headers);

  let serializedBody: string | undefined;
  if (body !== undefined) {
    serializedBody = JSON.stringify(body);
    if (!requestHeaders.has('Content-Type')) {
      requestHeaders.set('Content-Type', 'application/json');
    }
  }

  let response: Response;
  try {
    response = await fetch(resolveUrl(endpoint), {
      method,
      headers: requestHeaders,
      body: serializedBody,
      signal,
    });
  } catch (err) {
    if (isAbortError(err)) {
      throw err;
    }
    const reason = err instanceof Error ? err.message : 'Network connection failed';
    throw new ApiClientError({
      status: 0,
      code: 'NETWORK_ERROR',
      message: `Unable to reach backend API: ${reason}`,
    });
  }

  const parsedPayload = await parseJsonSafely(response);
  if (!response.ok) {
    throw buildApiClientErrorFromPayload(response.status, response.statusText, parsedPayload);
  }

  return parsedPayload as TResponse;
}
