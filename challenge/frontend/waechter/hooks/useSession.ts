import { useCallback, useEffect, useRef, useState } from 'react';

import {
  answerSession,
  getSession,
  newSubmissionId,
  startSession,
  undoSession,
  type Lang,
  type SessionAnswer,
  type SessionStep,
} from '../api/client';
import {
  clearClientSessionId,
  clearSessionMeta,
  ensureClientSessionId,
  metaExpired,
  readSessionMeta,
  sessionErrorAction,
  writeClientSessionId,
  writeSessionMeta,
  type SessionErrorAction,
} from '../model/session';
import { useLang } from './useLang';
import { useServerNow } from './useServerNow';

export type SessionState =
  | { phase: 'loading' }
  | { phase: 'ask'; step: SessionStep }
  | { phase: 'done'; step: SessionStep }
  | { phase: 'error'; action: SessionErrorAction; step: SessionStep | null }
  | { phase: 'fallback' };

/**
 * Adaptiver Check-in: startet bzw. setzt die Sitzung fort (gleiche `client_session_id` nach Neuladen),
 * sendet je Karte genau eine Antwort und übernimmt die nächste Frage oder den Stopp vom Server.
 *
 * Beleg nie verlieren (Vertrag v2.5, DR-029): Nach dem Stopp bleiben nur die Kennungen im sessionStorage
 * (nie Antworten oder Beleg). Beim Öffnen holt `GET /me/sessions/{id}` zuerst den Beleg (Akut-Hinweis oben);
 * bei 409 `session_closed` wird ebenfalls zuerst der Beleg geholt, nie still eine neue Sitzung gestartet.
 * Eine neue Sitzung beginnt nur mit „Neuer Check-in“ (oder nach der nächsten Fälligkeit).
 * 409 `not_current_question` ⇒ Sitzung mit derselben Kennung neu laden.
 */
export function useSession() {
  const lang: Lang = useLang();
  const serverNow = useServerNow();
  const [state, setState] = useState<SessionState>({ phase: 'loading' });
  const [isSending, setIsSending] = useState(false);
  const mounted = useRef(true);
  const lastStep = useRef<SessionStep | null>(null);
  const sessionId = useRef<string | null>(null);
  const nowRef = useRef<Date | null>(serverNow);
  nowRef.current = serverNow;
  /** Beleg stammt aus dem Speicher (Neuladen), nicht von einem eben beendeten Check-in */
  const restored = useRef(false);

  const apply = useCallback((step: SessionStep, fromStorage = false) => {
    restored.current = fromStorage && !step.next;
    lastStep.current = step;
    sessionId.current = step.session_id;
    if (step.next) {
      writeSessionMeta({ sessionId: step.session_id, closed: false, until: null });
      setState({ phase: 'ask', step });
    } else {
      // beendet: Kennungen bleiben bis „Neuer Check-in“ bzw. zur nächsten Fälligkeit (nur die Kennung, nie der Beleg)
      writeSessionMeta({
        sessionId: step.session_id,
        closed: true,
        until: step.due?.next_due_at ?? null,
      });
      setState({ phase: 'done', step });
    }
  }, []);

  const start = useCallback(
    (options: { fresh?: boolean } = {}) => {
      let clientSessionId: string | null = null;
      if (options.fresh) {
        lastStep.current = null;
        sessionId.current = null;
        clearSessionMeta();
        clientSessionId = newSubmissionId();
        writeClientSessionId(clientSessionId);
      }
      setState({ phase: 'loading' });

      const fail = (error: unknown, phase: 'start' | 'resume') => {
        if (!mounted.current) return;
        const action = sessionErrorAction(error, phase);
        if (action === 'fallback') setState({ phase: 'fallback' });
        else if (action === 'restart') start({ fresh: true });
        else setState({ phase: 'error', action, step: null });
      };

      // beendete Sitzung im Speicher ⇒ zuerst den Beleg abrufen (Neuladen, Zurück/Vorwärts)
      const meta = options.fresh ? null : readSessionMeta();
      if (meta?.closed && !metaExpired(meta, nowRef.current)) {
        getSession(meta.sessionId)
          .then((step) => {
            if (mounted.current) apply(step, true);
          })
          .catch((error: unknown) => fail(error, 'resume'));
        return;
      }
      if (meta?.closed) {
        // nach der nächsten Fälligkeit beginnt ein neuer Check-in
        clearSessionMeta();
        clearClientSessionId();
      }

      clientSessionId ??= ensureClientSessionId();
      startSession(clientSessionId, lang)
        .then((step) => {
          if (mounted.current) apply(step);
        })
        .catch((error: unknown) => fail(error, 'start'));
    },
    [apply, lang],
  );

  // Start beim Einhängen und nach Sprachwechsel (idempotent: dieselbe Sitzung, neu lokalisiert)
  useEffect(() => {
    mounted.current = true;
    // Eine beendete Sitzung wird nach Sprachwechsel nicht neu gestartet (der Beleg bleibt stehen)
    if (!(lastStep.current && !lastStep.current.next)) start();
    return () => {
      mounted.current = false;
    };
  }, [start]);

  // Fälligkeit des wiederhergestellten Belegs erneut prüfen, sobald die Serverzeit eintrifft (A3 F-10F F-01):
  // beim harten Neuladen ist /meta beim Start meist noch nicht da. Ohne Serverzeit wird nie automatisch verworfen,
  // und ein eben beendeter Check-in verschwindet nie von selbst.
  useEffect(() => {
    if (state.phase !== 'done' || !restored.current || !serverNow) return;
    const meta = readSessionMeta();
    const due = state.step.due?.next_due_at ?? meta?.until ?? null;
    if (metaExpired({ sessionId: state.step.session_id, closed: true, until: due }, serverNow)) {
      clearSessionMeta();
      clearClientSessionId();
      start({ fresh: true });
    }
  }, [serverNow, state, start]);

  /** Beleg/Stand der Sitzung vom Server holen (nach 409 session_closed, nie still neu starten). */
  const resume = useCallback(
    (id: string) => {
      setState({ phase: 'loading' });
      getSession(id)
        .then((step) => {
          if (mounted.current) apply(step);
        })
        .catch((error: unknown) => {
          if (!mounted.current) return;
          const action = sessionErrorAction(error, 'resume');
          if (action === 'restart') start({ fresh: true });
          else setState({ phase: 'error', action, step: null });
        });
    },
    [apply, start],
  );

  const answer = useCallback(
    (body: SessionAnswer) => {
      const id = sessionId.current;
      if (!id || isSending) return;
      setIsSending(true);
      answerSession(id, body)
        .then((step) => {
          if (mounted.current) apply(step);
        })
        .catch((error: unknown) => {
          if (!mounted.current) return;
          const action = sessionErrorAction(error, 'answer');
          if (action === 'reload') start();
          else if (action === 'restart') resume(id);
          else setState({ phase: 'error', action, step: lastStep.current });
        })
        .finally(() => {
          if (mounted.current) setIsSending(false);
        });
    },
    [apply, isSending, resume, start],
  );

  /** Zurück-Pfeil: letzte Antwort zurücknehmen; 409 `session_closed` ⇒ Stand/Beleg neu laden. */
  const undo = useCallback(() => {
    const id = sessionId.current;
    const steps = lastStep.current?.progress.asked ?? 0;
    if (!id || isSending || steps < 1) return;
    setIsSending(true);
    undoSession(id, steps)
      .then((step) => {
        if (mounted.current) apply(step);
      })
      .catch((error: unknown) => {
        if (!mounted.current) return;
        const action = sessionErrorAction(error, 'answer');
        if (action === 'reload') start();
        else if (action === 'restart') resume(id);
        else setState({ phase: 'error', action, step: lastStep.current });
      })
      .finally(() => {
        if (mounted.current) setIsSending(false);
      });
  }, [apply, isSending, resume, start]);

  return {
    state,
    isSending,
    answer,
    undo,
    reload: () => start(),
    /** Knopf „Neuer Check-in“ auf der Abschlussseite: neue Kennung, neue Sitzung */
    newCheckin: () => start({ fresh: true }),
  };
}
