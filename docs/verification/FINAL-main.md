# Abschluss-KURZ-Prüfung main bddfbf3 (nach freeze-poc 7462294) – Sa 17.10.2026 ~10:50

- Prüfer: A3 · Stufe KURZ (Herkunft, Änderungsumfang, Demo-Reset) · Ergebnis: **PASS**

| Prüfung | Ergebnis |
|---|---|
| `git log freeze-poc..main`: 8 Commits | Dateien: `challenge/pitch/{CLAIMS,DEMO_RUNBOOK,PITCH_3MIN,QA,TRANSPARENCY}.md`, `challenge/demo/AGENT_SETUP_PROMPT.md` (neu), `docs/handoffs/P-03.yaml` (neu) – **nur Doku/Pitch, kein Code, keine Tests, keine Plattform** |
| `AGENT_SETUP_PROMPT.md` | enthält keine Schlüssel/Geheimnisse (nur Verweis auf `llm.env` außerhalb des Repos, Demo-Passwort `demo-passwort-2026` ist öffentlich dokumentiert) |
| `python scripts/provenance.py` auf bddfbf3 | **526 Commits nach der Grenze, 6 berühren `platform`, 0 ohne `platform-fix:`**; challenge: 443 during-event + 1 pre-event (README); platform 156 pre-event; Dateien gesamt 754 |
| `git log --name-status pre-rakathon..HEAD -- platform tests scripts .github` | unverändert 6 × `platform-fix:` + der int/3-Merge (07acf36); in `scripts/` und `.github/` keine Änderung; `challenge/` zum Stichtag nur `README.md` ⇒ **kein Herkunftsverstoß** |
| Demo-Reset einmal | Exit 0, „Demo bereit.“: 7 Patientinnen, Ampeln SYN-0001 rot · 0002 grün · 0003 gelb · 0004 grau · 0005 rot · 0006 rot · 0007 gelb, 3 Sofortbenachrichtigungen, 8 Profile, Kurzfassung 12 Sätze/0 verworfen |

## Zählungen für A4 (518 vs 519, 442 vs 443)
- Die in `provenance/TABLE.md` eingecheckte Tabelle gehört zu **freeze-poc 7462294**: 518 Commits, 442 challenge-Dateien (during-event), 752 Dateien.
- Auf dem **finalen main bddfbf3** liefert dasselbe Skript: **526 Commits, 443 challenge-Dateien, 754 Dateien** (+8 Pitch-/Doku-Commits, +`AGENT_SETUP_PROMPT.md`, +`P-03.yaml`). Jeder weitere Commit erhöht die Commitzahl (auch ein Commit der Tabelle selbst). Im Pitch also entweder „Stand freeze-poc: 518 Commits, 6 platform-fix, 0 Verstöße“ oder die Tabelle nach dem letzten Commit neu erzeugen. „519“ stammt aus keinem Lauf von mir.
- Für die Aussage „0 Verstöße“ ist die Zahl der Commits unerheblich: berührt platform = 6 (alle `platform-fix:`).

## Hinweise zu CLAIMS.md (Wortlaut, kein Blocker)
- CL-29, Spalte Grenzen: „Rückblick-Rücksetzung bei jedem neuen Therapieeintrag (A3 H-1) bei A0 offen“ und „T-23 … PWR, 1 Low F-01“ sind **überholt**: T-23G ist umgesetzt (7 Tage nur bei Therapiebeginn/Regimewechsel, Zukunft ignoriert, recall wird mitgesendet), T-23 ist PASS (A3 `T-23.md`, 25 Tests, HAPI 0 Fehler).
- CL-32/33 stimmen mit meinen Berichten überein (T-24 F-01/F-02 behoben und im Gesamtlauf int/5 grün; T-25 „berücksichtigt den Therapiewechsel“).
- Alle Pitch-Sätze CL-29 bis CL-33 sind durch meine Berichte gedeckt; Live-Zahlen (CL-30/31) sind Stichproben von A2/A2b, nicht von A3.
