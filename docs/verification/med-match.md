# Verifikation fix/med-match (KURZ)

- Prüfer: A3 · Sa 17.10.2026, ~02:45 · Stufe: **KURZ** (Punkte 1, 2, 6, 8)
- Stand: `fix/med-match` fce2afa auf `verify/F-11F` (Branch `verify/med-match`)
- Ergebnis: **PASS**

## Änderung

`'id'` in `MEDICATION_MATCHES` (api/client.ts) und die Beschriftung „direkter Aufruf“ in cs/en/de (4 Dateien, 22 Zeilen). Behebt T-15 F-01.

## Ausgeführt

| Befehl | Ergebnis |
|---|---|
| Playwright `medications-a3 medications-ui ui-checks` (echtes T-15-Backend, Detailseite) | 48 passed (vorher medications-a3 „Detailseite“ rot) |
| `vitest run Medications.test.tsx` | 20 passed |
| eslint challenge/frontend, tsc -p platform/frontend | grün |
| Sprache/Verbotsliste | Beschriftung „direkter Aufruf“/„direct lookup“ ohne Verbotswörter; wird nur bei Suchtreffern gezeigt, die Detailseite zeigt `match` nicht |

## Befunde

Keine. F-01 aus T-15 ist behoben. NOT RUN: Gesamtlauf (Teillauf).
