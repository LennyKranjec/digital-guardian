# Demo – Digitaler Wächter für Nebenwirkungen

Ein Befehl setzt die Demo auf den **immer gleichen Ausgangszustand** zurück; ein zweiter startet sie. Alle Daten sind
synthetisch. Die Anwendung stellt keine Diagnose und trifft keine Therapieentscheidung: Ampel und Stufen kommen aus der
versionierten Regelkonfiguration, die KI-Kurzfassung ist ein belegter Entwurf.

## Zurücksetzen (1 Befehl)

| System | Befehl (im Repo-Wurzelordner) |
| --- | --- |
| Windows | `powershell -ExecutionPolicy Bypass -File challenge/demo/reset.ps1` |
| Linux/macOS/Git-Bash | `bash challenge/demo/reset.sh` |

Was passiert:

1. Gelöscht wird **ausschließlich** `platform/backend/data/demo.db` (samt `-wal`/`-shm`/`-journal`). Jede andere
   `DATABASE_URL` (andere Datei, anderer Ordner, Postgres, `:memory:`) wird abgelehnt, Exitcode 2, nichts gelöscht.
2. Gesetzt werden (nur für diesen Prozess): `DATABASE_URL=sqlite:///data/demo.db`,
   `APP_FROZEN_NOW=2026-10-17T09:00:00+02:00` (Ankerzeit des Szenarios), `DEMO_MODE=true`, `APP_ENV=development`,
   `WAECHTER_LLM=template` (überschreibbar: `template` | `cached` | `openai`).
3. Migration und Seed laufen mit derselben Engine wie die Anwendung (Konten, Patientinnen, Antworten, Meldungen).
4. Eine Prüfung per Testclient (kein Server nötig) bestätigt: alle Patientinnen des Szenarios (derzeit 7), die Demo-Konten, Ampeln wie im Szenario erwartet,
   SYN-0001 hat eine Kurzfassung. Ausgabe endet mit `Demo bereit.`

Exitcode: `0` bereit · `1` Prüfung fehlgeschlagen · `2` Reset abgelehnt oder Voraussetzung fehlt (`.venv` fehlt: zuerst
`scripts/setup.ps1`/`setup.sh`).

Erwarteter Ausgangszustand (Uhr = 17.10.2026 09:00 Europe/Prague):

| Pseudonym | Ampel | offene Meldungen |
| --- | --- | --- |
| SYN-0001 | rot | 2 |
| SYN-0002 | grün | 0 |
| SYN-0003 | gelb | 1 |
| SYN-0004 | grau | 1 |
| SYN-0005 | rot | 1 |
| SYN-0006 | rot | 2 |
| SYN-0007 | gelb | 2 |

Dazu 3 Sofortbenachrichtigungen (Ausgabe von `reset.ps1` auf `main` fff4db2 geprüft, 17.10.2026). Die Kurzfassung von SYN-0001 kommt im Standard aus dem Textbaustein
(`Modus fallback`; 12 Sätze, 0 verworfen). Mit `WAECHTER_LLM=openai` wird zuerst das Gateway versucht; antwortet es nicht
(zuletzt HTTP 404, Modellname unbekannt), greift automatisch der Textbaustein – die Demo bleibt lauffähig.

## Starten

| System | Befehl |
| --- | --- |
| Windows | `powershell -ExecutionPolicy Bypass -File challenge/demo/start.ps1 -Reset` |
| Linux/macOS/Git-Bash | `bash challenge/demo/start.sh --reset` |

`start` setzt dieselben Umgebungsvariablen wie der Reset, setzt auf Wunsch (`-Reset`/`--reset`) zuerst zurück und ruft
dann `scripts/dev.ps1`/`dev.sh` (Backend `http://127.0.0.1:8000`, Frontend `http://127.0.0.1:5173`). Eigene Ports:
`-BackendPort`, `-FrontendPort` (nur PowerShell).

Wer bereits einen Server laufen hat: Reset **vor** dem Start ausführen oder den Server nach dem Reset neu starten, sonst
hält er die alte Datei geöffnet.

## Konten (Passwort überall `demo-passwort-2026`)

| Konto | Rolle | Sicht |
| --- | --- | --- |
| `patient` | Patientin SYN-0001 | Fragebogen, eigener Verlauf |
| `patient2` | Patientin SYN-0002 (grün) | Fragebogen, eigener Verlauf |
| `patient6` | Patient SYN-0006 (Prostata, Enzalutamid) | Fragebogen, eigener Verlauf |
| `doctor` | Ärztin/Arzt | Arbeitsliste, Cockpit, Quittierung, Aufnahme, Bericht, Konfiguration |
| `admin` | Administration | wie `doctor`, zusätzlich Plattform-Verwaltung |

Eine Patientin sieht nie fremde Daten (fremdes Objekt: 404), falsche Rolle: 403 – serverseitig erzwungen.

## 5-Minuten-Klickpfad

Oberflächen-Routen laut Vertrag §7: `/patient`, `/clinic`, `/clinic/patients/:id`, `/clinic/patients/:id/assess`,
`/clinic/patients/:id/report`, `/clinic/alerts/:id`, `/clinic/settings`.

1. **Reset** ausführen, **Start** ausführen, `http://127.0.0.1:5173` öffnen. (0:30)
2. Als `patient2` anmelden → `/patient`: Tagesfragebogen, **Fieber** angeben (z. B. 38,5 °C) und senden. Die Antwort wird
   zuerst gespeichert; die Auswertung folgt getrennt (bei Störung bleibt die Antwort erhalten). (1:30)
3. Abmelden, als `doctor` anmelden → `/clinic`: SYN-0002 ist jetzt **rot**, neue Meldung oben in der Arbeitsliste;
   zusätzlich zeigt die Übersicht SYN-0001, SYN-0005 und SYN-0006 rot. (2:30)
4. Patientin öffnen → **Cockpit**: Verlauf, Ampel, Kurzfassung. Jeder Satz der Kurzfassung trägt **Belege** (Quellfelder
   mit Zeitpunkt); anklicken zeigt den Ursprung. (3:30)
5. Meldung öffnen → **quittieren** und die Entscheidung erfassen (Vertrag: `acknowledgeAlert`, nur aus Status offen). Die
   Meldung wandert aus „offen“ nach „quittiert“. (4:00)
6. **Aufnahme** (`/assess`): CTCAE-Grad durch die Ärztin/den Arzt festhalten – der Grad wird nie vorgeschlagen oder
   automatisch gesetzt. (4:30)
7. **Bericht** (`/report`): druckbare Zusammenfassung, Export als FHIR-R4-Bundle (`GET /api/v1/waechter/patients/{id}/fhir`).
   (5:00)

Danach wieder `reset` – der Zustand ist wieder identisch.

## API-Rückfallpfad (ohne Oberfläche)

Jede schreibende Anfrage braucht den Header `X-Requested-With: fetch`; die Sitzung läuft über Cookie.

```powershell
$h = @{ 'X-Requested-With' = 'fetch' }
$null = Invoke-RestMethod http://127.0.0.1:8000/api/v1/auth/login -Method Post -Headers $h `
  -ContentType 'application/json' -SessionVariable s `
  -Body '{"username":"doctor","password":"demo-passwort-2026"}'
Invoke-RestMethod http://127.0.0.1:8000/api/v1/waechter/patients -WebSession $s -Headers $h
```

```bash
curl -s -c jar -H 'X-Requested-With: fetch' -H 'Content-Type: application/json' \
  -d '{"username":"doctor","password":"demo-passwort-2026"}' http://127.0.0.1:8000/api/v1/auth/login
curl -s -b jar -H 'X-Requested-With: fetch' http://127.0.0.1:8000/api/v1/waechter/patients
```

Die vollständige Schnittstelle steht in `challenge/contract/openapi.yaml`.

## Ehrlicher Stand

- **Geprüft** (automatisiert): Reset-Kern gegen Temp-DB (`challenge/backend/test_demo.py`, inkl. echtem Szenario), die
  drei Skripte auf Windows (PowerShell, Git-Bash), die erwarteten Ampeln und die Kurzfassung im Textbaustein-Modus.
- **Nicht geprüft** von A2: Start der Server über `start.ps1`/`start.sh`, der oben beschriebene Klick-Pfad im Browser
  (die Oberfläche stammt von A2b) und das Verhalten mit erreichbarem LLM-Gateway. Der Klick-Pfad folgt dem Vertrag und
  ist vor der Vorführung einmal von Hand durchzuspielen.
- Die FHIR-Ausgabe besteht den HAPI-Validator ohne Fehler; die Warnungen betreffen eigene Codesysteme (`urn:waechter:*`).
- Nur synthetische Daten; die Demo ersetzt keine klinische Beurteilung.
