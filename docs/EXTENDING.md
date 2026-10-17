# Plattform erweitern

Alles Neue entsteht in `challenge/` (Zonenregel: `docs/RULES.md` §1). Die Plattform wird nur über **Erweiterungspunkte** ergänzt:
Backend `challenge/backend/plugin.py` mit `register(registry)`, Frontend `challenge/frontend/plugin.tsx` mit `register(api)`.
Die Beispiele unten sind **ausführbar getestet**: `tests/backend/integration/test_extending_examples.py` (Backend),
`platform/frontend/src/app/app.test.tsx` (Frontend).

## 1. Neues Modul (Backend-Router)

```python
# challenge/backend/plugin.py
from fastapi import APIRouter

def register(registry):
    router = APIRouter(prefix="/example", tags=["example"])

    @router.get("/ping")
    def ping() -> dict[str, str]:
        return {"pong": "ok"}

    registry.add_router(router)             # erscheint unter /api/v1/example/ping
    registry.add_role("reviewer", "Rolle")  # optional: neue Rolle (Name frei)
    registry.add_meta_extension(lambda settings: {"example": {"enabled": True}})  # Zusatzfelder in /meta
```

**Schreibender Endpunkt ⇒ Paralleltest** mit `tests/backend/helpers.py::run_parallel` (z. B. vier gleichzeitige Requests, genau ein Erfolg;
Beispiel: `test_parallel_logins_all_succeed` in `tests/backend/integration/test_auth_api.py`), auch für Challenge-Endpunkte (Test unter `challenge/backend/`).

Serverseitige Rollenprüfung: `Annotated[Principal, Depends(require_roles("reviewer"))]` aus `app.api.deps`; fremde Objekte
ergeben 404 (`app.services.access.not_found()`), falsche Rolle 403. Logik gehört in einen Service, nicht in die Route.

## 2. Neue Seite (Route + Navigation)

```ts
// challenge/frontend/plugin.tsx
import type { PluginApi } from '../../platform/frontend/src/registry';

export function register(api: PluginApi): void {
  api.registerRoutes({ path: 'example', element: <ExamplePage /> });
  api.registerNav({ to: '/example', labelKey: 'example.nav', roles: ['reviewer'] });
  api.registerRoleHome('reviewer', '/example');            // Startseite nach der Anmeldung
  api.registerCatalog('de', { example: { nav: 'Beispiel' } });  // je Sprache cs/en/de
}
```

Geschützte Seiten: `{ element: <RequireRole roles={['reviewer']} />, children: [...] }` (nur Navigationshilfe; der Server entscheidet).
Texte nie hart codieren: Schlüssel in allen drei Sprachen, Test auf Schlüssel-Parität.

## 3. Neues Datenmodell (Modell + Migration)

1. Eigene `DeclarativeBase` mit Tabellen in `challenge/backend/models.py`.
2. Migration in `challenge/backend/migrations/` mit `down_revision = "0001"` (Plattform-Revision) bzw. der vorherigen Challenge-Revision.
3. Registrieren: `registry.add_metadata(ChallengeBase.metadata, migrations=HERE / "migrations")`.
4. `python -m app.cli migrate` führt Plattform und Challenge-Migrationen als einen Verlauf aus.
5. Konto → Fachobjekt: `registry.set_subject_resolver(lambda session, user_id: ...)`, damit `Principal.subject_id` gefüllt ist.
6. Seed (nur `DEMO_MODE`, idempotent): `registry.add_seed_step(fn)` und Demo-Konten mit `registry.add_demo_account(DemoAccount(...))`.
   Fachdaten dürfen nur synthetisch sein und sind als `synthetic=true` zu kennzeichnen.

## 4. Neue Regel (deterministische Funktion + Test)

Regeln sind reine Funktionen mit festem, versioniertem Schwellenwert und Test; sie lesen keine Uhr, keinen Zufall und keine LLM-Ausgabe
(`docs/RULES.md` §2). Beispiel (aus dem Test):

```python
def deterministic_rule(value: int, threshold: int) -> str:
    return "above" if value >= threshold else "below"

def test_example_rule_is_deterministic() -> None:
    assert [deterministic_rule(v, 5) for v in (4, 5, 6)] == ["below", "above", "above"]
```

Jede Regel speichert nachvollziehbare Evidenz (Eingaben, Version, Ergebnis); eine Stufe entsteht nie aus einem Modell.
Für Sichtbarkeitsbedingungen in Formularen gibt es die Bedingungs-DSL (`app.core.conditions`, `shared/lib/conditions.ts`).

## Wo liegen Challenge-Tests, und was prüft der Testlauf?

Challenge-Tests liegen **unter `challenge/`, nie unter `tests/`** (`tests/` gehört zur Plattform und zählt zur Zone `platform`):

| Art | Ort | Prüfung in `scripts/test.*` und CI |
|---|---|---|
| Backend | `challenge/backend/test_*.py` (neben dem Plugin) | ruff (check, format), mypy und pytest erfassen `challenge/backend` automatisch, sobald der Ordner existiert |
| Frontend | `challenge/frontend/**/*.test.tsx` | tsc (`platform/frontend/tsconfig.json` schließt `challenge/frontend` ein), eslint (jede Tiefe unter `challenge/frontend/`, über das Wurzel-`tsconfig.json`), vitest (`include`) |

Ein Typ-, Lint- oder Testfehler unter `challenge/` macht den Lauf rot. Geprüft wurde das mit absichtlichen Typfehlern in `challenge/backend/plugin.py` (mypy rot)
und `challenge/frontend/plugin.tsx` (tsc rot); danach wieder grün.

## Erweiterungspunkte im Überblick

| Backend (`Registry`) | Zweck |
|---|---|
| `add_router`, `add_role`, `add_demo_account`, `add_seed_step` | Routen, Rollen, Demo-Konten, Seed |
| `add_meta_extension` | Zusatzfelder in `/meta` (Plattformschlüssel sind geschützt) |
| `add_metadata(metadata, migrations=...)` | Modelle und Migrationsordner |
| `set_subject_resolver` | Konto → Subjekt-ID |

| Frontend (`PluginApi`) | Zweck |
|---|---|
| `registerRoutes`, `registerNav`, `registerRoleHome` | Seiten, Navigation, Rollen-Startseite |
| `registerCatalog(locale, catalog)` | Übersetzungen |

Ports: `app.ports.llm.LlmPort`, `app.ports.notifier.Notifier`; Mocks: `app.adapters.mock_llm.MockLlm`, `memory_notifier.MemoryNotifier`.
Ein neuer Erweiterungspunkt in `platform/` ist eine Entscheidung der Projektleitung und ein `platform-fix:`-Commit.
