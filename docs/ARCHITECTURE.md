# Architektur der Plattform

`rakathon-platform` ist ein neutrales Template: Auth-Gerüst, Audit, Fehlerformat, Konfiguration und Erweiterungspunkte,
ohne Fachlogik. Alles Fachliche entsteht in `challenge/` (siehe `docs/EXTENDING.md`).

## Verzeichnisse

| Pfad | Inhalt |
|---|---|
| `platform/backend/app` | FastAPI-Kern: `core` (Settings, Uhr, DB, Fehler, Header, Logging, Sicherheit, Konfigurations-Loader, Bedingungs-DSL), `persistence` (Basis-Modelle, Migration), `services` (Auth, Audit, Seed, System), `api` (Routen), `ports` + `adapters` (Mock-Dienste), `registry.py`, `plugins.py` |
| `platform/backend/alembic` | Migrations-Gerüst und Plattform-Revision `0001` (`users`, `auth_sessions`, `audit_events`) |
| `platform/frontend/src` | React-App: `app` (Shell, Router, Provider), `features/auth`, `features/system`, `features/design-system`, `shared` (API-Client, i18n, UI-Bausteine, Bedingungs-DSL), `registry.ts`, `plugins.ts` |
| `platform/packages` | `design-tokens` (CSS-Variablen, neutrale Status-Tokens, Kontrastprüfung), `contracts` (Bedingungsvektoren, gemeinsam für Python und TypeScript) |
| `challenge/` | nur `README.md`; hier entsteht der Wettbewerbsbeitrag |
| `tests/backend`, `tests/e2e` | Plattformtests (pytest, Playwright-Smoke); Frontend-Komponententests liegen neben den Komponenten (siehe `tests/README.md`) |
| `scripts/` | `setup`, `dev`, `test`, `wheelhouse`, `provenance.py` |
| `docs/`, `agents/`, `kickoff/`, `provenance/` | Dokumentation, Agentenregeln und -prompts, Kickoff-Paket, Herkunftsnachweis |

## Schichten und Regeln

- **Routen** (`api/`) sind dünn: HTTP, Cookie, Validierung. Logik liegt in `services/`; Fachlogik nie in Routen oder UI-Komponenten.
- **Autorisierung ist serverseitig.** `require_roles(...)` (403) prüft die Rolle, objektbezogene Regeln liefert das Challenge-Paket
  (fremdes Objekt ⇒ 404, kein Existenzleck). Die UI-Wächter (`RequireRole`) sind nur Navigationshilfe.
- **Rollen sind Namen aus der Registry** (`admin` und `user` als neutrale Voreinstellung), kein festes Enum.
- **Subjekt statt Fachobjekt:** `Principal.subject_id` und `AuditEvent.subject_id` sind generisch; die Auflösung (Konto → Fachobjekt)
  hängt das Challenge-Paket mit `registry.set_subject_resolver` ein.
- **Fehlerformat:** `{ "code", "message", "field_errors": [{field, code, message}] }`; Fehlerantworten geben nie Eingabewerte zurück.
- **Logging ohne Bodies:** nur Methode, Pfad, Status, Dauer, Request-ID. Keine Query-Strings, Eingaben oder Freitexte.
- **Header:** Security-Header immer, `Cache-Control: no-store` für `/api/`; mutierende Requests brauchen `X-Requested-With: fetch`.
- **Sitzungen:** opake Zufalls-Token, nur der SHA-256-Hash liegt in der DB; HttpOnly-/SameSite-Strict-Cookie; einheitlicher Login-Fehler.
- **Audit:** append-only (ORM-Updates verboten), nie Passwörter oder Eingabewerte; Aktion, Akteur, Rolle, Ziel, Subjekt, Parameter-Details.
- **Uhr:** `Clock`-Abstraktion mit `FrozenClock` (`APP_FROZEN_NOW`, nie in `production`); Tests hängen nie am Tagesdatum.
- **Datenbank:** SQLite (Fremdschlüssel an), Alembic. Plattform- und Challenge-Migrationen bilden einen gemeinsamen Verlauf.
- **Konfiguration:** Pydantic-Schema + `load_yaml_model` (Fehler nennen Datei und Feldpfad, nie Werte).
- **Bedingungs-DSL:** `core/conditions.py` und `shared/lib/conditions.ts` sind semantisch identisch und werden gegen dieselben
  Vektoren (`platform/packages/contracts/*.json`) geprüft; kein `eval`.
- **Ports und Mocks:** `LlmPort` (Mock: `MockLlm`) und `Notifier` (Mock: `MemoryNotifier`) sind generische Protokolle. Ein LLM bestimmt
  nie eine Bewertung oder Stufe; Ausgaben sind Entwürfe mit Quellfeldern.
- **UI:** eine `h1` je Seite, kleinste Schrift 16 px, Touchziele ≥ 44 px, Status nie nur über Farbe (Icon + Text), Zustände
  Laden/Leer/Fehler/Offline/Forbidden/404, Sprachen cs/en/de mit Schlüssel-Parität.

## Ablauf eines Requests

Browser → Vite-Proxy `/api` → FastAPI (Access-Log, CSRF-Wächter, Header) → Route → Service (Rolle, Fachprüfung, Audit) → SQLAlchemy.
Beim Start lädt `create_app` die Settings, die Registry und ein optionales Plugin aus `challenge/backend/plugin.py`.
