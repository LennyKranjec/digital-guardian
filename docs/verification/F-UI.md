# F-UI – Prüfbericht F-01…F-05 + F-INT (A3)

- **Prüfstufe:** VOLL (Darstellung mit echtem Backend, Rollen/Datenzugriff, Endprüfung-Vorstufe)
- **Basis:** `verify/E2E-1` (= `feat/F-INT`), Tests `challenge/e2e/specs/ui-checks.spec.ts`
- **Ergebnis:** **PASS_WITH_RISKS** (Befund S5 siehe E2E-1.md F-01; Kurzfassung/Export NOT RUN)

## Ausgeführte Prüfungen (alle 5 Gesamtläufe grün, 67 passed)

| Prüfung | Umfang | Ergebnis |
|---|---|---|
| Je Seite × 375 px / 1366×768 | Check-in, Arbeitsliste, Cockpit, CTCAE-Aufnahme, Meldungsdetail: genau eine `h1`, kein horizontaler Überstand, Schrift ≥ 16 px, Steuerelemente ≥ 44 px (inkl. `label:has(input)`), keine Rohschlüssel/`undefined` | PASS |
| Patientenseite en/de/cs | `lang`-Attribut, Verbotsliste (COMMON §2), keine Ampel (`[data-traffic-light]` = 0), kein Überstand | PASS |
| Rollen | Patientin auf `/clinic`: keine Zeilen, keine Pseudonyme, 0 Klinik-API-Aufrufe; Ärztin auf `/patient`: kein Formular | PASS |
| Zustände | Serverfehler ⇒ `role=alert` + Wiederholen; leere Liste ⇒ Leerzustand; unbekannte Patientin ⇒ keine Cockpit-Anzeige | PASS |
| Tastatur | Jeder Knopf/Link/Feld von Arbeitsliste und Cockpit per Tab erreichbar, kein Tastaturfang | PASS |
| Verlauf (F-04) | Punkte im DOM = Server (`value != null`), Lücken (`gap-marker`) = Server, jedes Diagramm `role=img` mit `aria-label`, Datenpunkte per Pfeiltaste, fehlende Tage markiert | PASS |
| Kernpfad (E2E-1) | Check-in → Meldung → Arbeitsliste → Cockpit → Quittieren → Aufnahme; Netzfehler, XSS, Konflikt | PASS (siehe E2E-1.md) |

Bildschirmfotos: `docs/verification/screens/` (375 px: Check-in, Aufnahme, Arbeitsliste, Cockpit; 1366×768: Arbeitsliste, Cockpit, Meldungsdetail).

## Mutationsproben
`min-h-11`→`min-h-6` (Ziele), `text-xs` (Schrift), zweite `h1`, Überstand 600 px, Testid `gap-marker` entfernt ⇒ jeweils der zuständige Test rot; danach zurückgesetzt.

## Befunde

| ID | Schwere | Beschreibung | Beleg | Kleinste Korrektur |
|---|---|---|---|---|
| F-01 | Hoch (S5) / min. Medium | Cockpit passt nicht auf 1366×768 (Verlauf bei ≈ 6943 px) | E2E-1.md F-01, Screenshots | Banner einklappen, kompakter Verlauf im ersten Bildschirm |
| F-02 | Low | Headline zeigt Attributschlüssel „(severity)/(presence)“ | Screenshot Meldungsdetail | Attributlabel übersetzen (Backend-Vorlage) |
| F-03 | Low | Doppelte Navigationsziele nach `/clinic` | Cockpit-Kopf | einen Eintrag entfernen |

## Herkunft / Privacy
- Herkunftsprotokoll: `provenance/TABLE.md` erzeugt; 3 Plattform-Commits, alle `platform-fix:` und in `provenance/PROVENANCE.md` begründet; `challenge/` enthielt vor Beginn nur `README.md`.
- Testdaten ausschließlich synthetisch (SYN-0001…0005); Protokolle der Tests enthalten keine Echtdaten.

## NOT RUN
- Sprachumschaltung per UI-Schalter mit Erhalt der Antworten, „Viděno“-Banner nach Reload, Cockpit-Kurzfassung/≤ 2 Klicks bis Beleg über Kurzfassung (T-07 fehlt) – nach Integration 2b.
- FHIR-Export (T-08).
