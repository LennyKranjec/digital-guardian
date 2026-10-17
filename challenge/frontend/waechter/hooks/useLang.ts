import { useTranslation } from 'react-i18next';

import { toLang, type Lang } from '../api/client';

/** Aktive UI-Sprache als Vertragssprache (cs/en/de) – Teil jedes Abfrageschlüssels, damit ein Sprachwechsel neu lädt. */
export function useLang(): Lang {
  const { i18n } = useTranslation();
  return toLang(i18n.resolvedLanguage ?? i18n.language);
}
