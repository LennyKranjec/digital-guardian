# Endprüfung INT-4b (INTEGRATION, vor Freeze Sa 07:30): int/4b f7f68f7

- Prüfer: A3 · Sa 17.10.2026, ~05:10 (MESZ) · Stufe: **INTEGRATION** (Punkte 1 und 10 auf dem Integrationscommit, Herkunft, Demo-Reset; T-09G und T-07G als KURZ im selben Lauf)
- Stand: `int/4b` f7f68f7 (Branch `verify/INT-4b-final`, ein Folgecommit von mir: `fhir-ui.spec.ts` mit Triage-Aufwärmen)
- Ergebnis: **PASS** (0 Critical/High/Medium offen; Hinweise unten)

## Ausgeführte Befehle (ein Lauf in Abschnitten, Rechner ruhig, Skript wie INT-4a)

| Schritt | Ergebnis |
|---|---|
| ruff check / format --check / mypy | rc 0 (mypy 167 Dateien) |
| pytest Plattform + content + knowledge | 222 passed (14,7 s) |
| pytest challenge-A | 1049 passed, 2 skipped, **0 xfailed** (11,8 min) |
| pytest challenge-B | 771 passed, 2 skipped, **0 xfailed** (14,5 min) |
| eslint, prettier --check, tsc ×3 | rc 0 |
| vitest | 693 + 57 passed (39 + 1 Dateien) |
| `vite build` | rc 0 |
| Playwright (`npm run e2e`) | 174 passed, **1 failed** (siehe H-1: Kaltstart in `fhir-ui`, mit Aufwärmen behoben, 2× wiederholt 8/8 grün) |

Alle bisherigen xfail-Tests (T-07F/T-07G, T-09F/T-09G, T-13, T-14, T-15, T-16) sind grün; keiner ist mehr offen. Alle Befunde der Berichte T-07 … T-20bG sind damit geschlossen oder als Hinweis dokumentiert.

## Herkunftsprotokoll (Pflicht vor Merge und Abgabe)

- `python scripts/provenance.py`: 412 Commits nach der Grenze, **6 berühren `platform`, 0 ohne `platform-fix:`**; Zonen: challenge 374 during-event + 1 pre-event (README), platform 156 pre-event, sonstige 111 + 27.
- `git log --name-status pre-rakathon..HEAD -- platform tests scripts .github`: 7 Einträge, 6 × `platform-fix:` mit Begründung (nav-wrap, tailwind-source, design-system-Test ×2, Ankerzeit, Plattform-E2E tolerant) + der int/3-Merge; alle in `provenance/PROVENANCE.md` §5 (8 Einträge). `git diff pre-rakathon..HEAD`: nur 7 Plattformdateien (Shell.tsx, index.css, design-system.test.tsx, playwright.config.ts, mobile.spec.ts, smoke.spec.ts, tsconfig.json), **keine** Dateien in `scripts/` oder `.github/`, keine Wurzeldateien geändert.
- `challenge/` zum Stichtag nur `README.md`; seit dem Start nur Wettbewerbsdateien.
- Ergebnis: **kein Herkunftsverstoß.**

## Demo-Reset-Endprüfung (Reproduzierbarkeit der Demo)

| Prüfung | Ergebnis |
|---|---|
| `challenge/demo/reset.ps1` zweimal hintereinander | beide Läufe identisch, Exit 0, „Demo bereit.“; 7 Patientinnen, Ampeln SYN-0001 rot (2) · 0002 grün · 0003 gelb (1) · 0004 grau (1) · 0005 rot (1) · 0006 rot (2) · 0007 gelb (2); 3 Sofortbenachrichtigungen; Triage-Profile (8) kompiliert und verifiziert; Kurzfassung SYN-0001 `fallback`, 12 Sätze, 0 verworfen |
| `challenge/demo/start.ps1 -Reset` (eigene Ports 8310/5483), danach Live-Durchlauf des Hauptpfads über die laufende Demo | Backend nach 5 s erreichbar; Arbeitsliste: SYN-0006/0001/0005 rot oben, 0007/0003 gelb, 0004 grau, 0002 grün; `patient2` meldet Fieber = ja (Sitzung, 2 Fragen) ⇒ Beleg mit Akut-Hinweis (155); `doctor`: SYN-0002 jetzt **rot**, Cockpit-Übersicht lädt (R-URG-01); danach Server beendet, Ports frei |
| Antwortzeiten nach Start | **Kaltstart**: erster Arbeitslistenabruf 7,9 s, `config/triage` 18,5 s, Anmeldung 1,9 s; danach alle Aufrufe < 0,1 s. Entspricht dem Runbook-Hinweis (Backend ≥ 1 min vorher starten) |

## Befunde / Hinweise

| Nr | Schwere | Beschreibung |
|---|---|---|
| H-1 | Low | **Kaltstart im E2E:** `fhir-ui.spec.ts` (A2b) lief als eine der ersten Specs in die Triage-Vorwärmung und überschritt das 5-s-Limit auf `cockpit-header` (Seite „Načítání“). Mit `warmTriage` in `beforeAll` behoben (Commit auf `verify/INT-4b-final`, 8/8 grün). Der Fehler ist reproduzierbar nur beim ersten Lauf nach Serverstart; im `npm run e2e` kann er ohne diesen Commit je nach Lastlage auftreten. **Bitte mergen.** |
| H-2 | Low | **Doku:** `challenge/demo/README.md` (Tabelle „Erwarteter Ausgangszustand“: 5 Patientinnen, „2 Sofortbenachrichtigungen“) und `DEMO_RUNBOOK.md` Punkt 2 stimmen nicht mehr mit dem Reset überein (jetzt 7 Patientinnen, 3 Benachrichtigungen; SYN-0006 rot, SYN-0007 gelb fehlen in der Tabelle). Den Wortlaut für die Bühne anpassen (A4). |
| H-3 | Info | **Kaltstart bleibt ein Demo-Risiko:** die Vorwärmung belegt für ≈ 14–45 s den Prozess; Anmeldung und erste Seiten sind in dieser Zeit langsam. Runbook-Schritt 5 (≥ 1 min vorher starten oder `config/triage` einmal öffnen) ist Pflicht. |
| H-4 | Info | Wortlaut-Grenzen für die Abgabe (aus meinen Berichten): „0 Untertriage“ nur als Umsetzungstreue unter dem Sitzungsmodell mit Platzhalter-Inhalten (12 000 Sitzungen, T-15); Fragenzahl „etwa 5–6 statt 14–17“; Wissensmatrix „Herkunft je Zeile (A1) + Zweitleser A3 (331 von 533 Häufigkeitsklassen, 533/533 Begriffe)“; Push nur gegen lokalen Testserver; Live-LLM nicht gelaufen; Pipeline-Prüfer auf echten SmPC-Tabellen nur 93/351 (konservativ); cs/de-Texte nicht muttersprachlich geprüft. |

## KURZ: T-09G und T-07G

- T-09G (rote Regel nur auf erfragte Kombination und Wertebereich): meine vier vorher strikt xfail-markierten Tests in `test_a3_t09f.py` laufen ohne Marker grün; Mutationsprobe (Erreichbarkeitsprüfung `_reachable` ⇒ `True`) ⇒ 4 Tests rot, zurückgesetzt.
- T-07G (ein Beleg je Satz, Richtungswörter an den Beleg gebunden): meine drei vorher xfail-markierten Tests in `test_a3_t07f.py` grün; Mutationsprobe (Ein-Beleg-Regel im Verifier entfernt) ⇒ 3 Tests rot, zurückgesetzt.

## NOT RUN

- Zweiter vollständiger Lauf auf einer frischen Maschine (nur dieser eine Lauf auf f7f68f7 zusätzlich zu den Läufen von A0).
- Live-LLM der Pipeline und der Zusammenfassung (Gateway 404), Push gegen einen echten FHIR-Server.
- Muttersprachliche Prüfung cs/de, Screenreader.
- Nach dem Freeze: erneute Herkunftsprüfung des letzten Commits auf main (bitte nach dem Merge wiederholen: `python scripts/provenance.py --out provenance/TABLE.md`).

## Empfehlung

main darf auf `int/4b` f7f68f7 plus meinen Commit (`fhir-ui` Aufwärmen, Branch `verify/INT-4b-final`) vorgespult werden.
