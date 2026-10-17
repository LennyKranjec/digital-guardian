# Ursprung jeder Datei (PLATFORM_ORIGIN)

Quelle der Übernahmen: `git show archive/pre-pivot-full-app:<pfad>` (Stand `2b2c613`), nur Dateien mit `klasse_final = PLATFORM` laut
`docs/handover/01-inventory.csv` im Vorbereitungsrepo, plus **entkoppelte Neufassungen** (DR-091). Keine Git-Historie der Fachlogik.
D-01…D-28: `02-decoupling.md`, D-29…D-34: `01-inventory-review.md` §2 (beide im Vorbereitungsrepo).

**Umgesetzt:** alle S/M-Tickets sowie D-08 (L). **Nicht übernommen:** `AreaPage` (D-29, rollenspezifische Fachtexte entfallen), Fach-Tests
der Warnregeln, Fragebögen, Seed-Personas, klinische Konfiguration. Das Template bringt ein **neu erzeugtes** `package-lock.json` mit
(Pakete neu aufgelöst, Versionen exakt gepinnt wie in den `package.json`-Dateien).

## 1. Neufassungen und angepasste Dateien (mit Ursprung und D-Ticket)

| Datei | Ursprung | D-Ticket / Anmerkung |
|---|---|---|
| `.env.example` | .env.example | D-02 (Fach-Flags entfernt) |
| `.github/workflows/ci.yml` | .github/workflows/ci.yml | Pfade |
| `.github/workflows/e2e.yml` | .github/workflows/e2e.yml | Pfade |
| `.gitignore` | .gitignore | Pfade |
| `.prettierignore` | .prettierignore | D-33 |
| `eslint.config.js` | eslint.config.js | Pfade |
| `package.json` | package.json | D-26, Workspace-Pfade |
| `platform/backend/alembic/env.py` | backend/alembic/env.py | D-08 |
| `platform/backend/alembic/versions/0001_platform_base.py` | backend/alembic/versions/0001_initial_schema.py (nur users, auth_sessions, audit_events) | D-08 |
| `platform/backend/app/__init__.py` | backend/app/__init__.py | D-01 |
| `platform/backend/app/api/deps.py` | backend/app/api/deps.py | D-04 |
| `platform/backend/app/api/router.py` | backend/app/api/router.py | D-05 (Registry statt fester Fach-Router) |
| `platform/backend/app/api/v1/auth.py` | backend/app/api/v1/auth.py | D-05 (subject_id) |
| `platform/backend/app/api/v1/demo.py` | backend/app/api/v1/demo.py | D-23 (neutrale Konten aus der Registry) |
| `platform/backend/app/api/v1/system.py` | backend/app/api/v1/system.py | D-17 (Meta erweiterbar) |
| `platform/backend/app/cli.py` | backend/app/cli.py | D-23 (migrate, seed) |
| `platform/backend/app/core/conditions.py` | backend/app/domains/questionnaires/conditions.py | D-09 (nur Import und Ort) |
| `platform/backend/app/core/config_loader.py` | neu; Idee aus backend/app/domains/clinical_config/loader.py | Konfigurationssystem |
| `platform/backend/app/core/deps.py` | backend/app/core/deps.py | D-03 |
| `platform/backend/app/core/pydantic_base.py` | backend/app/domains/shared.py (nur StrictModel, ID_PATTERN) | D-09 |
| `platform/backend/app/core/settings.py` | backend/app/core/settings.py | D-02 |
| `platform/backend/app/main.py` | backend/app/main.py | D-02/D-03 (Registry und Plugin statt Fachkonfiguration) |
| `platform/backend/app/persistence/migrate.py` | backend/app/persistence/migrate.py | D-08 (Mehrfach-Migrationsordner) |
| `platform/backend/app/persistence/models.py` | backend/app/persistence/models.py | D-08 (nur User, AuthSession, AuditEvent) |
| `platform/backend/app/services/access.py` | backend/app/services/access.py | D-04 (nur require_role/not_found) |
| `platform/backend/app/services/audit.py` | backend/app/services/audit.py | D-07 |
| `platform/backend/app/services/auth.py` | backend/app/services/auth.py | D-06 |
| `platform/backend/app/services/seed.py` | backend/app/services/demo.py, backend/app/persistence/seed/* | D-23 (nur neutrale Konten) |
| `platform/backend/app/services/system.py` | backend/app/services/system.py | D-17 |
| `platform/backend/pyproject.toml` | backend/pyproject.toml | D-26 |
| `platform/frontend/index.html` | frontend/index.html | D-12 |
| `platform/frontend/package.json` | frontend/package.json | D-26 (ungenutzte Pakete entfernt) |
| `platform/frontend/public/favicon.svg` | frontend/public/favicon.svg | Beschriftung neutral (aria-label) |
| `platform/frontend/src/app/Logo.tsx` | frontend/src/app/Logo.tsx (neutrales Logo) | D-14 |
| `platform/frontend/src/app/Shell.tsx` | frontend/src/app/Shell.tsx | D-14 |
| `platform/frontend/src/app/app.test.tsx` | frontend/src/app/app.test.tsx | D-16, D-20 (neu geschrieben) |
| `platform/frontend/src/app/router.tsx` | frontend/src/app/router.tsx | D-16 |
| `platform/frontend/src/features/auth/RequireRole.tsx` | frontend/src/features/auth/RequireRole.tsx | D-15 |
| `platform/frontend/src/features/auth/auth.test.tsx` | frontend/src/features/auth/auth.test.tsx | D-15, D-20 (neu geschrieben) |
| `platform/frontend/src/features/auth/model.ts` | frontend/src/features/auth/model.ts | D-15 |
| `platform/frontend/src/features/auth/routes/LoginPage.tsx` | frontend/src/features/auth/routes/LoginPage.tsx | D-15 |
| `platform/frontend/src/features/design-system/design-system.test.tsx` | frontend/src/features/design-system/design-system.test.tsx | D-30 (neu geschrieben) |
| `platform/frontend/src/features/design-system/routes/DesignSystemPage.tsx` | frontend/src/features/design-system/routes/DesignSystemPage.tsx | D-21 |
| `platform/frontend/src/features/system/model.ts` | frontend/src/features/system/model.ts | D-17 |
| `platform/frontend/src/features/system/routes/HomePage.tsx` | frontend/src/features/system/routes/HomePage.tsx | D-17 (Platzhalter ohne Challenge) |
| `platform/frontend/src/plugins.ts` | neu | D-16 (Plugin-Lader) |
| `platform/frontend/src/registry.ts` | neu | D-14, D-15, D-16, D-18 (Erweiterungspunkte) |
| `platform/frontend/src/shared/i18n/cs.json` | frontend/src/shared/i18n/cs.json | D-18, D-34 |
| `platform/frontend/src/shared/i18n/de.json` | frontend/src/shared/i18n/de.json | D-18, D-34 |
| `platform/frontend/src/shared/i18n/en.json` | frontend/src/shared/i18n/en.json | D-18, D-34 |
| `platform/frontend/src/shared/i18n/i18n.test.ts` | frontend/src/shared/i18n/i18n.test.ts | D-34 (neu geschrieben) |
| `platform/frontend/src/shared/lib/format.test.ts` | neu | D-22 |
| `platform/frontend/src/shared/lib/format.ts` | frontend/src/features/patient/format.ts | D-22 (verschoben nach shared/lib, Kommentar neutral) |
| `platform/frontend/src/shared/ui/LinkButton.tsx` | frontend/src/features/patient/components/LinkButton.tsx | D-22 (verschoben nach shared/ui) |
| `platform/frontend/src/shared/ui/QueryErrorView.tsx` | frontend/src/features/patient/components/QueryErrorView.tsx | D-22 (verschoben, Importpfade angepasst) |
| `platform/frontend/src/shared/ui/StatusBadge.tsx` | frontend/src/shared/ui/LevelBadge.tsx | D-11, D-21 (neutrale Status) |
| `platform/frontend/src/test/render.tsx` | frontend/src/test/render.tsx | D-20 |
| `platform/frontend/tsconfig.json` | frontend/tsconfig.json | Pfade |
| `platform/packages/contracts/condition-vectors-extra.json` | docs/verification/t304/a3-condition-vectors.json | D-31 |
| `platform/packages/contracts/condition-vectors.json` | packages/contracts/condition-vectors.json | D-10 (neutrale Item-Namen) |
| `platform/packages/design-tokens/src/tailwind-theme.css` | packages/design-tokens/src/tailwind-theme.css | D-11 |
| `platform/packages/design-tokens/src/tokens.css` | packages/design-tokens/src/tokens.css | D-11 (level-* → status-*) |
| `platform/packages/design-tokens/src/tokens.ts` | packages/design-tokens/src/tokens.ts | D-11 |
| `platform/packages/design-tokens/tsconfig.json` | packages/design-tokens/tsconfig.json | Pfade |
| `scripts/dev.ps1` | neu (ersetzt scripts/start.ps1) | H-06 |
| `scripts/dev.sh` | neu (ersetzt scripts/start.sh) | H-06 |
| `scripts/provenance.py` | neu | H-06 |
| `scripts/setup.ps1` | scripts/setup.ps1 | D-23 (Seed-Hook, Offline) |
| `scripts/setup.sh` | scripts/setup.sh | D-23 |
| `scripts/test.ps1` | scripts/test.ps1 | Pfade |
| `scripts/test.sh` | scripts/test.sh | Pfade |
| `scripts/wheelhouse.ps1` | neu | H-06 |
| `tests/backend/conftest.py` | backend/tests/conftest.py | D-32 (Plattform-conftest abgetrennt) |
| `tests/backend/helpers.py` | neu (Paralleltest-Helfer, Projektvertrag §4) | — |
| `tests/backend/integration/test_auth_api.py` | neu (Muster: backend/tests/integration/test_auth_api.py) | D-05, D-06 |
| `tests/backend/integration/test_error_format.py` | backend/tests/integration/test_error_format.py | D-28, D-32 |
| `tests/backend/integration/test_extending_examples.py` | neu | EXTENDING.md |
| `tests/backend/integration/test_logging.py` | backend/tests/integration/test_logging.py | D-28 (Beispieltext neutral) |
| `tests/backend/integration/test_system_api.py` | neu | D-17 |
| `tests/backend/unit/test_conditions.py` | backend/tests/unit/test_conditions.py | D-09 (Import, Pfad) |
| `tests/backend/unit/test_conditions_vectors.py` | backend/tests/regression/test_t304_conditions.py | D-09, D-31 |
| `tests/backend/unit/test_core_modules.py` | neu | — |
| `tests/backend/unit/test_provenance.py` | neu | H-06 (Herkunft) |
| `tests/e2e/playwright.config.ts` | e2e/playwright.config.ts | Pfade |
| `tests/e2e/specs/conditions.spec.ts` | e2e/regression/t304-conditions.spec.ts | D-31 |
| `tests/e2e/specs/smoke.spec.ts` | neu (ersetzt e2e/specs/smoke.spec.ts) | D-20 |
| `tests/e2e/support/start-backend.mjs` | e2e/support/start-backend.mjs | D-24 |
| `tests/e2e/tsconfig.json` | e2e/tsconfig.json | Pfade |

## 2. Übernommen (Zuordnung `backend→platform/backend`, `frontend→platform/frontend`, `packages→platform/packages`, `e2e→tests/e2e`)

| Datei | Ursprung | Zustand |
|---|---|---|
| `.editorconfig` | `.editorconfig` | unverändert |
| `.gitattributes` | `.gitattributes` | unverändert |
| `.npmrc` | `.npmrc` | unverändert |
| `.pre-commit-config.yaml` | `.pre-commit-config.yaml` | Textanpassung (Kommentar/Pfad/Beispielwert, kein Fachbezug) |
| `.prettierrc.json` | `.prettierrc.json` | unverändert |
| `compose.yml` | `compose.yml` | unverändert |
| `platform/backend/alembic.ini` | `backend/alembic.ini` | unverändert |
| `platform/backend/alembic/script.py.mako` | `backend/alembic/script.py.mako` | unverändert |
| `platform/backend/app/api/__init__.py` | `backend/app/api/__init__.py` | unverändert |
| `platform/backend/app/api/v1/__init__.py` | `backend/app/api/v1/__init__.py` | unverändert |
| `platform/backend/app/core/__init__.py` | `backend/app/core/__init__.py` | unverändert |
| `platform/backend/app/core/clock.py` | `backend/app/core/clock.py` | unverändert |
| `platform/backend/app/core/db.py` | `backend/app/core/db.py` | Textanpassung (Kommentar/Pfad/Beispielwert, kein Fachbezug) |
| `platform/backend/app/core/errors.py` | `backend/app/core/errors.py` | unverändert |
| `platform/backend/app/core/headers.py` | `backend/app/core/headers.py` | unverändert |
| `platform/backend/app/core/logging.py` | `backend/app/core/logging.py` | unverändert |
| `platform/backend/app/core/security.py` | `backend/app/core/security.py` | Textanpassung (Kommentar/Pfad/Beispielwert, kein Fachbezug) |
| `platform/backend/app/persistence/__init__.py` | `backend/app/persistence/__init__.py` | unverändert |
| `platform/backend/app/services/__init__.py` | `backend/app/services/__init__.py` | unverändert |
| `platform/frontend/src/app/App.tsx` | `frontend/src/app/App.tsx` | unverändert |
| `platform/frontend/src/app/DemoBanner.tsx` | `frontend/src/app/DemoBanner.tsx` | unverändert |
| `platform/frontend/src/app/HydrateFallback.tsx` | `frontend/src/app/HydrateFallback.tsx` | unverändert |
| `platform/frontend/src/app/LanguageSelect.tsx` | `frontend/src/app/LanguageSelect.tsx` | unverändert |
| `platform/frontend/src/app/ThemeToggle.tsx` | `frontend/src/app/ThemeToggle.tsx` | unverändert |
| `platform/frontend/src/app/providers.tsx` | `frontend/src/app/providers.tsx` | unverändert |
| `platform/frontend/src/features/auth/api.ts` | `frontend/src/features/auth/api.ts` | unverändert |
| `platform/frontend/src/features/design-system/components/ChartExample.tsx` | `frontend/src/features/design-system/components/ChartExample.tsx` | Textanpassung (Kommentar/Pfad/Beispielwert, kein Fachbezug) |
| `platform/frontend/src/features/design-system/components/ContrastTable.tsx` | `frontend/src/features/design-system/components/ContrastTable.tsx` | unverändert |
| `platform/frontend/src/features/design-system/components/FormsExample.tsx` | `frontend/src/features/design-system/components/FormsExample.tsx` | unverändert |
| `platform/frontend/src/features/system/api.ts` | `frontend/src/features/system/api.ts` | unverändert |
| `platform/frontend/src/index.css` | `frontend/src/index.css` | unverändert |
| `platform/frontend/src/main.tsx` | `frontend/src/main.tsx` | Textanpassung (Kommentar/Pfad/Beispielwert, kein Fachbezug) |
| `platform/frontend/src/shared/api/client.test.ts` | `frontend/src/shared/api/client.test.ts` | Textanpassung (Kommentar/Pfad/Beispielwert, kein Fachbezug) |
| `platform/frontend/src/shared/api/client.ts` | `frontend/src/shared/api/client.ts` | unverändert |
| `platform/frontend/src/shared/i18n/index.ts` | `frontend/src/shared/i18n/index.ts` | unverändert |
| `platform/frontend/src/shared/lib/conditions.test.ts` | `frontend/src/shared/lib/conditions.test.ts` | unverändert |
| `platform/frontend/src/shared/lib/conditions.ts` | `frontend/src/shared/lib/conditions.ts` | Textanpassung (Kommentar/Pfad/Beispielwert, kein Fachbezug) |
| `platform/frontend/src/shared/lib/theme.ts` | `frontend/src/shared/lib/theme.ts` | unverändert |
| `platform/frontend/src/shared/lib/useCurrentTheme.ts` | `frontend/src/shared/lib/useCurrentTheme.ts` | unverändert |
| `platform/frontend/src/shared/lib/useOnlineStatus.ts` | `frontend/src/shared/lib/useOnlineStatus.ts` | unverändert |
| `platform/frontend/src/shared/ui/Button.tsx` | `frontend/src/shared/ui/Button.tsx` | unverändert |
| `platform/frontend/src/shared/ui/StateViews.tsx` | `frontend/src/shared/ui/StateViews.tsx` | unverändert |
| `platform/frontend/src/shared/ui/min-font-size.test.ts` | `frontend/src/shared/ui/min-font-size.test.ts` | unverändert |
| `platform/frontend/src/test/setup.ts` | `frontend/src/test/setup.ts` | Textanpassung (Kommentar/Pfad/Beispielwert, kein Fachbezug) |
| `platform/frontend/vite.config.ts` | `frontend/vite.config.ts` | Textanpassung (Kommentar/Pfad/Beispielwert, kein Fachbezug) |
| `platform/packages/design-tokens/package.json` | `packages/design-tokens/package.json` | unverändert |
| `platform/packages/design-tokens/src/contrast.test.ts` | `packages/design-tokens/src/contrast.test.ts` | unverändert |
| `platform/packages/design-tokens/src/contrast.ts` | `packages/design-tokens/src/contrast.ts` | unverändert |
| `platform/packages/design-tokens/src/index.ts` | `packages/design-tokens/src/index.ts` | unverändert |
| `tsconfig.base.json` | `tsconfig.base.json` | unverändert |

## 3. Neu im Template (ohne Vorlage im Archiv-Tag)

| Datei | Zweck |
|---|---|
| `CLAUDE.md` | Kurzvertrag, verweist auf docs/RULES.md |
| `README.md` | Einstieg |
| `challenge/README.md` | Platzhalter für den Wettbewerbsbeitrag |
| `docs/ARCHITECTURE.md` | Architektur |
| `docs/ENVIRONMENT.md` | Umgebung, Offline, Ports |
| `docs/EXTENDING.md` | Erweiterungsanleitung (getestete Beispiele) |
| `docs/PLATFORM_ORIGIN.md` | diese Datei |
| `docs/RULES.md` | Projektvertrag (Kopie von agents/COMMON.md) |
| `docs/THIRD_PARTY_LICENSES.md` | Lizenzen direkter Abhängigkeiten |
| `platform/backend/app/adapters/__init__.py` | Paketmodul |
| `platform/backend/app/adapters/memory_notifier.py` | In-Memory-Mock des Notifier |
| `platform/backend/app/adapters/mock_llm.py` | deterministischer Mock des LlmPort |
| `platform/backend/app/plugins.py` | Plugin-Lader challenge/backend/plugin.py |
| `platform/backend/app/ports/__init__.py` | Paketmodul |
| `platform/backend/app/ports/llm.py` | generischer LlmPort (Idee: feat/t-212 ports/llm.py, ohne Fachtypen) |
| `platform/backend/app/ports/notifier.py` | generischer Notifier (Idee: feat/t-212 ports/notification.py, ohne Fachtypen) |
| `platform/backend/app/registry.py` | Backend-Erweiterungspunkte (D-03, D-04, D-08) |
| `provenance/PROVENANCE.md` | Vorlage (A0 füllt) |
| `tests/README.md` | Teststruktur |
| `tests/__init__.py` | Paketmodul |
| `tests/backend/__init__.py` | Paketmodul |
| `tests/backend/integration/__init__.py` | Paketmodul |
| `tests/backend/unit/__init__.py` | Paketmodul |

`agents/*` und `kickoff/*` sind Kopien aus dem Vorbereitungsrepo (dort Version 2 der Agentenregeln; `kickoff/README.md` mit angepasstem Pfad `agents/`).
