import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router-dom';

import { Button } from '../../../../platform/frontend/src/shared/ui/Button';
import { toLang } from '../api/client';
import { useNotifications, useSeenNotifications } from '../hooks/useWorklist';
import { bannerNotifications } from '../model/notifications';
import { formatAbsolute } from '../model/time';
import { TrafficLight } from './TrafficLight';

/**
 * Sofortbenachrichtigungen als Banner (mit `collapsible` auf eine Zeile einklappbar, z. B. im
 * Cockpit, wo der Platz für Lage, Meldungen und Kurzfassung gebraucht wird; die Arbeitsliste zeigt es
 * immer ausgeklappt): rote, noch nicht als „gesehen“ markierte Meldungen,
 * Abfrage alle 30 s. Der Text enthält nur das Pseudonym (Vertrag G-17). Ein Ladefehler wird
 * sichtbar gemeldet, damit eine rote Meldung nicht still ausbleibt.
 */
export function NotificationBanner({ collapsible = false }: { collapsible?: boolean }) {
  const { t, i18n } = useTranslation();
  const query = useNotifications();
  const { seen, markSeen } = useSeenNotifications();
  const locale = toLang(i18n.resolvedLanguage ?? i18n.language);
  const visible = bannerNotifications(query.data ?? [], seen);
  const [open, setOpen] = useState(false);
  const folded = collapsible && !open;

  if (visible.length === 0 && !query.isError) return null;

  return (
    <section
      aria-label={t('waechter.clinic.banner.title')}
      data-testid="notification-banner"
      className={collapsible ? 'mb-3 space-y-2' : 'mb-6 space-y-3'}
    >
      {query.isError ? (
        <div
          role="alert"
          className="flex flex-wrap items-center gap-3 rounded-md border border-danger bg-surface p-4"
        >
          <p className="min-w-0 flex-1 text-base font-semibold">
            {t('waechter.clinic.banner.error')}
          </p>
          <Button variant="secondary" onClick={() => void query.refetch()}>
            {t('states.retry')}
          </Button>
        </div>
      ) : null}
      {collapsible && visible.length > 0 ? (
        <div className="flex flex-wrap items-center gap-3 rounded-md border-2 border-danger bg-surface px-3 py-1">
          <TrafficLight level="red" />
          <p className="m-0 min-w-0 flex-1 text-base font-semibold" data-testid="banner-count">
            {t('waechter.clinic.banner.count', { count: visible.length })}
          </p>
          <Button
            variant="secondary"
            aria-expanded={!folded}
            aria-controls="banner-list"
            onClick={() => setOpen((value) => !value)}
          >
            {folded ? t('waechter.clinic.banner.show') : t('waechter.clinic.banner.hide')}
          </Button>
        </div>
      ) : null}
      {visible.length > 0 && !folded ? (
        <ul id="banner-list" className="space-y-3" aria-live="polite">
          {visible.map((entry) => (
            <li
              key={entry.notification_id}
              data-testid="notification-item"
              className="flex flex-wrap items-center gap-3 rounded-md border-2 border-danger bg-surface p-4"
            >
              <TrafficLight level="red" />
              <div className="min-w-0 flex-1 space-y-1">
                <p className="break-words text-base font-semibold">{entry.text}</p>
                <p className="text-base text-muted">{formatAbsolute(entry.at, locale)}</p>
              </div>
              <Link
                to={`/clinic/patients/${encodeURIComponent(entry.patient_id)}`}
                className="inline-flex min-h-11 min-w-11 items-center justify-center rounded-md bg-accent px-5 py-2 text-base font-semibold text-on-accent hover:bg-accent-hover"
              >
                {t('waechter.clinic.banner.open')}
              </Link>
              <Button variant="secondary" onClick={() => markSeen(entry.notification_id)}>
                {t('waechter.clinic.banner.seen')}
              </Button>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
