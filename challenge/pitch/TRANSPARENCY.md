# TRANSPARENCY – Folie „Was wir vorher hatten – was hier entstand“ (A4, Tickets P-01 bis P-03)

Pflichtbaustein (`kickoff/PITCH_TRANSPARENCY.md`, `agents/A4.md`). Modulliste nur aus `docs/ARCHITECTURE.md` und `provenance/PROVENANCE.md`;
Zahlen nur aus den Befehlen unten. **Freigabe-Vorbehalt:** Ohne A3-Herkunftsprüfung vor der Abgabe ist der Pitch nicht freigegeben
(Prüfregel in `kickoff/PITCH_TRANSPARENCY.md`). A3 hat die Herkunft zuletzt in `docs/verification/INT-4b.md` / `CLAIMS-CHECK.md` bestätigt (int/4b: 412 Commits nach der
Grenze, main danach 417; 6 berühren `platform`, 0 ohne `platform-fix:`); die `challenge/`-Zahlen unten zählt A4 selbst auf `fff4db2` und lässt sie vor Abgabe von A3 gegenzählen (Claim CL-23).

## Zahlen (ausgeführt von A4 im Worktree, Python 3.11.9 vorhanden)

Stand: Branch `pitch/P-03` auf `origin/main` **7462294** (Tag `freeze-poc`, Integration 5, 17.10.2026 ~10:35 MESZ). Gesamtzahl Commits nach der Grenze: 519 laut `git rev-list --count pre-rakathon..origin/main` (A0 nennt 518 – ein Commit Unterschied durch den Zählzeitpunkt, A3 zählt vor Abgabe nach); davon 6 mit `platform`, alle `platform-fix:`, 0 Verstoß (A0 `provenance.py`). Die `challenge/`-Zahlen sind auf `origin/main` 7462294 gezählt (A4): **442 Dateien** (`grep -c "^| challenge/.*| challenge | during-event |" provenance/TABLE.md`; `git ls-files challenge` zeigt 443 = 442 `during-event` + die vorab vorhandene `challenge/README.md`; A0 nennt 443 – maßgeblich ist der Befehl aus `kickoff/PITCH_TRANSPARENCY.md`, A3 zählt nach), **323 Commits** in `challenge/`, **6** `platform-fix`. Vorher (Tag `freeze`, 07:30): 376 / 261 / 6.

```bash
python scripts/provenance.py --out provenance/TABLE.md   # A4: Ausgabe in den Temp-Ordner geschrieben, nicht ins Repo
grep -c "^| challenge/.*| challenge | during-event |" provenance/TABLE.md   # → 442
git rev-list --count pre-rakathon..HEAD -- challenge                        # → 323
git log --oneline --grep "^platform-fix:" pre-rakathon..HEAD | wc -l        # → 6
```

| Kennzahl | Wert | Befehl / Beleg |
|---|---|---|
| Dateien des Wettbewerbsbeitrags (`challenge/`, Zone challenge, `during-event`) | **442** | `grep -c …` (Zeile 2 oben) |
| Commits in `challenge/` seit Tag `pre-rakathon` | **323** | `git rev-list --count pre-rakathon..HEAD -- challenge` |
| Gekennzeichnete Plattform-Korrekturen (`platform-fix:`) | **6** | `git log … --grep "^platform-fix:"`; Liste mit Begründung in `provenance/PROVENANCE.md` §5 |
| Tag `pre-rakathon` | 21932cc, 15.10.2026 21:54 MESZ | `git rev-parse pre-rakathon`, `git log -1 --format=%cI pre-rakathon` |
| Erster Commit in `challenge/` seit dem Tag | 16.10.2026 15:14 MESZ | `git log pre-rakathon..HEAD --format=%cI -- challenge \| tail -1` (A0-Start verspätet: 15:07 statt 12:00, `docs/PROJECT_STATE.md`) |

Die 6 `platform-fix`-Einträge (PROVENANCE §5, jeweils mit Begründung): G-07 (Plattform-Smoke tolerant gegen geladene Challenge), design-system-Flake (Timeout 10 s),
design-system-Flake 2 (30 s/45 s), Tailwind `@source` (eine Zeile für Challenge-Styles), nav-wrap (`flex-wrap` in der Hauptnavigation), H-12 (feste Ankerzeit im E2E-Backend).
Keine dieser Korrekturen betrifft Fachlogik.

## Folie (zweispaltig, wie in `kickoff/PITCH_TRANSPARENCY.md`)

| **Vor dem Rakathon** (Tag `pre-rakathon`, 15.10.2026) | **Während des Rakathons** (16.10. 12:00 – 17.10. 12:00) |
|---|---|
| **Neutrale Plattform ohne Fachlogik** (`docs/ARCHITECTURE.md`, `provenance/PROVENANCE.md` §2): Backend-Kern (Settings, Uhr-Abstraktion, Datenbank, Fehlerformat, Security-Header, Logging ohne Bodies, Argon2/Sitzungs-Token, Konfigurations-Loader, Bedingungs-DSL ohne `eval`), Login und Rollen aus einer Registry, Audit-Log (append-only), Seed-Hook, Erweiterungspunkte, Ports + Mock-Adapter (`LlmPort`, `Notifier`), Frontend-Shell mit Design-System und i18n cs/en/de, Plattformtests | **Die gesamte Challenge-Lösung in `challenge/`**: Backend `waechter` (versionierte Regeln, Meldungen mit Rauschbremse, Quittierung, KI-Kurzfassung mit Belegprüfer, Triage-Kern mit kompiliertem Entscheidungsbaum und Verifikation, FHIR-R4-Export, Arzneimittelsuche, Demo-Reset) · Frontend (Check-in, Arbeitsliste, Cockpit, Verlauf, CTCAE-Aufnahme, Einstellungen, Bericht, Léčiva) · Inhalte (Fragebogen-Items, Therapieprofile, Tipps, Intervalle, CTCAE-Subset, Szenario mit Orakel) mit Quellenregister · Wissensbasis C61/C64 (SPC-Tabellen, je Zeile belegt, vom Prüf-Agenten zweitgelesen (533/533 Begriffe auf der zitierten Seite gefunden, Häufigkeitsklassen für 331 von 533 Zeilen gegengelesen), klinisch nicht freigegeben; CL-25) · Tests und E2E |
| **Agenten-Prompts, Ticket-/Handoff-Vorlagen, Zeitplan, Startablauf** (`agents/`, `kickoff/`) · `scripts/` (setup, dev, test, provenance) | **442 Dateien, 323 Commits** (Befehle oben) |
| **Keine Challenge-Inhalte, keine Daten, keine Regeln** (`challenge/` enthielt nur `challenge/README.md`) | **Plattform-Korrekturen: 6 `platform-fix`** (Liste in `provenance/PROVENANCE.md` §5) |

**Seit dem Freeze neu im Wettbewerbsbeitrag (P-03, alles in `challenge/`, nach dem Zähltag 07:30; Zahlen unten vor Abgabe neu zählen):** Dokumente ⇒ FHIR (T-21, Forschungsprototyp), Freitext mit Folgefragen (T-22, nur nach A3-PASS nennen), offizieller PRO-CTCAE-Wortlaut (T-23), Module je Wirkstoffklasse als Proof of Concept (T-24), Baseline ab Therapiewechsel und „Beobachtete Symptome“ (T-25). Das ändert die Aussage der Folie nicht: alles Fachliche entstand **während** der 24 Stunden.

**Fußzeile der Folie (sichtbar):** „Entwicklung durch KI-Agenten (Claude) unter menschlicher Leitung; unabhängige Prüfung durch einen separaten Prüf-Agenten (A3). Nur synthetische Daten. Prototyp – nicht klinisch validiert.“
(Quelle: `agents/ROSTER.md`, `docs/PROJECT_STATE.md`; die Aussage „KI-Agenten schrieben den Code“ ist Teil der Transparenz und wird nicht versteckt.)

## Externe Beiträge und Vorwissen (offen benennen)

| Was | Herkunft | Umfang / Grenze | Beleg |
|---|---|---|---|
| Spezifikation des Triage-Kerns („SymptomAmpel“, Implementierungs-Prompt v2) | Vom Menschen im Team **während** des Wettbewerbs eingebracht (Datei Fr 16.10. 21:51; Entstehungszeit des Textes nicht belegt) | **Wortlaut für Folie/Q&A (A0 Q4):** „Spec brought in by the team during the event (authoring time not documented); all code written during the event.“ Umsetzung (Code, Tests, Verifikation) vollständig im Wettbewerb | `challenge/contract/triage.md` Kopf, DR-023, ANN-16 (Commit 758a76f) |
| Klinikvorgabe Výzva 3, CTCAE-v6-PDF, Challenge-Material | vom Veranstalter/Menschen bereitgestellt | Eingabe, kein Code | `docs/PROJECT_STATE.md` DR-003/DR-020 |
| Inbox-Bündel der Menschen mit externer KI (`hm-gamification` u. a.) | Branch `inbox` | Nur die **Idee** (eine Frage je Karte) übernommen, **kein Code, kein Maskottchen, keine Texte**; übrige Bündel nicht eingehängt/gestrichen | `docs/handoffs/F-10.yaml` (Herkunft), DR-021, DR-024 |
| InterSystems-FHIR-AI-Hackathon-Kit | öffentliches Repository | Strukturen gelesen, **kein Code übernommen** | `challenge/contract/README.md` §11 |
| Vorwissen aus dem Vorbereitungsarchiv (PRO-CTCAE-Nutzungsbedingungen u. a.) | Vorbereitung, nur gelesen | nichts kopiert | `provenance/PROVENANCE.md` §3 (letzter Punkt), `SOURCES.md` |
| Drittbibliotheken | Plattform-Abhängigkeiten | keine neuen Abhängigkeiten im Wettbewerb (kein scikit-learn; eigener Baum-Compiler) | `docs/THIRD_PARTY_LICENSES.md`, `docs/triage/M2_BERICHT.md` §4 |
| Sprachmodell `gpt-6-1-sol-dz-eu` (gpt-6.1-sol, EU Data Zone, swedencentral) | externer Dienst über das Rakathon-Gateway; Zugang vom Menschen geliefert (17.10. ~04:00) | von uns **nicht trainiert**; nur Entwürfe (Kurzfassung; in den Forschungsprototypen Dokumente ⇒ FHIR und Freitext-Zuordnung, dort jeweils mit Prüfer und ärztlicher bzw. Patientenbestätigung), nur synthetische Daten, `store=false`; Prüfer und Fallback-Textbaustein sind unser Code (T-07H, `feae333`) | A0-Mitteilung 17.10. 04:59, `docs/TASKS.md` T-07H |
| Offizieller PRO-CTCAE-Wortlaut cs/en (T-23) | National Cancer Institute (NCI), Original-PDFs von healthcaredelivery.cancer.gov; **Registrierung/Nutzungsbedingungen ausstehend** (Entscheidung des Menschen, ANN-17) | Fragetexte und Antwortbeschriftungen unverändert übernommen (18 Items × cs/en), 4 eigene Items und die Tagesvariante (24 h) sind **unsere** Fassung und gekennzeichnet; PDFs liegen **nicht** im Repo; Markenhinweis und „Research prototype“ in der App | `SOURCES.md` §11, A3 `T-23.md` (SHA-256 der PDFs, Wortlautabgleich) |
| FHIR-Validator (HAPI 7.0.2) | Dritt-Tool, außerhalb des Repos | nur zur Prüfung | A3 `T-08.md` |

## Gesprochener Satz (≈ 15–25 s, aus `kickoff/PITCH_TRANSPARENCY.md`, mit Zahlen)

**EN:** “Before the Rakathon we prepared a neutral technical base – login and roles, audit log, design system, extension points – without any
domain logic. Everything that addresses the challenge – questionnaire, advice, alerts with a noise brake, a verified decision tree, FHIR export – was built here
during the last 24 hours: 442 files and 323 commits in `challenge/`, six marked platform fixes. The code was written by AI agents under human
direction, and the provenance log in the repository lists every file with its time stamp.”

**DE:** „Vor dem Rakathon haben wir eine neutrale technische Basis vorbereitet – Login und Rollen, Audit-Log, Design-System, Erweiterungspunkte – ohne jede
Fachlogik. Alles, was die Challenge löst – Fragebogen, Rat, Warnung mit Rauschbremse, geprüfter Entscheidungsbaum, FHIR-Export – ist in den letzten 24 Stunden
entstanden: 442 Dateien und 323 Commits in `challenge/`, sechs gekennzeichnete Plattformkorrekturen. Den Code haben KI-Agenten unter menschlicher Leitung geschrieben;
das Herkunftsprotokoll im Repository weist jede Datei mit Zeitstempel aus.“

(Im 3-Minuten-Pitch läuft die Kurzfassung aus `PITCH_3MIN.md`; dieser Satz dient Folie/Standgespräch.)

## Prüfregel (A3, vor Abgabe)

1. A3 führt die drei Zählbefehle aus und bestätigt, dass die Zahlen auf der Folie und im Pitch **identisch** sind.
2. A3 bestätigt, dass in `challenge/` vor 16.10.2026 12:00 nur `challenge/README.md` existierte (Tag `pre-rakathon`, `git ls-tree -r pre-rakathon -- challenge`).
3. A3 bestätigt, dass jede der 6 `platform-fix`-Einträge in `provenance/PROVENANCE.md` §5 steht und keine Fachlogik berührt.
4. A3 bestätigt die Zeile „Spezifikation SymptomAmpel“ (ANN-16, Commit 758a76f) in der Tabelle „Externe Beiträge“ – Entstehungszeit des Spec-Textes bleibt ausdrücklich „nicht dokumentiert“.

**Nicht behaupten:** „alles selbst geschrieben“ (KI-Agenten schrieben den Code), „ohne Vorarbeit“ (Plattform vorab), „Plattform wurde nicht verändert“ (6 `platform-fix`), „Modelle trainiert“ (keine Modelle trainiert; Entscheidungsbaum deterministisch kompiliert).
