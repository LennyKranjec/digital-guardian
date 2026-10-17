# Verifikation INT-4a (Integration 4a)

- Prüfer: A3 · Sa 17.10.2026, ~00:50 · Stufe: **INTEGRATION** (Punkte 1, 10, Herkunft)
- Stand: `int/4a` 4fe1c03 (= main 6588416 + feat/T-17, feat/F-12, verify/T-13/T-14/T-17/F-08/F-10/F-11/F-12, fix/nav-wrap); Branch `verify/INT-4a` ohne eigene Änderung
- Ergebnis: **PASS**

## Ausgeführte Befehle (eigener Lauf in Abschnitten, Skript wie A0, PYTEST_DEBUG_TEMPROOT=C:\rk\tmp\a3, Ports 8300/5473)

| Schritt | Ergebnis |
|---|---|
| ruff check / format --check / mypy | rc 0 |
| pytest tests/backend + challenge/content + challenge/knowledge | 188 passed (20 s) |
| pytest challenge-A (jede 2. Datei) | 710 passed, 5 xfailed (479 s) |
| pytest challenge-B | 591 passed, 10 xfailed (408 s) |
| eslint, prettier --check, tsc ×3 | rc 0 |
| vitest | 627 + 57 passed |
| vite build | rc 0 |
| Playwright (`npm run e2e`) | 142 passed (2,1 min) |
| Gesamt | „ALLES GRÜN“, Zahlen identisch zu A0 (188/710+5/591+10/627+57/142) |

## xfail-Zuordnung (15 = 5 + 10)

| Anzahl | Test | Befund | Behebung |
|---|---|---|---|
| 4 | test_a3_t09f (rote Regel auf Kombination ohne Antworten) | T-09F F-01 Medium | T-09G |
| 3 | test_a3_t07f (Neukombination über Zitate) | T-07F F-01 Medium | T-07G |
| 1 | test_a3_t13 (Replay-Beleg stabil) | T-13 F-01 Low | T-16 |
| 2 | test_a3_t14 (Gittergröße ≤ max_product) | T-14 F-01 Medium | T-14F/T-15 (H3) |
| 4 | test_a3_t14 (Eskalationssymptome verdecken Rot) | T-14 F-03 Medium | T-14F/T-15 |
| 1 | test_a3_t14 (Unicode-Ziffern) | T-14 F-02 Low | T-14F/T-15 |

Alle 15 sind dokumentierte, bekannte offene Punkte; keiner ist unerklärt.

## Herkunft

- `provenance.py`: 283 Commits nach der Grenze, 6 berühren `platform`, **0 ohne `platform-fix:`** (der 7. Eintrag von `git log` ist der Merge int/3, PROVENANCE §5 vorhanden).
- `challenge/` enthält nur Wettbewerbsdateien; keine Änderungen in `scripts/.github` außer den bekannten platform-fix-Commits.

## Befunde

Keine. NOT RUN: F-10F (nicht in 4a), T-15/T-16 (noch nicht gemergt), Gesamtlauf `scripts/test.ps1 -E2e` als ein Befehl (Abschnitte wie vereinbart).

main kann auf int/4a 4fe1c03 vorgespult werden.
