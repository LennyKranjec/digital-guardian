import { useTranslation } from 'react-i18next';
import { Link, Navigate, Outlet, useLocation } from 'react-router-dom';

import { homeFor } from '../../registry';
import { ErrorState, ForbiddenState, SkeletonBlock } from '../../shared/ui/StateViews';
import { useMe } from './api';

/**
 * Routen-Wächter. Reine Navigationshilfe: die verbindliche Autorisierung liegt serverseitig;
 * jede API-Antwort wird dort pro Rolle und Objekt geprüft. Ohne `roles` genügt eine Anmeldung.
 */
export function RequireRole({ roles }: { roles?: readonly string[] }) {
  const { t } = useTranslation();
  const location = useLocation();
  const me = useMe();

  if (me.isPending) return <SkeletonBlock lines={3} />;
  if (me.isError) return <ErrorState headingLevel={1} onRetry={() => void me.refetch()} />;
  if (me.data === null) {
    const from = `${location.pathname}${location.search}`;
    return <Navigate to="/login" replace state={{ from }} />;
  }
  if (roles && !roles.includes(me.data.role)) {
    return (
      <ForbiddenState
        headingLevel={1}
        action={
          <Link
            to={homeFor(me.data.role)}
            className="inline-flex min-h-11 items-center rounded-md border border-border-strong bg-surface px-5 font-semibold text-ink hover:bg-sunken"
          >
            {t('auth.toMyArea')}
          </Link>
        }
      />
    );
  }
  return <Outlet />;
}
