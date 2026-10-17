# DEMO_RUNBOOK – 5-Minuten-Demo (Standbewertung Sa 14–16 Uhr) · 3-Minuten-Kurzpfad (Finale) · Rückfall 90 s

A4, Tickets P-01 bis P-03 (Stand nach A0-Entscheid Q1–Q4; P-03 17.10. ~10:00: Zusatzbausteine für T-21 bis T-25). **Haupt-Demo = Variante B: synthetische Patientin SYN-0002 (Melanom C43.9, Pembrolizumab, Konto `patient2`,
Ausgang grün → rot) + Ärztin (`doctor`)** – der einzige Pfad, den A3 mit echtem Backend und Browser nachgespielt hat (E2E-1). **SYN-0006 (Prostata C61, Enzalutamid)
ist nur ein kurzer Zusatz „zweites Krankheitsbild“ (Profil/Verlauf zeigen, KEINE Live-Sendung)** und nur, wenn T-20b + Integration 4b + A3 PASS mit Konto `patient6`
vor dem Freeze stehen – sonst ganz streichen. Alle Daten synthetisch. Sätze EN (Pitchsprache) + kurz CS (die App zeigt Tschechisch).

> **STATUS – Entwurf, nicht geprobt.** Klickfolge und Sätze stützen sich auf `origin/main` (UI-Texte `challenge/frontend/waechter/i18n/cs.ts`), `challenge/demo/README.md`,
> A3-Berichte und vorhandene A3-Screenshots. Es gab **keine laufende App und keine Stoppuhr-Probe** (A4-Worktree ohne Abhängigkeiten). Maximalzeiten sind **Planwerte**.
> **⚠** = hängt an Integration 4b (T-16 Sitzungs-API, T-18, F-10F, F-11F, F-13) bzw. an T-16G (A3 HIGH: Cockpit brach nach einer Patientenmeldung wegen `reason_codes`, läuft bei A2).
> **Der Schritt „Patientin meldet ⇒ Cockpit“ wird erst nach Integration 4b geprobt (P-02, nach Signal von A0).** Bis dahin zeigt `/patient` auf `main` das **Vollformular**
> (Rückfall bei fehlender Sitzungs-API); „5–6 statt 14–17 Fragen“ wird dann **nicht live gezeigt**, nur als Aussage über simulierte Sitzungen genannt (CL-06).

## Vorbereitung (vor der Bühne, zählt nicht zur Demozeit)

1. **Reset (1 Befehl, Repo-Wurzel):** `powershell -ExecutionPolicy Bypass -File challenge/demo/reset.ps1` (Git-Bash: `bash challenge/demo/reset.sh`) → muss mit `Demo bereit.` enden (Exit 0). Die Reset-Prüfung zählt **alle Seed-Patientinnen (7)** und ihre Ampeln. Danach Server: `powershell -ExecutionPolicy Bypass -File challenge/demo/start.ps1 -Reset` (Backend `127.0.0.1:8000`, Frontend `127.0.0.1:5173`). Läuft schon ein Server: Reset **vor** dem Start bzw. Server nach dem Reset neu starten.
2. **Ausgangslage nach Reset** (Uhr `2026-10-17T09:00+02:00`): SYN-0001 rot (2 offene Meldungen) · SYN-0002 grün (0) · SYN-0003 gelb (1) · SYN-0004 grau (1) · SYN-0005 rot (1) · SYN-0006 rot (2) · SYN-0007 gelb (2); 3 Sofortbenachrichtigungen (A0 H-2; Ausgabe von `reset.ps1` auf main `fff4db2` geprüft). **Pro Reset nur ein Durchlauf** – A3 H-28: bei eingefrorener Uhr wird eine zweite Sendung/ein Rückfall nicht wie mit echter Uhr behandelt; vor jeder weiteren Vorführung neu zurücksetzen.
3. **Zwei Browserfenster, beide schon angemeldet** (Passwort überall `demo-passwort-2026`): Fenster P (Patientin, schmal 375 px oder echtes Telefon): `patient2` auf `/patient`. Fenster Ä (Ärztin, 1366×768): `doctor` auf `/clinic`. **Die Demo beginnt auf dem Check-in, nicht auf Login, Startseite oder Architektur.**
4. **LLM-Modus (A0 17.10. 04:59):** **Vor** Reset/Start die LLM-Umgebung in dieselbe PowerShell laden: `Get-Content C:\rk\secrets\llm.env | % { $k,$v = $_ -split '=',2; Set-Item env:$k $v }` – **Schlüssel nie anzeigen, nie in Skripte/Commits/Screenshots**; danach `reset.ps1`/`start.ps1 -Reset`. Dann kommt die Kurzfassung vom Modell `gpt-6-1-sol-dz-eu` (Prüfer verwirft unbelegte Sätze; cs kann 4–6 von 6 Sätzen behalten). **Rückfall:** ohne Umgebung oder bei Gateway-Fehler = Textbaustein („Režim: textová šablona bez AI“), die Demo läuft trotzdem. Welcher Modus aktiv ist, steht am Kopf der Kurzfassung – nicht „AI-Zusammenfassung“ sagen, wenn „šablona bez AI“ zu sehen ist. Live-Zahlen = A0-Stichprobe SYN-0001 (A3: Prüfer PASS, Live-Modell nicht von A3 ausgeführt). Der Reset-Standard zeigt SYN-0001 als Textbaustein (12 Sätze, 0 verworfen); mit Modell 4–6 von 6 Sätzen belegt.
5. **Kaltstart Triage (A0-Nachtrag, A3 T-16):** Backend **mindestens 1 min vor der Demo starten** oder einmal `/api/v1/waechter/config/triage` öffnen (Einstellungen → „Triážní karta pravidel“, Triage-Regelkarte). Sonst erscheint die erste Triage-Karte erst ≈ 14 s nach Serverstart. Nach jedem Neustart des Servers (auch nach dem Reset) wiederholen.
6. Statische Screenshots (Abschnitt „Rückfall 90 s“) in einem dritten Fenster/Folienpult. Reset-Befehl in der Zwischenablage.

## 5-Minuten-Klickpfad (Hauptdemo, Variante B) – Maximalzeit je Abschnitt

**Zeit** = Maximalzeit des Abschnitts (kumuliert in Klammern). Bei Überschreitung die „Kürzen wenn“-Liste anwenden. Sätze: EN, dahinter kurz CS. Claim-IDs aus `CLAIMS.md` (nicht mitsprechen).

| # | Zeit | Klick / Handlung | Erwarteter Bildschirm | Satz EN | Satz CS | Claim |
|---|---|---|---|---|---|---|
| A | 0:45 (0:45) | Fenster P: `/patient`, erste Karte sichtbar; nichts klicken, auf die Begründungszeile zeigen | Seite „Zaznamenat příznaky“, Zeile „Otázky odpovídající vaší léčbě: Pembrolizumab“ (A3-Screenshot `375-checkin-oben.png`); auf `main` Vollformular („Zodpovězeno 0 z 14“, erste Karte „Únava“), **⚠ nach 4b** eine Frage je Karte mit „Otázka 1 (nejvýše N)“, „Další“, „Přeskočit“. Kein Prozentbalken, keine Farbe, kein Ampelwort | “The check-in is built from the patient's current therapy. In simulated sessions the adaptive version asks about five or six questions instead of fourteen to seventeen.” | „Dotazník vychází z aktuální léčby. V simulacích se adaptivní verze ptá na asi pět až šest otázek místo čtrnácti až sedmnácti.“ | CL-06, CL-07, CL-11 |
| B | 1:00 (1:45) | Fenster P: Fieber → **ano** (z. B. 38,5 °C), optional Müdigkeit → hoch (**⚠ nur wenn in der Probe unter 1:00 bleibt**), senden („Odeslat“ bzw. „Další“ bis zum Stopp) | Abschluss „Uloženo / Děkujeme. Vaše odpovědi byly uloženy.“. **Oben zuerst** „Důležitý pokyn“: „Při akutních obtížích kontaktujte ambulanci nebo volejte 155.“ (375 px ohne Scrollen sichtbar). Tipps („Praktické rady“) nur für **nicht**-akute Symptome, **keine** Tipps für Fieber. Keine Telefonnummer in eckigen Klammern, kein Level/Ampelwort, keine Beruhigung/Zusage | “Fever, yes. First on the screen: contact the outpatient clinic or call 155 – the clinic's wording, before any tip. No colour, no reassurance, no promise that someone will call.” | „Horečka – ano. Nahoře je nejdřív pokyn: ambulance nebo 155. Žádná barva, žádné uklidňování, žádný slib zpětného volání.“ | CL-10, CL-09, CL-11 |
| C | 0:50 (2:35) | Fenster Ä (`/clinic`): Banner „Nová okamžitá upozornění: N“ → „Zobrazit“ → eine Zeile kurz zeigen; dann Arbeitsliste: SYN-0002 jetzt **rot** und mit der neuen Meldung R-URG-01 oben; SYN-0001/SYN-0005 rot; SYN-0003 gelb („Zkontrolovat“) und SYN-0004 grau („Chybí data (neznámé)“) **ohne** Banner | „Pracovní seznam“, Spalten Semafor/Pacient/Terapie/Hlášení/Poslední zadání/Další termín; Ampel immer Icon **und** Text; nur rote Fälle im Banner (A3 E2E-1 Schritt 2–3: genau 1 neue rote Meldung, `notified`) | “Only red notifies at once. Yellow and grey wait quietly in the list – the clinic asked: not every minor thing.” | „Okamžitě upozorňuje jen červená. Žlutá a šedá čekají v seznamu – klinika chtěla ne každou drobnost.“ | CL-12, CL-02 |
| D | 1:00 (3:35) | „Otevřít kartu pacienta“ (SYN-0002) → Kurzfassung kurz zeigen → bei der Meldung „Proč?“ → ein Beleg-Chip → (**⚠ nur nach 4b + T-16G**) Befundkarte „Triážní nález“ aufklappen („Proč tato úroveň?“, „Co by úroveň změnilo?“, „Položeno: x z y otázek“) | „Karta pacienta“: Ampel, offene Meldungen, „Shrnutí od AI“ mit „Návrh od AI – zkontrolujte doklady“ und **Režim: textová šablona bez AI**; „Proč?“ zeigt Pravidlo, Verze, Parametry, Pozorované hodnoty, Doklady; Beleg-Chip öffnet die Quelle; Befundkarte: Schutzboden („Ochranná hranice“, Schloss) zuerst, dann Pfad, Kontrafaktum, Spanne. Ohne Scrollen sichtbar: Ampel, Meldungen, Kurzfassung, Verlauf (1366×768, S5) | “Every alert explains itself: rule, threshold, values, each with its evidence. Today's summary is a text template – no language model answered. The decision tree equals the rulebook at every grid point: faithful to placeholder rules, not clinically validated.” | „Každé hlášení se vysvětluje: pravidlo, práh, hodnoty a doklady. Dnešní shrnutí je textová šablona – žádný jazykový model neodpověděl. Strom odpovídá pravidlům v každém bodě – věrnost zástupným pravidlům, ne klinická validace.“ | CL-15, CL-21, CL-14 |
| E | 0:40 (4:15) | Zurück zur Meldung → „Potvrdit“ → Entscheidung „Kontaktovat pacienta“ → „Potvrdit“. Dann „Hodnocení CTCAE“ → bei **einem** Begriff den Grad selbst wählen → „Uložit hodnocení“ | Dialog „Potvrdit hlášení“ mit „Rozhodnutí“; danach „Potvrzeno“ mit Zeit und Benutzer; CTCAE-Seite: nur die verfolgten Symptome, **keine** Vorauswahl, Gradtext vor der Wahl, PRO-Werte nur als „jen nápověda“; „Hodnocení CTCAE uloženo.“ | “The physician acknowledges with a recorded decision and chooses the CTCAE grade herself – the system never proposes one.” | „Lékař potvrdí s evidovaným rozhodnutím a stupeň CTCAE zvolí sám – systém ho nikdy nenavrhuje.“ | CL-16, CL-04 |
| F | 0:35 (4:50) | „Zpráva“ → „Balíček FHIR (JSON)“ (**⚠** Admin-Knopf „An FHIR-Server senden“ **nicht** klicken, nur erwähnen) → Nav „Léčiva“ → Suchfeld „Keytruda“ oder ATC „L01FF02“ | „Uloženo jako SYN-0002-bundle.json“ (Dateiname ohne Namen); Druckansicht mit Fußzeile „Syntetická data · podpora rozhodování, nikoli diagnóza“; Léčiva: Treffer mit Kód SÚKL (0209484), ATC, „Nalezeno přes: …“, SPC-Link (neuer Tab) (A3 T-17: Keytruda 0209484 / L01FF02) | “One click: FHIR R4, zero validator errors in the standard run. Drug search by name, SÚKL code or ATC. Push to a live FHIR server: not tested – only against a local test server.” | „Jedním kliknutím FHIR R4, nula chyb validátoru. Hledání léčiv podle názvu, kódu SÚKL nebo ATC. Odeslání na živý FHIR server jsme netestovali – jen na lokálním testovacím.“ | CL-18, CL-20, CL-19 |
| G | 0:10 (5:00) | Folie „vorher / während“ (`TRANSPARENCY.md`) einblenden | Tabelle mit den Zahlen aus den Zählbefehlen | “Before: a neutral platform. During the 24 hours: everything in challenge/ – numbers on the slide.” | „Předtím neutrální platforma; během 24 hodin vše v challenge/ – čísla na slajdu.“ | CL-23 |

**Kürzen wenn zu lang (Reihenfolge):** (1) F: „Léčiva“ weglassen (−20 s) · (2) E: nur „Potvrdit“, CTCAE nur erwähnen (−20 s) · (3) D: Befundkarte weglassen (−25 s) · (4) B: nur Fieber, keine Müdigkeit/Tipps (−20 s; Satz B auf „keine Tipps bei Fieber“ kürzen).
**Rückfall-Schalter:** Dauert ein Ladevorgang > 5 s oder zeigt die App einen Fehler → sofort „Rückfall 90 s“ (kein Debuggen auf der Bühne).

## Optionaler Zusatz „zweites Krankheitsbild C61“ (max. 25 s, **keine Live-Sendung**)

**Nur wenn alle erfüllt sind**, sonst ersatzlos streichen (A0-Entscheid): T-20b (Triage-Profile ENZALUTAMIDE …) und T-20 integriert · Integration 4b auf `main` · A3-Bericht PASS/PASS_WITH_RISKS zu T-20/T-20b · Konto `patient6` vorhanden · einmal von Hand durchgespielt – **vor dem Freeze**.
Zeitpunkt: nach D. Handlung: Fenster Ä → Arbeitsliste → SYN-0006 öffnen (Therapie Enzalutamid, Verlauf: Müdigkeit steigend = gelber Trend, Fieber rot; Orakel in `docs/handoffs/T-20.yaml`) → **nichts senden**.
Satz: “A second disease picture – prostate cancer, synthetic, on enzalutamide – uses the same machinery with its own profile; the rules are placeholders until the clinic reviews them.” (CS: „Druhé onemocnění – syntetický případ karcinomu prostaty – používá stejný mechanismus s vlastním profilem; pravidla jsou zástupná, dokud je klinika nezkontroluje.“) · Claim CL-27 (A, nur nach A3-Bericht). **Nicht sagen:** „5–6 Fragen“ oder „0 Untertriage“ für dieses Profil (nicht gemessen), „klinisch geprüft“.

## Zusatzbausteine „neue Funktionen“ (P-03) – **optional, nicht geprobt, nur nach Integration int/5 + A3-Gesamtlauf**

Gilt auf `main` 7462294 (Tag `freeze-poc`, Integration 5; A3 INT-5 PASS_WITH_RISKS laut A0 10:35). **Keiner dieser Bausteine gehört in die 3-Minuten-Fassung.** Jeder Baustein verändert den Zustand (Bestätigung/Freitext sind endgültig) ⇒ danach **Reset**. Die UI-Texte stammen aus `cs.ts` auf int/5 (1294b1f); **kein Baustein wurde in der laufenden App gesehen** (A4 hatte keine laufende App, Playwright/375 px dieser Bereiche sind bei A3 „NOT RUN“ bzw. im Gesamtlauf offen).
Zusatzbausteine nur an der Standbewertung (5 Min.), und nur, wenn der Hauptpfad A–G in der Probe unter 4:15 bleibt.

| Z | Max. | Klick / Handlung | Erwarteter Bildschirm (cs.ts) | Satz EN | Claim |
|---|---|---|---|---|---|
| Z1 | 0:10 | Im Schritt A (Fenster P) auf die Fußzeile mit dem Prototyp-Hinweis zeigen | NCI-Markenhinweis (englisch) + „Výzkumný prototyp – registrace u NCI zatím nevyřízena …“; Fragetext ist der offizielle PRO-CTCAE-Wortlaut | “The wording is the official PRO-CTCAE – NCI registration is pending, so this stays a research prototype.” | CL-29 |
| Z2 | 1:00 | Fenster Ä: SYN-0001 öffnen → Bereich „Dokumenty“ → „Nahrát dokument“ → `challenge/demo/docs/laborbefund_SYN-0001.csv` → Kandidaten mit Zitat zeigen → **eine** Ressource bestätigen (endgültig!) → „Balíček FHIR (JSON)“ enthält nur diese | Zeile „Extrakce: … (sada pravidel, bez jazykového modelu)“ **oder** „jazykový model, koncept s kontrolou dokladu“ (je nach Modus – nicht „AI“ sagen, wenn „sada pravidel“ steht); „N otevřených · M potvrzených“; erwartet laut `challenge/demo/docs/README.md`: 7 Laborwerte (CSV) bzw. 5 Kandidaten + verworfenes `I10` (Arztbrief) | “A physician uploads a synthetic lab report. The system proposes drafts, each with its quote; I confirm one – and only that one reaches the FHIR export. This is a proof of concept.” | CL-30 |
| Z3 | 1:00 | (A3 T-22 PASS_WITH_RISKS, A0 10:35) Fenster P nach dem Senden: Feld „Další potíže“, **ein** vorbereiteter synthetischer Satz (z. B. „od včerejška mám silný průjem“) → „Odeslat doplnění“ → Folgefrage-Karte beantworten; Fenster Ä: Bereich „Freitexte“ mit Zitat | „Děkujeme. Vaše doplnění bylo uloženo.“; Folgefrage mit Standardantworten; im Cockpit das Zitat; **nur die Antwort wirkt** | “The model only proposes which symptom the text mentions; the patient answers the standard question, and only her answer counts. The physician sees the quote.” | CL-31 |
| Z4 | – | **Nicht live gezeigt:** Module (T-24, Lungenmodul braucht ICD-Änderung ⇒ ≈ 27 s Erstkompilierung), Baseline nach Therapiewechsel (T-25; Seed hat keinen Wechsel), Nachverfolgung (T-26). Nur Q&A 21/22. | – | – | CL-32, CL-33 |

**Rückfall:** Läuft Z2/Z3 nicht (Fehler, > 5 s Ladezeit), Baustein ohne Kommentar überspringen und mit E weitermachen. Bei Z3 ohne LLM-Umgebung entsteht die Zuordnung über die Wortliste (A2: bei Verneinung trotzdem eine Karte möglich) – dann **nicht** vorführen.
Nach Z2/Z3: `reset.ps1` (sonst fehlt SYN-0001/SYN-0002 der Ausgangszustand).

## 3-Minuten-Kurzpfad (Finale; ersetzt die Live-Passage 0:45–1:55 des Pitches, max. 70 s)

Reihenfolge: **B** (Fieber → Akut-Hinweis, 20 s, Müdigkeit weglassen) → **C** (Arbeitsliste/Banner, 15 s) → **D** (Karte → „Proč?“ → Beleg, 25 s) → **F** nur „Balíček FHIR (JSON)“ (10 s). Sätze = Live-Passage in `PITCH_3MIN.md`. Alles andere entfällt; A (Begründungszeile) wird in B mitgesprochen. Der C61-Zusatz entfällt im Finale.

## Rückfall 90 s (statische Screenshots, kein Live-Klick)

**Auslöser:** App startet nicht / Fehler / Netz / Zeit. **Dauer:** 90 s gesprochen ≈ 165 Wörter. Screenshots im Vollbild nacheinander, je ≤ 15 s.
**Soll-Dateien** (werden in **P-02 nach A0-Signal „Integration 4b“** mit der laufenden App aufgenommen; Ablage `challenge/pitch/screens/`): **noch nicht vorhanden**.
Bis dahin **vorläufige echte Screenshots** von A3 (älterer UI-Stand, Patient:innen SYN-0001…0005, ohne Triage-Befundkarte; bei Verwendung **sichtbar als „Stand Fr 16.10., vor Integration 4a“ kennzeichnen**):

| R | Soll (P-02) `screens/…` | Vorläufig vorhanden (A3, `docs/verification/screens/`) | Zeigt | Satz (EN) |
|---|---|---|---|---|
| R1 | `R1-checkin-karte.png` (375 px, Check-in + Begründungszeile) | `375-checkin-oben.png` | „Zaznamenat příznaky“, „Otázky odpovídající vaší léčbě: Pembrolizumab“, erste Karte „Únava“ | “The check-in is built from the patient's therapy.” |
| R2 | `R2-abschluss-akut-155.png` (375 px, Akut-Hinweis oben + Tipps) | – (nicht vorhanden; A3-Specs prüfen den Zustand `escalation-acute`) | Abschluss mit „Důležitý pokyn“ + 155, Tipps darunter | “First on the screen: contact the clinic or call 155 – before any tip. No colour, no promise.” |
| R3 | `R3-arbeitsliste-rot-banner.png` (1366×768) | `1366-arbeitsliste.png`, `1366-cockpit-viewport.png` (Banner SYN-0005/SYN-0001 „Ihned zkontrolovat“) | Sofort-Banner nur für rot, Ampel mit Text | “Only red notifies at once; the rest waits quietly in the list.” |
| R4 | `R4-cockpit-warum-beleg.png` (1366×768, Kurzfassung + „Proč?“ + Beleg) | `1366-cockpit-ganz.png`, `1366-meldungsdetail.png` | Ampel, Meldungen, Kurzfassung, Erklärung (Regel, Schwelle, Belege) | “Every alert explains itself; the summary is a text template, every sentence has evidence.” |
| R5 | `R5-ctcae-oder-regelkarte.png` (CTCAE-Aufnahme **oder** Regelkarte mit Banner „Umsetzungstreue geprüft“) | `375-aufnahme-oben.png` (CTCAE-Aufnahme) | Arzt wählt den Grad, keine Vorauswahl | “The physician chooses the grade. The tree equals the rulebook – faithful to placeholder rules, not clinical validation.” |
| R6 | `R6-transparenz-folie.png` | – (Folie aus `TRANSPARENCY.md`) | vorher/während | “Before: neutral platform. During: everything in challenge/.” |

Zusätzlich vorläufig vorhanden: `docs/verification/evidence/F-06-bericht-druck.pdf` (A4-Bericht mit Fußzeile „Syntetická data · podpora rozhodování, nikoli diagnóza“).
Sprechtext Rückfall = die sechs Sätze, verbunden mit: „This is a recorded state from our independent verification – the live app is not running right now.“ (ehrlich sagen, **dass** es Screenshots sind).
**API-Rückfallpfad** (nur Oberfläche streikt, Server läuft): `challenge/demo/README.md` „API-Rückfallpfad“ – nur zeigen, wenn Zeit bleibt.

## Zurücksetzen nach der Vorführung

`powershell -ExecutionPolicy Bypass -File challenge/demo/reset.ps1` → `Demo bereit.`, Exit 0 (Git-Bash: `bash challenge/demo/reset.sh`). Löscht **ausschließlich** `platform/backend/data/demo.db`; fremde `DATABASE_URL` ⇒ Exit 2, nichts gelöscht. Danach Server ggf. neu starten.

## Probeprotokoll (Messung ausstehend – nicht ausfüllen, bevor tatsächlich gemessen)

| Probe | Datum/Zeit | Variante | Abschnitte A / B / C / D / E / F / G (mm:ss) | Gesamt | Abweichungen / Fehler | durch |
|---|---|---|---|---|---|---|
| 1 | ausstehend (P-02, nach Signal Integration 4b) | B | | | | |

Messung beginnt mit „Karte A sichtbar“ und endet mit „Folie G sichtbar“; Reset/Start zählen nicht. Genau eine Probe pro Reset (eingefrorene Uhr).

## Was in der Demo nicht gezeigt/gesagt wird

Kein Login, kein Setup, keine Architekturfolie als Einstieg · keine zweite Sendung/kein Rückfall-Szenario mit eingefrorener Uhr (H-28) · kein Klick auf „An FHIR-Server senden“ (nur gegen lokalen Testserver getestet; Live-IRIS NOT RUN) ·
keine Behauptung, das Modell bewerte oder entscheide etwas · keine Aussage zu Zeitersparnis/Wirkung · keine Aussage „Prostata/Enzalutamid ist klinisch geprüft“ (Platzhalterregeln, CL-14/CL-27).
