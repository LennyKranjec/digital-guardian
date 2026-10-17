import { useMemo } from 'react';
import { z } from 'zod';

import { useMeta } from '../../../../platform/frontend/src/features/system/api';

/** Meta-Erweiterung des Vertrags v1.2 (DR-009): `GET /meta` → `waechter.server_now` (ISO 8601 mit Zeitzone). */
export const metaExtensionSchema = z.object({
  waechter: z.object({ server_now: z.string() }).passthrough(),
});

/**
 * „Jetzt“ laut Server (aus Clock bzw. APP_FROZEN_NOW). Relative Zeitangaben („vor 2 Tagen“) werden
 * nur dagegen gerechnet, nie gegen die Browseruhr; fehlt der Wert, zeigt die Oberfläche nur absolute Zeiten.
 */
export function useServerNow(): Date | null {
  const meta = useMeta();
  const serverNow = useMemo(() => {
    const parsed = metaExtensionSchema.safeParse(meta.data);
    return parsed.success ? parsed.data.waechter.server_now : null;
  }, [meta.data]);

  return useMemo(() => {
    if (!serverNow) return null;
    const date = new Date(serverNow);
    return Number.isNaN(date.getTime()) ? null : date;
  }, [serverNow]);
}
