# INT-2 – Integrationsprüfung int/2 cc88a99 (A3)

- **Prüfstufe:** INTEGRATION (Punkte 1 und 10, Herkunft); Tickets sind einzeln geprüft
- **Stand:** `int/2` cc88a99 = main + feat/T-04c + verify/T-04c
- **Ergebnis:** **PASS** (Flake als eigener Befund F-01, Medium/Infrastruktur, siehe unten)

## Ausgeführte Befehle (eigener Lauf, Worktree C:\rk\wt\a3, Ports 8300/5473)
| Befehl | Ergebnis |
|---|---|
| `scripts/test.ps1 -E2e` | Exit 0; ruff/mypy grün; pytest 666 passed, 5 xfailed (387 s, die 5 xfail = dokumentierte Befunde T-04b F-02, T-05 F-01 ×2/F-02/F-04); vitest 108 + 57 passed (29 s); build grün; Playwright 39/39 (16 s) |
| `python scripts/provenance.py --out TABLE.md` | 96 Commits nach der Grenze, 3 berühren `platform`, 0 ohne `platform-fix:` |
| `git log --name-status pre-rakathon..HEAD -- platform tests scripts .github` | nur `cfbc6bb`, `c551804`, `cf766e6`; je `platform-fix:` und in `provenance/PROVENANCE.md` begründet |
| `git ls-tree pre-rakathon -- challenge` | nur `challenge/README.md` |
| Wurzeldateien | keine Änderung außerhalb der erlaubten Zonen |

Der Lauf von A0 (Exit 1 nur in vitest) ließ sich nicht wiederholen: bei mir bestanden alle 108 vitest-Tests im ersten Versuch.

## Befund F-01 (Medium, Infrastruktur): design-system-Flake bleibt unter Last
- **Anforderung:** Handoff nur mit vollständigem Testlauf (CLAUDE.md); Lauf darf nicht zufällig rot werden.
- **Beobachtet (A0, Log C:\rk\tmp\a0\int2.log):** `design-system.test.tsx` rot nach 13 s, Seite zeigt „Wird geladen“; der 10-s-Timeout aus `c551804` reichte nicht, während pytest 412 s lang Last erzeugte. Bei mir kein Fehlschlag (kein paralleler Last-Agent).
- **Ursache (Vermutung, nicht belegt):** `findBy*` wartet auf Daten des gemockten `fetch`; ein überlasteter Worker braucht für Rendern/Hydration > 10 s.
- **Kleinste Korrektur (platform-fix:, A0-Entscheidung):** Timeout dieser beiden `findBy*` auf 30 s und `testTimeout` für diese Datei auf 45 s (`it(…, { timeout: 45_000 })`); alternativ in `test.ps1` vitest nach dem pytest-Schritt nur einmal wiederholen (`--retry 1`), das wäre aber eine Maskierung. Keine Prüfung entfernen. Eintrag in `provenance/PROVENANCE.md`.
