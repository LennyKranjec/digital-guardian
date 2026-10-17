# Prüfplan A3 – Vertrag v1 (Ticket A3-P)

Stand: Fr 16.10.2026 · Vertrag `challenge/contract/{openapi.yaml,content.schema.json,README.md}@6068fe6` · Tag `pre-rakathon` → `21932cc`
(15.10. 21:54, vor Wettbewerbsbeginn; seither genau 1 Commit `6068fe6`, 0 Plattformänderungen – gemessen mit `scripts/provenance.py`).
Maßgeblich bei Widerspruch: `openapi.yaml` / `content.schema.json` vor `README.md`. Ich ändere keinen Produktcode und keinen Vertrag;
Lücken (§7) gehen als Q an A0.

## 0. Konventionen für jede Ticketprüfung

**Umgebung (A3):** Worktree `C:\rk\wt\a3`, Ports `8300/5473`, Temp `C:\rk\tmp\a3`. Jeder Befehl mit `cd C:\rk\wt\a3 && …`.

```powershell
cd C:\rk\wt\a3
$env:E2E_BACKEND_PORT='8300'; $env:E2E_FRONTEND_PORT='5473'; $env:PYTEST_DEBUG_TEMPROOT='C:\rk\tmp\a3'
$env:APP_FROZEN_NOW='2026-10-17T09:00:00+02:00'          # Ankerzeit (Vertrag §8) – nie das Tagesdatum
git switch -c verify/<Ticket> feat/<Ticket>              # Branch im selben Repo; Produktcode bleibt unverändert
```

**Schritt 0 (≤ 3 min, jede Stufe):**
1. `git diff --name-status main...feat/<Ticket>` – jede Datei außerhalb der im Ticket genannten Dateigrenze ⇒ Befund
   (Zone `platform` ohne `platform-fix:` ⇒ High).
2. `git log --format='%h %s' main..feat/<Ticket>` – Präfixe prüfen.
3. Handoff `docs/handoffs/<Ticket>.yaml` lesen, aber **nur als Behauptung**: Ticketlauf selbst wiederholen (Punkt 1).

**Punkt 1 Reproduzierbarkeit (alle Stufen):** frische DB, dann
`powershell -ExecutionPolicy Bypass -File scripts/test.ps1` (BE-Tickets ohne `-E2e`, FE-Tickets mit `-E2e`; Plattform-Smoke-Konflikt siehe §3 und G-07);
Bei Speicherdruck Abschnitte: `cd platform\backend; .venv\Scripts\python -m pytest -q ..\..\challenge` bzw. `npx vitest run challenge/frontend`.
Zweiter Lauf auf neuer DB (`DATABASE_URL` auf leere Datei) muss identische Zahlen liefern (Tagesdatum-Unabhängigkeit:
einmal mit `APP_FROZEN_NOW` gesetzt, einmal mit anderem Wert `2026-12-31T10:00:00+01:00` – Tests dürfen nicht kippen, Orakel-Tests
rechnen relativ zum Szenario-`anchor`).

**Eigene Tests (Zone `challenge`, Besitz A3, damit keine Dateikollision):**
`challenge/backend/test_a3_*.py`, `challenge/frontend/waechter/a3/*.test.tsx`, `challenge/e2e/**`. Jeder Test hat eine Mutationsprobe
(im Bericht: Mutation, erwartetes Rot, beobachtetes Rot). Ablage der Mutationsproben: Befehl in der Testdatei als Kommentar `# MUTATION:`.

**Referenzprüfer außerhalb des Repos** (keine neue Abhängigkeit, Vertrag/ENVIRONMENT): `jsonschema` ist **nicht** in der venv
(geprüft: `ModuleNotFoundError`). A3 nutzt `C:\rk\tools\a3-venv` (`python -m venv …; pip install jsonschema==4.* pyyaml`), nur für
Schema-/Antwortvalidierung. Netz nötig ⇒ sonst `NOT RUN: jsonschema nicht installiert`. HAPI: `C:\rk\tools\validator_cli.jar` ist vorhanden,
Java 17.0.20 vorhanden.

## 1. Wiederverwendbare Prüfbausteine

### B1 Rollen-/Fehlermatrix (aus `openapi.yaml` erzeugt, nicht von Hand)
Test `test_a3_matrix.py` liest `openapi.yaml`, ruft jede Operation mit vier Identitäten (anonym, `patient`, `doctor`, `admin`) und
vergleicht Statuscode **und** Fehlerformat `{code,message,field_errors}`. Erwartung:

| Pfadgruppe | anonym | patient | doctor | admin |
|---|---|---|---|---|
| `/me/*` | 401 | 200/201 | 403 | 403 (kein Subjekt) |
| `/patients*`, `/alerts*`, `/notifications` | 401 | 403 | 200 | 200 |
| `GET /config` | 401 | 403 | 200 | 200 |
| `PUT /config/rules`, `PUT /config/report` | 401 | 403 | 403 | 200 / 409 / 422 |

Zusätzlich je mutierender Operation: ohne `X-Requested-With: fetch` ⇒ 403 `csrf_header_missing` (Plattform-Guard läuft **vor** der
Authentifizierung ⇒ anonym ohne Header ist 403, nicht 401 – so testen, nicht als Befund werten). Unbekannte ID ⇒ 404 (gleicher Body wie
„fremd“, kein Existenz-Orakel); Pfad-ID syntaktisch ungültig ⇒ 404 oder 422, nie 500. **Jede 5xx = Befund** (mindestens Medium).

### B2 Paralleltest „4 ⇒ 1“ (Helfer `tests/backend/helpers.py::run_parallel`)
Eigene Session je Thread (eigene Cookies), Barriere-Start. Erwartet jeweils nur die Codes aus dem Vertrag; **alles andere (500, `database is
locked`, 2×200 bei bedingtem Update) = High**. Nach dem Lauf Zustand per GET/DB prüfen (Zeilenzahl, Version, Audit-Anzahl).

### B3 Orakel-Abgleich (S2) – unabhängige Referenz
`test_a3_oracle.py` implementiert die Regeln **selbst** aus Vertrag §3 (≈ 80 Zeilen, ohne Import aus `waechter.*`) und vergleicht
(a) Referenz ⇔ `scenario.yaml.expected`, (b) Referenz ⇔ Systemausgabe nach Seed (`GET /patients/{id}/alerts`, Ampel) für **alle** Szenario-Patient:innen.
Abweichungen in (a) ⇒ Vertragslücke (§7 G-01/G-03) oder Orakelfehler (A1); in (b) ⇒ Implementierungsbefund.
Pflicht-Grenzfälle (eigene Parametrisierung, unabhängig vom Szenario): Wert = Schwelle−1 / Schwelle (`>=`), Baseline mit genau 1 / 2 Werten, gerade
und ungerade Zahl Baseline-Werte (Median), Baseline-Fenster-Rand ±1 Tag, Trend mit `min_points−1`/`min_points`, Trend mit zwei Antworten
am selben Zeitpunkt, `null`-Antworten (nie als Wert, nie imputiert), `missing` genau `max_days` / `max_days+1`, Antwort mit nur `null`.
Mutationsproben: `>=`→`>`, Median→Mittelwert, Fenster ±1 Tag, `null`→0 – jeweils muss mindestens ein Test rot werden.

### B4 IDOR / Subjektbindung
Zweites Patientenkonto nötig (Vertrag liefert nur `patient` = SYN-0001; §7 G-14): Fixture legt per Registry/Seed-Hilfe ein zweites an
oder das Szenario enthält `username` für SYN-0002 (Q). Prüfen: (1) `/me/*` akzeptiert keinen `patient_id` in Query/Body/Header
(wird ignoriert, nicht honoriert); (2) `patient`-Token auf **alle** Clinician-Pfade mit echten fremden IDs ⇒ 403 (nicht 404, nicht 200);
(3) Antwort-IDs (`response_id`) von Patientin A in `GET /me/responses` von B nicht sichtbar; (4) `client_submission_id` von A durch B
wiederverwendet ⇒ keine Fremddaten im Beleg, B bekommt eigene Antwort oder 409/422, **nie** A's `response_id`; (5) Clinician-Pfad
Konsistenz: `GET /patients/{A}/facts/{Fakt von B}` ⇒ 404; `POST /patients/{A}/assessments` mit `related_alert_ids` einer Meldung von B ⇒ 422/404;
(6) `assessed_by`, `by`, `actor_role` im Body ignoriert (serverseitig aus Principal).

### B5 Sprach-/Verbotsprüfung (Punkt 6)
Test scannt **ausgelieferte** Texte (API-Fragebogen `lang=cs|en|de`, i18n-Kataloge, Quittungs-`message_key` aufgelöst) der Patientenseite.
Verbotsliste (Regex, case-insensitiv, cs/en/de), alle als `NOT`-Assertion:
`ampel|traffic|semafor|červen|žlut|rot\b|red\b|yellow|gelb|grün|green|alarm|alert|meldung (an|für) (das )?(team|arzt)|grad\b|grade|stupeň|ctcae|schwere? nebenwirkung|diagnos|therapie(empfehlung|änderung)|doporuč|recommend|empfehl|
alles (in )?ordnung|keine sorge|kein grund|no need to worry|don.?t worry|nemusíte se bát|v pořádku|we will (contact|call)|wir (melden|rufen)|ozveme se|zavoláme|innerhalb von|within \d+|do \d+ (hodin|minut)|notfall|emergency|nouz|112|155`.
Positiv: Bestätigungstext existiert in allen drei Sprachen, enthält **weder** Bewertung **noch** Reaktionszusage; Eskalationstext = Platzhalter
„klinikfreigegeben folgt“ (Vertrag §2). Clinician-Texte/KI-Sätze zusätzlich: `diagnos|empfehl|recommend|doporuč|dose|dosis|absetzen|discontinue|reduce|erhöhen Sie`.
Mutationsprobe: verbotenes Wort in `en.ts` einfügen ⇒ Test rot. Key-Parität cs/en/de als Test (Mutation: Key in `de.ts` löschen).
Fragebogentexte: kein NCI-Wortlaut (Stichprobe `git grep -nEi "at its worst|how often did you have|in the last 7 days.*(what was|how)" -- challenge/content/items.yaml` ⇒ Treffer manuell würdigen; Struktur-Elemente erlaubt, Satzidentität nicht).

### B6 UI 375 px / a11y (Punkt 8)
Playwright-Viewport 375×800: `scrollWidth − clientWidth ≤ 0` (Helfer wie `tests/e2e/specs/mobile.spec.ts`); genau 1 `h1`; jedes Eingabefeld hat Label;
kleinste berechnete Schrift ≥ 16 px (`page.evaluate`: alle sichtbaren Textknoten `getComputedStyle().fontSize`); Touchziele ≥ 44×44 px
(`boundingBox()` aller `button, a, [role=radio], input`); Tastatur: Fragebogen vollständig per Tab/Leertaste/Pfeil bedienbar, sichtbarer Fokus;
Leer-/Fehlerzustand (Backend 500 per `page.route` simuliert) zeigt Text + Wiederholen, nie leere Seite; Ampel **Icon + Text** (nicht nur Farbe).
Warten nie per `sleep`: auf `data-testid`-Zustand (`data-state="ready"`) warten, damit halb geladene Seiten keine falschen Rots erzeugen.

### B7 Privacy (Punkt 7)
`git grep -nIiP "@[a-z0-9.-]+\.[a-z]{2,}|\+?\d{3}[ -]?\d{3}[ -]?\d{3}|\b\d{6}/\d{3,4}\b" -- challenge` (E-Mail/Telefon/Rodné číslo; `rg` ist in dieser Shell nicht installiert) ⇒ 0 Treffer außer
Platzhaltern; Logs eines Testlaufs (`LOG_LEVEL=DEBUG`) enthalten weder Antwortwerte noch `display_name` noch Notiztexte; `Patient.name` fehlt im FHIR-Bundle
(nur Pseudonym + Geburtsjahr); jede Patientenzeile `synthetic=true`; Notification-Text enthält Pseudonym, nicht `display_name` (Q G-17).

## 2. Backend-Tickets (Prüfstufen: **T-06 und T-09 sind per A3.md VOLL**, nicht KURZ – schreibender Endpunkt bzw. versionierte Regelkonfiguration; F-06 ebenfalls VOLL: Export + schreibende Einstellungen. Bei A0-Gegenzeichnung nötig, §7 G-06)

### T-02 Gerüst, Rollen, Seed, `GET /config` (VOLL, ≤ 45 min)
1. Repro: B-Punkt 1 + `python -m app.cli migrate` zweimal (idempotent) + `python -m app.cli seed` zweimal (keine Duplikate, kein Fehler); Migration mit `down_revision="0001"`;
   `pytest`-Lauf lädt die **echte** `challenge/`-Konfiguration (eigene Fixture, da `tests/backend/conftest.py` `challenge_dir` auf leeres tmp setzt).
2. Rollen: `/auth/me` je Demo-Konto (`patient`→role `patient`, `doctor`→`clinician`, `admin`→`admin`), `Principal.subject_id` nur für `patient` gesetzt.
3. Inhaltslader: Je Datei **kaputte Variante** (fehlendes Pflichtfeld, falscher Typ, unbekannter Schlüssel, `value` 5, `version` falsches Muster) ⇒ Start schlägt fehl
   mit Meldung „Datei + Feldpfad“. Querverweis-Integrität (Schema kann sie nicht): `items.ctcae_terms ⊂ ctcae.terms.id`, `regimens.symptom_keys ⊂ items.symptom_keys`,
   `rules.symptom_keys ⊂ items`, `scenario.regimen_id ∈ regimens`, `scenario.answers`-Schlüssel ∈ Items×Attribute, `expected.rule_id ∈ rules` – je Verletzung ein Negativtest.
   Pflicht-Parameter je `kind` (Schema erzwingt sie nicht, §7 G-15): `threshold{min_value}`, `baseline_delta{baseline_days,min_delta,min_value}`, `trend{window_days,min_points,horizon_days,target_value,min_slope_per_day}`, `missing{max_days_without_response}`.
4. Seed: `synthetic=true` überall; Seed liest nur `scenario.yaml` (Anker = `APP_FROZEN_NOW`, sonst Abbruch/Hinweis); zweimal ausgeführt ⇒ gleiche Zeilenzahl; kein Test hängt an der Anzahl (nur an Szenario-Schlüsseln).
5. `GET /config`: B1-Zeile; Antwort validiert gegen `$defs` (Referenzprüfer) – `rules.version`/`report.version` vorhanden; kein Passwort/Secret im Body.
6. Randfälle: Start ohne `challenge/content/` ⇒ klarer Fehler, nicht Halb-Start; `de` fehlt in LocalizedText ⇒ definierter Fallback (Q G-15).
7. Herkunft: nur `challenge/**`; Migration/Modelle in Zone challenge.

### T-03 Fragebogen + Antworten (VOLL)
1. Fragebogenauswahl: Kern-Items immer; Regime-Profil nur des aktuellen Regimes; Regimewechsel (zweites Regime im Szenario) ändert `questionnaire_id`; `questionnaire_id = <items_version>:<regimen_id>`; `lang=cs|en|de`, ungültig ⇒ 422 (nie 500), Default = Patientensprache (G-18).
   Attribute je Symptom nur die in `items.yaml` definierten; Optionen 0–4 (presence 0/1 – G-10).
2. `POST /me/responses`: 201 mit `response_id,recorded_at,message_key`; `answered+skipped = Anzahl answers`; **keine** Felder `level/alert/traffic_light/grade` im Beleg (Test auf Schlüsselmenge).
   Negativ: 422 bei `value` −1/5/„a“/Float, unbekanntem `symptom_key`/`attribute`, fremder/veralteter `questionnaire_id`, doppeltem (symptom,attribute) im Body, leerem `answers` (Q G-10), `client_submission_id` kein UUID; 401/403 B1; CSRF.
   Randfälle: alle `null` ⇒ gespeichert als fehlend, `missing`-Uhr? (Q G-19); `recorded_at` stets Serverzeit (Body-`recorded_at` ignoriert); zwei Sendungen mit gleichem `recorded_at` (eingefrorene Uhr!) behalten stabile Reihenfolge (G-08).
3. Idempotenz: gleiche `client_submission_id` + gleicher Body ⇒ 200 mit **identischem** Beleg, 1 Zeile, 0 neue Meldungen/Notifications; gleiche ID + **anderer** Body ⇒ vom Vertrag nicht definiert (G-10) – Verhalten dokumentieren, mindestens kein stilles Überschreiben.
4. Paralleltest B2: (a) 4× gleiche ID ⇒ genau 1×201 + 3×200, 1 Zeile; (b) 4× verschiedene IDs mit rotem Wert ⇒ höchstens 1 offene Meldung je Tripel und 1 Notification (Vertrag §3 Rauschbremse), kein 500.
5. B4 (Subjektbindung), B5 für `message_key`-Auflösung (nur Katalogprüfung), `GET /me/responses` enthält `answers` mit `null`, **kein** `level`.
6. Privacy: Logzeilen eines POST enthalten keine Antwortwerte.

### T-04 Regeln, Meldungen, Rauschbremse, Notifier, Quittierung (VOLL – Kerntest)
1. B3 vollständig (Orakel gegen `scenario.yaml.expected` **100 %**, Erfolgskriterium S2) + Szenario-unabhängige Grenzfälle. Regeln sind reine Funktionen: Test ruft die Regelfunktion mit fester Eingabe zweimal, nach `FrozenClock` und `SystemClock`, Ergebnis identisch; Quelltext-Grep `git grep -nEi "datetime\.now|time\.time|random|llm" -- challenge/backend/waechter/services/rules*.py` (Pfad laut Ticket anpassen) ⇒ 0 Treffer.
2. Meldung: `rule_id,rule_version` (z. B. `rules-v1`), `explanation.{kind,params,observed,evidence,cycle_day,rationale}`; Evidenz-IDs lösen über `GET …/facts/{id}` auf (Klick-Beleg) ⇒ 200 und Wert passt zu `observed`; `level` der Meldung = `level` der Regel (nie vom Wert abgeleitet außer Regelparametern).
3. Rauschbremse: zweite rote Antwort für dasselbe Tripel solange offen ⇒ keine zweite Meldung; nach Quittierung innerhalb `cooldown_hours` ⇒ keine neue; nach `cooldown_hours+1 s` ⇒ neue (Uhr eingefroren: Zeit per Test-Clock verschieben, nicht schlafen).
   **Sicherheitsfrage (G-02):** Verschlechterung während Cooldown (Wert 3→4, neues Warnsymptom Fieber) darf nicht still unterdrückt werden – Verhalten aufzeichnen; ohne A0-Entscheid = Befund Medium/High je nach Antwort.
4. Notifier: `notify_levels=[red]` ⇒ nur rote Meldung erzeugt genau 1 Eintrag in `GET /notifications` (`channel=in_app`, `level=red`); gelb/grau ⇒ 0; Notification enthält keinen Diagnose-/Handlungstext; Zustellung nicht zugesagt.
5. Quittierung `POST /alerts/{id}/acknowledge`: 200 mit `status=acknowledged`, `acknowledgement.{by,at,decision}`, `by` = Rolle/Konto aus Sitzung. Negativ: 401/403 (patient, admin darf), 404 unbekannt, 409 `alert_not_open` zweite Quittierung, 422 ungültige `decision`/`note` > 500 Zeichen/fehlend, CSRF. **Paralleltest B2: 4 ⇒ genau 1×200 + 3×409**, 1 Audit-Zeile `acknowledge`, Ergebnis-Entscheidung = die des 200-Antworters.
6. Ampel: alle 8 Kombinationen (rot/gelb/grau offen/ack) ⇒ Vertrag §3-Reihenfolge; quittierte Meldung zählt nicht (Folge: G-02, falsche Beruhigung); Sortierung der Arbeitsliste später in T-05.
7. `missing`: nur beim Lesen ausgewertet, 4× paralleles `GET /patients` ⇒ höchstens 1 offene `R-MIS-01`-Meldung je Patientin; Regel deaktiviert (`enabled:false`) ⇒ keine Meldung und Ampel-Rückfall dokumentiert (G-19).
8. Keine LLM-Abhängigkeit: Regeln laufen mit `WAECHTER_LLM` ungesetzt/kaputt identisch (Mutation: `WAECHTER_LLM=anthropic` ohne Schlüssel ⇒ Regeln unverändert).
9. Audit: Quittierung schreibt Zeile mit Rolle, Zeit, Ziel, ohne Freitext `note` im Klartext in Logs.

### T-05 Arbeitsliste, Übersicht, Verlauf, Fakten, Missing (VOLL)
1. Arbeitsliste: Sortierung rot > gelb > grau > grün, dann älteste offene Meldung zuerst; Gleichstand deterministisch (zweites Kriterium = `patient_id`/`pseudonym`; sonst Befund Low); leere Liste ⇒ `[]` nicht 404.
2. Overview: Felder laut Schema; `since_last_visit` ohne letzten Termin ⇒ Fallback definiert (Bezug „seit Beginn“) und im UI erkennbar; `next_visit_at` Randfall (kein geplanter Termin ⇒ `null`); `watch_notes` stammen aus `regimens.yaml` (Quelle `source_id` vorhanden).
3. Timeline: **Vollständigkeit** – Anzahl Punkte je `(symptom,attribute)` = Anzahl Antworten inkl. `null` (Lücke sichtbar, `value:null`); `from/to` Filter (Grenzen inklusiv/exklusiv dokumentieren, ungültiges Datum ⇒ 422); `missing_days` TZ-richtig (G-04); Meldungen/Termine/Arztaufnahmen/`therapy_events` enthalten; keine Imputation (Mutation: Lücke füllen ⇒ Test rot).
4. Fakten `GET …/facts/{id}`: jede in Timeline/Overview/Alert/Summary vorkommende `fact_id` löst auf (Property-Test über alle IDs); falsches Präfix ⇒ 404/422; Fakt einer anderen Patientin ⇒ 404.
5. IDOR/B1 für alle sechs GETs; `/patients/{id}/audit` zeigt Zugriffe (G-16); Antwortzeit-Richtwert Overview < 1 s auf Szenariogröße (informativ, kein Fail).
6. Missing-Auswertung (siehe T-04.7) hier mit Arbeitsliste statt Overview zusätzlich.

### T-06 CTCAE-Template + Aufnahmen (per A3.md **VOLL**)
1. Template: nur Begriffe der Symptome mit Antworten/Tracking der Patientin (**Subraum**): Patientin mit nur 3 getrackten Symptomen ⇒ nur deren `ctcae_terms` (Mutation: alle Begriffe ausliefern ⇒ Test rot); Gradtexte wörtlich aus `ctcae.yaml` (Stichprobe 5 Begriffe gegen PDF/Quelle, Seite `locator`); `pro_hint` nur Hinweis, **kein** vorausgefüllter `grade`/Grad-Vorschlag im Template (Schlüsselmenge prüfen).
2. `POST /assessments`: 201/200 idempotent; 422 für `ctcae_term_id` außerhalb des Subraums, `grade` −1/6, nicht definierter Grad des Begriffs (G-13), leeres `items`, doppelter Begriff, `note` > 500, ungültiger `attribution`; 404 fremde Patientin; 401/403 (Patient 403!); CSRF.
3. Paralleltest: 4× gleiche `client_submission_id` ⇒ 1×201 + 3×200, 1 Zeile; 4× verschiedene ⇒ 4 Zeilen, keine Vermischung.
4. `related_alert_ids`: fremde Meldung ⇒ 422/404 (G-13); Aufnahme **quittiert nicht automatisch** (Meldung bleibt `open`); `assessed_by` serverseitig.
5. Autonomie-Grenze: Server berechnet nie einen Grad; `last_grade` stammt nur aus früherer Arztaufnahme.
6. Append-only: kein PUT/DELETE vorhanden (405).

### T-07 KI-Zusammenfassung (VOLL; hängt am Belegprüfer)
1. **Belegprüfer mit absichtlich falscher Zahl (S4):** Test fügt dem Adapter (Fake-`LlmPort`) Sätze zu: (a) richtige Zahl + gültiger Beleg ⇒ `verified`; (b) Zahl weicht ab (`[obs-…]` hat 3, Satz sagt 4) ⇒ verworfen, `dropped_sentences` +1; (c) Beleg-ID existiert nicht; (d) fremde Patientin-ID als Beleg; (e) kein Beleg; (f) Zahl nur als Teilstring (`4` in `2026-10-14`, `14`) ⇒ muss **verworfen** werden (Tokengrenze, G-09); (g) Zahlwort („vier“, „čtyři“) und Datumsformat (`17. 10.`) – dokumentieren; (h) Beleg richtig, Aussage gegenteilig („steigt“ bei fallender Reihe) ⇒ Vertrag erkennt das nicht – ehrlich als Grenze (Claim-Stufe B/C) im Bericht, nicht als Pass.
   **Anzeige-Invariante:** Summe der ausgelieferten `sentences` mit `verified=false` = 0 in allen Modi (`template`, `cached`, Fake-`live`); Prüfer läuft **auch** auf `template`/`cached` (Mutation: Prüfer für `cached` abschalten ⇒ Test rot).
2. Adapter: `WAECHTER_LLM` ungesetzt ⇒ `template`, `mode=fallback`; `cached` ⇒ ohne Netz (Test mit `HTTP_PROXY=http://127.0.0.1:9`, `NO_PROXY=127.0.0.1,localhost`, Sockets gesperrt) liefert Zusammenfassung; `azure`/`anthropic` ohne Schlüssel oder mit Timeout ⇒ Fallback `template`, **kein** 5xx; kein Schlüssel in Logs/Antwort/Provenance (Suche nach dem Testschlüssel „sk-TEST“ in Logs, Antworten, Provenance ⇒ 0 Treffer). Cache-Schlüssel enthält Fakten-Hash; geänderte Fakten ⇒ Cache-Miss, nie veraltete Antwort (G-09).
3. Inhalt: nur Fakten der Patientin (Prompt-Kontext enthält keine Fremd-IDs – Fake-Port protokolliert Kontext); `unknown_topics` für Thema ohne Daten; **Policy-Filter** (Diagnose/Therapieempfehlung, B5-Clinician-Liste) – Fake-LLM liefert „Dosis reduzieren empfohlen [ther-…]“ ⇒ muss verworfen werden (sonst Befund, G-09).
4. Provenance/Audit: `provenance_id`, `generator`, `generated_at`, Fakten-Hash vorhanden; Audit-Zeile; Hinweis-Key `disclaimer_key` aufgelöst in cs/en/de („KI-Entwurf – prüfen Sie die Belege“).
5. `POST …/summary`: B1; Paralleltest 4× ⇒ Verhalten definieren (G-09: mehrere Entwürfe oder Dedupe nach Fakten-Hash); `GET` vor erster Erzeugung ⇒ 404 `summary_none`.
6. Ein LLM darf `traffic_light`, `level`, `grade` nie ändern: Test mit Fake-LLM, das „rot“ behauptet ⇒ Ampel/Meldungen unverändert.

### T-08 FHIR-Export + HAPI (VOLL)
Befehle (`<Datei>` = Antwort von `GET /api/v1/waechter/patients/<id>/fhir` des Demo-Falls, eingefrorene Uhr):
```powershell
java -version                                                                    # Version im Bericht
java -jar C:\rk\tools\validator_cli.jar C:\rk\tmp\a3\bundle.json -version 4.0.1             # 1) STANDARDLAUF zuerst, Fehlerzahl berichten (S3)
java -jar C:\rk\tools\validator_cli.jar C:\rk\tmp\a3\bundle.json -version 4.0.1 -extension any   # 2) getrennt; nie als „valide“ zählen
```
1. Standardlauf: **0 Fehler** (Warnungen listen, nicht ignorieren); Lauf 2 getrennt mit eigener Zahl. Terminologieprüfung (`-tx`) ist eigener Schritt: offline ⇒ `NOT RUN: Terminologieserver nicht erreichbar`, nicht als bestanden.
   Mutationsprobe: Bundle mit absichtlich kaputter Ressource (`Observation` ohne `status`) ⇒ Validator meldet Fehler (beweist, dass der Lauf etwas prüft).
2. Inhalt gegen Vertrag §5: Ressourcenarten vollständig vorhanden (Patient, MedicationStatement, Questionnaire, QuestionnaireResponse, Observation PRO+CTCAE, Flag, DocumentReference+Provenance, AuditEvent); `Bundle.type=collection`; `fullUrl` `urn:uuid:`; **alle Referenzen** lösen innerhalb des Bundles auf (Test, G-11); alle Zeiten mit Zeitzone; `Patient`: kein `name`, nur Geburtsjahr, `meta.tag` synthetic; `null`-Antworten ⇒ `dataAbsentReason=asked-declined`, nie `valueInteger:0`; CTCAE-Observation: MedDRA-Code 8-stellig + `valueCodeableConcept` Grad; ATC-Code aus Regime; Kanal/`entered_by` als `meta.tag`.
3. Rundlauf-Zählung (nicht an Seed-Anzahlen): Anzahl `Observation(survey)` = Anzahl nicht-`null` Antworten der Patientin per API; Anzahl `Flag` = Anzahl Meldungen; offene Meldung ⇒ `Flag.status=active`, quittiert ⇒ `inactive`.
4. B1: nur clinician/admin; fremde ID 404; `Content-Type: application/fhir+json`; Export schreibt Audit-Zeile (G-16); deterministisch (zwei Exporte, Zeitstempel eingefroren ⇒ byte-gleich nach Entfernung der `urn:uuid`-Werte; sonst Befund Low).
5. Privacy B7. Handoff muss Validator-Version und beide Fehlerzahlen enthalten, sonst Befund Medium.

### T-09 PUT `/config/rules`, `/config/report`, Audit (per A3.md **VOLL**)
1. `PUT /config/rules`: 200 ⇒ `rules-v(N+1)` aktiv (`GET /config` zeigt sie), `changed_by` = admin; Negativ: 401, **403 für doctor und patient**, 409 `version_conflict` bei veraltetem `expected_version`, 422 (unbekannte/fehlende `rule_id`, `kind` geändert, negative/NaN-Parameter, `min_value` > 4, `cooldown_hours` < 0, `notify_levels` leer, fehlender Pflichtparameter je `kind`, `version` im Body), CSRF.
   **Sicherheitsboden (G-12):** alle roten Regeln deaktivieren / `R-URG-01` aus ⇒ vom Server abgelehnt oder zumindest auditiert? Verhalten aufzeichnen.
2. **Paralleltest B2: 4× PUT mit gleicher `expected_version`** ⇒ genau 1×200 + 3×409 `version_conflict`; danach genau `vN+1` (nicht N+2..N+4); `GET /config` und `/audit` konsistent; zusätzlich 2 PUT mit **verschiedenen** Inhalten ⇒ nur der Gewinner sichtbar (kein Mischzustand der Parameter).
3. Wirkung: nach Änderung neue Antworten nutzen neue Schwelle; bestehende Meldungen behalten ihre `rule_version` (Test: Meldung vor PUT hat `rules-v1`); Neustart des Backends (DB-Datei behalten) ⇒ aktive Version bleibt (Persistenz, Datenverlust-Test).
4. `PUT /config/report`: gleiche Matrix inkl. 4 ⇒ 1; `sections`/`since` nur erlaubte Enum-Werte (422); Antwortschema im OpenAPI fehlt (G-12) – Antwortkörper dokumentieren.
5. Audit: `GET /patients/{id}/audit` enthält Konfigänderung? (Vertrag: patientenbezogen; Konfig-Audit ohne Endpunkt ⇒ G-16).

## 3. Frontend-Tickets (F-01…F-06) – gemeinsam: B5, B6 und
**Plattform-Smoke-Konflikt (G-07a):** `tests/e2e/specs/smoke.spec.ts` und `mobile.spec.ts` erwarten `data-testid="no-challenge"` und `meta-version` bei geladener Plattform **ohne** Challenge; sobald
`challenge/backend/plugin.py` Router registriert, ist `challenge_loaded=true` und der Platzhalter verschwindet ⇒ `scripts/test.ps1 -E2e` wird ab T-02/F-01 rot. Das ist ein **Integrationsrisiko für A0**: Änderung der Plattformspecs = `platform-fix:`
(+ Eintrag `provenance/PROVENANCE.md`) oder Smoke mit `CHALLENGE_DIR=<leerer Ordner>` starten (Config in `tests/e2e` nicht änderbar ohne `platform-fix`). Ich prüfe bei jedem FE-/Integrationslauf, dass dies erkannt und sauber dokumentiert ist.

### F-01 Plugin, Routen, i18n, API-Client, Patienten-Check-in (VOLL)
Routen (Vertrag §7): `/patient, /clinic, /clinic/patients/:id, …/assess, …/report, /clinic/alerts/:id, /clinic/settings` existieren; `RequireRole` nur Navigationshilfe ⇒ **Server-Test**: Patient ruft `/clinic` ⇒ Weiterleitung, API-Aufrufe liefern 403 (kein Datenblitz im DOM: Request-Log prüfen, dass keine Clinician-Endpunkte aus der Patientenseite aufgerufen werden).
1. Check-in: Fragebogen aus API, alle Items per Tastatur; Überspringen je Item möglich (sendet `null`, nie 0); Doppelklick „Senden“ ⇒ 1 Request bzw. gleiche `client_submission_id` (Test: Netzwerk-Log); Offline/Fehler ⇒ Entwurf bleibt, Wiederholen ohne neue UUID; Bestätigung nur `message_key`-Text.
2. **Patiententexte ohne Ampel/Grad/Beruhigung**: B5 gegen den **gerenderten DOM** nach dem Senden (cs/en/de) und gegen Katalog; DOM enthält keine Farbklasse/Icon einer Ampel; Eskalations-Platzhalter vorhanden.
3. 375 px (B6) auf `/patient` in cs und en; `lang`-Attribut des Dokuments passt zur Sprache; Sprachumschalter erreichbar per Tastatur; Key-Parität-Test (cs/en/de) + Verbotslisten-Test existieren und haben Mutationsprobe.
4. Vitest: `npx vitest run challenge/frontend/waechter`; `tsc` (Plattform-Config inkludiert `challenge/frontend`).

### F-02 Arbeitsliste, Benachrichtigungs-Banner (KURZ: Punkte 1, 2, 6, 8)
Ampel = Icon + Text (nicht nur Farbe, Kontrast ≥ 4.5:1 per Stichprobe), Sortierung = API-Reihenfolge (nicht erneut sortiert – Mutation: Reihenfolge der Mock-Antwort ändern ⇒ UI folgt); rote Meldung ⇒ Banner genau 1× (Neuladen zeigt nicht doppelt); leere Liste/Fehler-Zustand; 375 px; Klick auf Zeile ⇒ Cockpit ≤ 1 Klick; Banner-Text ohne Zustellversprechen (B5).

### F-03 Cockpit (VOLL, S5)
Screenshot 1366×768 ohne Scrollen: Ampel, offene Meldungen, KI-Kurzfassung, Verlauf gleichzeitig im Viewport (`boundingBox().bottom ≤ 768` je Bereich, Seite `scrollHeight ≤ innerHeight`); ≤ 2 Klicks Arbeitsliste ⇒ Beleg (Klickzähler im Test: Zeile → Zitat → Beleg-Panel); jede Satz-`ref` anklickbar ⇒ `GET facts` ⇒ Beleg sichtbar; **unverifizierte Sätze nie im DOM** (Mock mit `verified:false` ⇒ nicht gerendert, Hinweis „nicht belegt“ nur als Zähler); Hinweis „KI-Entwurf – prüfen Sie die Belege“ sichtbar; fehlt die Kurzfassung (404 `summary_none`) ⇒ definierter Leerzustand + Schaltfläche (G-09); Zeit-bis-Erkenntnis < 30 s mit Stoppuhr im Test (nur Richtwert); Fehlerzustand/Offline (`cached`).

### F-04 Verlauf (VOLL)
Eigene SVG-Kurven: je Symptom/Attribut eine Serie; `null` ⇒ Lücke (Pfad unterbrochen, nicht auf 0), Meldungsmarker an der Zeit der Meldung, fehlende Tage markiert, Termine; Punkt-Anzahl im DOM = Punkte der API (nicht Seed-Zahl); Alternativtext/Tabellenansicht für Screenreader (`<title>`/`aria-label`/Tabelle); Fokus per Tastatur auf Punkt ⇒ Wert + Zeit; 375 px ohne Überstand; Achsenschrift ≥ 16 px (Befund Low, falls SVG-Text kleiner; als Ausnahme begründen lassen).

### F-05 Meldungsdetail + Quittierung; CTCAE-Formular (VOLL)
Erklärung zeigt Regel-ID, Version, Schwelle, Baseline, Zyklustag, Belege (Klick); Quittieren: Doppelklick ⇒ 1 Request; zweiter Browser-Tab quittiert zuerst ⇒ 409 wird als klare Meldung gezeigt (kein Fehlerdialog-Loop); `decision` Pflichtfeld; Formular: nur Subraum-Begriffe, **kein Vorschlag eines Grads** (Radio initial ungewählt), Gradtext sichtbar vor Auswahl, Speichern idempotent (Doppelklick, Wiederholen nach Netzfehler gleiche UUID), Erfolg zeigt gespeicherte Aufnahme; Tastatur komplett; 375 px.

### F-06 Export, Druckansicht, Einstellungen (per A3.md **VOLL**: Export + schreibend)
FHIR-Download ⇒ Datei = API-Antwort (Hash gleich), Dateiname ohne `display_name`; Druckansicht (`@media print`, `page.pdf()`): Abschnitte laut `report.yaml`, „KI-Entwurf“-Kennzeichnung, Synthetik-Hinweis, kein Seitenüberstand; Einstellungen: nur `admin` sichtbar/bedienbar (doctor ⇒ ausgeblendet **und** Server 403), 409 `version_conflict` wird mit Reload-Angebot angezeigt, 422-`field_errors` am Feld; Änderungen erscheinen sofort in `GET /config`.

## 4. Herkunftsprüfung (jede Stufe, vor jedem Merge und vor der Abgabe)

```powershell
cd C:\rk\wt\a3
$py='C:\rk\wt\a3\platform\backend\.venv\Scripts\python.exe'
& $py scripts/provenance.py --out provenance/TABLE.md                    # erzeugen und LESEN (Summen, „Commits nach der Grenze“, „davon berühren platform“)
git log --name-status --format='%h %an %ad %s' --date=iso pre-rakathon..HEAD -- platform tests scripts .github   # muss leer sein oder nur platform-fix:
git log --name-status --format='%h %s' pre-rakathon..HEAD -- ':(top,exclude)platform' ':(top,exclude)tests' ':(top,exclude)scripts' ':(top,exclude).github' ':(top,exclude)challenge' ':(top,exclude)docs' ':(top,exclude)agents' ':(top,exclude)kickoff' ':(top,exclude)provenance' ':(top,exclude)inbox'   # Wurzeldateien: package.json, README.md, CLAUDE.md, .gitignore …
git log --oneline --grep "^platform-fix:" pre-rakathon..HEAD
git diff --stat pre-rakathon..HEAD -- platform tests scripts .github     # muss leer sein (außer registrierte platform-fix)
git ls-tree -r --name-only pre-rakathon -- challenge                       # vor dem Wettbewerb: nur challenge/README.md
git ls-tree -r --name-only HEAD -- challenge | Select-String -NotMatch '^challenge/README\.md$'   # Wettbewerbsbeitrag (nur Info; Zeitpunkt in TABLE.md „during-event“)
git rev-list --count pre-rakathon..HEAD -- challenge
git tag --list "pre-rakathon*"; git rev-parse pre-rakathon                # Tag unverändert: Tag-Objekt 1196374…, Ziel 21932cc
```
Bewertung: jede Änderung in Zone `platform` ohne `platform-fix:`-Präfix, ohne Begründung im Commit oder ohne Eintrag in `provenance/PROVENANCE.md` ⇒ **High, blockiert Merge**.
Tag-Bewegung (`pre-rakathon` zeigt nicht mehr auf 1196374) ⇒ High. Neue Dateien in `challenge/` mit Zeitstempel vor Wettbewerbsbeginn (Fr 16.10. 12:00) außer README ⇒ High.
Zusätzlich: Drittcode/Texte in `challenge/` (Inhalte kopiert?) ⇒ `challenge/content/SOURCES.md` vorhanden, jedes `SourceRef` hat `claim_level`; NCI-Wortlaut-Stichprobe B5; keine Bundles/JAR in Repo (`git ls-files | Select-String '\.jar$'` ⇒ leer; `C:\rk\tools` bleibt außerhalb).
Aussagen in Pitch/README trennen „vor dem Rakathon“ (Plattform, Tag) und „während“ (alles unter `challenge/`).
`provenance/TABLE.md` wird erzeugt und gelesen, aber nur auf Anforderung von A0 committet. Basismessung dieses Plans (16.10.): 189 Dateien, 1 Commit nach der Grenze, 0 berühren `platform`, 0 ohne `platform-fix:`.

## 5. Zeitbudget je Stufe (Richtwerte)

| Stufe | Schritte | Minuten |
|---|---|---|
| Schritt 0 + Punkt 1 | Diff, Dateigrenzen, Testlauf (+ Zweitlauf) | 8 |
| Punkt 2 | Akzeptanz, Negativ-/Randfälle (B1 automatisch) | 8 |
| Punkt 3 | Paralleltests B2 + Persistenz | 6 |
| Punkt 4 | IDOR B4 | 4 |
| Punkt 5 | Orakel B3 (nur T-04, T-09) | 6 |
| Punkt 6 | Sprache B5 | 3 |
| Punkte 7/8/9 | Privacy, UX, Resilienz | 5 |
| Punkt 10 | E2E-Kernpfad (Integration) | 3 |
| Bericht + Herkunft | `docs/verification/<Ticket>.md`, §4-Befehle | 4 |
| **VOLL gesamt** | | **≈ 45** |
| **KURZ** (1, 2, 6, 8 + Herkunft) | | **≈ 22** |

Vorbereitete Tests (`test_a3_matrix.py`, `test_a3_oracle.py`, Verbotsliste) werden **einmal** geschrieben und je Ticket nur parametriert – das hält die Zeitbox. Standardgründe für `NOT RUN`: Netz fehlt (jsonschema/HAPI-Terminologie), Ticket-Branch nicht lauffähig, Port belegt, Speicher (dann Abschnittslauf benennen). PASS nur, wenn alle Pflichtpunkte der Stufe liefen.

## 6. Befundvorlage (Kurzform für jeden Eintrag in `docs/verification/<Ticket>.md`)
`F-<n> · Schwere · Anforderung (Quelle: Vertrag-Pfad/Ticket-Kriterium) · Commit · Schritte · erwartet · beobachtet · Beleg (Befehl+Ausgabe/Datei) · kleinste Korrektur`.
Critical/High ⇒ FAIL. Befunde ohne reproduzierbaren Beleg werden nicht aufgenommen.

## 7. Widersprüche und Lücken im Vertrag v1 (Q an A0; Priorität = Wirkung auf Bau/Prüfung)

Schwere = Risiko, falls ungeklärt gebaut wird. **Blockierend** = vor Bau/Prüfung des genannten Tickets entscheiden.

| ID | Prio | Lücke / Widerspruch (Fundstelle) | Wirkung | Vorschlag (Default, wenn A0 schweigt) |
|---|---|---|---|---|
| G-01 | Blockierend T-04 | README §3: „Median“ bei gerader Anzahl (Baseline, Theil-Sen) undefiniert; Baseline-Fenster Rand (inklusive/exklusive), Einheit der Steigung („pro Tag“ als Bruchteil von 86400 s oder Kalendertage), Paare mit gleichem Zeitpunkt (Division durch 0), „letzte `window_days`“-Rand | S2 (100 %-Orakel) nicht eindeutig prüfbar; Implementierung und A3-Referenz können legitim abweichen | Median = Mittel der zwei mittleren Werte; Fenster `(t − N·24 h, t)` exklusiv des aktuellen Punkts, Rand inklusive; Steigung in Wert/Tag mit Δt in Tagen (Float); Paare mit Δt = 0 verworfen |
| G-02 | Blockierend T-04 (Safety) | §3 Rauschbremse: „nach Quittierung `cooldown_hours` keine neue für dasselbe Tripel“ – auch bei Verschlechterung (3→4) oder neuem Warnsymptom; quittierte Meldungen zählen nicht in der Ampel ⇒ grün trotz fortbestehendem Wert | Falsche Beruhigung der Ärztin (Critical/High im Sinne „unterdrückter Alarm“) | Cooldown gilt nicht, wenn der neue Wert höher als der quittierte ist oder `R-URG-01` feuert; Ampel-Fußnote „quittiert, Wert weiter ≥ Schwelle“ als `grey`/`yellow`-Hinweis |
| G-03 | Blockierend T-01/T-04 | `ScenarioFile.expected.alerts` enthält nur `{day_offset, rule_id, symptom_key}`: kein `attribute`, `level`, Status, `notified`; `missing` hat keinen Antworttag; mehrere Antworten am selben `day_offset` (verschiedene `hour`) nicht unterscheidbar; „keine weiteren Meldungen“ (Rauschbremse) nicht ausdrückbar | Orakel S2 zu grob; Abwesenheit/Unterdrückung ungeprüft | Orakel um `attribute`, `level`, `hour` ergänzen und Semantik „Menge exakt“ festlegen (nicht aufgeführte Meldungen dürfen nicht entstehen); `traffic_light_at_anchor` je Patientin Pflicht |
| G-04 | Blockierend T-04/T-05 | Zeitzone der Tagesgrenzen (`hour` im Szenario, `missing_days`, „Tage seit letzter Antwort“, Baseline-Tage, `date`-Felder) nicht festgelegt; Browser-Locale der Plattform-E2E ist `de-DE` | Orakel kippt um Mitternacht/Sommerzeit | Alle Tagesgrenzen in `Europe/Prague`; `hour` = Prager Ortszeit; ganze Tage = Differenz der Kalendertage |
| G-05 | Blockierend T-02 | `jsonschema` fehlt in der Plattform-venv, „keine neuen Abhängigkeiten ohne A0-Entscheid“; Vertrag verlangt Prüfung „gegen `content.schema.json`“ | Lader kann das Schema nicht nutzen; Handparser = Abweichungsrisiko | Entscheid: (a) `platform-fix:` mit gepinntem `jsonschema` oder (b) Pydantic-Modelle, die A3 per Referenzprüfer außerhalb des Repos gegen das Schema abgleicht |
| G-06 | Vor T-06/T-09/F-06 | `docs/TASKS.md`: T-06, T-09, F-06 = KURZ; `agents/A3.md`: schreibender Endpunkt, Export, versionierte Regelkonfiguration ⇒ VOLL; „herabstufen nie“ | Prüfzeit knapp; Schlafblock hat nur 2 Agenten | Tabelle auf VOLL korrigieren (Zeitbudget +20 min je Ticket) |
| G-07 | Blockierend Integration | (a) Plattform-E2E-Specs (`smoke`, `mobile`) erwarten `no-challenge`/`meta-version` ohne Challenge ⇒ rot, sobald Plugin lädt (§3). (b) `playwright.config.ts` hat `testDir ./specs`, `npm run e2e` und `tests/e2e/tsconfig.json` erfassen `challenge/e2e` **nicht**; `scripts/test.ps1 -E2e` führt E2E-1 daher nicht aus | S1 „im Integrationslauf“ ist so nicht erreichbar; `test.ps1`-Grün irreführend | A0 entscheidet `platform-fix:` (Specs anpassen; Skript/tsconfig erweitern) **oder** A0 führt im Integrationslauf zusätzlich `npx playwright test -c challenge/e2e/playwright.config.ts` und `npx tsc -p challenge/e2e --noEmit` aus (A3 liefert beides) |
| G-08 | Blockierend T-02/E2E-1 | Eingefrorene Uhr ⇒ neue Antworten haben `recorded_at` = Anker; Reihenfolge bei gleichem Zeitpunkt undefiniert (Tie-Break); Seed-Zustand der Meldungen zum Anker (welche offen/quittiert?) und Wiederholbarkeit des Kernpfads (E2E braucht Patientin ohne offene rote Meldung, Aktion „heute“ = Anker) nicht festgelegt | E2E-1 nicht deterministisch/möglich; Trend/Baseline mit identischen Zeiten | Sortierung `(recorded_at, response_id)`; Szenario-Hauptfall endet am Anker mit gelb/grün und **ohne offene rote** Meldung; Seed erzeugt Meldungen über dieselbe Regel-Engine; E2E setzt Uhr nicht, nutzt dafür getrennte Kernpfad-Patientin (SYN-0001) und frische DB je Lauf |
| G-09 | Blockierend T-07/F-03 | (a) Belegprüfer: „jede Zahl kommt in den Belegtexten vor“ – Teilstring vs. Token, Dezimalkomma, Zahlwörter, Datumsformate nicht festgelegt; (b) kein Policy-Filter gegen Diagnose-/Therapieaussagen im Modelltext (COMMON §2); (c) Wer erzeugt die erste Kurzfassung (Seed `cached`? Klick? beim Senden?), `POST /summary` nicht idempotent; (d) Cache-Schlüssel nicht definiert | S4/S5 „0 unbelegte Sätze“ und „Kurzfassung ohne Scrollen“ nicht prüfbar; Diagnoseformulierungen möglich | (a) Zahlen als Tokens `(?<![\d.,])\d+([.,]\d+)?(?![\d])`, Normalisierung `,`→`.`; (b) Verbotsliste (Clinician-Liste in B5) auf Sätze anwenden, Treffer verwerfen; (c) Seed legt `cached`-Kurzfassung für den Demo-Fall an, `POST` erzeugt neuen Entwurf, Dedupe nach Fakten-Hash; (d) Cache-Schlüssel = Fakten-Hash + Prompt-Version |
| G-10 | T-03 | `ResponseSubmit`: `value` 0–4 für alle Attribute, README/Schema: `presence` nur 0/1; gleiche `client_submission_id` mit **anderem** Inhalt; `questionnaire_id` nicht (mehr) passend; leeres/Alles-`null`-`answers`; doppelte (symptom,attribute); fremde Attribute | Uneindeutige 422/200/409; Datenverfälschung | `presence` ∈ {0,1} sonst 422; gleiche ID + anderer Body ⇒ 409 `idempotency_conflict`; unpassende `questionnaire_id`/Attribute ⇒ 422; Alles-`null` erlaubt (zählt als Antwort, aber nicht als Wert) |
| G-11 | T-08 | FHIR §5: Referenzierung per `fullUrl` nicht beschrieben; R4-Pflichtfelder fehlen im Vertrag (`AuditEvent.type/agent.requestor/source.observer`, `Questionnaire.status`, `QuestionnaireResponse.status`, `Flag.subject`, `DocumentReference.status/content`, `Provenance.target`); Terminologie-Lauf offline | 0-Fehler-Ziel (S3) hängt an Details, nicht an der Tabelle | Vertrag um Pflichtfeld-Zeile pro Ressource ergänzen (A2-Hinweis), Terminologie als eigener Schritt `NOT RUN` benennen |
| G-12 | T-09 | `openapi.yaml`: `PUT /config/report` ohne 401/403/422 und ohne Antwortschema (`report: object` statt `ReportFile`); `RulesUpdate.rules: object` ohne `RulesFile`-Referenz; 422-Fälle undefiniert; admin kann alle roten Regeln abschalten; fast alle Clinician-Pfade führen 401/403 nicht auf | Negativtests nicht aus dem Vertrag generierbar | Responses ergänzen; `$ref` auf `content.schema.json#/$defs/…`; Server lehnt Konfiguration ohne aktive rote Regel mit 422 ab (Sicherheitsboden) und auditiert jede Änderung |
| G-13 | T-06 | `AssessmentCreate`: `related_alert_ids` fremder Patientin, nicht definierter Grad eines Begriffs (`grades` hat Lücken „-“), doppelter Begriff, `grade 0` vs. Template ohne Grad 0 | Datenintegrität der Arztaufnahme | 422 bei fremder Meldung, bei nicht definiertem Grad und Duplikaten |
| G-14 | Blockierend IDOR-Test | Nur ein Patientenkonto (`patient`/SYN-0001); „patient→fremde Patientin“ nicht prüfbar; `clinician` sieht per Vertrag alle (keine Zuordnung) | IDOR-Pflichtpunkt 4 bleibt `NOT RUN` | `scenario.yaml`: `username` für SYN-0002 (Demo-Konto `patient2`, Passwort Standard) |
| G-15 | T-01/T-02 | `content.schema.json`: `params` je `kind` ohne Pflichtparameter (`additionalProperties:number` genügt `{}`), `LocalizedText.de` optional ohne definierten Fallback, `format` (date-time) nur mit Format-Checker prüfbar, Querverweise zwischen Dateien nicht ausdrückbar | Fehlerhafte Inhalte passieren das Schema | `if/then` je `kind`; Fallback `de→en→cs`; Querverweis-Prüfung im Lader mit Tests (siehe T-02.3) |
| G-16 | T-05/T-08/T-09 | Audit: „was gesehen“ undefiniert (Lesezugriffe?), Konfig-Änderungen nicht patientenbezogen, `AuditRow` ohne Pflichtfelder; Zugriffsprotokoll bei `GET`-Seiteneffekt | Audit-Test nicht eindeutig; `GET` mit Schreibseiteneffekt | Audit-Aktionen als Enum (`view_overview`, `acknowledge`, `generate_summary`, `export_fhir`, `config_change`) festlegen; globaler Konfig-Audit-Pfad ergänzen |
| G-17 | T-04 | `Notification.text`: PII-Gehalt (Name oder Pseudonym?), kein Gelesen-Status (Banner wiederholt sich nach Neuladen?) | Privacy/UX | Text nur mit Pseudonym; Frontend merkt gesehene `notification_id` lokal |
| G-18 | T-03 | `lang` Standard bei fehlendem Parameter; „heutiger“ Fragebogen – Mehrfachsendung pro Tag erlaubt? Limit gegen Flut | Randfälle, Rauschbremse | Default = `patient.language`; Mehrfachsendung erlaubt (jede zählt als Punkt), kein Limit im v1 |
| G-19 | T-04 | `missing`: Patientin ohne jede Antwort (Referenz = Zyklusstart?); zählt eine Alles-`null`-Sendung als „Antwort“? `R-MIS-01` deaktiviert/fehlend – Ampelregel „grün/grau“ stützt sich auf `max_days_without_response` | Ampel falsch grün/grau | Referenz = `max(letzte Antwort, Zyklusstart)`; Alles-`null` zählt nicht; Ohne `R-MIS-01` gilt Ampel nur aus offenen Meldungen und wird als „unbekannt“ gekennzeichnet |

Reihenfolge der Entscheidung (kritischster Pfad zuerst): G-05 · G-01/G-03/G-04 (zusammen mit A1/T-01) · G-02 · G-08 · G-07 · G-09 · G-10 · G-14 · G-06 · Rest.

## 8. Entwurf E2E-Kernpfad (Ticket E2E-1, Erfolgskriterium S1)

**Ort (Zone `challenge`, Besitz A3):** `challenge/e2e/playwright.config.ts`, `challenge/e2e/specs/core-path.spec.ts`, `challenge/e2e/support/{login.ts,api.ts}`, `challenge/e2e/tsconfig.json` (extends `../../tsconfig.base.json`, include `playwright.config.ts`, `specs`, `support`).
**Aufruf:** `npx playwright test -c challenge/e2e/playwright.config.ts` (Ports `E2E_BACKEND_PORT/E2E_FRONTEND_PORT`; `npx tsc -p challenge/e2e --noEmit`). Einbindung in `scripts/test.ps1 -E2e` nur per `platform-fix:` (G-07, Entscheid A0).

**Konfiguration:** wie `tests/e2e/playwright.config.ts`, aber `testDir ./specs`, `fullyParallel:false`, `workers:1` (ein Zustand, eine DB), `outputDir C:\rk\tmp\<agent>\pw`, `locale 'cs-CZ'`, `timezoneId 'Europe/Prague'`, `webServer[0].env = { E2E_BACKEND_PORT, APP_FROZEN_NOW: '2026-10-17T09:00:00+02:00', DEMO_MODE: 'true' }` (das Plattformskript `tests/e2e/support/start-backend.mjs` reicht die Umgebung durch, löscht die Wegwerf-DB und seedet vor jedem Lauf). Browseruhr: `page.clock.install({ time: '2026-10-17T09:00:00+02:00' })` vor `goto` (Playwright 1.64 vorhanden) – relative Zeitangaben („vor 2 Tagen“) stabil.

**Ankerzeit & Datenunabhängigkeit:** Zeit nur über Anker; Tests lesen **keine** Szenario-Zählwerte. Vorbedingung per API (`doctor`): Hauptfall-Patientin (SYN-0001) hat **keine offene rote Meldung** (`GET /patients/{id}/alerts?status=open` ohne `level=red`), sonst Abbruch mit klarer Meldung „Vorbedingung verletzt: Seed/Anker“ (nicht still grün). Das Symptom für die rote Eingabe wird **zur Laufzeit** aus `GET /config` abgeleitet: erste aktive `threshold`-Regel mit `level=red`, deren (`symptom_key`,`attribute`) im Fragebogen der Patientin vorkommt; Wert = `params.min_value` (Grenzwert, prüft `>=`). Fehlt eine solche Regel ⇒ Test schlägt mit Verweis auf Vertrag fehl.

**Selektorenkonvention:** ausschließlich `data-testid`, kebab-case, `<bereich>-<element>[-<schlüssel>]`; keine Texte/CSS-Klassen als Selektor (Sprache wechselt). Dynamische Schlüssel: Symptom/Attribut `q-<symptom_key>-<attribute>-<value>` (Radio), Zeilen `worklist-row-<pseudonym>`, Meldungen `alert-<alert_id>`, Belege `cite-<fact_id>`. Zustandsattribut `data-state="loading|ready|error|empty"` an jedem Seitenwurzelelement; Tests warten auf `[data-testid=…][data-state=ready]`, nie auf Zeit. Plattform-Login darf die dokumentierten Plattform-Selektoren nutzen (`demo-account-<name>`, Label „Benutzername“).
Erforderliche `testid`s (A2b-Vertrag, wird als Q/Hinweis an A0 für F-01…F-05 gemeldet):

| Seite | testids |
|---|---|
| `/patient` | `patient-page`, `q-<sym>-<attr>-<0..4>`, `q-skip-<sym>-<attr>`, `submit-checkin`, `submit-receipt` |
| `/clinic` | `worklist-page`, `worklist-row-<pseudonym>`, `traffic-light-<pseudonym>` (+ `data-level`), `notification-banner` |
| Cockpit | `cockpit-page`, `cockpit-traffic-light`, `cockpit-alerts`, `alert-<id>`, `summary-sentence-<i>`, `cite-<fact_id>`, `fact-panel`, `timeline-chart` |
| Meldung | `alert-detail`, `ack-decision`, `ack-submit`, `ack-result` |
| Aufnahme | `assess-form`, `assess-term-<ctcae_id>`, `assess-grade-<ctcae_id>-<0..5>`, `assess-submit`, `assess-saved` |
| Export | `export-fhir`, `print-view` |

**Schritte (ein Test, `test.describe.serial`; jeder Schritt `test.step`):**
1. *Setup (API):* Login `doctor`, Vorbedingung prüfen, Ausgangsstand `n_alerts_open_red`, `n_notifications`, `n_assessments` merken (Differenz statt Absolutwerte).
2. *Patient (Kontext A, Viewport 375×800, cs):* Login `patient` ⇒ `/patient` (`data-state=ready`); eine h1; Fragebogen sichtbar; roter Grenzwert wählen, restliche Items beantworten/überspringen; **Doppelklick** `submit-checkin` ⇒ genau 1 `POST /me/responses` (Netzwerk-Zähler, gleiche UUID oder 1 Request); `submit-receipt` sichtbar; **kein** Treffer der Verbotsliste (B5) im sichtbaren Text; kein horizontales Scrollen (B6).
3. *Meldung entsteht (API):* als `doctor` `GET alerts?status=open`: genau +1 rote Meldung für Symptom/Attribut, `rule_version` gesetzt, `notified=true`; `GET /notifications` +1 (`level=red`).
4. *Ärztin (Kontext B, 1366×768, cs):* Login `doctor` ⇒ `/clinic`; `notification-banner` zeigt die Meldung; `worklist-row-SYN-0001` steht in der Liste **vor** allen Nicht-roten Zeilen (Reihenfolge per DOM-Index); `traffic-light-…[data-level=red]` mit Text (nicht nur Farbe).
5. *Cockpit (S5):* Klick auf Zeile (Klick 1) ⇒ `cockpit-page` ready; Ampel, offene Meldungen, Kurzfassung, `timeline-chart` ohne Scrollen sichtbar (`scrollHeight ≤ innerHeight`, `boundingBox().bottom ≤ 768`); Klick auf erstes `cite-*` (Klick 2) ⇒ `fact-panel` zeigt den Beleg; Anzahl der Klicks Liste→Beleg ≤ 2; **jedes** `summary-sentence-*` hat ≥ 1 `cite-*` (0 Sätze ohne Beleg).
6. *Quittieren:* `alert-<id>` öffnen ⇒ `alert-detail` zeigt Regel-ID, Version, Schwelle, Beleg; `ack-decision` wählen, `ack-submit` **zweimal schnell** ⇒ genau 1 Erfolg, danach Status „quittiert“ (`ack-result`); API: Meldung `acknowledged`, Audit-Zeile; zweiter API-Aufruf desselben `acknowledge` ⇒ 409 `alert_not_open`.
7. *CTCAE-Aufnahme:* `/clinic/patients/<id>/assess`: nur Begriffe des Subraums (Anzahl = Begriffe der getrackten Symptome per `GET assessment-template`, nicht fest), kein vorgewählter Grad; Grad für das rote Symptom wählen; `assess-submit` ⇒ `assess-saved`; API: +1 Aufnahme mit `related_alert_ids` (Meldung bleibt unverändert quittiert).
8. *FHIR-Export:* Klick `export-fhir` (Download) oder API ⇒ Datei ist gültiges JSON, `Bundle`/`collection`, enthält `Flag` mit `urn:waechter:rule#<rule_id>`, CTCAE-`Observation` mit dem gewählten Grad, `Patient` ohne `name`; Datei zusätzlich außerhalb von Playwright mit HAPI validiert (Schritt 9).
9. *Validator (Skript im Spec, nur wenn `C:\rk\tools\validator_cli.jar` und `java` vorhanden, sonst `test.skip` mit Grund):* `java -jar … -version 4.0.1` ⇒ „0 Errors“; zweiter Lauf `-extension any` getrennt protokolliert (Spec schreibt beide Zahlen als Annotation).
10. *Aufräumen:* nichts (DB ist Wegwerf); Spec ändert nie Konfig.

**Resilienz/Wiederholbarkeit:** Lauf zweimal hintereinander auf frischer DB identisch; `--repeat-each=2` auf frischer DB je Wiederholung nicht erlaubt (Zustand) ⇒ stattdessen zwei volle Playwright-Aufrufe. Kein `waitForTimeout`; Timeouts 15 s je Erwartung.
**Mutationsproben (im Bericht belegen):** (1) Backend: Schwelle `>=`→`>` ⇒ Schritt 3 rot; (2) Frontend: Sortierung der Arbeitsliste umkehren ⇒ Schritt 4 rot; (3) Cockpit: Satz ohne `cite` rendern ⇒ Schritt 5 rot; (4) Quittierung ohne Bedingung (zweimal 200) ⇒ Schritt 6 rot; (5) FHIR: `Flag` weglassen ⇒ Schritt 8 rot; (6) Patiententext „Ihr Befund ist rot“ ⇒ Schritt 2 rot.
**Abhängigkeiten:** T-02…T-05, T-06 (Template), T-08 (Export), F-01…F-03, F-05, F-06; Vorbereitungsschritt A0: G-07, G-08, G-14.
