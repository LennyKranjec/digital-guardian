# Umgebung

Gemessen auf dem Entwicklungsrechner am 2026-10-15; andere Rechner können abweichen (nicht geprüft).

## Voraussetzungen

- Python ≥ 3.12 (lokal getestet mit 3.14; CI 3.12), Node ≥ 22 (lokal 24), npm. Kein pnpm, kein Docker nötig.
- Windows (PowerShell 5.1) oder Linux/macOS/Git-Bash. `compose.yml` ist ein optionales, nicht verifiziertes Postgres-Profil.
- Auf **exFAT** (kein Symlink-Support) scheitert `npm ci` an den Workspace-Links: das Repository auf einem NTFS-Laufwerk klonen.

## Ein Befehl

```powershell
powershell -ExecutionPolicy Bypass -File scripts/dev.ps1          # Linux/macOS: bash scripts/dev.sh
```

Der Befehl richtet bei Bedarf ein (venv, `pip install -e platform/backend[dev]`, `npm ci`, Seed) und startet Backend
(`127.0.0.1:8000`) und Frontend (`127.0.0.1:5173`). Ohne Challenge zeigt die UI „Noch keine Challenge-Funktionen geladen“.
Demo-Konten (synthetisch): `admin` und `user`, Passwort `demo-passwort-2026` (nur mit `DEMO_MODE=true`).

## Offline

Einmal mit Netz vorbereiten, danach ohne Netz arbeiten:

1. `scripts/setup.ps1` (bzw. `setup.sh`) legt venv und `node_modules` an; dabei füllt npm seinen lokalen Cache (`~/.npm`).
2. `scripts/wheelhouse.ps1` lädt alle Python-Wheels nach `~/.rakathon/wheelhouse` (**außerhalb des Repos**; anderer Ort: `RK_WHEELHOUSE`),
   einschließlich der gepinnten Build-Abhängigkeit aus `[build-system] requires` (heute `setuptools==82.0.1`; ohne sie scheitert `pip install -e`
   offline). Das Wheelhouse gilt nur für **dieselbe Python-Minor-Version und dasselbe Betriebssystem** (binäre Wheels).
3. Offline: `scripts/setup.ps1 -Offline` (bzw. `OFFLINE=1 bash scripts/setup.sh`) installiert aus Wheelhouse und npm-Cache
   (`npm ci --offline`). Playwright-Chromium (`npx playwright install chromium`) braucht einmalig Netz; mit `-SkipBrowser` entfällt es.
   Ob der npm-Cache für **alle** Pakete reicht, hängt vom Cache-Stand ab: er muss durch einen Online-`npm ci` desselben Lockfiles gefüllt sein.
4. Beim Testen mit gesperrtem Netz über Proxy-Variablen (`HTTP_PROXY`/`HTTPS_PROXY` auf einen toten Port) zusätzlich
   `NO_PROXY=127.0.0.1,localhost` setzen; sonst läuft der Playwright-Health-Check über den toten Proxy und der E2E-Start scheitert (Timeout).

## Server beenden und Betrieb

`scripts/dev.ps1` startet Backend und Frontend in **zwei eigenen PowerShell-Fenstern** (`-NoExit`); es gibt kein Stop-Skript:
beenden durch Schließen der Fenster (oder Strg+C darin). `scripts/dev.sh` läuft im Vordergrund und beendet das Backend beim Verlassen (Strg+C).
Für Betrieb außerhalb der Demo `DEMO_MODE=false` und `APP_ENV=production` setzen: `Settings.demo_mode` ist standardmäßig `true`, und die Demo-Konten
(`/api/v1/demo/accounts`) liefern Benutzername und Passwort ohne Anmeldung. Ein Validator „production ⇒ demo_mode=false“ ist **nicht** eingebaut (nur dokumentiert).

## Qualitätsläufe

`scripts/test.ps1` bzw. `scripts/test.sh` (bricht beim ersten Fehler ab): ruff check/format, mypy, pytest, eslint, prettier,
tsc (Frontend inkl. `challenge/frontend`, Tokens, E2E), vitest (inkl. `challenge/frontend`), Build; mit `-E2e` bzw. `E2E=1` zusätzlich der Playwright-Smoke.

## Ports und Temp-Verzeichnisse

| Zweck | Wert |
|---|---|
| Backend / Frontend (Entwicklung) | `127.0.0.1:8000` / `127.0.0.1:5173` |
| E2E (Standard) | `E2E_BACKEND_PORT=8100`, `E2E_FRONTEND_PORT=5273`; je Agent/Person abweichend setzen, damit nichts kollidiert |
| pytest-Temp | Gemeinsames `%TEMP%\pytest-of-<Benutzer>` kann gesperrt sein (`WinError 5`): `PYTEST_DEBUG_TEMPROOT=<eigener Ordner>` setzen |
| Wegwerf-DB E2E | `platform/backend/data/e2e.db` (wird je Lauf neu angelegt) |

### Ports je Agent (E2E)

| Agent | `E2E_BACKEND_PORT` / `E2E_FRONTEND_PORT` | `PYTEST_DEBUG_TEMPROOT` (Beispiel) |
|---|---|---|
| A0 | `8100` / `5273` (Standard) | `C:\rk\tmp\a0` |
| A2 | `8200` / `5373` | `C:\rk\tmp\a2` |
| A3 | `8300` / `5473` | `C:\rk\tmp\a3` |
| A2b | `8400` / `5573` (Ticketlauf ohne `-E2e`, COMMON §6) | `C:\rk\tmp\a2b` |

Dev-Server nur über die Dev-Commands der Arbeitsumgebung starten, nie als Hintergrundprozess aus der Shell.

## Speicher

Gemessen am 2026-10-15 auf dem Entwicklungsrechner (15,9 GB RAM, davon etwa 3,8 GB frei): der **Gesamtlauf** `scripts/test.ps1 -E2e`
des leeren Templates (Backend, Frontend, Build, E2E-Smoke) dauerte **55 s**. Mit einer wachsenden Challenge steigt das; Richtwerte für den Betrieb:

- Nie zwei Gesamtläufe gleichzeitig; Gesamtläufe nur durch eine Person/einen Agenten zur selben Zeit (der E2E-Lauf startet Backend, Vite und Chromium).
- Bei knappem Speicher in **Abschnitten** laufen lassen: `cd platform/backend && python -m pytest -q <Ordner>` (z. B. `../../tests/backend/unit`,
  `../../tests/backend/integration`, `../../challenge`), `npx vitest run <Pfad>`, `npx playwright test -c tests/e2e/playwright.config.ts --workers=2 <Spec>`.
- Kein einzelner Aufruf länger als etwa 8 Minuten; Läufe darüber in Abschnitte teilen.

## Herkunftsprüfung

Nach dem Tag `pre-rakathon` (Grenze der Zone `platform`; Details in `provenance/PROVENANCE.md`):

```
python scripts/provenance.py --out provenance/TABLE.md
grep -c "^| challenge/.*| challenge | during-event |" provenance/TABLE.md   # Dateien des Wettbewerbsbeitrags (ohne Summenzeile)
git rev-list --count pre-rakathon..HEAD -- challenge                   # Commits in challenge/ seit dem Tag
git log --oneline --grep "^platform-fix:" pre-rakathon..HEAD | wc -l   # gekennzeichnete Plattform-Korrekturen
git log --name-status pre-rakathon..HEAD -- platform tests scripts .github   # jede Änderung an der Plattform seit dem Tag
```

Die Tabelle enthält Summen je Zone und Klasse sowie die Anzahl der Commits nach der Grenze; jede Plattformänderung ohne `platform-fix:`-Präfix ist dort markiert.

## Referenzvalidator (falls die Challenge einen Standard verlangt)

Gilt nur, wenn die Aufgabe ein Austauschformat mit Standardprofil verlangt (z. B. FHIR); sonst nicht nötig. Im **ersten** Exportticket einplanen:

- Java 17 (auf dem Entwicklungsrechner vorhanden; `java -version` prüfen). Den Validator (`validator_cli.jar`) **außerhalb des Repos** ablegen (nicht einchecken, Lizenz/Größe).
- Aufruf: `java -jar <Pfad>/validator_cli.jar <datei.json> -version <Fassung>` (Fassung laut Standard, z. B. `4.0.1`).
- **Standardvalidierung zuerst und getrennt berichten.** Ein zweiter Lauf mit `-extension any` unterdrückt nur Fehler zu unbekannten Erweiterungen und darf
  nie als „valide“ gelten; beide Ergebnisse (Zahl der Fehler je Lauf, Befehl, Version) gehören ins Handoff. Terminologieprüfung ist ein eigener Schritt (`NOT RUN`, wenn nicht ausgeführt).

## Konfiguration (`.env`, siehe `.env.example`)

`APP_ENV`, `DEMO_MODE`, `DATABASE_URL`, `LOG_LEVEL`, `APP_FROZEN_NOW` (nie in `production`), `SESSION_COOKIE_SECURE`,
`SESSION_TTL_HOURS`, `CHALLENGE_DIR`, `APP_NAME`. Keine Secrets in Repo und Logs.
