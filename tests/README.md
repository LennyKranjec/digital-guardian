# Tests

| Ort | Inhalt | Befehl |
|---|---|---|
| `tests/backend/unit`, `tests/backend/integration` | Plattformtests (pytest): Kern, Auth, Audit, Registry, Beispiele aus `docs/EXTENDING.md`, Bedingungs-DSL, Provenance-Skript | `cd platform/backend && python -m pytest -q` |
| `tests/backend/helpers.py` | Paralleltest-Helfer `run_parallel` (gleichzeitige Requests) | wird von Tests importiert |
| `tests/e2e/specs` | Playwright-Smoke gegen echtes Backend (Wegwerf-DB) und Bedingungsvektoren | `npm run e2e` (Ports `E2E_BACKEND_PORT`/`E2E_FRONTEND_PORT`) |
| `platform/frontend/src/**/*.test.ts(x)` | Frontend-Komponenten- und Hilfstests (Vitest) | `npm test` |

**Begründete Ausnahme:** Frontend-Komponententests liegen **neben den Komponenten** (`*.test.tsx`), weil Vitest, der jsdom-Aufbau
(`src/test/setup.ts`) und die Pfad-Importe der Komponenten dort ohne zusätzliche Konfiguration zusammenpassen; ein getrennter
`tests/frontend`-Ordner bräuchte ein zweites Vitest-Projekt. Backend- und E2E-Tests liegen unter `/tests`.

Pflichten für neue Challenge-Tests: Tests hängen nicht an Seed-Anzahlen oder am Tagesdatum (feste Ankerzeit), jeder schreibende
Endpunkt bekommt einen Paralleltest, UI-Seiten haben genau eine `h1` (siehe `docs/RULES.md` §4).
