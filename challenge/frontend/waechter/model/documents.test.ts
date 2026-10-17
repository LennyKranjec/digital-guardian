import { describe, expect, it } from 'vitest';

import { ApiClientError } from '../../../../platform/frontend/src/shared/api/client';
import { DOCUMENT_MAX_BYTES } from '../api/documents';
import { documentErrorKey, fileProblem, valueText } from './documents';

describe('Dokument-Hochladen (T-21): Dateiprüfung vor dem Senden', () => {
  it('lässt Text, Markdown und CSV bis 200 kB zu', () => {
    expect(fileProblem('brief.txt', 10)).toBeNull();
    expect(fileProblem('Brief.MD', 10)).toBeNull();
    expect(fileProblem('labor.csv', DOCUMENT_MAX_BYTES)).toBeNull();
  });

  it('lehnt PDF, andere Formate, zu große und leere Dateien ab', () => {
    expect(fileProblem('scan.pdf', 10)).toBe('pdf');
    expect(fileProblem('bild.png', 10)).toBe('format');
    expect(fileProblem('labor.csv', DOCUMENT_MAX_BYTES + 1)).toBe('tooLarge');
    expect(fileProblem('leer.txt', 0)).toBe('empty');
  });
});

describe('Dokument-API: Fehlerschlüssel', () => {
  it.each([
    [new ApiClientError(0, 'network_error', 'x'), 'network'],
    [new ApiClientError(403, 'forbidden', 'x'), 'forbidden'],
    [new ApiClientError(404, 'not_found', 'x'), 'notFound'],
    [new ApiClientError(409, 'not_synthetic', 'x'), 'notSynthetic'],
    [new ApiClientError(409, 'already_decided', 'x'), 'conflict'],
    [new ApiClientError(413, 'document_too_large', 'x'), 'tooLarge'],
    [new ApiClientError(415, 'pdf_not_supported', 'x'), 'pdf'],
    [new ApiClientError(415, 'unsupported_format', 'x'), 'format'],
    [new ApiClientError(422, 'empty_document', 'x'), 'invalid'],
    [new ApiClientError(500, 'internal', 'x'), 'generic'],
    [new Error('boom'), 'generic'],
  ])('%#', (error, key) => {
    expect(documentErrorKey(error)).toBe(key);
  });

  it('formatiert Wert und Einheit', () => {
    expect(valueText('108', 'g/l')).toBe('108 g/l');
    expect(valueText('108', null)).toBe('108');
    expect(valueText(null, 'g/l')).toBe('');
  });
});
