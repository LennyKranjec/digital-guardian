import { z } from 'zod';

/** Fehlerformat laut docs/contracts/api.md: { code, message, field_errors[{field, code, message}] }. */
const errorBodySchema = z.object({
  code: z.string(),
  message: z.string(),
  field_errors: z
    .array(z.object({ field: z.string(), code: z.string(), message: z.string() }))
    .default([]),
});

export interface FieldError {
  field: string;
  code: string;
  message: string;
}

export class ApiClientError extends Error {
  readonly status: number;
  readonly code: string;
  readonly fieldErrors: FieldError[];

  constructor(status: number, code: string, message: string, fieldErrors: FieldError[] = []) {
    super(message);
    this.name = 'ApiClientError';
    this.status = status;
    this.code = code;
    this.fieldErrors = fieldErrors;
  }

  /** Netzwerkfehler (kein HTTP-Status) – Ansichten zeigen dann den Offline-/Fehlerzustand. */
  get isNetwork(): boolean {
    return this.status === 0;
  }
}

export const API_BASE = '/api/v1';

async function toError(response: Response): Promise<ApiClientError> {
  try {
    const parsed = errorBodySchema.parse(await response.json());
    return new ApiClientError(response.status, parsed.code, parsed.message, parsed.field_errors);
  } catch {
    return new ApiClientError(response.status, 'unknown_error', response.statusText);
  }
}

/** Header gegen Cross-Site-Requests; Pflicht für jede ändernde Anfrage (api.md, auch Login/Logout). */
export const CSRF_HEADER = { 'X-Requested-With': 'fetch' } as const;

async function request(path: string, init: RequestInit): Promise<Response> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { credentials: 'same-origin', ...init });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === 'AbortError') throw cause;
    throw new ApiClientError(0, 'network_error', 'Network request failed');
  }
  if (!response.ok) throw await toError(response);
  return response;
}

async function parse<T>(response: Response, schema: z.ZodType<T>): Promise<T> {
  const payload: unknown = await response.json().catch(() => undefined);
  const result = schema.safeParse(payload);
  if (!result.success) {
    throw new ApiClientError(response.status, 'invalid_response', 'Unexpected response shape');
  }
  return result.data;
}

/** GET mit Antwortvalidierung. Die Antwort wird nie geloggt. */
export async function apiGet<T>(
  path: string,
  schema: z.ZodType<T>,
  signal?: AbortSignal,
): Promise<T> {
  const response = await request(path, { headers: { Accept: 'application/json' }, signal });
  return parse(response, schema);
}

/** Ändernde Anfrage (POST) mit CSRF-Header und Antwortvalidierung. Der Body wird nie geloggt. */
export async function apiPost<T>(path: string, body: unknown, schema: z.ZodType<T>): Promise<T> {
  const response = await request(path, {
    method: 'POST',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json', ...CSRF_HEADER },
    body: JSON.stringify(body),
  });
  return parse(response, schema);
}

/** Ändernde Anfrage (PUT) mit CSRF-Header und Antwortvalidierung. Der Body wird nie geloggt. */
export async function apiPut<T>(path: string, body: unknown, schema: z.ZodType<T>): Promise<T> {
  const response = await request(path, {
    method: 'PUT',
    headers: { Accept: 'application/json', 'Content-Type': 'application/json', ...CSRF_HEADER },
    body: JSON.stringify(body),
  });
  return parse(response, schema);
}

/** Ändernde Anfrage ohne Antwortkörper (z. B. 204 bei Logout). */
export async function apiPostVoid(path: string): Promise<void> {
  await request(path, { method: 'POST', headers: { ...CSRF_HEADER } });
}
