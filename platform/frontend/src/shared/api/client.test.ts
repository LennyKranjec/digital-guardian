import { afterEach, describe, expect, it, vi } from 'vitest';
import { z } from 'zod';

import { jsonResponse, mockFetch } from '../../test/render';
import { ApiClientError, apiGet } from './client';

afterEach(() => {
  vi.unstubAllGlobals();
});

const schema = z.object({ ok: z.boolean() });

describe('apiGet', () => {
  it('liefert validierte Daten und ruft /api/v1 auf', async () => {
    const fetchMock = mockFetch(() => jsonResponse({ ok: true }));
    await expect(apiGet('/health', schema)).resolves.toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/health', expect.anything());
  });

  it('übersetzt das Fehlerformat aus api.md inklusive field_errors', async () => {
    mockFetch(() =>
      jsonResponse(
        {
          code: 'validation_failed',
          message: 'Eingabe ungültig',
          field_errors: [{ field: 'answers.score', code: 'out_of_range', message: 'zu groß' }],
        },
        422,
      ),
    );
    const error = await apiGet('/x', schema).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiClientError);
    expect(error).toMatchObject({
      status: 422,
      code: 'validation_failed',
      fieldErrors: [{ field: 'answers.score', code: 'out_of_range', message: 'zu groß' }],
    });
  });

  it('behandelt Fehlerantworten ohne api.md-Format als unknown_error', async () => {
    mockFetch(() => new Response('<html>Bad Gateway</html>', { status: 502 }));
    await expect(apiGet('/x', schema)).rejects.toMatchObject({
      status: 502,
      code: 'unknown_error',
    });
  });

  it('markiert Netzwerkfehler (Status 0)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))),
    );
    const error = await apiGet('/x', schema).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiClientError);
    expect((error as ApiClientError).isNetwork).toBe(true);
    expect((error as ApiClientError).code).toBe('network_error');
  });

  it('lehnt unerwartete Antwortformen ab', async () => {
    mockFetch(() => jsonResponse({ ok: 'ja' }));
    await expect(apiGet('/x', schema)).rejects.toMatchObject({ code: 'invalid_response' });
  });
});
