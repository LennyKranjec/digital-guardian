# PROVENANCE – Herkunftsprotokoll

**Alle Challenge-Funktionen entstehen nach Freitag, 16.10.2026, 12:00 Uhr (MESZ), im Ordner `challenge/`.**
Vor diesem Zeitpunkt existiert in `challenge/` nur `challenge/README.md`.

## 1. Zustand vor dem Rakathon

| Punkt | Wert |
|---|---|
| Wettbewerbs-Repo | `LennyKranjec/rakathon-waechter` (privat), angelegt 2026-10-15 aus dem Template `LennyKranjec/rakathon-platform` (Stand 06ec49b, Tags übernommen). Darauf ein Vorbereitungscommit nur mit Wettbewerbs-Hilfsmitteln (Challenge-Wahl, Startablauf, Kader) – siehe §3; danach `pre-rakathon` neu gesetzt, Template-Stand bleibt als `pre-rakathon-v2` = 06ec49b |
| Tag | `pre-rakathon` – zeigt auf den letzten Commit vor dem Wettbewerb (Beschleunigung DR-092/DR-093; `git rev-parse pre-rakathon`; Zeitpunkt: `git log -1 --format=%ci pre-rakathon`). Erster Tag-Stand (Einführung dieser Datei) bleibt erhalten als `pre-rakathon-v1` = 34427c4 |
| Geprüfter Plattformstand | `faad4c949ff7f31ecdc9c4a4b7387223c030ffa2` (faad4c9) – unabhängige Verifikation durch A3 (H-07 FAIL → Korrekturen H-06F/H-06G → H-07b PASS_WITH_RISKS, 0 Critical/High); Bericht im Vorbereitungsrepo `LennyKranjec/rakathon`, `docs/handover/05-template-verification.md` |
| Unterschied Tag ↔ geprüfter Stand | nur Dokumentation (`git diff --stat faad4c9 pre-rakathon`): diese Datei; `docs/ENVIRONMENT.md` und `kickoff/PITCH_TRANSPARENCY.md` (Zählbefehl ohne Summenzeile – Befehl von A3 verifiziert, H-07b N-1; Tabellenreparatur N-2); `kickoff/TIMEPLAN_24H.md` (Integrationsabstand im Schlafblock, N-3). Danach Beschleunigung DR-092/DR-093 (`git diff --stat pre-rakathon-v1 pre-rakathon`): `agents/A0.md`, `agents/A2.md`, `agents/A3.md`, `agents/COMMON.md` (+ Kopie `docs/RULES.md`), `agents/TICKET_TEMPLATE.md`, `docs/ENVIRONMENT.md` (Ports A2b), `kickoff/KICKOFF_PROMPT.md`, `kickoff/TICKET_TEMPLATE.md`, `kickoff/TIMEPLAN_24H.md`, `kickoff/README.md` und diese Datei – Bau ≤ 60 min je Ticket, Prüfstufen VOLL/KURZ/INTEGRATION, Fließband Bau ‖ Prüfung, in Bauphasen bis zu 4 Agenten (A2 ‖ A2b) mit Abbruchkriterium; nur Text, **nicht von A3 geprüft** (A0-Selbstprüfung; Begründung im Vorbereitungsrepo `docs/handover/04-prompt-changes.md`, Abschnitt DR-092/DR-093) |
| Herkunft der Plattformdateien | `docs/PLATFORM_ORIGIN.md` (Ursprungsdatei im Vorbereitungsrepo, Tag `archive/pre-pivot-full-app`, und Entkopplungsticket je Neufassung) |
| Klassifikation | Vorbereitungsrepo `docs/handover/01-inventory.csv` (PLATFORM 91 / DOMAIN 254 / KNOWLEDGE 89, A3-Stichprobe 42,4 %) |

## 2. Plattformmodule (vor dem Rakathon entstanden)

Quelle: `docs/ARCHITECTURE.md`.
- **Backend-Kern** (`platform/backend/app/core`): Settings, Uhr-Abstraktion (`FrozenClock`), Datenbank, Fehlerformat, Security-Header,
  Logging ohne Bodies, Sicherheit (Argon2, Sitzungs-Token), Konfigurations-Loader (Pydantic + YAML), Bedingungs-DSL ohne `eval`.
- **Persistenz** (`persistence`, `alembic`): Basis-Modelle `users`, `auth_sessions`, `audit_events`; Plattform-Migration `0001`.
- **Dienste** (`services`): Anmeldung/Sitzungen, Audit (append-only), Seed-Hook, Systeminfo.
- **Erweiterungspunkte** (`registry.py`, `plugins.py`; Frontend `registry.ts`, `plugins.ts`): Router, Rollen, Subjekt-Auflösung,
  Demo-Konten, Seed, Meta, Routen/Navigation, i18n-Kataloge.
- **Ports + Mock-Adapter:** `LlmPort` (`MockLlm`), `Notifier` (`MemoryNotifier`) – generisch, ohne Fachbezug.
- **Frontend** (`platform/frontend`): Shell, Router, Provider, Anmeldung mit Rollen aus der Registry, Systemseiten
  (Laden/Leer/Fehler/Offline/403/404), Design-System-Seite, UI-Bausteine, i18n cs/en/de mit Schlüssel-Parität,
  Platzhalter „Noch keine Challenge-Funktionen geladen“.
- **Pakete** (`platform/packages`): `design-tokens` (neutrale Status-Tokens, Kontrastprüfung), `contracts` (Bedingungsvektoren).
- **Tests** (`tests/`): Plattformtests (pytest, Playwright-Smoke inkl. 375 px), Helfer `run_parallel` für Paralleltests.

## 3. Vorab erstellte Hilfsmittel

- `agents/` – Agenten-Prompts A0–A4 (v2), gemeinsame Regeln, Ticket- und Handoff-Vorlage.
- `kickoff/` – Kickoff-Prompt, 24-h-Zeitplan, Intake-Checkliste, Transparenzbausteine, Ticket-Vorlage.
- `scripts/` – `setup`, `dev`, `test`, `wheelhouse` (Offline-Installation), `provenance.py` (diese Herkunftstabelle).
- `docs/` – `ARCHITECTURE.md`, `EXTENDING.md`, `ENVIRONMENT.md`, `RULES.md`, `PLATFORM_ORIGIN.md`, `THIRD_PARTY_LICENSES.md`.
- Wettbewerbs-Hilfsmittel (2026-10-15, nach Wahl der Challenge durch den Menschen): `kickoff/CHALLENGE.md` (Challenge-Material als
  Eingabe, wörtlich aus der Vorbereitung; keine Lösung), `kickoff/START.md` (autonomer Startablauf für A0), `kickoff/PASTE_PROMPT.md`
  (die eine Startnachricht), `docs/EXT_KONTEXT.md` (die eine Kontextdatei für externe KIs) und `inbox/README.md` (Upload-Weg der Menschen, Branch `inbox`; Inbox-Spur START §4a), `agents/ROSTER.md` (Kader, Modelle, Worktrees, Ports); `agents/A0.md` verweist darauf.
- Außerhalb des Repos eingerichtet: AgentsRoom-Projekt „Rakathon Waechter“ mit gespeicherten Agenten-Vorlagen A0–A4/A2b
  (Persona = Rollendatei), Prompt „Rakathon START (A0)“, Trigger „Rakathon weiter nach Limit“ (ausgeschaltet), Worktrees
  `C:\rk\wt\a1…a4` mit installierten Abhängigkeiten (keine Inhalte).
- Keine Challenge-Lösung: kein Code, keine Fachregeln, keine fachbezogenen Daten, keine Pitch-Inhalte, kein MVP-Zuschnitt
  (den legt A0 ab 12:00 fest). Vorbereitetes Wissen aus dem Archiv wird bei Nutzung hier mit Pfad nachgetragen (`kickoff/START.md` §7).
- Vorwissen genutzt (T-01, A1, nur gelesen, nichts kopiert, 2026-10-16): `E:\rakathon\docs\science\challenge-research.md` und `limitations.md` (PRO-CTCAE-Nutzungsbedingungen, L-51); Details in `challenge/content/SOURCES.md`.

## 4. Herkunftstabelle

`python scripts/provenance.py --out provenance/TABLE.md` (Datei · erste Änderung · Zeitpunkt · Zone · pre-event/during-event ·
Ursprungspfad, Summen je Zone/Klasse, Commits nach der Grenze, `platform-fix:`-Liste). Vor der Abgabe erzeugen und committen;
A3 prüft zusätzlich `git log --name-status pre-rakathon..HEAD -- platform tests scripts .github` (siehe `agents/A3.md`).

## 5. Änderungen an der Zone platform während des Rakathons (nur `platform-fix:`)

| Commit | Datei(en) | Begründung | A0-Entscheid |
|---|---|---|---|
| `platform-fix: G-07` (Branch fix/G-07) | `tests/e2e/specs/smoke.spec.ts`, `tests/e2e/specs/mobile.spec.ts`, `tests/e2e/playwright.config.ts`, `tests/e2e/tsconfig.json` | Plattform-Smoke erwartete den Platzhalter „keine Challenge“ und wurde rot, sobald das Challenge-Plugin lädt; Challenge-E2E (`challenge/e2e`) wurde von `test.ps1 -E2e` nicht erfasst (neuer Erweiterungspunkt). Prüfung jetzt bedingt über `/api/v1/meta.challenge_loaded`; ohne Challenge unverändert 39/39 grün | A0, DR-007 G-07 (A3-PLAN §7) |
| `platform-fix: design-system-Flake` (Branch fix/G-07) | `platform/frontend/src/features/design-system/design-system.test.tsx` | Bekannter Flake (§7): `findBy*` mit Standard-Timeout 1 s; unter Last (mehrere Agenten) lädt die Seite länger ⇒ Integrationslauf rot (Basislauf Fr 15:09 und Probe-Integration Fr ~16:00). Nur Warte-Timeout 10 s, keine Prüfung entfernt | A0 |
| `platform-fix: design-system-Flake 2` (Branch fix/flake2) | `platform/frontend/src/features/design-system/design-system.test.tsx` | 10 s reichten unter Last nicht (Integrationslauf 2: 13 s „Wird geladen“); Warte-Timeout 30 s, Testtimeout 45 s; kein Retry, keine Prüfung entfernt (A3 INT-2 F-01) | A0 |
| `platform-fix: Tailwind @source` (Branch fix/tailwind-source) | `platform/frontend/src/index.css` | Tailwind v4 erzeugte Utility-Klassen nur aus Dateien unter `platform/frontend`; Klassen, die nur in `challenge/frontend` vorkommen, fehlten im Build (A2b F-07 Q1). Eine Zeile `@source '../../../challenge/frontend'` – fehlender Erweiterungspunkt für Challenge-Styles | A0 |
| `platform-fix: nav-wrap` (Branch fix/nav-wrap) | `platform/frontend/src/app/Shell.tsx` | Hauptnavigation `flex gap-1` brach nicht um; ab fünf Einträgen (Challenge-Navigation „Léčiva“) horizontaler Überstand ≈48 px bei 375 px (A2b F-12, im Browser gemessen) – Verstoß gegen die 375-px-Regel. Nur `flex-wrap` ergänzt | A0 |
| `platform-fix: H-12` (Branch fix/G-07) | `tests/e2e/playwright.config.ts`, `tests/e2e/specs/mobile.spec.ts` (Titel) | E2E-Backend ohne feste Ankerzeit ⇒ Seed/Challenge-E2E nicht deterministisch; `APP_FROZEN_NOW` = Szenario-Anker im webServer-env (A3: alle 39 Plattform-Tests damit grün) | A0, A3-Befund H-12 |
| `platform-fix: Kopfzeile` (d0588b6, Branch feat/T-30) | `platform/frontend/src/app/ThemeToggle.tsx`, `LanguageSelect.tsx`, `Shell.tsx` | **Keine Fehlerkorrektur, sondern ausdrückliche UI-Vorgabe des Menschen am Wettbewerbstag (Sa 11:20, DR-044):** Hell/Dunkel als ein Sonne/Mond-Symbol, Sprachwahl mit Globus-Symbol statt Textbeschriftung, Design-System-Link als Drei-Striche-Symbol. Barrierefreie Namen unverändert; transparent hier ausgewiesen | Mensch, A0 DR-044 |

## 6. Annahmen aus dem Intake (während des Rakathons zu füllen)

| ID | Annahme | Quelle/Default |
|---|---|---|
| ANN-01 | Jury-Kriterien: Klinischer Wert & UX 30 %, Konfigurierbarkeit 20 %, Verlässlichkeit KI 20 %, Datenanbindung/Standards 15 %, Prozess & verantwortungsvolle KI 15 %, +10 % Bonus | Startnachricht des Menschen (Fr 15:07) |
| ANN-02 | Abgabe Sa 13:00 (Code/Demo 12:30), Bewertung Sa 14–16 am Stand durch Klinikärzt:innen, Finale So 3-min-Pitch ohne Fragen | Startnachricht |
| ANN-03 | Mentorin = einzige Jurorin; Fokus: im Krankenhaus integrierte Web-App, Historie jederzeit, Metriken + Meldungen im Verlauf, LLM-Kurzfassung | Startnachricht |
| ANN-04 | Patientenseite PRO-CTCAE-artig cs/en; Arztseite CTCAE-Subraum der getrackten Symptome, Speicherung HL7 FHIR | Startnachricht |
| ANN-05 | Keine NCI-PRO-CTCAE-Itemtexte im Repo (Nutzungsbedingungen ungeprüft); eigene Formulierung in PRO-CTCAE-Struktur | kickoff/CHALLENGE.md, START §6, DR-002 |
| ANN-06 | CTCAE v6.0 (Jan 2026) ist US-Regierungswerk, Gradtexte dürfen mit Quellenangabe zitiert werden | PDF vom Menschen; A1 prüft Hinweis im PDF |
| ANN-07 | Nur synthetische Daten; keine Daten gestellt | START §6 |
| ANN-08 | Kein LLM-Schlüssel vorhanden ⇒ Adapter `cached`/`template` für Demo, Azure/Anthropic per Umgebungsvariable vorbereitet | START §6, Frage an Menschen |
| ANN-09 | Kein KIS; „Integration“ = FHIR-R4-Export + Rollen/Login + dokumentierte Integrationsstelle | kickoff/CHALLENGE.md |
| ANN-10 | Sofortbenachrichtigung als In-App-Benachrichtigung (Notifier-Port); keine Zustellzusage | COMMON §2 |
| ANN-11 | Sprache App cs (Standard) + en (+ de aus Plattform), Pitch Englisch | START §6 |
| ANN-12 | Feature-Freeze Sa 07:30 (nach Zeitkorrektur DR-030; zwischenzeitlich irrtümlich 08:00–09:00) (Start 3 h verspätet, Abgabe 12:30) | A0, DR-005 |
| ANN-15 | Klinikvorgabe Výzva 3 (PDF FNM, Sa 01:30) verlangt Fragebogen nach Diagnose + Therapie in Intervallen, Rady pacientovi (Ambulanz/155), Team-Alarm; Eingangsdaten SPC (SÚKL), CTCAE v6.0, gemeinsamer Datensatz. Datensatz liegt nicht vor (vom Menschen bestätigt Sa 02:00: kein Klinik-Datenzugriff; echte Quellen nur Klinik-PDF + SÚKL-Datenbank prehledy.sukl.cz) ⇒ weiter synthetisch | Klinik-PDF, Mensch, A0 DR-020 |
| ANN-16 | Spezifikation „SymptomAmpel“ (`implementation_prompt.md`, 808 Zeilen) wurde vom Menschen **während** des Wettbewerbs eingebracht (Datei heruntergeladen Fr 16.10. 21:51). Wann der Text verfasst wurde, ist nicht belegt ⇒ Ausweisung „Spezifikation: vom Team eingebracht, Entstehungszeit unbelegt“; der gesamte Code dazu (`challenge/backend/waechter/triage/`, T-14 ff.) ist während des Wettbewerbs entstanden | Mensch, A0 DR-023 |
| ANN-17 | PRO-CTCAE-Wortlaut (cs/en) wörtlich aus den NCI-PDFs übernommen ohne vorherige NCI-Registrierung – Entscheidung und Risiko beim Menschen (DR-040); Markenhinweis und „NCI registration pending“ in App und SOURCES.md | Mensch, A0 DR-040 |
| ANN-14 | MedDRA-Codes aus der NCI-CTCAE-Veröffentlichung im Prototyp; produktive Nutzung erfordert MedDRA-Lizenz. CTCAE-PDF ohne Nutzungshinweis, NCI verlangt Quellenangabe + Link (`challenge/content/SOURCES.md` §2) | A1 T-01, A0 |
| ANN-13 | Klinische CTCAE-Aufnahme als FHIR `Observation` (MedDRA-Code + Grad); `AdverseEvent`/ECCDM-Profil nicht umgesetzt | A0, Vertrag §5 |

## 7. Bekannte Grenzen der Plattform (Stand Tag)

- Lizenzen: `docs/THIRD_PARTY_LICENSES.md` nennt nur direkte Abhängigkeiten; transitive Pakete und Schrift (OFL) nur als Hinweis;
  **keine `LICENSE`-Datei** – Entscheidung des Menschen (2026-10-15): keine Lizenz, das Repo bleibt privat.
- `DEMO_MODE=true` als Standard (lokaler Demo-Betrieb; für echten Betrieb nicht geeignet, siehe `docs/ENVIRONMENT.md`).
- Offline-Installation nur mit vorab befülltem Wheelhouse (`scripts/wheelhouse.ps1`) und npm-Cache derselben Python-Minor-Version
  und desselben Betriebssystems.
- NOT RUN vor dem Tag: GitHub-Actions-Lauf, Python 3.12 lokal (CI-Ziel), Referenzvalidator (HAPI) gegen Plattformdaten (keine vorhanden).
- Einmal beobachtet (A0, Lauf vor dem Tag): `design-system.test.tsx` lief unter Rechnerlast in eine Zeitüberschreitung (8,5 s,
  Seite noch „Wird geladen“); einzeln 3/3 grün, anschließender Gesamtlauf `test.ps1 -E2e` Exit 0 (159 / 108 + 57 / 39, 58 s).
- Beschleunigung DR-092/DR-093 (Ticketgröße, Prüfstufen, Fließband, 4 Agenten in Bauphasen) ist ungemessen und nicht von A3 geprüft; Wirkung erst an den
  Ist-Zeiten im Zeitplan ablesbar.
- `dev.ps1` ohne Stop-Skript (Server über die Dev-Commands der Arbeitsumgebung beenden).
- Herkunftsprüfung von Hand (`git log … -- platform tests scripts .github`) erfasst Wurzeldateien nicht; das Skript listet sie im
  Abschnitt „Commits nach der Grenze, die die Zone platform berühren“.
