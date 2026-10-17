# Integrationsprüfung INT-5 (int/5 48180a5) – Endergebnis Sa 10:30

- Prüfer: A3 · Stufe INTEGRATION (Punkte 1 und 10 auf dem Integrationscommit) · Branch `verify/INT-5` (int/5 1294b1f + meine Test-/Berichtscommits)
- Ergebnis: **PASS_WITH_RISKS** (0 Critical/High/Medium offen; Low: F-03 Parallelrennen T-22, SQLite-`rowid`). Der High-Befund S5 (T-25-Zeile) ist mit T-25G behoben und nachgeprüft.

## Ausgeführt (Phasen parallel, 16 Kerne, danach Playwright)

| Schritt | Ergebnis |
|---|---|
| ruff, ruff format --check, mypy | rc 0 |
| pytest Plattform + content + knowledge | rc 0 (25 s) |
| pytest challenge-B | rc 0 (36 min unter Last) |
| pytest challenge-A | 1061 passed, 5 skipped, 6 xfailed, **1 failed** = `test_a3_same_instant_submissions_have_stable_order` (Gleichstand-Reihenfolge jetzt SQLite-`rowid` statt id; Test auf die neue Regel angepasst) |
| eslint, prettier, tsc ×3, vitest, `vite build` | rc 0 (vitest 73 s) |
| Playwright `npm run e2e` | 163 passed, **12 failed** (siehe unten) |
| T-22F gezielt (f553333): `test_a3_t22.py` + `test_a3_t22f.py` | 44 passed (F-01/F-02 behoben); die eine Meldung war mein F-03-xfail als XPASS (nun nicht strikt) |

## Befunde

### H-1 · **High** · S5 verletzt: Cockpit überschreitet 1366×768 (T-25)
- SYN-0001: `summary-panel` endet bei 782,8 px (Grenze 768), `timeline-compact` bei 876,8 px. 9 Tests rot: ui-checks S5 F-07 ×2, F-08 en/de, core-path 11, fhir-ui Admin, medications-ui, triage-a3, triage-ui.
- Ursache: T-25 `TrackedSymptoms` („Beobachtete Symptome: …“ mit allen ~12–14 englischen CTCAE-Begriffen) wird zweimal gerendert (`PatientCockpitPage.tsx` Z. 122 und `SummaryPanel.tsx` Z. 97), mehrzeilig. Auf INT-4b war S5 grün.
- Kleinste Korrektur: einmal und einzeilig (truncate + `title`) oder als eingeklapptes `<details>`; die Kopie im SummaryPanel entfernen.

### H-2 · Low · Gleichstand-Reihenfolge der eigenen Antworten ist SQLite-spezifisch
- `list_own` sortiert `(recorded_at desc, wa_responses.rowid desc)` (T-22); Vertrag G-08 (`contract/README.md` Z. 122) nennt `(recorded_at, response_id)`. Test angepasst, Vertragstext nachziehen; bei anderem DBMS (PostgreSQL) fehlt `rowid`.

### H-3 · Info · Mein Verbotslistentest auf der Patientenseite traf den Pflichthinweis
- Der NCI-Hinweis (DR-040: „PRO-CTCAE®“, „not for diagnostic … purposes“) enthält „ctcae“/„diagnos“. Test nimmt den Hinweis aus (`display:none`) und prüft, dass er vorhanden ist; 4 passed. Kein Produktfehler.

## NOT RUN / offen
- Wiederholung der 9 S5-Specs nach der Korrektur; Playwright-Gesamtlauf wurde einmal wegen Kaltstart des Frontends (60-s-Webserver-Limit unter Last) wiederholt.

## Endlauf auf int/5 48180a5 (nach T-25G)

| Schritt | Ergebnis |
|---|---|
| Playwright `npm run e2e` (vollständig, inkl. 375 px, Kernpfad, Freitext, Dokumente, Cockpit S5) | **175 passed, 0 failed** (3,6 min) |
| Die 6 vorher roten Spec-Dateien einzeln (ui-checks, core-path, fhir-ui, medications-ui, triage-a3, triage-ui) | 83 passed, 0 failed |
| Alle übrigen Phasen (ruff/format/mypy, pytest Plattform+content+knowledge, pytest challenge-A/B, eslint, prettier, tsc ×3, vitest, build) | grün auf 1294b1f; T-25G ändert nur Frontend (TrackedSymptoms, i18n, Test) und Doku (G-08) ⇒ keine erneute Backend-Wiederholung |
| T-22F f553333 gezielt | 44 passed (F-01, F-02 behoben) |
| Herkunft: `scripts/provenance.py`; `git log --name-status pre-rakathon..HEAD -- platform tests scripts .github`; `challenge/` zum Stichtag | 508 Commits nach der Grenze, **6 berühren `platform`, 0 ohne `platform-fix:`**; scripts/.github unberührt; `challenge/` zum Stichtag nur `README.md` ⇒ **kein Verstoß** |
| Demo-Reset | Exit 0, „Demo bereit.“: 7 Patientinnen, Ampeln SYN-0001 rot · 0002 grün · 0003 gelb · 0004 grau · 0005 rot · 0006 rot · 0007 gelb, 3 Sofortbenachrichtigungen, 8 Profile, Kurzfassung 12 Sätze/0 verworfen |

## PoC-Stand (alle auf int/5)
T-21 PASS (Verneinungs-Grenze Low) · T-22/T-22F PASS_WITH_RISKS (Low: F-03 Parallelrennen) · T-23/T-23G PASS (HAPI 0 Fehler, Wortlaut wörtlich) · T-24 PASS (Korrektur geprüft im Gesamtlauf: test_t24/test_a3_t24 grün) · T-25 PASS_WITH_RISKS (2 Low) + T-25G (S5 wieder grün).

## NOT RUN / Grenzen
- Live-Gateway (Modell) nicht im Lauf; cs/de-Texte nicht muttersprachlich; NCI-Registrierung ausstehend (Pitch: „Research prototype“); Push nur gegen lokalen Testserver; Rohgitter-Vollnachweise (`A3_FULL_GRID`) nicht neu gelaufen.
