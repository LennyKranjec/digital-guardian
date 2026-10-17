# Digitaler Wächter – Stand, Architektur und Roadmap

Stand: Sa 17.10.2026, 10:35 (main nach Integration 5, A3-Endlauf PASS_WITH_RISKS) · Autor: A0 (Lead-Agent) · Grundlage:
`docs/PROJECT_STATE.md` (DR-001…DR-035), `docs/TASKS.md`, Prüfberichte `docs/verification/`.

> Forschungsprototyp, nur synthetische Daten. Keine Diagnose, keine Therapieentscheidung, keine autonome Handlung. Alle
> klinischen Inhalte sind `status: placeholder`, bis ein Kliniker freigibt. Ein LLM bestimmt nie Farbe, Stufe, Grad oder
> Meldung.

## 1. Stand auf einen Blick

| Bereich                                                                     | Stand                       | Beleg                                    |
| --------------------------------------------------------------------------- | --------------------------- | ---------------------------------------- |
| Fragebogen (voll + adaptiv), Fälligkeit nach Therapie/Diagnose, cs/en       | fertig                      | T-03, T-12, T-14…T-16, F-10/F-10F        |
| Patiententipps mit Akut-Weiche (Ambulanz/155)                               | fertig                      | T-10, T-12, F-10F                        |
| Regel-Engine + Triage-Baum, Rauschbremse, Sicherheitsböden                  | fertig, Inhalte Platzhalter | T-04, T-09/T-09G, T-14, T-15, T-16G      |
| Arbeitsliste, Cockpit mit Verlauf, Quittierung, CTCAE-Aufnahme, Bericht     | fertig                      | F-07…F-12, T-13                          |
| LLM-Kurzfassung mit deterministischem Prüfer, Textbaustein-Rückfall         | fertig, Live-LLM nicht aktiv | T-07, T-07F, T-07G                       |
| FHIR R4 Export (Collection/Transaction) + Push (nur Administration)         | fertig                      | T-08, T-18, F-13                         |
| Arzneimittelsuche (Name, kód SÚKL, ATC)                                     | fertig                      | T-17, med-match                          |
| Wissensbasis C61/C64 (SmPC 4.8 ⇒ AE-Matrix ⇒ FHIR), Profile für 4 Wirkstoffe | Schritte 1–3 fertig         | T-KB, T-19/T-19b, T-20/T-20b             |
| Live-LLM (gpt-6.1-sol, EU-Datenzone) für Kurzfassung, Freitext, Dokumente   | fertig, Textbaustein-Rückfall | T-07H                                   |
| Freitext der Patientin: LLM ordnet allen Symptomen zu ⇒ Folgefragen, Antwort zählt | fertig (PoC)            | T-22, T-22F                              |
| Dokumente ⇒ FHIR über LLM (Vorschlag, Bestätigung durch Ärztin)             | fertig (PoC)                | T-21                                     |
| Offizieller PRO-CTCAE-Wortlaut cs/en (7-Tage zu Therapiebeginn, dann 24 h)  | fertig, NCI-Registrierung ausstehend | T-23, T-23G                     |
| Module je Wirkstoffklasse + Diagnosemodul (adaptive Sitzung fragt Diagnosefragen) | fertig (PoC)          | T-24                                     |
| Baseline ab Regimewechsel, Subraum der getrackten Symptome sichtbar         | fertig                      | T-25, T-25G                              |
| Demo (Reset/Start, 7 synthetische Patientinnen), Pitch-Paket                | fertig, Probe durch Mensch  | INT-5, P-03                              |

Gesamtlauf auf main (INT-5, A3): Playwright 175/175, pytest challenge-A 1 061 + challenge-B grün, Plattform/Content/Knowledge,
ruff/mypy/eslint/prettier/tsc/vitest/build grün. Herkunft: 518 Commits nach `pre-rakathon` (Tag `freeze-poc`), 6 Plattform-Korrekturen
(`platform-fix:`), 0 Verstoß.

## 2. Architektur

### 2.1 Einbettung

Plug-in auf der neutralen Plattform (vor dem Wettbewerb entstanden: Login, Rollen, Audit, Designsystem). Der Wächter hängt
sich nur über die Erweiterungspunkte aus `docs/EXTENDING.md` ein:

- Backend: `challenge/backend/plugin.py` (`register(registry)`) ⇒ Paket `waechter`, Routen unter `/api/v1/waechter`,
  eigene Alembic-Migrationen `w001…w007` (SQLite, Tabellen `wa_*`).
- Frontend: `challenge/frontend/plugin.tsx` (`register(api)`) ⇒ `challenge/frontend/waechter/**` (React, Vite,
  Tailwind v4, zod-Schemas je Antwort).
- Verträge zuerst: `challenge/contract/openapi.yaml` (API), `content.schema.json` (Inhalte), `triage.md` (Triage-Kern),
  `README.md` §1–§13. Fixtures aus dem echten Backend (`test_frontend_shapes.py`) halten Frontend und Backend synchron.

### 2.2 Schichten

```
Patient-UI / Klinik-UI (React)           nur Darstellung, keine Fachlogik
        │  zod-geprüfte JSON-Antworten
API-Routen (waechter/api.py)             Autorisierung serverseitig, keine Fachlogik
        │
Services (waechter/services/*)           Fachlogik: checkin, responses, alerts, triage, advice,
        │                                 summary, assessments, fhir_export/push, medications, config
Kerne (rein, testbar ohne DB)            triage/ (Parser, Engine, Policy, Compiler, Verifier, Counterfactual)
        │                                 llm/ (Adapter, Prüfer), fhir/ (Builder), knowledge/ (Pipeline)
Inhalte (challenge/content/*.yaml)       versioniert, schema-validiert, alle klinischen Werte placeholder
Persistenz (SQLite, wa_*-Tabellen)       Antworten, Meldungen, Entscheidungen, Audit
```

### 2.3 Datenfluss einer Meldung

1. Patientin beantwortet Karten (`/me/sessions`, idempotent) oder das Vollformular (`/me/responses`).
2. **Triage-Kern:** Profil aus Therapie (base ⇒ Klasse ⇒ Regime), Selection Policy fragt nur, solange die Stufe nicht
   feststeht (Schranken lo/hi, Gates, kritische Items immer), kompilierter Entropie-Baum entscheidet; Ergebnis mit
   Begründungen, Kontrafaktischen und Spanne lo–hi in `wa_triage_decisions`.
3. **Regel-Engine:** R-SEV/R-URG (rot), R-DLT (Baseline), R-TRD (Theil-Sen-Trend), R-MIS (fehlende Meldung).
4. **Rauschbremse:** Wiederholungen bleiben still, eine offene Meldung gleicher/höherer Stufe trägt die Entscheidung,
   Verschlechterung bricht immer durch (G-02). Nur Rot benachrichtigt sofort.
5. **Patientenantwort:** Akut ⇒ zuerst Klinikhinweis (Ambulanz/155), Tipps unterdrückt; sonst Tipp-Regeln `ADV-*`.
6. **Klinik:** Arbeitsliste nach Dringlichkeit, Cockpit mit Verlauf und Befundkarte, Quittierung, CTCAE-Grad durch die
   Ärztin, Export als FHIR.

### 2.4 Sicherheitsstrategie

- **Determinismus vor KI:** Stufen, Farben, Meldungen und Tipps kommen aus Regeln und dem kompilierten Baum, nie aus einem
  Sprachmodell.
- **Sicherheitsböden** (z. B. Fieber ⇒ Rot) und zwei Konfig-Böden (`no_red_rule`, `no_red_notification`) lassen sich nicht
  wegkonfigurieren; eine rote Regel muss auf eine tatsächlich erfragte Kombination treffen (T-09G).
- **Verifikation des Baums:** V1 (Baum = Regelwerk an jedem Gitterpunkt, komprimiert und ungekürzt), V3 Monotonie, V4
  Schild; Regelkarte wird mit zwei unabhängigen Parsern neu ausgewertet. Große Rohgitter im Betrieb als `sampled_raw`
  ausgewiesen, Vollnachweis einmalig erbracht.
- **LLM nur als Entwurf:** jeder Satz braucht genau einen Beleg aus den Fakten, Zahlen/Richtungen werden gegen den Beleg
  geprüft, Verbotsliste, Injektion abgewehrt; sonst Textbaustein. Externes LLM nur temporär und nur mit synthetischen Daten.
- **Datenschutz:** nur synthetische Patientinnen; vom gemeinsamen Datensatz nur Aggregate (k ≥ 5), kein Code liest ihn
  (Test); ICD-Code nie in Patientenendpunkten, im Export nur in der Condition.
- **Herkunft:** jede Datei vorher/während ausgewiesen (`provenance/TABLE.md`), Annahmen ANN-01…ANN-16.

### 2.5 Interoperabilität

FHIR R4 im Klinikformat: `PUT {Typ}/{id}`, stabile uuid5-IDs, Referenzen `Typ/id`, Patient ohne Namen, Condition mit
ICD-10, Observations je Antwort, Meldungen und Kurzfassung als Dokument. HAPI-Validator 7.0.2: 0 Fehler für alle 7
Patientinnen (beide Bundle-Typen) und das Wissensbundle (706 Ressourcen). Eigene Codesysteme `urn:waechter:*` erzeugen
Warnungen (unveröffentlicht).

## 3. Bekannte Einschränkungen

- Live-LLM nur mit Gateway-Konfiguration (außerhalb des Repos); ohne sie läuft alles über deterministische Rückfälle. Live-Zahlen
  sind Stichproben (Kurzfassung SYN-0001: en 6/6, cs 4–6/6 Sätze belegt; Dokumente: Labor 7/7, Arztbrief 4 zugelassen / 1 verworfen /
  1 nicht erkannt), nicht Teil des A3-Laufs.
- PRO-CTCAE-Wortlaut ohne NCI-Registrierung übernommen (Entscheidung des Menschen, DR-040): Repo privat halten, „Research prototype“.
- Freitext und Dokumente sind Proof of Concept: Zuordnung/Extraktion nicht klinisch validiert, Verneinung im Regelwerk nur über
  Wortlisten; ärztliche Bestätigung Pflicht. Parallele Folgeantworten mit verschiedenen IDs können Dubletten erzeugen (Low).
- Nachfrage am Folgetag zu gemeldeten Symptomen (T-26) ist nicht im Produkt (Roadmap, Branch feat/T-26).
- Deterministischer Prüfer an echten SmPC-Tabellen: nur 93/351 Zeilen bestätigt (bewusst streng); Matrix von einem
  separaten KI-Testagenten zweitgelesen (533/533 Begriffe, 331/533 Häufigkeitsklassen), nicht von einem Kliniker.
- Push nur gegen lokalen Testserver; keine IRIS-Instanz angebunden.
- Adaptive Sitzung folgt dem Therapieprofil; diagnosegruppenspezifische Zusatzfragen nur im Vollformular.
- Kaltstart: erste Triage-Karte bis ≈ 18 s nach Serverstart (Kompilieren + Verifizieren) ⇒ Backend vor der Demo starten.
- cs/de nicht muttersprachlich geprüft; Fragetexte eigene Formulierung in PRO-CTCAE-Struktur, nicht offizieller Wortlaut.
- Composite-Grading als Platzhalter-Abbildung statt Basch-Tabelle; Beschneiden (§8.3) und Diff/Distanz (§8.6) nicht umgesetzt.

## 4. Was noch kommt

### Bis zur Abgabe (heute)

| Zeit       | Schritt                                                                                       | Wer       |
| ---------- | --------------------------------------------------------------------------------------------- | --------- |
| 10:40      | Integration 5 auf main, Tag `freeze-poc` (harte Deadline 11:00, DR-042)            | A0        |
| 07:20      | Kurz-Endprüfung auf main (Herkunft, Demo-Reset, nur Doku seit Endlauf)                        | A3        |
| 07:30      | Tag `freeze`; danach nur Korrekturen und Doku                                                 | A0        |
| ab ~09:00  | Proben mit Stoppuhr                                                                           | Mensch    |
| 12:30      | Code/Demo fertig, letzter Push, Herkunftstabelle neu, Trigger aus                              | A0        |
| 13:00      | Abgabeformular                                                                                | Mensch    |

### Roadmap nach dem Wettbewerb (nicht begonnen, bewusst nach dem Freeze)

1. **Klinische Freigabe:** Schwellen, Böden, Kaskaden, Tipps, Intervalle und Composite-Grading durch FN Motol prüfen
   (`knowledge/CLINICAL_TODO.md`, Mentor-Fragen MQ-T12-01…04, MQ-T20-01/02).
2. **Nachfrage am Folgetag (T-26)** fertigstellen und prüfen; PRO-CTCAE-Item „Bauchschmerzen“ (Ort) aufnehmen; NCI-Registrierung.
3. **Wissensbasis Schritte 4–6:** Kern ∪ Module je Wirkstoffklasse mit Fragenbudget und linearer Schranke, Priore nur als
   Intervalle, Kompilieren mit V1–V5, Tests C1/C4 (Delta v2.1, Meilenstein MA).
4. **Triage-Ausbau:** beschnittene Baumvariante (§8.3) mit ausgewiesener Obertriage-Masse, Diff/Distanz zwischen
   Regelversionen (§8.6), Orbit-Verifikation (V2b), Simulator mit Prioren, Editor/Governance-Panel.
5. **Integration Krankenhaus:** IRIS for Health/FHIR-Server der Klinik statt Testserver, SMART-on-FHIR-Login, Abgleich der
   Medikation aus dem NIS statt Zuordnung bei Aufnahme.
6. **LLM:** funktionierendes Modell am Gateway, Messung der Ausbeute belegter Sätze, Prüfer für Tabellenlayouts
   lockern (heute 93/351).
7. **Sprache und Inhalte:** muttersprachliche Prüfung cs/de, lizenzierter PRO-CTCAE-Wortlaut, weitere Diagnosegruppen.

## 5. Wo was steht

| Thema                      | Ort                                                       |
| -------------------------- | --------------------------------------------------------- |
| Entscheidungen, Zeitplan   | `docs/PROJECT_STATE.md`, `docs/TASKS.md`                  |
| Verträge                   | `challenge/contract/`                                     |
| Prüfberichte (A3)          | `docs/verification/` (Endlauf: `INT-4b.md`, Claims: `CLAIMS-CHECK.md`) |
| Triage-Statusbericht M2    | `docs/triage/M2_BERICHT.md`                               |
| Herkunft, Annahmen         | `provenance/PROVENANCE.md`, `provenance/TABLE.md`         |
| Demo und Pitch             | `challenge/demo/README.md`, `challenge/pitch/`            |
