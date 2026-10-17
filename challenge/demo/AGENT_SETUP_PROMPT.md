# Prompt: Demo-Rechner einrichten und Demo starten (für einen KI-Agenten auf einer frischen Maschine)

Diesen Text einem Coding-Agenten (z. B. Claude Code) auf dem Demo-Laptop als Auftrag geben. Er richtet das Repo ein,
startet die Demo und meldet, was im Browser zu tun ist.

---

Du richtest auf DIESER Maschine die Demo „Digitaler Wächter für Nebenwirkungen“ (Rakathon 2026) ein und startest sie.
Antworte auf Deutsch. Arbeite selbstständig, aber halte dich strikt an diese Regeln:

**Regeln**

1. Du änderst KEINEN Code und KEINE Datei im Repo und committest/pushst nichts. Du richtest nur ein und startest.
2. Die Datei mit dem API-Schlüssel (`llm.env`) liest du nie in die Ausgabe, zeigst ihren Inhalt nie an, kopierst ihn nie in Befehle,
   Logs oder Dateien. Du lädst sie nur mit dem unten angegebenen Befehl in die Umgebung der PowerShell.
3. Nur synthetische Daten; lade keine fremden Dateien hoch.
4. Wenn ein Schritt scheitert: Fehlermeldung wörtlich melden, die naheliegende Ursache prüfen (Version, fehlendes Programm, Port belegt),
   höchstens zwei Lösungsversuche, dann stoppen und berichten. Nichts „reparieren“, indem du Code änderst.
5. Starte keine Testsuite (`scripts/test.ps1`, pytest, Playwright) – sie braucht viel Speicher und ist für die Demo nicht nötig.

**Schritt 1 – Voraussetzungen prüfen und melden**

- `git --version`, `py --version` bzw. `python --version` (nötig: Python ≥ 3.12), `node --version` (nötig: ≥ 22), `npm --version`.
- Fehlt etwas: melden, welche Version installiert werden muss (Python von python.org, Node LTS von nodejs.org), und warten.
- Prüfen, ob die Ports 8000 und 5173 frei sind (`Get-NetTCPConnection -LocalPort 8000,5173 -ErrorAction SilentlyContinue`).
  Belegt ⇒ melden, welcher Prozess sie nutzt; nichts beenden, ohne zu fragen.

**Schritt 2 – Repo klonen (Branch main)**

```powershell
cd $HOME
git clone https://github.com/LennyKranjec/rakathon-waechter.git
cd rakathon-waechter
git log --oneline -1
```

Das Repo ist privat: fragt Git nach Anmeldung, den Menschen bitten, sich bei GitHub anzumelden (`gh auth login` oder Browser).
Melde den Commit-Hash von `main`.

**Schritt 3 – Einrichten**

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup.ps1 -SkipBrowser
```

Erwartet: venv in `platform/backend/.venv`, `node_modules` angelegt, Ende ohne Fehler. Dauer einige Minuten.

**Schritt 4 – LLM-Zugang (optional)**

Frage den Menschen, ob und wo die Datei `llm.env` liegt (sie ist bewusst NICHT im Repo; er bringt sie per USB-Stick oder
Passwortmanager mit, z. B. nach `C:\rk\secrets\llm.env`). Wenn ja, in DERSELBEN PowerShell, in der du gleich startest:

```powershell
Get-Content C:\rk\secrets\llm.env | % { $k,$v = $_ -split '=',2; Set-Item env:$k $v }
```

Prüfe nur, DASS die Variable gesetzt ist (`[bool]$env:WAECHTER_LLM_API_KEY` ⇒ True), nie ihren Wert.
Ohne Datei: weiter ohne LLM – die Kurzfassung kommt dann aus dem Textbaustein, alles andere funktioniert.

**Schritt 5 – Demo zurücksetzen und starten**

```powershell
powershell -ExecutionPolicy Bypass -File challenge/demo/start.ps1 -Reset
```

- Die Ausgabe muss mit `Demo bereit.` enden (7 Patientinnen, Ampeln SYN-0001 rot, SYN-0002 grün, SYN-0003 gelb, SYN-0004 grau,
  SYN-0005 rot, SYN-0006 rot, SYN-0007 gelb). Abweichung ⇒ melden.
- Danach laufen Backend `http://127.0.0.1:8000` und Frontend `http://127.0.0.1:5173` in diesem Fenster weiter (nicht schließen).
  Falls dein Werkzeug Befehle nur kurz laufen lässt: den Start als Hintergrundprozess ausführen und nur den Ausgabe-Log beobachten.

**Schritt 6 – Vorwärmen und prüfen (mindestens 1 Minute nach dem Start)**

```powershell
Invoke-WebRequest http://127.0.0.1:8000/api/v1/health -UseBasicParsing | Select-Object StatusCode
```

Erwartet 200. Dann den Menschen bitten, im Browser `http://127.0.0.1:5173` zu öffnen, sich als `doctor` anzumelden
(Passwort `demo-passwort-2026`) und **Einstellungen → Triážní karta pravidel** einmal zu öffnen (kompiliert die Triage-Bäume;
die erste Karte kann sonst bis zu 18 s dauern).

**Schritt 7 – Übergabe an den Menschen**

Melde kurz: main-Commit, Python/Node-Version, ob das LLM geladen ist (ja/nein, ohne Wert), `Demo bereit.` ja/nein, URL.
Gib ihm dann diese Kurzanleitung:

- Zwei Browserfenster, Passwort überall `demo-passwort-2026`:
  Patientin `patient2` auf `/patient` (schmal/Handy), Ärztin `doctor` auf `/clinic` (1366×768).
- Klickpfad: Patientin beantwortet den Check-in, **Fieber = ja** ⇒ Hinweis „ambulance / 155“ ⇒ optional Freitext
  („od včera mám průjem“) ⇒ Folgefragen beantworten ⇒ Ärztin: SYN-0002 rot oben ⇒ Cockpit (Proč?, Sledované příznaky,
  Kurzfassung mit Belegen, Freitexte) ⇒ Meldung quittieren ⇒ CTCAE-Aufnahme ⇒ Bericht / FHIR-Export.
  Optional bei SYN-0001: Dokument hochladen aus `challenge/demo/docs/` (Arztbrief .md oder Laborbefund .csv), Vorschläge bestätigen.
- Ausführlich: `challenge/pitch/DEMO_RUNBOOK.md`.
- Vor jedem weiteren Durchlauf: Server mit Strg+C beenden und Schritt 5 wiederholen (eingefrorene Demo-Uhr ⇒ pro Reset ein Durchlauf).

**Fehlerbilder**

- `.venv fehlt` / `node_modules` fehlen ⇒ Schritt 3 erneut.
- Port belegt ⇒ melden; eigene Ports: `start.ps1 -Reset -BackendPort 8010 -FrontendPort 5180`.
- Kurzfassung zeigt „šablona bez AI“ ⇒ LLM nicht geladen oder Gateway nicht erreichbar; Demo läuft trotzdem.
- `Demo bereit.` fehlt ⇒ letzte 30 Zeilen der Ausgabe wörtlich melden und stoppen.
