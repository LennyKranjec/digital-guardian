# Verifikation fix/int4b-A2 (T-20bG F-01 Fixtures, T-19G F-02 Prüfer) – KURZ

- Prüfer: A3 · Sa 17.10.2026, ~07:10 · Stufe: **KURZ**
- Stand: `int/4b` edd6600 (enthält fix/int4b-A2 5827977 und d6f8672); Branch `verify/INT-4b` = int/4b + meine drei Spec-Änderungen (session-a3 Aufwärmen, triage-real ohne test.fail, fhir-a3 Aufwärmen)
- Ergebnis: **PASS** (F-01 und F-02 aus T-20b behoben), mit einer Messung zur Strenge (Hinweis)

## Ausgeführt

| Befehl | Ergebnis |
|---|---|
| `vitest run challenge/frontend/waechter/api` (contract.test, contract-logic.test, alert-triage.test) | 81 passed (vorher 4 rot) |
| `pytest test_a3_t19.py test_t19_knowledge.py test_frontend_shapes.py` | 137 passed; mein Teilwort-Test grün (A2 hat den xfail-Marker entfernt); Fixtures `overview_red`/`overview_quiet` wieder SYN-0001/SYN-0003 |
| Messung: `verify_manual` der neuen Prüfung über alle 533 Zeilen der echten Matrix mit dem Text der zitierten PDF-Seite (`pdftotext -raw` und `-layout`) | je Modus 93 von 351 verified-Zeilen bleiben verified, **257 würden verworfen** (`term_not_in_source` 329, `frequency_contradicts_source` 79/32); Sunitinib und Pazopanib fast vollständig (Tabellenlayout) |

## Bewertung

- Die Korrekturen wirken: Teilwort leiht keine Häufigkeit mehr, Fixtures sind stabil.
- **Hinweis (Low, kein Befund an A2):** Die verschärfte Prüfung ist konservativ; auf den echten SmPC-Tabellen (Text-Layer entkoppelt) ist sie unbrauchbar (73 % der korrekten Zeilen würden verworfen). Sie schützt nie falsch, aber „deterministischer Prüfer belegt die Matrix wörtlich“ gilt nur für Listentext und den Live-LLM-Pfad (nicht gelaufen). Für die echte Matrix bleibt die Aussage „A1 + Zweitleser A3“ (siehe T-KB). A2 hatte diese Messung als offen angegeben (T-20bG not_run); sie liegt jetzt vor.
- Auf `int/4b` fehlt mein Spec-Commit (`triage-real.spec.ts` trägt noch zwei `test.fail`-Marker, die mit T-16G grün werden und dann als „unerwartet bestanden“ rot melden; `session-a3` ohne Aufwärmen). Beides steckt in `verify/INT-4b` (oder `verify/T-16G` 75aec98).

## NOT RUN

- Gesamtlauf (Absprache mit A0: kein weiterer Großlauf vor dem Endlauf auf int/4b).
