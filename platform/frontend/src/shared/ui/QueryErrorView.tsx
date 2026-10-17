import { ApiClientError } from '../api/client';
import { ErrorState, ForbiddenState, NotFoundState, OfflineState } from './StateViews';

/**
 * Wählt den Pflichtzustand (ui.md §2) zum Fehler einer Abfrage:
 * Netzwerk → Offline · 403 → Forbidden · 404 → NotFound · sonst Fehler mit „Erneut versuchen“.
 * Eingebettet (h2); die Seite besitzt ihre eigene h1.
 */
export function QueryErrorView({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  if (error instanceof ApiClientError) {
    if (error.isNetwork) return <OfflineState />;
    if (error.status === 403) return <ForbiddenState />;
    if (error.status === 404) return <NotFoundState />;
  }
  return <ErrorState onRetry={onRetry} />;
}
