# Vertrag v1 – Digitaler Wächter (eingefroren Fr 16.10.2026, A0)

Maschinenlesbar: `openapi.yaml` (API) und `content.schema.json` (Inhalts- und Konfigurationsdateien). Diese Datei erläutert
nur; bei Widerspruch gelten die maschinenlesbaren Dateien. Änderungen nur per A0-Entscheid (Decision Record in
`docs/PROJECT_STATE.md`, Version v1.x).

## 1. Kernpfad (Demo, eine Patientin)

```
Therapie (Regime + Wirkstoffe, ATC) ──► Fragebogenauswahl (Kern-Items + Profil des Regimes)
Patientin (cs/en, 375 px) beantwortet PRO-Items (Attribute 0–4, Überspringen erlaubt)
   └► deterministische, versionierte Regeln (Schwelle · Baseline-Delta · Trend · fehlende Daten)
        └► Meldung (Flag) rot/gelb/grau + Erklärung (Regel-ID, Version, Schwelle, Baseline, Zyklustag, Belege)
             ├► rot ⇒ Sofortbenachrichtigung (In-App, Notifier-Port); gelb/grau ⇒ nur Arbeitsliste (keine Bagatellflut)
             └► Ärztin: Arbeitsliste ⇒ Cockpit (<30 s): Ampel, KI-Kurzfassung mit Belegen, Verlauf aller Metriken + Meldungen
                  ⇒ Meldung quittieren + Entscheidung (Audit) ⇒ CTCAE-Aufnahme im Subraum der getrackten Symptome
                  ⇒ Speicherung + FHIR-R4-Bundle-Export (validiert) / Druckansicht (PDF über Browser)
```

## 2. Rollen, Konten, Zugriff

| Rolle | Darf | Demo-Konto (synthetisch, Passwort wie Plattform `demo-passwort-2026`) |
|---|---|---|
| `patient` | nur `/me/*` (eigene Daten; Subjekt-Auflösung Konto → Patient) | `patient` (= SYN-0001, Hauptfall der Demo) |
| `clinician` | `/patients/*`, `/alerts/*`, `/notifications`, `GET /config` | `doctor` |
| `admin` (Plattformrolle) | zusätzlich `PUT /config/*` und alles von clinician | `admin` (Plattformkonto) |

Patient:in sieht **nie** Ampel, Meldung oder Grad; nach dem Senden nur eine neutrale Bestätigung (`message_key`), Eskalationstext
nur als Platzhalter „klinikfreigegebener Text folgt“ (COMMON §2). Fremdes Objekt ⇒ 404, falsche Rolle ⇒ 403.

## 3. Regeln (Semantik, bindend für Implementierung und Testorakel)

- Zeitreihe je `(symptom_key, attribute)` aus allen Antworten, sortiert nach `recorded_at`; `null` (übersprungen) zählt nie als
  Wert, wird als fehlend gespeichert und im Verlauf als Lücke gezeigt (nie imputiert).
- `threshold`: feuert für die neue Antwort, wenn `value >= params.min_value`.
- `baseline_delta`: Baseline = Median der Werte in den `baseline_days` Tagen **vor** der aktuellen Antwort (ohne sie);
  braucht ≥ 2 Baseline-Werte, sonst kein Alarm; feuert, wenn `value - baseline >= min_delta` und `value >= min_value`.
- `trend` („schleichende Veränderung“, statistisches Modell, kein LLM): Theil-Sen-Steigung (Median der paarweisen Steigungen,
  pro Tag) über die Werte der letzten `window_days` inkl. aktueller Antwort; braucht ≥ `min_points`; Prognose
  `projected = last_value + slope * horizon_days`; feuert, wenn `slope >= min_slope_per_day` und `projected >= target_value`
  und der aktuelle Wert `< target_value` (sonst greift die Schwelle).
- `missing`: Tage seit der letzten Antwort `> max_days_without_response` (Uhr = `Clock`); ausgewertet idempotent beim Lesen der
  Arbeitsliste/Übersicht (höchstens eine offene Meldung je Patientin), Ebene `grey` = „unbekannt“, nie „gut“.
- **Rauschbremse:** höchstens eine offene Meldung je `(rule_id, symptom_key, attribute)`; nach Quittierung `cooldown_hours`
  keine neue für dasselbe Tripel. Sofortbenachrichtigung nur für `noise.notify_levels` (Standard `[red]`).
- **Ampel:** höchste offene Stufe rot > gelb > grau; sonst grün, wenn die letzte Antwort nicht älter als
  `max_days_without_response` ist; sonst grau. Sortierung Arbeitsliste: rot, gelb, grau, grün; dann älteste offene Meldung.
- Regeln sind reine Funktionen (keine Uhr/Zufall/LLM), Version `rules-vN` wird in jeder Meldung gespeichert.
- Standardregeln (IDs fest, Parameter konfigurierbar; Inhalte/Begründung liefert A1 in `challenge/content/rules.yaml`):
  `R-SEV-01` threshold rot (severity/interference ≥ 3), `R-URG-01` threshold rot (presence = 1 für Warnsymptome wie Fieber),
  `R-DLT-01` baseline_delta gelb, `R-TRD-01` trend gelb, `R-MIS-01` missing grau.

## 4. KI-Kurzzusammenfassung (Entscheidungsunterstützung, keine Bewertung)

- Eingabe nur Fakten dieser Patientin aus der DB (RAG auf Patientendaten), je Zeile mit Fakt-ID: `ther-…`, `visit-…`, `resp-…`,
  `obs-…` (einzelner Antwortwert), `alert-…`, `assess-…`. Ausgabe: Sätze mit `[fakt-id]`-Belegen.
- **Prüfer (deterministisch):** Satz gilt als `verified`, wenn ≥ 1 Beleg, alle Belege existieren und jede Zahl im Satz in den
  Belegtexten vorkommt. Ungeprüfte Sätze werden verworfen (`dropped_sentences`). Themen ohne Daten ⇒ `unknown_topics`.
- Adapter über Umgebungsvariable `WAECHTER_LLM` = `template` (Standard, deterministischer Textbaustein, `mode=fallback`) |
  `cached` (aufgezeichnete Antworten in `challenge/content/llm_cache/`, Offline-Demo) | `azure` (`AZURE_OPENAI_ENDPOINT`,
  `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_DEPLOYMENT`, `AZURE_OPENAI_API_VERSION`) | `anthropic` (`ANTHROPIC_API_KEY`,
  `WAECHTER_LLM_MODEL`). HTTP nur über Standardbibliothek (keine neuen Abhängigkeiten). Zeitüberschreitung/Fehler ⇒ `template`.
- Implementiert den Plattform-Port `app.ports.llm.LlmPort`. Jede Zusammenfassung ⇒ Provenance (Generator, Zeit, Fakten-Hash)
  und Audit. Hinweis in der UI: „KI-Entwurf – prüfen Sie die Belege“.

## 5. FHIR R4 (Integrationsfähigkeit, keine KIS-Anbindung)

| Domäne | Ressource | Kern |
|---|---|---|
| Patientin (pseudonym, synthetisch) | `Patient` | `identifier` system `urn:waechter:pseudonym`; `meta.tag` `urn:waechter:tag#synthetic`; nur Geburtsjahr |
| Therapie | `MedicationStatement` | ATC `http://www.whocc.no/atc`; `effectivePeriod.start` = Zyklusbeginn |
| Fragebogen | `Questionnaire` | `url` `urn:waechter:questionnaire:<items_version>:<regime>`; `linkId` `<symptom>.<attribut>`; answerOption Codes 0–4 (`urn:waechter:pro-scale`) |
| Antworten | `QuestionnaireResponse` | `authored`, `source`; Kanal und `entered_by` als `meta.tag` (`urn:waechter:channel`, `urn:waechter:entered-by`) |
| Einzelwert | `Observation` | category `survey`; code `urn:waechter:pro-item#<symptom>.<attribut>`; `valueInteger` oder `dataAbsentReason` (`asked-declined`); `derivedFrom` QR |
| Meldung | `Flag` | code mit `urn:waechter:rule#<rule_id>` + Text; status active/inactive; `period.start` |
| CTCAE-Aufnahme | `Observation` | category `exam`; code MedDRA `http://terminology.hl7.org/CodeSystem/mdr#<code>` + CTCAE-Begriff; `valueCodeableConcept` `urn:waechter:ctcae-grade#<0–5>`; Komponente Attribution; ANNAHME: `AdverseEvent`/ECCDM-Profil als nächster Schritt |
| KI-Text | `DocumentReference` + `Provenance` | Provenance.agent = Generator (Device-Anzeige), `recorded` |
| Quittierung | `AuditEvent` | `action` U, `recorded`, `agent.who.display` Rolle |

Bundle `type=collection`, ISO 8601 mit Zeitzone, `fullUrl` `urn:uuid:…`. Validierung: HAPI `validator_cli.jar` (außerhalb des
Repos, `C:\rk\tools\`) `-version 4.0.1`; Standardlauf zuerst und getrennt berichten (docs/ENVIRONMENT.md).

## 6. Inhalte (`challenge/content/`, geprüft gegen `content.schema.json`)

`items.yaml` (ItemsFile) · `regimens.yaml` (RegimensFile) · `ctcae.yaml` (CtcaeFile, Gradtexte wörtlich aus CTCAE v6.0 des NCI;
Nutzungsbedingungen nicht im PDF, Quellenangabe + Link laut NCI in UI und Export, ANN-06/ANN-14) · `rules.yaml` (RulesFile) · `report.yaml` (ReportFile) · `scenario.yaml` (ScenarioFile, synthetisch, mit
Testorakel `expected`) · `SOURCES.md`. PRO-Items: **PRO-CTCAE-Struktur** (Attribute, 5-stufige Skala), **eigene Formulierung**,
keine NCI-Itemtexte (ANN-05).

## 7. Code-Ablage und Besitz

- Backend: `challenge/backend/plugin.py` (Registrierung) + Paket `challenge/backend/waechter/` (`models.py`, `migrations/`,
  `content.py`, `services/*.py`, `llm/*.py`, `fhir/*.py`, `api.py` dünn); Tests `challenge/backend/test_*.py`. Owner A2.
- Frontend: `challenge/frontend/plugin.tsx` + `challenge/frontend/waechter/**` (Seiten, Komponenten, `i18n/{cs,en,de}.ts`,
  API-Client); Tests `*.test.tsx`. Owner A2b. Routen: `/patient`, `/clinic`, `/clinic/patients/:id`,
  `/clinic/patients/:id/assess`, `/clinic/patients/:id/report`, `/clinic/alerts/:id`, `/clinic/settings`.
- Inhalte: `challenge/content/` Owner A1. Pitch: `challenge/pitch/` Owner A4.

## 8. Feste Ankerzeit

`APP_FROZEN_NOW=2026-10-17T09:00:00+02:00` für Demo und Tests (Szenario `anchor` identisch). Tests hängen nie am Tagesdatum
und nie an Seed-Anzahlen.

## 9. Klarstellungen v1.1 (DR-007/DR-008, Fr 16.10. ~16:00, aus A3-Prüfplan `docs/verification/PLAN.md` §7)

- **G-01 Statistik:** Median gerader Anzahl = Mittel der zwei mittleren Werte. Baseline-Fenster `[t − N·24 h, t)` (aktueller
  Punkt ausgeschlossen, Rand inklusive). Theil-Sen: Steigung in Wert/Tag, Δt in Tagen als Float; Paare mit Δt = 0 verworfen;
  Fenster `window_days` analog `[t − N·24 h, t]` inklusive aktuellem Punkt.
- **G-02 Safety vor Rauschbremse:** Cooldown/Dedupe gilt **nicht**, wenn der neue Wert höher ist als der Wert der offenen bzw.
  quittierten Meldung desselben Tripels, oder wenn eine Regel der Stufe rot feuert und die bestehende Meldung niedriger ist.
  Eine quittierte Meldung, deren Wert in der jüngsten Antwort weiter ≥ Schwelle liegt, macht die Ampel nicht grün: Übersicht
  zeigt `persisting` (Hinweis „quittiert, Wert besteht weiter“), Ampel mindestens gelb.
- **G-03 Orakel:** `expected.alerts` mit `attribute`, `level`, optional `hour`; Menge exakt; `traffic_light_at_anchor` Pflicht
  (Schema aktualisiert).
- **G-04 Zeitzone:** alle Tagesgrenzen, `hour`, `missing_days`, „Tage seit letzter Antwort“ in `Europe/Prague`; ganze Tage =
  Differenz der Kalendertage.
- **G-05 Schemaprüfung:** eigener kleiner Validator für die im Schema genutzten Schlüsselwörter (keine neue Abhängigkeit) plus
  Querverweisprüfung (symptom_keys, ctcae_terms, regimen_id) im Lader; A3 gleicht außerhalb des Repos mit `jsonschema` ab.
- **G-06:** T-06, T-09, F-06 = VOLL.
- **G-07 E2E:** A0 macht bei Integration 1 einen `platform-fix:` (Plattform-Smoke tolerant gegenüber geladener Challenge;
  Playwright erfasst zusätzlich `challenge/e2e/**/*.spec.ts`).
- **G-08 Uhr/Seed:** Sortierung `(recorded_at, response_id)`; Freitexte und eigene Antwortlisten bei gleichem Zeitpunkt nach Einfügereihenfolge (SQLite-rowid, T-22) statt zufälliger ID. Seed erzeugt Meldungen über dieselbe Regel-Engine (chronologisch).
  SYN-0001 (Hauptdemo) hat am Anker eine offene rote Meldung (Demo-Geschichte). E2E-1 nutzt **SYN-0002** (Konto `patient2`,
  grün am Anker) und sendet Fieber = 1 ⇒ R-URG-01 rot.
- **G-09 KI-Prüfer:** Zahlen-Tokens `(?<![\d.,])\d+([.,]\d+)?(?!\d)`, `,`→`.`; Datumsangaben im Satz nur als ISO `YYYY-MM-DD`
  und als Token geprüft; Verbotsliste (Diagnose/Therapie/Beruhigung) auf jeden Satz, Treffer verwerfen; Seed legt für SYN-0001
  eine `cached`-Kurzfassung an; `POST /summary` dedupliziert über Fakten-Hash + Prompt-Version (= Cache-Schlüssel).
- **G-10 Antworten:** `presence` ∈ {0,1} sonst 422; gleiche `client_submission_id` + anderer Body ⇒ 409 `idempotency_conflict`;
  unpassende `questionnaire_id`, fremde/doppelte Tripel ⇒ 422; Alles-`null` erlaubt (zählt nicht als Antwort für R-MIS-01).
- **G-11 FHIR:** R4-Pflichtfelder laut Validator; Referenzen über `fullUrl` `urn:uuid:…`; Terminologielauf `NOT RUN` (offline).
- **G-12 Konfig:** `RulesUpdate.rules`/`report` = `RulesFile`/`ReportFile` ohne `version`; 401/403/422 wie überall; Server lehnt
  Konfiguration ohne mindestens eine aktive rote Regel mit 422 `no_red_rule` ab; jede Änderung auditiert.
- **G-13 Aufnahme:** 422 bei fremder Meldung, nicht definiertem Grad (außer 0), doppeltem Begriff.
- **G-14:** zweites Patientenkonto `patient2` = SYN-0002.
- **G-16 Audit-Aktionen (Enum):** `view_overview`, `view_timeline`, `acknowledge_alert`, `generate_summary`, `create_assessment`,
  `export_fhir`, `config_change`, `submit_response`. Lesezugriffe werden auditiert (Audit ist kein fachlicher Seiteneffekt).
- **G-17:** Benachrichtigungstext nur mit Pseudonym; Frontend merkt gesehene IDs lokal.
- **G-18:** `lang` Standard = Sprache der Patientin; Mehrfachsendung pro Tag erlaubt.
- **G-19:** R-MIS-01-Referenz = `max(letzte Antwort mit ≥ 1 Wert, Zyklusstart)`.
- **DR-008 LLM-Adapter `openai`:** OpenAI-v1-kompatibles Gateway des Veranstalters (Azure API Management).
  `WAECHTER_LLM=openai`, `WAECHTER_LLM_BASE_URL` (z. B. `https://apim-rakathon-q7146n.azure-api.net/openai/v1`),
  `WAECHTER_LLM_API_KEY` (nur Umgebungsvariable/lokale Datei `C:
k\secrets\llm.env`, nie Repo/Log; **nur Header `api-key`**,
  Bearer/Ocp-Apim ⇒ 401), `WAECHTER_LLM_MODEL` (= Deployment-Name, Beispiel der Veranstalter: `MODEL_DEPLOYMENT`).
  Aufruf wie Veranstalter-Beispiel: `POST {base}/responses` mit `{model, input, store: false}` (Text aus `output[].content[].text`
  bzw. `output_text`); Rückfall `POST {base}/chat/completions`. Temperatur 0 wo unterstützt, Timeout 20 s ⇒ sonst `template`. Antworten des Live-Laufs
  werden für die Offline-Demo in `challenge/content/llm_cache/` aufgezeichnet (ohne Schlüssel, nur synthetische Fakten).
- **DR-009 (v1.2) Serverzeit:** `GET /api/v1/meta` enthält über `add_meta_extension` den Schlüssel
  `waechter: { server_now: <ISO 8601 mit Zeitzone, aus Clock bzw. APP_FROZEN_NOW>, timezone: "Europe/Prague", content_versions: {items, rules, report} }`.
  Das Frontend rechnet relative Zeiten („vor 2 Tagen“) nur gegen `server_now`, nie gegen die Browseruhr (Demo mit eingefrorener Uhr).
- **DR-011 (v1.3) Zusatzfelder:** `WorklistRow` und `Overview` tragen `persisting` (bool), `evaluation_pending` (bool),
  `days_without_response` (int|null); `Overview` zusätzlich `persisting_alerts` (Alert[]). Kein `persisting` am einzelnen Alert.
  `therapy.watch_notes` = lokalisierte Texte (string[]). `GET /patients` und `/overview` dürfen R-MIS-01 anlegen/schließen
  (idempotent, partieller Unique-Index) – bewusster Lese-Seiteneffekt, auditiert.
- **DR-012 (v1.4) Episodenende (Safety, A3 T-04a F-01):** Liegt nach einer Meldung (offen oder quittiert) eine Antwort desselben
  Tripels **unter** der Auslöseschwelle der Regel vor (Entwarnung), endet die Episode: Dedupe und Cooldown gelten für spätere
  Antworten nicht mehr – ein Rückfall erzeugt sofort eine neue Meldung. Eine offene Meldung bleibt dabei offen (Ärztin quittiert).
- **DR-013 Seed-Benachrichtigungen (A3 T-04a F-02):** Rote Seed-Meldungen lösen bewusst Benachrichtigungen aus (Demo-Start zeigt
  den Banner); keine Änderung.
- **DR-014 (v1.5) Konfig-Historie:** zusätzlich `GET /config/history?kind=rules|report` (clinician, admin) ⇒ Liste
  `{version, changed_at, changed_by, change_note, active}`; `GET /config` liefert die aktive DB-Version (Dateiinhalt = Startversion).
- **DR-015 (v1.6) Sprache:** alle GET-Endpunkte für Ärztinnen (`/patients…`, `/alerts…`, `/notifications`, `/config`) akzeptieren
  `?lang=cs|en|de` (Standard cs) und liefern headline/label/watch_notes/Regelbegründung lokalisiert; das Frontend sendet stets
  die UI-Sprache. Optionale Felder dürfen `null` sein (nullish) – Frontend-Schemata sind entsprechend tolerant (F-INT).
- **DR-016 (v1.7) zweiter Sicherheitsboden:** `PUT /config/rules` lehnt `noise.notify_levels` ohne `red` mit 422
  `no_red_notification` ab (Sofortbenachrichtigung roter Meldungen ist nicht abschaltbar).
- **DR-017 (v1.8) Eingabe im Namen der Patientin (Mehrkanal):** `POST /patients/{id}/responses` (clinician, admin), Body =
  `ResponseSubmit` mit `channel ∈ {phone, paper}`, `entered_by = nurse`; gleiche Validierung, Idempotenz (je Patientin), H-5 und
  Regelauswertung wie `/me/responses`; Audit `submit_response_on_behalf`; patient ⇒ 403.

## 10. Vertrag v1.9 – Klinikvorgaben Výzva 3 (DR-020, Sa 01:45; Quelle: „Rakathon výzvy – onkologie FNM“, MUDr. A. Pirshtuk)

Rozsah první verze: **Dotazník** (krátký, v pravidelných intervalech, přizpůsobený diagnóze a aktuální léčbě) · **Rady pacientovi**
(praktické rady ke zvládání symptomů; při akutních obtížích odkaz na ambulanci nebo linku 155) · **Upozornění týmu** (bei
Überschreiten festgelegter Werte automatisch) · „Chceme být ihned informováni o závažných nežádoucích účincích, nikoli o každé
drobnosti.“ Eingangsdaten laut Klinik: SPC aus der Databáze léků SÚKL, CTCAE v6.0, gemeinsamer Datensatz (uns nicht vorliegend ⇒
synthetisch, ANN-15).

- **Diagnose-Anpassung:** `challenge/content/diagnoses.yaml` (DiagnosesFile). Fragebogen = Kern ∪ Profil des Regimes ∪ Profil der
  Diagnosegruppe (ICD-10-Präfix aus `patient.diagnosis_code`), dedupliziert, Reihenfolge Kern → Regime → Diagnose; Quelle
  `source: diagnosis` je Item; `questionnaire_id` = `<items_version>:<regimen_id>:<diagnosis_group|none>`.
- **Intervalle:** `challenge/content/schedule.yaml` (ScheduleFile). Intervall nach Zyklustag (Phase, sonst Standard);
  `due.next_due_at` = letzte Antwort mit Wert + Intervall (Prager Kalendertage; ohne Antwort: Zyklusbeginn); `overdue` wenn Uhr ≥
  next_due_at. R-MIS-01 bleibt unabhängig (Parameter in rules.yaml).
- **Rady pacientovi:** `challenge/content/advice.yaml` (AdviceFile). Nach dem Senden liefert `SubmitReceipt.advice` Tipps nur für
  Symptome mit einem Wert ≥ `min_value` (deterministisch, keine KI); `escalation.level = acute`, wenn für diese Antwort eine rote
  Regel feuert ⇒ Text „při akutních obtížích kontaktujte ambulanci nebo volejte 155“ (Wortlaut aus der Klinikvorgabe, Telefonnummer
  der Ambulanz als Platzhalter); sonst `general`. Patientin sieht weiterhin nie Ampel, Regel oder Grad. Keine Reaktionszusage
  („tým byl informován“ ist verboten), keine Beruhigung, keine Dosis-/Therapieratschläge. `GET /me/advice` = Hilfeseite mit allen
  Tipps ihres Fragebogens.
- **SPC-Quellen:** Profile in `regimens.yaml` zitieren vorrangig die SPC aus der SÚKL-Datenbank (bei zentral zugelassenen
  Arzneimitteln die dort verlinkte EU-SPC), Claim-Stufe B.
- **DR-022 (v1.10) Anzeige der Rady (A3 T-12 F-01, hm-selfcare):** `escalation.level = acute`, wenn (a) für diese Antwort eine rote
  Regel feuert ODER (b) ein Symptom aus `advice.escalation.always_acute_for` (Fieber, Atemnot) mit Wert ≥ 1 gemeldet wurde. Bei
  acute steht der Akut-Hinweis **zuerst** und hervorgehoben (375 px ohne Scrollen sichtbar); für Symptome, die rot ausgelöst haben
  oder in `always_acute_for` stehen, werden **keine** Selbsthilfe-Tipps angezeigt (nur der Hinweis). `ambulance_phone` mit
  Platzhalter in eckigen Klammern wird nicht angezeigt.

## 11. Vertrag v2.6 – FHIR-Server-Anbindung nach InterSystems FHIR-AI-Hackathon-Kit (DR-031, Fr 23:30)

Quelle: Wunsch des Menschen; Strukturen aus `intersystems-community/FHIR-AI-Hackathon-Kit` (Tutorials 3.0, 3.3, 3.4; gelesen, kein Code
übernommen). Ziel: „Integration in klinische Systeme“ (Klinikvorgabe) zeigen – nicht nur Export, sondern Schreiben in einen
FHIR-R4-Server (IRIS for Health oder jeder andere R4-Server).
- **v2.8 (DR-033, ersetzt die folgende Zeile):** Transaction-Bundle im **Format der Klinik-Exporte** (beobachtet im Rakathon-Datensatz):
  `request: PUT {Typ}/{id}` mit festen, deterministischen ids (uuid5 aus internen IDs bzw. Pseudonym), Referenzen `Patient/<id>` statt
  `urn:uuid`, Zeiten mit Offset Europe/Prague, keine leeren Elemente; idempotent bei wiederholtem Upload. Medikation zusätzlich mit
  kódSÚKL (System-URI ANNAHME) + ATC, sofern bekannt.
- **Transaction-Bundle:** `GET /patients/{id}/fhir?type=transaction` ⇒ Bundle `type=transaction`; je Eintrag `fullUrl urn:uuid:…` und
  `request`: Patient ⇒ `PUT Patient?identifier=urn:waechter:pseudonym|<SYN-…>` (bedingtes Upsert, idempotent); alle anderen Ressourcen
  ⇒ `POST <Typ>` mit `ifNoneExist: identifier=urn:waechter:<typ>|<interne-id>` (jede Ressource bekommt dafür einen `identifier`);
  interne Referenzen über `urn:uuid` (Server löst sie auf). Standard bleibt `type=collection` (bisheriges Verhalten, Tests unverändert).
- **Condition:** neue Ressource je Patientin aus `diagnosis_code` (ICD-10 `http://hl7.org/fhir/sid/icd-10`, synthetisch, clinicalStatus
  active, `meta.tag synthetic`), in beiden Bundle-Typen.
- **Push:** `POST /patients/{id}/fhir/push` (nur admin; clinician ⇒ 403) sendet das Transaction-Bundle an `WAECHTER_FHIR_BASE_URL`
  (z. B. `http://localhost:52773/fhir/r4/`) mit `Content-Type: application/fhir+json`, optional Basic Auth aus `WAECHTER_FHIR_USER` /
  `WAECHTER_FHIR_PASSWORD` (nur Umgebung, nie Log/Repo), Timeout 20 s, nur Standardbibliothek. Antwort: `{status: sent|disabled|failed,
  http_status, entries: n, created: n, updated: n, errors: [Kurztext ohne Patientendaten]}` aus dem `transaction-response`-Bundle.
  Ohne Basis-URL ⇒ `disabled` (kein Fehler). Audit `fhir_push` (Status, Anzahl). Nur synthetische Daten (Guard: Patient ohne
  `synthetic=true` ⇒ 409 `not_synthetic`).
- **Prüfung:** HAPI-Validator auch für das Transaction-Bundle (Standardlauf 0 Fehler); Push-Tests gegen einen lokalen Test-HTTP-Server
  (Python `http.server` im Test, kein Netz), inkl. 401, 500, Timeout, Wiederholung (zweiter Push ⇒ keine Dubletten dank PUT/ifNoneExist
  – am Testserver simuliert). Live gegen IRIS for Health: NOT RUN, solange kein Server verfügbar (Docker fehlt lokal) – ehrlich so
  im Pitch.
- **Nicht übernommen (Roadmap):** Vektorsuche, LangChain-Agenten, MCP-Server, FHIR-SQL-Projektion (neue Abhängigkeiten, nicht
  Kern der Výzva 3).

## 12. Vertrag v2.7 – Wissensbasis C61/C64 (DR-032, Fr 23:45; Auftrag des Menschen)

Zieldiagnosen der Klinik: **C61 (Prostata) und C64 (Niere)**. Aufbau einer belegten Wissensbasis, aus der das Ausgangsmodell später
kompiliert wird (Schritt 4 erst nach Abnahme des M2-Berichts durch den Menschen). **Ort: `challenge/knowledge/`** (Zonenregel; „knowledge/“
des Auftrags = dieser Ordner).
- **Harte Regeln:** kein Lesen/Anfordern/Speichern von Rohdaten des Rakathon-Datensatzes (nur vom Menschen gelieferte Zähltabellen);
  Test „kein Code greift auf einen Datensatz zu“ (statische Prüfung: keine Pfade/Lader für Datensatzdateien, kein Netz in Lader-Code).
  Kein medizinischer Inhalt aus dem Gedächtnis: jede AE-Zeile mit Dokument, Abschnitt (4.8), wörtlichem Originalbegriff, Abrufdatum;
  sonst `status: unverified` + Eintrag `challenge/knowledge/CLINICAL_TODO.md`. Alles `draft|placeholder|unverified` bis klinische Freigabe.
- **Schritt 1:** `challenge/knowledge/drugs/substances.yaml` (INN, ATC, kódSÚKL falls auffindbar, Klasse, Quelle EAU/ESMO bzw.
  SÚKL/EMA-Produktinformation, `mapping_status`), `challenge/knowledge/regimens/*.yaml` (Delta v2.1 Δ3.2/Δ3.3).
- **Schritt 2:** `challenge/knowledge/ae_matrix.csv` (Spalten: substance_id, document, document_url, section, retrieved, original_term
  (wörtlich, Sprache des Dokuments), frequency_class (MedDRA-Konvention: very common/common/uncommon/rare/very rare/not known),
  ctcae_v6_term (nur aus der bereitgestellten CTCAE-v6-PDF, sonst leer), patient_reportable (yes/no), pro_item (Symptomschlüssel oder
  custom), status (verified|unverified), extraction (manual|llm:<modell>)).
- **Schritt 3:** Aggregation über Wirkstoffe, Deduplikation auf CTCAE-Term, Matrix Symptom × Wirkstoffklasse
  (`challenge/knowledge/symptom_class_matrix.csv`), Trennung (a) patientenberichtbar ⇒ `challenge/knowledge/items_draft.yaml` (cs/de/en
  Entwurf, `text_* : TODO_OFFICIAL_WORDING`), (b) nur Labor/Personal ⇒ `challenge/knowledge/staff_context.yaml` (nicht im Fragebogen).
- **LLM → FHIR (Wunsch des Menschen):** Pipeline `challenge/backend/waechter/knowledge/` (A2, T-19): Quelltexte der SmPC (PDF-Text, HTML,
  TXT) ⇒ LLM-Extraktion (Adapter wie §4/DR-008, geschlossenes Schema, Belegstelle wörtlich) ⇒ deterministischer Prüfer (Belegstelle muss
  im Quelltext vorkommen, Häufigkeitsklasse aus Enum, CTCAE-Term aus Liste) ⇒ FHIR-R4-Bundle mit `MedicinalProductUndesirableEffect`
  je Zeile (+ `Provenance` mit Dokument/Abschnitt/Modell) und HAPI-Validierung. **Modell:** das Gateway liefert für jeden Namen 404
  `DeploymentNotFound` ⇒ LLM-Lauf NOT RUN, bis `MODEL_DEPLOYMENT` bekannt; dieselbe Pipeline verarbeitet bis dahin die manuell belegte
  `ae_matrix.csv` (`extraction: manual`) deterministisch nach FHIR. Keine Patientendaten an das LLM (nur öffentliche SmPC-Texte).
- **Schritte 4–6** (Kern/Module/Priore/Kompilieren V1–V5, Tests C1/C4, Bericht): erst nach Abnahme des M2-Berichts.

## 13. Vertrag v2.8 – Demo auf die Zieldiagnosen ausrichten (DR-033, Fr 23:58)
- Neue Therapieschemata für **C61** (`ENZALUTAMIDE`, `ABIRATERONE`) und **C64** (`PAZOPANIB`, `NIVOLUMAB`) in regimens.yaml mit
  SPC-Quellen aus T-KB (A1), Diagnosegruppen `PROSTATE` (C61) und `KIDNEY` (C64) in diagnoses.yaml, Triage-Profile (triage.yaml,
  placeholder) und Präparate in medications.yaml. Auswahl begründet durch die aggregierte Datensatz-Zählung
  (`challenge/knowledge/dataset_counts.yaml`: Enzalutamid 43, Bicalutamid 38, Abirateron 21 bei C61; Pazopanib 21, Nivolumab 13,
  Sunitinib 10 bei C64).
- Zwei **neue synthetische** Szenario-Patient:innen `SYN-0006` (C61, Enzalutamid; Hauptfall Prostata) und `SYN-0007` (C64, Pazopanib)
  mit Orakel; bestehende SYN-0001…0005 und Orakel bleiben unverändert (keine echten Daten, keine Ableitung aus Einzelfällen).

## 14. Vertrag v2.9 – Dokumente ⇒ FHIR über LLM, Proof of Concept (T-21, Mensch-Vorgabe, Sa 17.10.)
- **Ablauf:** `POST /patients/{id}/documents` (Text/Markdown/CSV, höchstens 200 kB, nur clinician/admin, nur synthetische Patient:innen
  sonst 409, kein PDF ⇒ 415) ⇒ Extraktor (`WAECHTER_LLM=openai` ⇒ Sprachmodell über den Adapter von T-07/T-19, sonst und bei jedem Fehler
  das deterministische Regelwerk `template-regex-v1`) ⇒ **deterministischer Prüfer** (Zitat wörtlich im Dokument; Code in der Allow-Liste:
  ICD-10-Präfixe aus `diagnoses.yaml`, ATC/kód SÚKL aus `medications.yaml`, LOINC aus der versionierten Laborliste `labs-v1`; Code bzw.
  Name, Wert und Einheit im Zitat, der Wert direkt hinter dem Namen des benannten Laborwerts; Zeilen, die etwas verneinen oder
  ausschließen oder Angehörige betreffen, ergeben keinen Kandidaten (`context_negated`/`context_family`); Datum im Dokument;
  sonst verworfen und mit Grund aufgelistet) ⇒ Entwurf in `wa_documents` (Migration
  w009) ⇒ Ärztin bestätigt oder verwirft **je Ressource** (`POST …/candidates/{id}`, bedingtes Update) ⇒ erst bestätigte Ressourcen stehen
  im Patientenexport (`/fhir`, `/fhir?type=transaction`, `/fhir/push`). Ohne Bestätigung ist der Export byte-gleich wie vorher.
- **FHIR:** Condition (`verificationStatus` unconfirmed ⇒ confirmed), MedicationStatement (`status` unknown, weil ein Dokument die
  Einnahme nicht belegt), Observation (preliminary ⇒ final, `valueQuantity` mit UCUM). `meta.tag` `urn:waechter:source|document-extraction`
  und `urn:waechter:review|unconfirmed|confirmed`. Je Ressource eine `Provenance`: Agent = Extraktor (Adapter/Modell), bei Bestätigung
  zusätzlich die bestätigende **Rolle** (kein Name), Entitäten = Dokument-SHA-256 (`urn:waechter:document-sha256`) und Zitat.
- **Grenzen (ehrlich):** Das Sprachmodell liefert nur Vorschläge; Gateway/Modell sind NOT RUN, bis `MODEL_DEPLOYMENT` bekannt ist. Die
  Laborliste (12 Werte, LOINC-Codes aus Standardwissen) ist klinisch nicht freigegeben. Keine Rohdaten des Wettbewerbsdatensatzes; die
  Demo-Dokumente liegen synthetisch in `challenge/demo/docs/`. Der Dokumenttext wird nicht gespeichert (nur Hash, Zitate).

## 15. Vertrag v2.9 (T-25) – Baseline nach Therapiewechsel, Subraum anzeigen
- **Baseline-Fenster (R-DLT-01 u. a. `baseline_delta`):** Das Fenster `[now − baseline_days, now)` beginnt frühestens beim Start des
  **aktuellen Therapieschemas**, wenn dem aktuellen Schema ein anderes `regimen_id` vorausging (Therapie-Einträge bis `now`; ein neuer
  Zyklus desselben Schemas setzt **nicht** zurück). Ohne Schemawechsel bleibt alles wie vor T-25 (Seed-/Szenario-Orakel unverändert). Zu
  wenige Werte im gekürzten Fenster (< 2) ⇒ keine Baseline-Meldung (wie bisher). Die Erklärung nennt das tatsächliche Fenster
  (`baseline_window`) und, nur bei Kürzung, `baseline_limit {reason: regimen_change, regimen_id, since}`.
- **Subraum:** `GET /patients/{id}/overview` liefert `tracked_symptoms[]` (`ctcae_term_id`, `term_en`, `label`): die CTCAE-Begriffe des
  aktuellen Fragebogens, über dieselbe Funktion wie die Aufnahmevorlage (`assessment_queries.term_order`). Das Cockpit zeigt sie als Zeile
  „Sledované příznaky / Tracked symptoms / Beobachtete Symptome“ im Meldungsbereich und am Kopf der Kurzfassung.
