import { render } from '@testing-library/react';
import { RouterProvider, createMemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';

import { Providers } from '../app/providers';
import { buildRoutes } from '../app/router';

export const META_FIXTURE = {
  app_name: 'Test-Plattform',
  version: '0.1.0',
  demo_mode: true,
  synthetic_data: true,
  roles: ['admin', 'user'],
  challenge_loaded: false,
};

export const UNAUTHENTICATED = {
  code: 'unauthenticated',
  message: 'Authentication required',
  field_errors: [],
};

export const ADMIN = { id: 'u1', username: 'admin', display_name: 'Admin (Demo)', role: 'admin' };
export const USER = { id: 'u2', username: 'user', display_name: 'Nutzer:in (Demo)', role: 'user' };

export const DEMO_ACCOUNTS = [
  { username: 'admin', password: 'demo-pw', role: 'admin', label: 'Admin (Demo)' },
  { username: 'user', password: 'demo-pw', role: 'user', label: 'Nutzer:in (Demo)' },
];

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

/** Standardantworten: /meta ok, nicht angemeldet, Demo-Konten. */
export function defaultApiResponse(url: string): Response {
  if (url.endsWith('/auth/me')) return jsonResponse(UNAUTHENTICATED, 401);
  if (url.endsWith('/demo/accounts')) return jsonResponse(DEMO_ACCOUNTS);
  return jsonResponse(META_FIXTURE);
}

function requestUrl(input: RequestInfo | URL): string {
  return typeof input === 'string' ? input : input instanceof URL ? input.href : input.url;
}

export function mockFetch(
  handler: (url: string, init?: RequestInit) => Response | Promise<Response>,
) {
  const fn = vi.fn((input: RequestInfo | URL, init?: RequestInit) =>
    Promise.resolve(handler(requestUrl(input), init)),
  );
  vi.stubGlobal('fetch', fn);
  return fn;
}

export function renderApp(path = '/') {
  const router = createMemoryRouter(buildRoutes(), { initialEntries: [path] });
  return render(
    <Providers>
      <RouterProvider router={router} />
    </Providers>,
  );
}
