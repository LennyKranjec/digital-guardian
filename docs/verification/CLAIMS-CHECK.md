# Claims-Abgleich (A3 gegen `challenge/pitch/CLAIMS.md`, Stand int/4b f7f68f7)

- Prüfer: A3 · Sa 17.10.2026, ~06:20 · Grundlage: meine Berichte T-07 … INT-4b und die Läufe auf int/4b. Nur Abgleich Aussage ⇔ Messung; keine neuen Aussagen.
- Zusätzlich gemessen für diesen Abgleich (alle auf int/4b): 14 FHIR-Bundles + das Wissens-Bundle mit dem HAPI-Validator 7.0.2 (FHIR 4.0.1), Fragenzahl und Untertriage der vier neuen Profile.

## Neue Messwerte (zum Einsetzen)

| Thema | Messwert |
|---|---|
| FHIR (CL-18/CL-19) | **Alle 7 Patientinnen (SYN-0001…0007): Collection-Bundle und Transaction-Bundle je „Success: 0 errors“** (14 von 14); dazu das Wissens-Bundle (706 Ressourcen: 6 Medication, 350 MedicinalProductUndesirableEffect, 350 Provenance) „0 errors“. Warnungen (≈ 300–490 je Bundle) kommen aus den eigenen, unveröffentlichten Codesystemen `urn:waechter:*`. |
| Push (CL-19) | gegen einen **eigenen lokalen Testserver** von A3 geprüft: nur Administration, Basic-Zugangsdaten nur im Header (nicht in Antwort/Log/Audit), zweiter Push mit identischen Ressourcen-IDs (keine Dubletten), 401/500/ungültige Antwort/nicht erreichbar ⇒ `failed` ohne Stacktrace, nicht synthetisch ⇒ 409. **Live gegen IRIS/echten Server: NOT RUN.** |
| Baum = Regelwerk (CL-14, neue Profile) | ENZALUTAMIDE 93 312, ABIRATERONE 43 904, PAZOPANIB 281 216, NIVOLUMAB 221 184 Punkte des natürlichen Gitters: Baum = unabhängiger Lehrer an **jedem** Punkt; Rohgitter-Vollnachweis PAZOPANIB/NIVOLUMAB 0 Verstöße (im Betrieb nur Stichprobe `sampled_raw`, wird so gemeldet). |
| Fragenzahl neue Profile (CL-06) | Ø Fragen je Sitzung (1 000 simulierte Sitzungen je Profil und Modell, A3-Wahrheitsmodell, Platzhalterregeln): **ENZALUTAMIDE 5,4 / 5,6 von 14 · ABIRATERONE 4,5 / 4,7 von 10 · PAZOPANIB 6,3 / 6,3 von 22 · NIVOLUMAB 5,9 / 6,0 von 20**; 8 000 Sitzungen: 0 Untertriage, 0 Übertriage, 0 Protokollfehler. |
| Reset/Demo (CL-24) | Reset zweimal identisch, **7 Patientinnen**, 3 Sofortbenachrichtigungen, Live-Hauptpfad über `start.ps1 -Reset` bestanden (Fieber ⇒ Akut-Hinweis 155 ⇒ SYN-0002 rot ⇒ Cockpit lädt). |
| Herkunft (CL-23, S7) | int/4b: **412 Commits, 6 berühren `platform`, 0 ohne `platform-fix:`**; main danach 417 Commits, gleiches Ergebnis (A0). |

## Abgleich je Aussage

| ID | Urteil | Hinweis |
|---|---|---|
| CL-01 – CL-05 | unverändert ok | CL-05 weiter ohne A3-Prüfung (Zählung nur durch A0). |
| CL-06 | **ok, erweiterbar** | „5–6 statt 14–17“ gilt für die vier Erstprofile. Für die neuen Profile ist der volle Fragensatz kleiner oder größer (10–22): Wortlaut nur mit Bezug, z. B. „about 5–6 questions per session, instead of 10–22 (depending on therapy)“, immer mit „model: synthetic answers, placeholder rules“. |
| CL-07, CL-08, CL-09, CL-10, CL-11 | ok | Der adaptive Pfad ist jetzt auch gegen das echte Backend geprüft (core-path Test 1, 12 000 + 8 000 Sitzungen). CL-10: Akut-Hinweis zuerst, nach Neuladen/409 erhalten (F-10F, T-16). |
| CL-12, CL-13 | ok | CL-13: seit T-16G gilt auch „eine offene rote Meldung je Ereignis“ bei wiederholter Meldung. |
| CL-14 | **ok mit Pflichtzusatz** | „Umsetzungstreue von Platzhalterregeln, nicht klinische Richtigkeit“ bleibt Pflicht. Jetzt 8 Profile; der Pflichtzusatz gilt für alle. „zero missed red“ nur im Sitzungsmodell. |
| CL-15 | **ok** | Befund- und Regelkarte sind jetzt gegen das echte Backend geprüft (T-16, `triage-real`), Banner „Umsetzungstreue geprüft (Baum = Regelwerk)“ mit Umfang; Hash-Überstand bei 375 px behoben (T-16G). |
| CL-16, CL-17 | ok | S5/375 px nach Integration 4b: Playwright 174/175 grün (der eine Kaltstart-Fehler ist behoben). |
| CL-18 | **ok, Aussage erweiterbar** | „for all synthetic patient bundles“ gilt jetzt belegt für **7 Patientinnen**, Collection und Transaction (14 Bundles). |
| CL-19 | **A3-Bericht liegt jetzt vor** (T-18 in `docs/verification/T-20b.md`) | Wortlaut „tested against a local test server only; live NOT RUN“ bleibt. Nicht: „Push funktioniert“. |
| CL-20 | ok, Katalog jetzt 10 Präparate | Die vier neuen (Xtandi, Zytiga, Votrient, Opdivo) stimmen mit den SÚKL-Open-Data überein; weiter „kein vollständiges SÚKL-Register“. |
| CL-21 | ok | Modell nur Entwurf der Kurzfassung; Textbaustein ist der Standard. Die Pipeline-Prüfung (CL-26) ist davon getrennt. |
| CL-22 | ok | |
| CL-23, S7 | **ok, Zahlen aktualisieren** | INT-4b-Zahlen oben (412/417 Commits, 6, 0). Vor Abgabe nach dem letzten Merge einmal `python scripts/provenance.py` wiederholen (A3 auf Zuruf). |
| CL-24 | **ok** | Reset prüft jetzt 7 Patientinnen; README/Runbook nennen noch 5 Patientinnen und 2 Benachrichtigungen (real 7 und 3) – A4 anpassen. |
| CL-25 | **ok** | Bericht liegt als Datei vor (`docs/verification/T-KB.md`): 533 von 533 Originalbegriffen auf der zitierten Seite, 191 von 191 CTCAE-Terme in der NCI-Liste, **331 von 533** Häufigkeitsklassen gegengelesen; seit T-KB-F01 350 verified, 183 unverified. Wortlaut „Herkunft je Zeile, Zweitlesung (KI-Testagent)“; **keine Aussage zur Vollständigkeit** und nicht „vom Prüfer wörtlich verifiziert“. |
| CL-26 | **jetzt A3-geprüft (PASS_WITH_RISKS)** | 706 Ressourcen (6/350/350), HAPI 0 Fehler (A3 selbst nachgemessen). Der Prüfer weist erfundene Belege, falsche Häufigkeit, Zusatzfelder und Prompt-Injection zurück; **auf den echten SmPC-Tabellen verwirft die verschärfte Prüfung 257 von 351 korrekten Zeilen (nur Listentext prüfbar)** ⇒ nur sagen: „Pipeline-Prüfer belegt Belegstellen in Listentext; die ausgelieferte Matrix beruht auf Zeilenbelegen (A1) und Zweitlesung.“ LLM-Teil weiter „not run“. |
| CL-27 | **freigabefähig** | T-20/T-20b sind A3-geprüft (Bäume exakt, Sitzungen 0/0, Seed SYN-0006/7 = Referenz, Kodierung C61/C64, Präparate gegen SÚKL). Optionaler Zusatz ohne Live-Sendung bleibt zulässig; „5–6 Fragen“ für diese Profile nur mit den Werten oben (Enzalutamid 5,4–5,6 von 14). |
| CL-28 | ok | Zukunftsvision. |
| S1 – S7 | **alle sieben auf int/4b bestätigt** | S1 Kernpfad 14/14 · S2 Orakel (Triage und Regeln) · S3 FHIR 0 Fehler (14 + 1 Bundles) · S4 Kurzfassung ohne unbelegte Sätze (Textbaustein) · S5 Cockpit ohne Scrollen · S6 375 px/Parität/Verbotsliste · S7 Herkunft. |

## Grenzen (nicht sagen)

- „klinisch validiert/geprüft“, „0 Untertriage“ ohne „Umsetzungstreue, Platzhalterregeln“, „der Prüfer verifiziert die ganze Matrix wörtlich“.
- Push gegen einen echten FHIR-Server (nicht getestet), Live-LLM (Gateway 404, nicht gelaufen).
- cs/de-Texte nicht muttersprachlich geprüft; Screenreader nicht gemessen; Kaltstart: erste Triage-Karte und Regelkarte erscheinen nach Serverstart erst nach ≈ 14–45 s (Runbook: ≥ 1 min vorher starten).
