# Vertrag v2.0 – Triage-Kern „SymptomAmpel“ (DR-023, Sa 02:30, A0)

Quelle: Vorgabe des Menschen `implementation_prompt.md` (Implementierungs-Prompt v2 „SymptomAmpel – kompilierte Wissensbäume mit
gebremstem Lernen“), Abschnitte 2, 6, 7, 8, 12, 15, 17. **Übernommen wird der Kern** (Selection Policy + Entscheidungsalgorithmus +
Verifikation + Erklärung); **nicht** übernommen bis zum Freeze (Roadmap, ehrlich im Pitch): Simulator/Priore (§9), LLM-Freitext-
Mapper (§10), Datenpipelines (§11), Editor/Governance/Panel (§13), Lernleiter (§14), Streamlit-Apps, eigenes Repo-Layout. Alle
klinischen Inhalte (Schwellen, Böden, Kaskaden, Composite-Grading) sind **`status: placeholder`** mit `source`/`assumption`.

## 1. Begriffe (Spec §7.1, §6.1)
- **Level** GREEN < YELLOW < RED, plus `incomplete`. Patient:innen sehen nie ein Level (Spec §12/§15).
- **State**: `(symptom_key, attribute) → 0..4 | fehlt`. **Grad je Symptom** (Composite, Placeholder A-CG-01):
  `grade = max_over_answered_attributes(map[v])`, `map = [0,1,2,3,3]`; presence-Items: grade_max 1 (ja = 1). „größer = schlechter“.
- **Aggregate (Whitelist, monoton):** `max_over`, `min_over`, `count_ge`, `trend_flag` (irgendein Grad ≥ +1 ggü. letztem Bericht
  derselben Patientin; erster Bericht 0). Domänen aus Itemzahl und grade_max abgeleitet.
- **Lehrer (Teacher)** = Regeln `red`/`yellow` als Ausdrücke NUR über Aggregate. **Böden (Floors/Schild)** = Ausdrücke über Items
  (`<sym>.grade`, `<sym>.present`) mit `min_level`, `locked: true`. `final = max(Baum, Böden)`.

## 2. Wissensbasis `challenge/content/triage.yaml` (Schema `content.schema.json#/$defs/TriageFile`)
Profile mit Vererbung `base` → Klasse (`chemo`, `ici`) → Regime-Profil (Schlüssel = `regimen_id` aus regimens.yaml).
„Nur verschärfen“: Kind darf Items/Aggregate/Regeln/Böden hinzufügen (ODER-Verknüpfung, Böden vereinigt), nichts entfernen.
Je Profil: `fixed_items` (Kern, nie entfernt), `safety_items` (gesperrt), `screening {max_questions, rotating_slots, rotation_pool}`,
`cascade {<sym>: {attributes_order, escalate_when?, escalation_items?}}`, `aggregates`, `teacher {red[], yellow[]}`, `floors[]`;
jede Regel/Zahl mit `source` oder `assumption` + `status`.

## 3. Selection Policy (Spec §7.2–7.5) – serverseitig, deterministisch
- **Schranken:** `lo`/`hi` = Level mit unbeantworteten Feldern auf mildeste (0) bzw. schlimmste (grade_max) Antwort. `lo == hi` ⇒
  Stopp `decided`. Fragenzähler ≥ `max_questions` ⇒ Stopp `burden_cap`, `incomplete = (lo < hi)`.
- **Gate-Fragen:** je Symptom zuerst das erste Attribut aus `attributes_order` (Gate). **Kaskade:** Gate > 0 ⇒ Folgeattribute in
  fester YAML-Reihenfolge; Folgefragen, die das Level nicht mehr ändern können (Schranken), werden übersprungen; `escalation_items`
  nur bei erfülltem `escalate_when`. Gate = 0 ⇒ Folgeattribute gelten als 0 („nicht gefragt“, gespeichert als nicht gefragt, nicht
  als fehlend).
- **Reihenfolge (FlipPolicy):** Kandidaten = Gate-Items mit `red_flag` (Safety/Floor-Item) oder Flip (eine Antwort ändert das
  aktuelle Level); Sortierung `(red_flag, flips, priority, -burden)`, Tie-Break stabil nach Symptomschlüssel. Safety-Items werden
  immer gefragt (nie durch `decided` übersprungen).
- **Rotierende Slots:** `rotating_slots` Symptome aus `rotation_pool` als Ja/Nein, Round-Robin nach Zykluswoche; dürfen das Level nur
  erhöhen.
- **Fehlend:** unbeantwortete Safety-Items ⇒ `incomplete=True` und mindestens YELLOW (Reason `INCOMPLETE_SAFETY_ITEMS`); sonstige
  unbeantwortete Felder ⇒ mildeste Antwort für das angezeigte Level, `level_hi` mitgespeichert.

## 4. Kompilierter Baum + Verifikation (Spec §8) – reines Python, KEINE neue Abhängigkeit
- **Gitter** = kartesisches Produkt der Aggregat-Domänen (Schutz `max_product` 2 000 000). Labels aus dem Lehrer.
- **Baum:** eigener Entscheidungsbaum (Entropie, ganzzahlige Schwellen „x ≤ t“, feste Merkmalsreihenfolge, bis zur Reinheit) je
  Ziel (`>= YELLOW`, `RED`), deterministisch; Export JSON mit stabilen Blatt-IDs (Hash des Pfads) und Kopf (KB-Hash, Compiler-Version).
- **V1** exhaustiv: Baum == Lehrer an jedem Gitterpunkt (Unter-/Obertriage 0), **Blattbox-Monotonie** (Spec §8.2 Code), Rot ⇒ Gelb.
  **V3** Einzelschritt-Nachbarn auf dem Rohgitter (Stichprobe mit festem Seed + alle Einzelitem-Kanten) – nie sinkend inkl. Schild.
  **V4** Schild: jeder Punkt im Bodenbereich ≥ min_level. Ergebnis `verification {points, under, over, monotone_violations, scope}`.
- **CompiledEngine** ist Standard; **TeacherEngine** = Referenz. Kompilat beim Start (Cache nach KB-Hash), Verifikation muss 0/0/0
  ergeben, sonst Start mit Fehler (Engine fällt NICHT still zurück).
- **render_rules:** vereinfachte Pfade (je Merkmal engste Schranken), rot zuerst, Klartextnamen cs/en; Pflichttest: gerenderte Regeln
  mit dem sicheren Parser neu ausgewertet == Baum auf dem Gitter.
- **Kontrafaktische** (exakt durch Aufzählung, Endlevel Baum+Schild): „würde sinken, wenn …“ (Einzel-, dann Paaränderungen, max 2),
  „nächste Verschlechterung“ (+1 pro Item); bei Schild „Boden X verhindert Senkung“.
- **Sicherer Parser:** eigener Ausdrucksparser (Vergleiche, and/or/not, Klammern, Aggregatnamen, `sym.grade`, `sym.present`), kein
  `eval`; Lade-Check: Lehrerregel monoton (Einzelschritt-Nachbarn auf dem Aggregatgitter), `not` auf Aggregat ⇒ Ladefehler.

## 5. Einbindung in den Wächter
- **Jede gespeicherte Antwort** (Web-Sitzung, `/me/responses`, Telefon/Papier) ⇒ Triage-Entscheidung (Tabelle `wa_triage_decisions`:
  response_id, level, level_lo, level_hi, incomplete, reason_codes, rule_version=KB-Hash, tree_version, leaf_ids, shield_hits,
  counterfactuals, created_at) – reine Funktion, keine Uhr/kein LLM.
- **Meldungen:** RED ⇒ Meldung `R-TRI-RED` (rot, Sofortbenachrichtigung), YELLOW ⇒ `R-TRI-YEL` (gelb) – je Antwort höchstens eine;
  **Rauschbremse:** besteht für dieselbe Antwort bereits eine Meldung mindestens gleicher Stufe aus den Bestandsregeln (R-SEV-01,
  R-URG-01 …), wird KEINE zusätzliche Meldung erzeugt, sondern die Entscheidung an diese Meldung gehängt (`explanation.triage`).
  Längsschnittregeln (R-DLT-01, R-TRD-01, R-MIS-01) bleiben unverändert. Bestandsorakel bleiben gültig; neue Meldungen nur, wo der
  Baum zusätzlich anschlägt (Orakel-Ergänzung durch A3 mit unabhängiger Lehrer-Auswertung).
- **API (openapi v2.0):** `POST /me/sessions` {client_session_id} ⇒ {session_id, next, progress{asked, max}, stop}; `POST
  /me/sessions/{id}/answers` {symptom_key, attribute, value|null} ⇒ {next | null, stop{reason: decided|burden_cap|complete,
  incomplete}, receipt (bei Stopp: SubmitReceipt inkl. advice/escalation v1.10)}; Sitzungen idempotent je client_session_id;
  Antwort nur auf die aktuell angebotene Frage (sonst 409 `not_current_question`). `GET /patients/{id}/triage?response_id=` ⇒
  Decision (Befundkarte); Overview enthält `triage_latest`. `GET /config/triage` ⇒ Regelkarte (gerenderte Regeln je Profil,
  Böden mit Schloss, Blätter/Tiefe, Verifikationsbanner, Hashes, alle Placeholder-Kennzeichen).
- **Patiententexte:** nie Farbe; nach Stopp Rady/Eskalation laut v1.10; Grün nie als „alles in Ordnung“ (Verbotsliste ergänzt um
  Spec §16 banned_phrases, soweit sprachlich anwendbar).

## 6. Empfehlungsregeln (v2.1, DR-025 – Wunsch des Menschen „recommendation rule feature“, Idee hm-selfcare)
- Jede Empfehlung in `challenge/content/advice.yaml` ist eine **Regel** mit stabiler ID `ADV-<SYMPTOM>-NN`, Symptom, Wertebereich
  `[min_value, max_value]` (max Standard 4) und `status` (draft bis klinische Freigabe). Mehrere Regeln je Symptom (z. B. leicht/
  mittel) sind erlaubt; dann gelten alle passenden.
- **Auswertung (deterministisch, Backend, nie UI):** Regel feuert, wenn irgendein beantwortetes Attribut des Symptoms im Bereich liegt.
  **Unterdrückung:** Symptom löst eine rote Regel aus ODER steht in `escalation.always_acute_for` ⇒ Ergebnis `suppressed_acute`
  (keine Tipps, nur Akut-Hinweis, v1.10).
- **Ausgabe:** Patientin – `SubmitReceipt.advice[]` mit `rule_id` (ID nicht anzeigen); Ärztin – `TriageDecision.recommendations[]`
  (rule_id, Symptom, Wert, shown|suppressed_acute) in der Befundkarte; Regelkarte/Einstellungen zeigen die Tabelle (ID, Symptom,
  Bereich, Anzahl Tipps, Quelle, Status) read-only. Audit `advice_shown` je Antwort (nur Regel-IDs).
- Tests: jede Regel feuert genau im Bereich; Unterdrückung bei Fieber/Atemnot/rot; Patiententexte gegen Verbotsliste.

## 7. Delta v2.1 „Wirkstoff-Module“ – nur Hooks H1–H5 (v2.2, DR-026, Sa ~04:00)
Quelle: Ergänzungsprompt des Menschen (Delta v2.1). Jetzt umgesetzt werden **nur** die Hooks; Module, Wirkstoffkatalog,
Therapieschema-Katalog, SÚKL-Importer (`refdata/`), Orbit-Verifikation (V2b) und `demo compose` sind ausdrücklich NICHT jetzt.
- **H1 Loader/Resolver:** Profile akzeptieren optionales `includes: []` (Schema: Liste von Modul-IDs, derzeit leer erzwungen).
  **v2.9 (T-24, PoC Module):** `includes` ist freigegeben und nennt **Klassenprofile** (ohne `regimen_ids`, ohne eigenes
  `includes`) als Module je Wirkstoffklasse; die Kette wird um deren Vererbungskette erweitert (ohne Doppel) und über dieselbe
  Zusammenführung aufgelöst, also **nur verschärfend** (Neudefinition einer geerbten Regel ohne `loosening` ⇒ Ladefehler).
  Neuer Abschnitt `modules:` (`kind: diagnosis_group`, `diagnosis_groups`): je Blattprofil entsteht die Variante
  `<Profil>+<Modul>`; die Diagnosegruppe der Patientin (ICD-10, `diagnoses.yaml`) wählt sie in `profile_id_for`. Ein durch das
  Modul fest gefragtes Symptom verlässt den Rotationspool. Profile mit `includes` und Varianten liegen in
  `KnowledgeBase.compositions` (nicht in `profiles`): bestehende Profile, Hashes und Prüfläufe bleiben unverändert (Golden-Test).
  Kompilieren/Verifizieren wie jedes Profil (V1/V3/V4); Varianten werden beim ersten Zugriff kompiliert, Klassenmodul-Profile beim
  Vorwärmen und erscheinen in der Regelkarte.
  `resolve()` liefert intern `ResolvedComposition(components, items, max_questions, q_worst_total, coverage_gap=False,
  composition_status, composition_hash)` mit **genau einer Komponente** = bisheriges Profil. Regression: Hash und Verhalten aller
  bestehenden Profile unverändert (Test).
- **H2 Engine:** `TeacherEngine`/`CompiledEngine` halten `components: list` und bilden `max(Komponentenlevel…)`, danach
  `max(…, Böden)`; Reason-Codes tragen `component_id` (bei einer Komponente = Profil-ID). `bounds()` unverändert.
- **H3 Compiler:** `compile_component(component)`; **Domänenkompression** (Δ5.1): Aggregat, das in allen Regeln nur direkt mit
  Konstanten verglichen wird (`>=,>,<=,<,==,!=`), bekommt Domäne `min(natürliches Maximum, k_max + 1)`; mit Arithmetik über Aggregate
  keine Kürzung (Warnung). Tests: Regelergebnisse vor/nach Kürzung identisch; Negativtest Arithmetik; Messung Gitterpunkte/Blätter/
  Laufzeit vorher/nachher im Handoff.
- **H4 Verifikationsbericht:** Felder `components[]` (je Komponente points/under/over/monotone_violations/leaves/depth) und
  `verification_scope ∈ {exhaustive_raw, exhaustive_orbit, sampled_raw}` (`exhaustive_orbit` vorerst unbenutzt). Regelkarte
  (`/config/triage`) gibt `components[]` je Profil mit aus.
- **H5 Schema:** `wa_triage_decisions` zusätzlich `composition_hash`, `composition_status`, `component_ids_json`, `coverage_gap`
  (nullable); Tabelle `wa_patient_regimens` (patient_id, regimen_id, substances_json, module_ids_json, composition_hash,
  composition_status, coverage_gap, valid_from, valid_to) **angelegt, leer**.
- Pitch (Claim D – Zukunft): „Wirkstoff-Module mit höchstens linear wachsender Fragenzahl; SÚKL nur zur Identifikation“ – erst nach
  Umsetzung und Test als Claim A.

## 8. Arzneimittelsuche für die Ärztin (v2.3, DR-027 – Wunsch des Menschen)
- Katalog `challenge/content/medications.yaml` (`$defs/MedicationsFile`): Präparate der Demo-Regime mit Wirkstoff (cs/en),
  Handelsname, **kódSÚKL** (7-stellig), ATC, Regime, SPC-Quelle, Status. Identifikation, **nie** Regel (Delta v2.1 C7).
- `GET /medications?q=` (clinician, admin; patient ⇒ 403): q normalisiert (trim, klein, ohne Diakritik); **Nummern**: nur Ziffern ⇒
  kódSÚKL-Vergleich mit führenden Nullen aufgefüllt (exakt vor Präfix); ATC-Muster (Buchstabe+Ziffern…) ⇒ ATC-Präfix; **Namen**:
  Anfang vor Teilwort über INN cs/en, Handelsname, Synonyme. q < 2 Zeichen ⇒ 422. Antwort inkl. Regime mit Symptomprofil, SPC-Link,
  Anzahl Patient:innen mit Regime. Audit `medication_search` (ohne Suchtext).
- UI: Suchfeld „Léčivo – název, kód SÚKL nebo ATC“ im Ärztebereich (eigene Seite `/clinic/medications` + Navigation; Treffer zeigen
  wie gefunden, Regime, Fragebogen-Symptome, SPC-Link); Wirkstoffe im Cockpit-Kopf verlinken auf die Detailansicht.
- Grenze (ehrlich): nur 6 Präparate der Demo-Regime; vollständiger SÚKL-Katalog = Roadmap (Lizenz klären).

## 9. Klarstellungen nach A3-Prüfung T-14 (v2.4, DR-028)
- **Kritische Items sind immer Gate-Fragen (Safety, A3 T-14 F-03):** Jedes Item mit `critical: true`, das im Profil vorkommt, muss in
  `fixed_items` oder `safety_items` des aufgelösten Profils stehen; sonst **Ladefehler**. Grund: isoliert schweres Erbrechen wurde
  als reine Eskalationsfrage nie gestellt ⇒ Sitzung GRÜN, Volleingabe ROT. Eskalationsfragen dürfen nur nicht-kritische Items sein.
- **Gittergröße (A3 T-14 F-01):** `max_product` bleibt 2 000 000; die Einhaltung erfolgt über die Domänenkompression (H3). `max_product` bezieht sich auf das **komprimierte** Gitter; V1 prüft zusätzlich Baum == Lehrer auf dem **ungekürzten** Gitter (A3-Messung: FOLFOX/CAPECITABINE/DOCETAXEL je 221 184, PEMBROLIZUMAB 13 824 Punkte nach Kürzung). Bleibt ein
  Profil darüber, ist das ein Kompilierfehler mit Meldung (kein stilles Stichproben-V1).
- **Parser (F-02):** Zahlen nur ASCII `[0-9]` (re.ASCII); Unicode-Ziffern ⇒ ExpressionError.
- **Claim-Wortlaut:** „0 Untertriage gegenüber Volleingabe“ erst nach erneuter A3-Messung mit **unabhängiger** Wahrheit (nicht gekoppelt).
- **/me/advice (v2.4):** Symptome aus `always_acute_for` (Fieber, Atemnot) erscheinen auf der Hilfeseite nur als `acute_only` (Akut-Hinweis,
  keine Tipps) – bestätigt (A0, T-13). `Questionnaire.items[].source` ∈ {core, regimen, diagnosis}.

## 10. Sitzungen: Beleg nie verlieren (v2.5, DR-029, A3 F-10 F-01/F-02)
- **Idempotente Stopp-Antwort:** Wiederholt der Client die **identische** letzte Antwort einer bereits beendeten Sitzung, liefert der
  Server **200 mit demselben SessionStep inkl. receipt** (kein neuer Datensatz). `409 session_closed` nur bei **abweichender** Antwort.
- **Beleg abrufbar:** neu `GET /me/sessions/{sessionId}` (nur eigene; fremd ⇒ 404) ⇒ aktueller SessionStep (offen: nächste Frage;
  beendet: stop + receipt). Der Client behält die `client_session_id`/`session_id` nach dem Stopp bis zur nächsten Fälligkeit im
  sessionStorage (nur die Kennung, keine Gesundheitsdaten im Browser) und zeigt beim Neuladen zuerst den Beleg (Akut-Hinweis oben)
  mit Knopf „Neuer Check-in“.
- UI: bei `409 session_closed` nach einem Wiederholversuch zuerst `GET /me/sessions/{id}` und den Beleg zeigen, nie still eine neue
  Sitzung starten.
- **Benennung (v2.5):** in Ärztetexten „Tipps an die Patientin“/„Tipp-Regeln“ statt „Empfehlung“ (Verbotsliste Ärzteseite).
  Kontrafaktik-`text` = Satzteil ohne Einleitung (siehe openapi). `GET /config` enthält `advice`, `medications`, `triage_version`.
- **Anzeige der Verifikation (v2.7, A3 F-11):** Banner nennt immer den Umfang (`exhaustive_raw`/`exhaustive_orbit` ⇒ „vollständig, alle N
  Punkte“, Haken; `sampled_raw` ⇒ „Stichprobe von N Punkten“, kein Haken). Wortlaut „Umsetzungstreue geprüft (Baum = Regelwerk)“ statt
  „verifiziert“, direkt neben „Regelwerk: Platzhalter, klinisch nicht freigegeben“. Kontrafaktik-Einträge mit `kind: shield` werden als
  eigener Schloss-Hinweis gezeigt, nicht als Satzteil.
- **Meldungsart (v2.8, A2-Q T-16):** R-TRI-RED/YEL tragen `explanation.kind = triage` (nicht threshold – sonst falsche Erklärung) und `explanation.triage {…}`; an Bestandsmeldungen angehängte Entscheidungen stehen ebenfalls in `explanation.triage`. Frontend-Schema und „Warum?“-Anzeige nehmen `triage` auf (F-11F).
- **Bekannte Grenzen nach T-16 (v2.8, A0):** (a) Seed erzeugt Triage-Entscheidungen, aber keine R-TRI-Meldungen (Bestandsorakel/E2E
  unverändert); R-TRI-Meldungen entstehen bei neuen Antworten. (b) Der adaptive Sitzungsweg folgt dem Regime-Profil; Zusatzfragen
  einer Diagnosegruppe (derzeit nur LUNG) stellt nur der Vollfragebogen – saubere Lösung = Diagnose als Modul (Delta v2.1, Roadmap).
  (c) Erster Zugriff je Prozess kompiliert + verifiziert ≈ 26 s ⇒ Warmup beim Start und im Demo-Reset.
