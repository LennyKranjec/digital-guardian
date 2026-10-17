# M2-Statusbericht – Triage-Kern „SymptomAmpel“ im Digitalen Wächter

Stand: Sa 17.10.2026 ~01:30 · Autor: A0 · Grundlage: Implementierungs-Prompt v2 (§20) und Delta v2.1 (Δ13) des Menschen ·
Umsetzung: Vertrag `challenge/contract/triage.md` (v2.0–v2.8) · Code: `challenge/backend/waechter/triage/` · Prüfung: A3
(`docs/verification/T-14.md`, `T-15.md` auf den verify-Branches).

> Forschungsprototyp, nicht klinisch validiert. Alle klinischen Inhalte (Schwellen, Böden, Kaskaden, Composite-Grading) sind
> `status: placeholder`. Die Verifikation belegt **Umsetzungstreue** (Baum = Regelwerk), **nicht** klinische Richtigkeit.

## 1. Teststatus (Claim-Level `rule_derived` bzw. `synthetic`)

| Prüfung | Ergebnis | Quelle |
|---|---|---|
| Lader, Parser, Vererbung „nur verschärfen“, Monotonie der Lehrerregeln | 167 + 82 Tests grün; 20 Parser-Angriffe und 15 unsichere KB-Änderungen abgewiesen | T-14/T-15, A3 |
| Exaktheit Baum = Lehrer (V1), **ungekürztes** Gitter | FOLFOX 2 048 000, CAPECITABINE 2 048 000, DOCETAXEL 1 492 992, PEMBROLIZUMAB 93 312 Punkte – **0 Unter-, 0 Obertriage** (A2 und unabhängig A3) | T-15 |
| Exaktheit V1, komprimiertes Gitter | 221 184 / 221 184 / 221 184 / 13 824 Punkte – 0/0 | T-15 |
| Monotonie | Blattbox-Paarvergleich 0 Verletzungen; V3 Einzelschritt-Nachbarn auf dem Rohgitter exhaustiv (262 144 / 262 144 / 65 536 / 65 536 Punkte, je mit/ohne Vorbericht) 0 | T-15 |
| Schild (V4) | jeder Punkt im Bodenbereich ≥ min_level, 0 Verletzungen | T-15 |
| Regelkarte | gerenderte Regeln mit dem sicheren Parser (A2) **und** A3s eigenem Parser neu ausgewertet = Baum auf dem ganzen Gitter | T-15 |
| Kontrafaktische | gegen A3-Referenz wahr und minimal (Brute-Force), Schild-Hinweis als `kind: shield` | T-15 |
| Sitzungen (Selection Policy), unabhängige Wahrheit | 12 000 Sitzungen (1 500 je Profil × gekoppelt/unabhängig): **0 Untertriage, 0 Übertriage, 0 verpasstes Rot, 0 Protokollfehler** | A3 T-15 |
| Fragen je Sitzung | Ø ≈ 5–6 statt 14–17 (A3: 6,0/5,9/5,5/5,2; A2: 5,5/5,1/4,9/4,5 – unterschiedliche Wahrheitsmodelle), gesunder Fall 8–9 | T-14/T-15 |
| Determinismus | zweimal Kompilieren ⇒ identischer Hash; Kompilat unabhängig von Simulator (kein Simulator vorhanden) | T-15 |
| Mutationsproben | Kappe zu klein, Baum nicht rein, Böden ignoriert, vorzeitiger Stopp – alle erkannt | T-14/T-15 |

## 2. „demo compile“ – Entsprechung im Produkt

Statt einer CLI `symptomampel demo compile` zeigt der Wächter dieselben Inhalte live: `GET /api/v1/waechter/config/triage`
(Regelkarte je Profil) und **Einstellungen → „Triage-Regelkarte“** (Banner „Umsetzungstreue geprüft (Baum = Regelwerk) –
vollständig, alle N Punkte“, Regeln rot zuerst, Böden mit Schloss, Platzhalter-Liste) sowie die **Befundkarte** je Antwort im
Cockpit (Begründung: Schild zuerst, Pfadbedingungen mit beteiligten Symptomen, Kontrafaktische, Spanne lo–hi, „Gefragt x von y“).

| Profil | Blätter Gelb/Rot (exakt) | Tiefe | Kompilierzeit vorher ⇒ nachher (H3) |
|---|---|---|---|
| FOLFOX | 15 / 7 (vorher 20 / 8) | 11 / 9 | 3,84 s ⇒ 0,41 s |
| CAPECITABINE | 15 / 7 | 11 / 9 | wie FOLFOX |
| DOCETAXEL | 15 / 7 (vorher 20 / 8) | 11 / 9 | 2,85 s ⇒ 0,37 s |
| PEMBROLIZUMAB | 13 / 6 (vorher 16 / 6) | – | 0,15 s ⇒ 0,03 s |

Verifikation je Profil beim ersten Zugriff 2,5–6,5 s (Vorwärmen beim Start). **Beschnittene Variante (§8.3): nicht umgesetzt**
(siehe Abweichungen) – es gibt nur die exakte Variante, daher auch keine Obertriage-Masse.

## 3. Delta v2.1 – Hooks H1–H5

- **H1** `includes: []`, `ResolvedComposition` mit genau einer Komponente: **Regression leer** – Hash und Verhalten aller bestehenden
  Profile unverändert (Golden-Test).
- **H2** Engines halten `components[]`, Level = Maximum, Reason-Codes mit `component_id`.
- **H3** Domänenkompression gemessen (Tabelle oben; Kappen max_grade/max_critical 3, n_ge1/n_ge2 5, n_ge3 2, worsening 1);
  Regelergebnisse vor/nach Kürzung identisch (V1 auf beiden Gittern); Arithmetik über Aggregate ⇒ keine Kürzung (Negativtest).
  **Geänderte Hashes:** Kompilat-Hashes sind neu, weil Kappen Teil des Kopfs sind und die Blattzahl sinkt – Verhalten identisch.
- **H4** Verifikationsbericht mit `components[]` und `verification_scope` (`exhaustive_raw` nur bei Vollprüfung).
- **H5** `wa_triage_decisions` mit `composition_hash`, `composition_status`, `component_ids_json`, `coverage_gap`; Tabelle
  `wa_patient_regimens` angelegt (leer) – T-16.

## 4. Abweichungen vom Prompt (mit Begründung)

1. **Kein scikit-learn, eigener Entropie-Baum** (reines Python): keine neuen Abhängigkeiten im Wettbewerb (Plattformregel);
   Verhalten wie §8.1 (bis zur Reinheit auf dem vollständigen Gitter, deterministische Tie-Breaks), kein `monotonic_cst`.
2. **Kein eigenes Repo-Layout/Streamlit/CLI:** eingebaut in die bestehende Plattform (FastAPI + React) als Plugin; Regelkarte und
   Befundkarte statt CLI-Demo.
3. **V2 nicht als eigene Stufe:** die Rohgitter-Prüfung nutzt eine zweite, unabhängige Aggregat-Implementierung (Abgleich 0
   Abweichungen) plus A3s Referenz; Orbit-Verifikation (V2b) nicht begonnen (laut Delta erst nach Freigabe).
4. **Beschneiden (§8.3) und Diff/Distanz (§8.6) nicht umgesetzt** – nicht im Vertrag, Zeitbudget.
5. **Composite-Grading:** Platzhalter `map = [0,1,2,3,3]` statt Basch-Tabelle (Tabelle nicht bereitgestellt).
6. **Wortlaut:** keine offiziellen PRO-CTCAE-Texte; eigene Formulierung cs/en in PRO-CTCAE-Struktur.
7. **Nicht begonnen** (laut §20 bis zur Freigabe): Simulator/Priore, LLM-Mapper, Editor/Governance/Panel, Lernleiter.
8. **Safety-Ergänzung gegenüber Prompt:** kritische Items sind immer Gate-Fragen (Ladefehler sonst) – A3 fand, dass isoliert
   schweres Erbrechen als reine Eskalationsfrage nie gestellt wurde (3–6 % Untertriage gegen unabhängige Wahrheit); nach der
   Korrektur 0.

## 5. Platzhalter und was ein Kliniker prüfen muss (Anhang A)

Alle Lehrerregeln, Böden (z. B. Fieber ⇒ ROT), Kaskaden, Composite-Grading, Fragenlimit und Rotationspool in
`challenge/content/triage.yaml` (`status: placeholder`, Annahmen A-…); Tipp-Regeln `advice.yaml` (draft); Intervalle
`schedule.yaml` (Demo-Werte). Wissensbasis C61/C64 (`challenge/knowledge/`, 533 AE-Zeilen aus SmPC 4.8, 351 verified) mit
`CLINICAL_TODO.md` (Klassenzuordnung gegen EAU/ESMO, Kombinationsschemata, KI-assistierte Zuordnungen patient_reportable/CTCAE,
Nivolumab-Kombinationstabellen). Offene Punkte 1–10 aus Anhang A des Prompts gelten unverändert.

## 6. Bitte um Freigabe

Nach Freigabe dieses Berichts: Schritte 4–6 der Wissensbasis C61/C64 (Kern ∪ Module je Wirkstoffklasse mit Budgets und linearer
Schranke, Priore nur als Intervalle, Kompilieren V1–V5, Tests C1/C4) bzw. Meilenstein MA des Delta.
