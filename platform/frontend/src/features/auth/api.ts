import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { ApiClientError, apiGet, apiPost, apiPostVoid } from '../../shared/api/client';
import { demoAccountsSchema, userSchema, type User } from './model';

export const meQueryKey = ['me'] as const;

/** Aktuelle Sitzung: `null` = nicht angemeldet (401 ist hier ein normaler Zustand, kein Fehler). */
export function useMe() {
  return useQuery({
    queryKey: meQueryKey,
    queryFn: async ({ signal }): Promise<User | null> => {
      try {
        return await apiGet('/auth/me', userSchema, signal);
      } catch (error) {
        if (error instanceof ApiClientError && error.status === 401) return null;
        throw error;
      }
    },
    staleTime: 60_000,
  });
}

export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (credentials: { username: string; password: string }) =>
      apiPost('/auth/login', credentials, userSchema),
    onSuccess: (user) => {
      queryClient.setQueryData(meQueryKey, user);
    },
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      try {
        await apiPostVoid('/auth/logout');
      } catch (error) {
        // Sitzung ist serverseitig schon beendet: Ziel erreicht. Alles andere bleibt ein Fehler.
        if (!(error instanceof ApiClientError && error.status === 401)) throw error;
      }
    },
    onSuccess: () => {
      // Nutzerbezogene Daten dürfen nach dem Abmelden nicht im Cache bleiben; /meta ist öffentlich.
      queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== 'meta' });
      queryClient.setQueryData(meQueryKey, null);
    },
  });
}

export function useDemoAccounts(enabled: boolean) {
  return useQuery({
    queryKey: ['demo-accounts'],
    queryFn: ({ signal }) => apiGet('/demo/accounts', demoAccountsSchema, signal),
    enabled,
  });
}
