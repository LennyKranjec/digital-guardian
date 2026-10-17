import { useTranslation } from 'react-i18next';

import { useFreeTexts } from '../hooks/useFreeText';
import { mentionsFor } from '../model/freetext';
import { formatAbsolute } from '../model/time';

interface FreeTextMentionsProps {
  patientId: string;
  /** Symptome, an denen die Meldung bzw. der CTCAE-Begriff beteiligt ist */
  symptomKeys: readonly string[];
  locale: string;
}

/**
 * „Patientin schrieb: ‚…‘ (Datum, Modus, bestätigt durch Antwort ja/nein)“ zu den beteiligten Symptomen
 * (T-22). Nur Anzeige für die Ärztin: kein Gradvorschlag, nichts davon geht in Regeln oder Triage.
 * Ohne Freitexte, bei Ladefehler oder ausgeschaltetem Freitext erscheint nichts.
 */
export function FreeTextMentions({ patientId, symptomKeys, locale }: FreeTextMentionsProps) {
  const { t } = useTranslation();
  const query = useFreeTexts(patientId);
  const mentions = mentionsFor(query.data ?? [], symptomKeys);
  if (mentions.length === 0) return null;
  return (
    <ul
      className="m-0 list-none space-y-1 rounded-md border border-dashed border-border-strong p-2 text-base"
      data-testid="free-text-mentions"
    >
      {mentions.map(({ item, suggestion }) => (
        <li key={`${item.free_text_id}:${suggestion.symptom_key}:${suggestion.start}`}>
          {t('waechter.clinic.freeText.wrote', {
            quote: suggestion.quote,
            date: formatAbsolute(item.created_at, locale),
            mode: t(`waechter.clinic.freeText.modes.${item.mode}`),
            confirmed: t(
              suggestion.confirmed ? 'waechter.clinic.freeText.yes' : 'waechter.clinic.freeText.no',
            ),
          })}
        </li>
      ))}
    </ul>
  );
}
