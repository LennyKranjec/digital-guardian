import { useEffect, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';

import { ApiClientError } from '../../../../platform/frontend/src/shared/api/client';
import { Button } from '../../../../platform/frontend/src/shared/ui/Button';
import { LinkButton } from '../../../../platform/frontend/src/shared/ui/LinkButton';
import {
  ForbiddenState,
  SkeletonBlock,
} from '../../../../platform/frontend/src/shared/ui/StateViews';
import { MedicationCard } from '../components/MedicationCard';
import { useLang } from '../hooks/useLang';
import { useMedicationSearch } from '../hooks/useMedications';
import { useConfig } from '../hooks/useTimeline';
import { MAX_QUERY_LENGTH, SEARCH_DEBOUNCE_MS, canSearch, cleanQuery } from '../model/medications';

/** Ehrlicher Hinweis zur Reichweite des Katalogs (Vertrag v2.3 §8): Auswahl, kein vollständiges Register. */
export function MedicationNote() {
  const { t } = useTranslation();
  return (
    <p className="text-base text-muted" data-testid="medication-note">
      {t('waechter.clinic.medications.note')}
    </p>
  );
}

/**
 * Arzneimittelsuche der Ärztin: ein Feld für Name, kódSÚKL oder ATC. Gesucht wird nach kurzer Pause
 * (≈ 250 ms) oder mit Enter, ab 2 Zeichen. Treffer, Reihenfolge und „gefunden über“ liefert der Server;
 * das Verzeichnis dient nur der Identifikation (bestimmt nie Fragen, Ampel oder Regeln).
 */
export function MedicationsPage() {
  const { t } = useTranslation();
  const lang = useLang();
  const config = useConfig();
  const [params, setParams] = useSearchParams();
  const initial = params.get('q') ?? '';
  const [text, setText] = useState(initial);
  const [committed, setCommitted] = useState(initial);
  const query = useMedicationSearch(committed);
  const searching = canSearch(committed);

  // Eingabepause ⇒ suchen
  useEffect(() => {
    const id = setTimeout(() => setCommitted(text), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(id);
  }, [text]);

  // Suchtext in der Adresse halten (Link aus dem Cockpit, Neuladen, Weitergeben)
  useEffect(() => {
    const clean = cleanQuery(committed);
    if (canSearch(committed)) setParams({ q: clean }, { replace: true });
    else if (params.has('q')) setParams({}, { replace: true });
    // nur auf den abgeschickten Suchtext reagieren
  }, [committed]);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setCommitted(text);
  }

  const status = query.error instanceof ApiClientError ? query.error.status : null;
  const results = query.data ?? [];

  return (
    <section aria-labelledby="medications-title" className="mx-auto w-full max-w-4xl space-y-4">
      <div className="space-y-2">
        <LinkButton to="/clinic">{t('waechter.clinic.alertPage.toList')}</LinkButton>
        <h1 id="medications-title" className="text-3xl font-bold leading-tight">
          {t('waechter.clinic.medications.title')}
        </h1>
        <p className="text-base text-muted">{t('waechter.clinic.medications.intro')}</p>
      </div>

      <form role="search" onSubmit={submit} className="space-y-2" data-testid="medication-search">
        <label htmlFor="medication-q" className="block text-base font-semibold">
          {t('waechter.clinic.medications.label')}
        </label>
        <div className="flex flex-wrap gap-2">
          <input
            id="medication-q"
            name="q"
            type="search"
            value={text}
            maxLength={MAX_QUERY_LENGTH}
            autoComplete="off"
            aria-describedby="medication-hint"
            onChange={(event) => setText(event.target.value)}
            className="min-h-11 min-w-0 flex-1 basis-56 rounded-md border border-border-strong bg-surface px-3 py-2 text-base text-ink"
          />
          <Button type="submit">{t('waechter.clinic.medications.search')}</Button>
        </div>
        <p id="medication-hint" className="m-0 text-base text-muted">
          {t('waechter.clinic.medications.hint')}
        </p>
      </form>

      <div aria-live="polite" className="space-y-3" data-testid="medication-results">
        {!searching ? (
          <p className="text-base text-muted" data-testid="medication-idle">
            {t('waechter.clinic.medications.idle')}
          </p>
        ) : null}
        {searching && query.isPending ? <SkeletonBlock lines={3} /> : null}
        {query.isError ? (
          status === 403 ? (
            <ForbiddenState />
          ) : status === 422 ? (
            <p
              role="alert"
              data-testid="medication-invalid"
              className="rounded-md border border-danger p-3 text-base font-semibold"
            >
              {t('waechter.clinic.medications.invalid')}
            </p>
          ) : (
            <div
              role="alert"
              data-testid="medication-error"
              className="space-y-2 rounded-md border border-danger p-3"
            >
              <p className="text-base font-semibold">{t('waechter.clinic.medications.error')}</p>
              <Button variant="secondary" onClick={() => void query.refetch()}>
                {t('states.retry')}
              </Button>
            </div>
          )
        ) : null}
        {searching && query.data && results.length === 0 ? (
          <p className="text-base font-semibold" data-testid="medication-empty">
            {t('waechter.clinic.medications.empty', { q: cleanQuery(committed) })}
          </p>
        ) : null}
        {searching && query.data && results.length === 0 ? (
          <p className="m-0 text-base text-muted" data-testid="medication-empty-sukl">
            {t('waechter.clinic.medications.emptySukl')}
          </p>
        ) : null}
        {results.length > 0 ? (
          <>
            <p role="status" className="m-0 text-base text-muted" data-testid="medication-count">
              {t('waechter.clinic.medications.count', { count: results.length })}
            </p>
            <ul className="m-0 list-none space-y-3 p-0">
              {results.map((medication) => (
                <li key={medication.medication_id}>
                  <MedicationCard medication={medication} config={config.data} lang={lang} />
                </li>
              ))}
            </ul>
          </>
        ) : null}
      </div>
      <MedicationNote />
    </section>
  );
}
