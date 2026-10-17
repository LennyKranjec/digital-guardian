import { useQuery } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';

import { getConfig, getTimeline, type TimelineRange } from '../api/client';
import { useLang } from './useLang';

export function useTimeline(patientId: string, range: TimelineRange | null) {
  const lang = useLang();
  return useQuery({
    queryKey: ['waechter', 'timeline', patientId, range?.from ?? null, range?.to ?? null, lang],
    queryFn: ({ signal }) => getTimeline(patientId, range ?? {}, lang, signal),
    enabled: range !== null,
  });
}

/** Aktive Konfiguration (Regeln, Bericht, Regime, Fragebogen-Items) in der UI-Sprache. */
export function useConfig() {
  const lang = useLang();
  return useQuery({
    queryKey: ['waechter', 'config', lang],
    queryFn: ({ signal }) => getConfig(lang, signal),
    staleTime: 60_000,
    retry: false,
  });
}

/** Aktive Regeln für die Schwellenlinien; ein Ausfall verhindert den Verlauf nicht (dann ohne Schwelle). */
export function useRules() {
  const lang = useLang();
  return useQuery({
    queryKey: ['waechter', 'config', lang],
    queryFn: ({ signal }) => getConfig(lang, signal),
    select: (bundle) => bundle.rules,
    staleTime: 60_000,
    retry: false,
  });
}

const FALLBACK_WIDTH = 600;
const MIN_WIDTH = 260;

/** Breite eines Elements in Pixeln, damit SVG-Beschriftung in echten 16 px gezeichnet wird. */
export function useElementWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(FALLBACK_WIDTH);

  useEffect(() => {
    const element = ref.current;
    if (!element) return undefined;
    const update = () => {
      const measured = Math.round(element.getBoundingClientRect().width);
      if (measured > 0) setWidth(Math.max(MIN_WIDTH, measured));
    };
    update();
    if (typeof ResizeObserver === 'undefined') return undefined;
    const observer = new ResizeObserver(update);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  return { ref, width };
}
