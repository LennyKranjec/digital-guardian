import { describe, expect, it } from 'vitest';

import { ApiClientError } from '../../../../platform/frontend/src/shared/api/client';
import {
  SESSION_META_KEY,
  SESSION_STORAGE_KEY,
  clearSessionMeta,
  metaExpired,
  readSessionMeta,
  writeSessionMeta,
  clearClientSessionId,
  dueView,
  ensureClientSessionId,
  escalationView,
  hasPlaceholder,
  questionNumber,
  readClientSessionId,
  safeUrl,
  sessionErrorAction,
  visiblePhone,
  visibleText,
  writeClientSessionId,
} from './session';

function memoryStorage(initial: Record<string, string> = {}) {
  const data = new Map(Object.entries(initial));
  return {
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => void data.set(key, value),
    removeItem: (key: string) => void data.delete(key),
    data,
  };
}

const throwing = {
  getItem: () => {
    throw new Error('gesperrt');
  },
  setItem: () => {
    throw new Error('gesperrt');
  },
  removeItem: () => {
    throw new Error('gesperrt');
  },
};

describe('Sitzungskennung im sessionStorage', () => {
  it('erzeugt eine UUID, speichert sie und liefert danach dieselbe', () => {
    const storage = memoryStorage();
    const first = ensureClientSessionId(storage);
    expect(first).toMatch(/^[0-9a-f-]{36}$/);
    expect(storage.data.get(SESSION_STORAGE_KEY)).toBe(first);
    expect(ensureClientSessionId(storage)).toBe(first);
    expect(readClientSessionId(storage)).toBe(first);
  });

  it('kann überschrieben und gelöscht werden', () => {
    const storage = memoryStorage({ [SESSION_STORAGE_KEY]: 'alt' });
    writeClientSessionId('neu', storage);
    expect(readClientSessionId(storage)).toBe('neu');
    clearClientSessionId(storage);
    expect(readClientSessionId(storage)).toBeNull();
  });

  it('bleibt bei gesperrtem Speicher ohne Ausnahme (try/catch)', () => {
    expect(readClientSessionId(throwing)).toBeNull();
    expect(() => writeClientSessionId('x', throwing)).not.toThrow();
    expect(() => clearClientSessionId(throwing)).not.toThrow();
    expect(ensureClientSessionId(throwing)).toMatch(/^[0-9a-f-]{36}$/);
  });

  it('behandelt einen leeren gespeicherten Wert wie keinen', () => {
    expect(readClientSessionId(memoryStorage({ [SESSION_STORAGE_KEY]: '' }))).toBeNull();
  });
});

describe('Fehlerbehandlung der Sitzung', () => {
  const err = (status: number, code = 'x') => new ApiClientError(status, code, code);

  it.each([
    [err(409, 'not_current_question'), 'answer', 'reload'],
    [err(409, 'session_closed'), 'answer', 'restart'],
    [err(404, 'not_found'), 'start', 'fallback'],
    [err(501, 'not_implemented'), 'start', 'fallback'],
    [err(404, 'not_found'), 'answer', 'generic'],
    [err(0, 'network'), 'answer', 'network'],
    [err(403, 'forbidden'), 'start', 'forbidden'],
    [err(401, 'unauthenticated'), 'answer', 'forbidden'],
    [err(422, 'invalid'), 'answer', 'invalid'],
    [err(500, 'boom'), 'start', 'generic'],
    [new Error('irgendwas'), 'start', 'generic'],
  ] as const)('%#: %s (%s) ⇒ %s', (error, phase, expected) => {
    expect(sessionErrorAction(error, phase)).toBe(expected);
  });
});

describe('Platzhalter und Eskalation', () => {
  it('erkennt Platzhalter in eckigen Klammern und blendet sie aus', () => {
    expect(hasPlaceholder('[Telefon der Ambulanz]')).toBe(true);
    expect(hasPlaceholder('Telefon 155')).toBe(false);
    expect(visiblePhone('[Telefon der Ambulanz]')).toBeNull();
    expect(visiblePhone('  ')).toBeNull();
    expect(visiblePhone(null)).toBeNull();
    expect(visiblePhone(' +420 123 456 789 ')).toBe('+420 123 456 789');
    expect(visibleText('Rufen Sie 155 an [Nummer der Ambulanz folgt].')).toBe('Rufen Sie 155 an .');
    expect(visibleText('[Text der Klinik folgt]')).toBe('');
  });

  it('bereitet die Eskalation auf: Stufe, Text ohne Platzhalter, Telefon nur echt', () => {
    expect(
      escalationView({ level: 'acute', text: 'Rufen Sie 155 an.', ambulance_phone: '[Telefon]' }),
    ).toEqual({ acute: true, text: 'Rufen Sie 155 an.', phone: null });
    expect(escalationView({ level: 'general', text: '[folgt]' })).toEqual({
      acute: false,
      text: '',
      phone: null,
    });
  });

  it('verlinkt nur http(s)', () => {
    expect(safeUrl('https://www.sukl.cz')).toBe('https://www.sukl.cz');
    expect(safeUrl('http://a.b')).toBe('http://a.b');
    expect(safeUrl('javascript:alert(1)')).toBeNull();
    expect(safeUrl('data:text/html,x')).toBeNull();
    expect(safeUrl(null)).toBeNull();
  });
});

describe('Fortschritt und Fälligkeit', () => {
  it('zählt die angezeigte Frage und hält max nur als Obergrenze', () => {
    expect(questionNumber({ asked: 0, max: 8 })).toEqual({ current: 1, max: 8 });
    expect(questionNumber({ asked: 3, max: 8 })).toEqual({ current: 4, max: 8 });
    // Server überschreitet die Obergrenze nie, aber die Anzeige bleibt konsistent
    expect(questionNumber({ asked: 8, max: 8 })).toEqual({ current: 9, max: 9 });
  });

  it('liest die Fälligkeit tolerant', () => {
    expect(dueView(null)).toBeNull();
    expect(dueView({})).toBeNull();
    expect(dueView({ next_due_at: '2026-10-18T09:00:00+02:00' })).toEqual({
      overdue: false,
      at: '2026-10-18T09:00:00+02:00',
    });
    expect(dueView({ overdue: true })).toEqual({ overdue: true, at: null });
  });
});

describe('Beleg-Kennungen nach dem Stopp (v2.5)', () => {
  it('speichert nur Kennung, Zustand und Fälligkeit und liest sie wieder', () => {
    const storage = memoryStorage();
    writeSessionMeta(
      { sessionId: 'sess-1', closed: true, until: '2026-10-20T09:00:00+02:00' },
      storage,
    );
    expect(JSON.parse(storage.data.get(SESSION_META_KEY) ?? '{}')).toEqual({
      sessionId: 'sess-1',
      closed: true,
      until: '2026-10-20T09:00:00+02:00',
    });
    expect(readSessionMeta(storage)).toEqual({
      sessionId: 'sess-1',
      closed: true,
      until: '2026-10-20T09:00:00+02:00',
    });
    clearSessionMeta(storage);
    expect(readSessionMeta(storage)).toBeNull();
  });

  it('liest beschädigte oder fremde Werte als „nichts gespeichert“ und überlebt gesperrten Speicher', () => {
    expect(readSessionMeta(memoryStorage({ [SESSION_META_KEY]: 'kein json' }))).toBeNull();
    expect(readSessionMeta(memoryStorage({ [SESSION_META_KEY]: '{"sessionId":5}' }))).toBeNull();
    expect(readSessionMeta(memoryStorage({ [SESSION_META_KEY]: '{"sessionId":""}' }))).toBeNull();
    expect(readSessionMeta(throwing)).toBeNull();
    expect(() =>
      writeSessionMeta({ sessionId: 'x', closed: false, until: null }, throwing),
    ).not.toThrow();
    expect(() => clearSessionMeta(throwing)).not.toThrow();
  });

  it('läuft nach der nächsten Fälligkeit ab – nur mit bekannter Serverzeit und nur beendete Sitzungen', () => {
    const closed = { sessionId: 's', closed: true, until: '2026-10-20T09:00:00+02:00' };
    expect(metaExpired(closed, new Date('2026-10-19T09:00:00+02:00'))).toBe(false);
    expect(metaExpired(closed, new Date('2026-10-20T09:00:00+02:00'))).toBe(true);
    expect(metaExpired(closed, new Date('2026-10-21T09:00:00+02:00'))).toBe(true);
    expect(metaExpired(closed, null)).toBe(false); // ohne Serverzeit nie ablaufen (keine Browseruhr)
    expect(metaExpired({ ...closed, closed: false }, new Date('2030-01-01T00:00:00Z'))).toBe(false);
    expect(metaExpired({ ...closed, until: null }, new Date('2030-01-01T00:00:00Z'))).toBe(false);
    expect(metaExpired({ ...closed, until: 'kein datum' }, new Date('2030-01-01T00:00:00Z'))).toBe(
      false,
    );
  });

  it('behandelt 404 beim Beleg-Abruf als „vergessen“, andere Fehler nicht', () => {
    expect(sessionErrorAction(new ApiClientError(404, 'nf', 'nf'), 'resume')).toBe('restart');
    expect(sessionErrorAction(new ApiClientError(0, 'network', 'x'), 'resume')).toBe('network');
    expect(sessionErrorAction(new ApiClientError(500, 'boom', 'x'), 'resume')).toBe('generic');
    expect(sessionErrorAction(new ApiClientError(403, 'f', 'x'), 'resume')).toBe('forbidden');
  });
});
