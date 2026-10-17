# INT-3 – Integrationsprüfung (Prüfbericht A3)

- **Prüfstufe:** INTEGRATION (Punkte 1 und 10, Herkunft; Tickets sind einzeln geprüft) + KURZ für `a19844a`
- **Stand:** `verify/INT-3` `1f54c47` = `int/3` `a19844a` + `verify/F-07` `28116d0` (nur meine Specs/Berichte/Bilder, kein Produktcode)
- **Ergebnis:** **PASS**

## Ausgeführte Befehle (eigener Lauf, Worktree C:\rk\wt\a3, Ports 8300/5473)
| Befehl | Ergebnis |
|---|---|
| `scripts/test.ps1 -E2e` | **Exit 0**, „test: OK“. ruff/mypy grün; pytest **934 passed, 7 xfailed** (557 s; die 7 xfail sind die dokumentierten Medium-Reste T-09F (4) und T-07F (3), strict); vitest **525** (28 Dateien) + **57** passed; vite build ok; Playwright **89 passed** (1,5 min; darin Kernpfad mit HAPI-Validator, UI-Prüfungen, Einstellungen/Bericht/Export, S5) |
| `python scripts/provenance.py --out TABLE.md` | 179 Commits nach der Grenze, 5 berühren `platform`, **0 ohne `platform-fix:`**; `challenge/` vor Beginn nur `README.md` |
| `git log --name-status pre-rakathon..HEAD -- platform tests scripts .github` | nur `cfbc6bb`, `c551804`, `cf766e6`, `c4906fc`, `82a0532` – alle `platform-fix:`, alle in `provenance/PROVENANCE.md` §5 begründet |
| Dateien außerhalb `challenge/ docs/ agents/ kickoff/ provenance/ platform/ tests/ scripts/` | keine |

## End-to-End (Punkt 10)
Der Kernpfad läuft über Patientin → Server → Arbeitsliste → Cockpit → Quittieren → CTCAE-Aufnahme → FHIR-Export mit HAPI-Validator (0 Fehler, Standardlauf) vollständig grün; dazu Netzfehler-Retry, XSS-Notiz, Konflikt-Dialog, S5-Messung nach Quittierung und für alle Patientinnen.

## KURZ `a19844a` (Fixture-Abgleich)
- Änderung: `test_frontend_shapes.py` maskiert `attachment.data` (base64) vor der UUID-Normalisierung; Fixtures auf das integrierte Backend neu geschrieben (u. a. `fhir_bundle.json` 777 KB).
- Der Vergleichstest ist im Lauf grün (Teil der 934 pytest-Tests); die Fixtures enthalten keine echten Namen (Stichprobe `Testpatientin|Alena|Demová`: 0 Treffer im FHIR-Fixture, nur Pseudonyme/Synthetik).
- Grenze: Der Inhalt von `DocumentReference.attachment` (Kurzfassungstext) wird durch die Maskierung nicht mehr festgeschrieben; Form und Pflichtfelder bleiben geprüft. Akzeptiert.

## Offene Befunde (nicht blockierend, bei A0/A2/A2b)
- **Medium:** T-09F-Rest (rote Regel auf Kombination ohne Antworten), T-07F-Rest (mehrere Belege je Satz im LLM-Modus), F-07 F-01 (SYN-0001: zweite Meldung unter dem ersten Bildschirm, 827 px).
- **Low:** F-07 F-02 (921 px nach Quittierung), F-06 F-01 (Erfolgsmeldung zeitweise), F-06 F-02 (Belegnummern 12 px), F-06 F-03 (Historientabelle 375 px), T-05/F-UI Low 3 (doppelte Navigation).
- Die zugehörigen Tests sind `test.fail`/`xfail(strict)` und werden rot, sobald der Fehler behoben ist (Marker dann entfernen).

## NOT RUN
- Echter LLM-Lauf (Gateway 404), Linux/macOS-Reset, Browser-Druckdialog, Dunkelmodus-Kontrast.
