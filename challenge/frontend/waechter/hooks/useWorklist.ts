import { useQuery } from '@tanstack/react-query';
import { useCallback, useRef, useState } from 'react';

import { getNotifications, getWorklist } from '../api/client';
import { useLang } from './useLang';
import { readSeen, writeSeen } from '../model/notifications';

/** Abfrageintervall der Sofortbenachrichtigungen (Vertrag: In-App-Kanal, kein Push). */
export const NOTIFICATION_REFETCH_MS = 30_000;

export function useWorklist() {
  const lang = useLang();
  return useQuery({
    queryKey: ['waechter', 'worklist', lang],
    queryFn: ({ signal }) => getWorklist(lang, signal),
  });
}

export function useNotifications() {
  const lang = useLang();
  return useQuery({
    queryKey: ['waechter', 'notifications', lang],
    queryFn: ({ signal }) => getNotifications(lang, signal),
    refetchInterval: NOTIFICATION_REFETCH_MS,
    // Jede Abfrage soll neue rote Meldungen zeigen, nie einen alten Stand als „frisch“ behandeln.
    staleTime: 0,
  });
}

/** Lokal gemerkte „gesehen“-IDs (localStorage, mit Rückfall auf reinen Arbeitsspeicher). */
export function useSeenNotifications() {
  const [seen, setSeen] = useState<ReadonlySet<string>>(() => readSeen());
  const latest = useRef(seen);

  const markSeen = useCallback((id: string) => {
    const next = new Set(latest.current);
    next.add(id);
    latest.current = next;
    writeSeen(next);
    setSeen(next);
  }, []);

  return { seen, markSeen };
}
