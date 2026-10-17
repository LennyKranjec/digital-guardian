# SOURCES – Quellen, Annahmen, Orakel (T-01, T-12, Owner A1)

Stand: Fr 16.10.2026 (T-12 ergänzt am selben Tag). Zugriffsdatum aller Web-Quellen: **2026-10-16**. Claim-Stufen: A reproduzierbarer Test · B zitierte externe
Evidenz, im Prototyp ungetestet · C plausible Hypothese · D Zukunftsvision (agents/COMMON.md §7).
Vollständig gelesen = der genannte Abschnitt wurde im Volltext geöffnet; nichts davon ist nur als Abstract gelesen.

## 1. Quellenregister

| SRC-ID | Quelle (Titel, Organisation, Jahr) | URL / Fundort | Locator | Stufe | Stützt | Einschränkung |
|---|---|---|---|---|---|---|
| SRC-CTCAE-V6 | Common Terminology Criteria for Adverse Events (CTCAE) v6.0 (MedDRA 28.0), NCI/NIH/DHHS, veröffentlicht 2025-07-22 (PDF-Stand Jan 2026, 312 S.) | https://dctd.cancer.gov/research/ctep-trials/for-sites/adverse-events/ctcae-v6.pdf (Datei vom Menschen: `CTCAEv6_Jan2026.pdf`, **nicht** im Repo) | `ctcae.yaml`, Feld `locator` je Begriff (Seite 6, 51, 69, 82, 84, 85, 89, 175, 223, 272, 297, 299) | B | Begriffe, Definitionen, Gradtexte 1–5 wörtlich; Fieber ab 38,0 °C = Grad 1 (S. 85) | Gradtexte beschreiben ärztliche Bewertung, nicht PRO-Werte; PDF enthält keine MedDRA-Codes |
| SRC-CTCAE-V6-XLSX | CTCAE v6.0 (2025, MedDRA 28.0), Excel mit „Clean Copy“, Tracked Changes, Mapping v5→v6, Errata; NCI/DCTD | https://dctd.cancer.gov/research/ctep-trials/trial-development/ctcae-v6.0.xlsx | Blatt „CTCAE v6.0 Clean Copy“ (850 Zeilen), Spalten A–C | B | MedDRA-**LLT-Code** und SOC je Begriff | MedDRA ist Eigentum der MSSO/ICH-Lizenzgeber (siehe §3) |
| SRC-CTCAE-V6-FAQ | CTCAE v6.0 Implementation FAQs, NCI/NIH, 2025-09-09 | https://dctd.cancer.gov/research/ctep-trials/for-sites/adverse-events/ctcae-v6-faq.pdf | S. 1 | B | v6.0 „ready for immediate use for any study except NCI CTEP or DCP NCORP studies“; „release version is the final version“ | betrifft Studien, nicht Software-Demos |
| SRC-FDA-OXALIPLATIN | Oxaliplatin injection (Hospira), US prescribing information, rev. 9/2024, DailyMed setid e51a62ba-d163-4c57-835c-8c86cf097e40 | https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=e51a62ba-d163-4c57-835c-8c86cf097e40 | Highlights; §5.2; §6 | B | alle 2 Wochen mit Fluorouracil/Leucovorin; häufigste NW (≥ 40 %): periphere sensorische Neuropathie, Übelkeit, Diarrhö, Erbrechen, Fatigue, Stomatitis; akute und verzögerte Neuropathie | US-Label (kein EU-SmPC); ein Generikahersteller |
| SRC-SUKL-OXALIPLATIN | Oxaliplatin Accord 5 mg/ml, SPC aus der Databáze léků SÚKL (kodSUKL 0239968, SÚKL-Dokument 81375, 22 S.; T-12) | https://prehledy.sukl.cz/prehledy/v1/dokumenty/81375 | §4.8 (PDF S. 7), Neurotoxicita (PDF S. 13), §4.2 Zyklus alle 2 Wochen (PDF S. 2) | B | Průjem, nauzea, zvracení, mukozitida, akutní periferní senzorická neuropatie am häufigsten; akutní neurosenzorické projevy oft bei Kälte | nationale SPC eines Herstellers (Accord); Neuropathie-Verlauf „> 14 Tage“ steht dort nicht so, bleibt beim US-Label |
| SRC-SUKL-FLUOROURACIL | Fluorouracil Accord 50 mg/ml, SPC aus der Databáze léků SÚKL (kodSUKL 0242250, SÚKL-Dokument 94827; ersetzt SRC-FDA-FLUOROURACIL, T-12) | https://prehledy.sukl.cz/prehledy/v1/dokumenty/94827 | §4.4 (PDF S. 4-5), §4.8 Tabelle (PDF S. 10) | B | Stomatitida, průjem, zánět sliznice, nauzea, zvracení, syndrom ruka-noha: „velmi časté“ (Tabelle); GI-Effekte und HFS in den Warnhinweisen | nationale SPC eines Herstellers (Accord); andere Hersteller können abweichen |
| SRC-SUKL-XELODA | Xeloda (kapecitabin), SPC laut Databáze léků SÚKL (kodSUKL 0027023); SÚKL verlinkt die EU-SPC der EMA, **tschechische Fassung** (52 S.; ersetzt SRC-EMA-CAPECITABINE) | https://www.ema.europa.eu/cs/documents/product-information/xeloda-epar-product-information_cs.pdf | §4.4 (PDF S. 7), §4.8 (PDF S. 14, Tabelle S. 16) | B | Toxicita limitující dávku: průjem, nauzea, stomatitida, syndrom ruka-noha; Definition HFS Stufe 1/2; Gastrointestinal, HFS, únava, astenie häufig/relevant | Fassung vom Abrufdatum |
| SRC-SUKL-KEYTRUDA | Keytruda (pembrolizumab), SPC laut Databáze léků SÚKL (kodSUKL 0209484); SÚKL verlinkt die EU-SPC der EMA, **tschechische Fassung** (412 S.; ersetzt SRC-EMA-PEMBROLIZUMAB) | https://www.ema.europa.eu/cs/documents/product-information/keytruda-epar-product-information_cs.pdf | §4.4 (PDF S. 14), §4.8 (PDF S. 21-22, Tabelle S. 26, Pneumonitida S. 29) | B | Únava 31 %, průjem 22 %, nauzea 20 % (Monotherapie); vyrážka „velmi časté“; imunitně zprostředkovaná pneumonitida 4,2 % | Zuordnung Dyspnoe↔Pneumonitida ist Annahme (ANN-A1-02) |
| SRC-SUKL-TAXOTERE | Taxotere (docetaxel), SPC laut Databáze léků SÚKL (kodSUKL 0167638); SÚKL verlinkt die EU-SPC der EMA, **tschechische Fassung** (314 S.; ersetzt SRC-EMA-DOCETAXEL) | https://www.ema.europa.eu/cs/documents/product-information/taxotere-epar-product-information_cs.pdf | §4.4 (PDF S. 7-8), §4.8 (PDF S. 12, Tabelle S. 14) | B | Nauzea, zvracení, stomatitis, průjem, astenie am häufigsten (Monotherapie); febrilní neutropenie; periferní senzorická neuropatie | Dosierungszyklus nicht im Detail gelesen (ANN-A1-03) |
| SRC-SUKL-XTANDI | Xtandi (enzalutamid), SPC laut Databáze léků SÚKL (kodSUKL 0194246); SÚKL verlinkt die EU-SPC der EMA, **tschechische Fassung** (97 S.; T-20, abgerufen 2026-10-17; SHA-256 und Volltext-Extraktion siehe `challenge/knowledge/SOURCES.md` SRC-KB-XTANDI) | https://www.ema.europa.eu/cs/documents/product-information/xtandi-epar-product-information_cs.pdf | §4.8 (PDF S. 8), Tabulka 1 (PDF S. 9) | B | astenie/únava „velmi časté“; snížená chuť k jídlu, nauzea, zvracení, průjem, vyrážka, myalgie, bolest zad „není známo“ (spontánní hlášení) | Fassung vom Abrufdatum; nur §4.8 gelesen |
| SRC-SUKL-ZYTIGA | Zytiga (abirateron), SPC laut Databáze léků SÚKL (kodSUKL 0168443); SÚKL verlinkt die EU-SPC der EMA, **tschechische Fassung** (78 S.; T-20) | https://www.ema.europa.eu/cs/documents/product-information/zytiga-epar-product-information_cs.pdf | §4.8 (PDF S. 7), Tabulka 1 (PDF S. 8) | B | průjem „velmi časté“, vyrážka „časté“ | nur §4.8 gelesen; Kombination mit Prednison/Prednisolon laut SPC nicht abgebildet |
| SRC-SUKL-VOTRIENT | Votrient (pazopanib), SPC laut Databáze léků SÚKL (kodSUKL 0167725); SÚKL verlinkt die EU-SPC der EMA, **tschechische Fassung** (57 S.; T-20) | https://www.ema.europa.eu/cs/documents/product-information/votrient-epar-product-information_cs.pdf | §4.8 Tabulka 2 (RCC, n = 1149), PDF S. 12-16 | B | průjem, nauzea, zvracení, snížení chuti k jídlu, únava, syndrom palmoplantární erytrodysestezie, vyrážka „velmi časté“; stomatitida, dyspnoe „časté“ | Sarkom-Tabelle (Tabulka 3) nicht ausgewertet |
| SRC-SUKL-OPDIVO | Opdivo (nivolumab), SPC laut Databáze léků SÚKL (kodSUKL 0210772); SÚKL verlinkt die EU-SPC der EMA, **tschechische Fassung** (310 S.; T-20) | https://www.ema.europa.eu/cs/documents/product-information/opdivo-epar-product-information_cs.pdf | §4.8 (PDF S. 25-26), Tabulka 18 Monotherapie (PDF S. 26-27), §4.2 Tabulka 14 (PDF S. 10) | B | únava 44 % (Monotherapie, n = 4 646); průjem, zvracení, nauzea, vyrážka, svědění, pyrexie, dyspnoe „velmi časté“ | Kombinationstabellen 19/20 nicht ausgewertet; Dyspnoe↔Pneumonitis Annahme ANN-A1-02 |
| SRC-WHO-ATC | WHO Collaborating Centre for Drug Statistics Methodology, ATC/DDD Index (Update 2026-01-20) | https://atcddd.fhi.no/atc_ddd_index/?code=<Code> | je Code | B | L01XA03 oxaliplatin · L01BC02 fluorouracil · V03AF03 calcium folinate · L01BC06 capecitabine · L01FF02 pembrolizumab · L01CD02 docetaxel | – |
| SRC-FNM-VYZVA3 | „Rakathon výzvy – onkologie FNM“, Výzva 3 „Digitální hlídač nežádoucích účinků“, Fakultní nemocnice Motol a Homolka (MUDr. A. Pirshtuk), PDF vom Menschen, **nicht im Repo**; Text: `C:\rk\tmp\a0\pdf\vyzvy.txt` | – | Folie „Rozsah první verze“ (PDF-Seite 9): „Praktické rady ke zvládání symptomů; při akutních obtížích odkaz na ambulanci nebo linku 155.“; „Chceme být ihned informováni o závažných nežádoucích účincích, nikoli o každé drobnosti.“ | B | Wortlaut der Eskalation in `advice.yaml`; Umfang der ersten Version | externe Vorgabe der Klinik; keine Telefonnummer der Ambulanz (Platzhalter) |
| SRC-BASCH-2017 | Basch E, Deal AM, Dueck AC, Scher HI, Kris MG, Hudis C, Schrag D. Overall Survival Results of a Trial Assessing Patient-Reported Outcomes for Symptom Monitoring During Routine Cancer Treatment. JAMA 2017;318(2):197-198 (Research Letter, PMID 28586821) | https://doi.org/10.1001/jama.2017.7156 (Volltext **nicht** geöffnet: HTTP 403) | PubMed-Eintrag (nur Einleitungssatz); Zahlen siehe §7 | B | regelmäßiges elektronisches Symptom-Reporting vs. Standardversorgung bei Chemotherapie: Überleben (Nachanalyse) | **Abstract/Sekundärquellen**, nicht Volltext; ein Zentrum, fortgeschrittene solide Tumoren; Primärstudie: SRC-BASCH-2016 |
| SRC-BASCH-2016 | Basch E, Deal AM, Kris MG, et al. Symptom Monitoring With Patient-Reported Outcomes During Routine Cancer Treatment: A Randomized Controlled Trial. J Clin Oncol 2016;34(6):557-565, doi:10.1200/JCO.2015.63.0830 (PMID 26644527) | https://doi.org/10.1200/JCO.2015.63.0830 (Abstract über PubMed gelesen) | Abstract | B | n = 766; Notaufnahme 34 % vs. 41 % (P = .02); Hospitalisierung 45 % vs. 49 % (P = .08); Chemotherapie länger (8,2 vs. 6,3 Monate); 1-Jahres-Überleben 75 % vs. 69 % (P = .05) | **nur Abstract gelesen**; ein Zentrum (MSKCC), fortgeschrittene solide Tumoren, Intervention mit Pflege-E-Mail-Alerts |
| SRC-WHO-ICD10 | ICD-10 Version 2019, WHO (Browser) | https://icd.who.int/browse10/2019/en | Kapitel II: C18, C19, C20, C34, C43, C50; T-20 (geöffnet 2026-10-17 über die JSON-Schnittstelle des Browsers): C61 „Malignant neoplasm of prostate“, C64 „Malignant neoplasm of kidney, except renal pelvis“ | B | Zuordnung der Codes zu den Diagnosegruppen in `diagnoses.yaml` | nur Klassifikation; Zuordnung Code→Fragen ist **keine** Quellenaussage |
| SRC-PROCTCAE-EN | NCI PRO-CTCAE Items – English (Universal), Item Library Version 1.0, Division of Cancer Control and Population Sciences, NCI/NIH, Version date 5/11/2023 (PDF, 628 200 Byte, SHA-256 `ba97cfbe81c5e019d2d865de4d1892845eaecb6398b146e756a6f29c889791e1`) | https://healthcaredelivery.cancer.gov/pro-ctcae/instruments/pro-ctcae/pro-ctcae_english.pdf (abgerufen 2026-10-17; Datei **nicht** im Repo) | Items 3, 8, 9, 10, 16, 19, 30, 39, 48, 53 (siehe §11) | B | Wortlaut der englischen Fragen und Antwortoptionen in `items.yaml` | Nutzung nur unter NCI Terms of Use (SRC-PROCTCAE-TERMS); Wortlaut unverändert; PDF nicht weitergeben |
| SRC-PROCTCAE-CS | NCI PRO-CTCAE Items – Czech, Item Library Version 1.0, NCI/NIH, Version date 11/11/2024 (PDF, 339 680 Byte, SHA-256 `16de8337ade72348ffc53de9cb5915c77cc1bd802d59827efe20d98e786dfb20`) | https://healthcaredelivery.cancer.gov/pro-ctcae/instruments/pro-ctcae/pro-ctcae_czech.pdf (abgerufen 2026-10-17; Datei **nicht** im Repo) | wie SRC-PROCTCAE-EN | B | Wortlaut der tschechischen Fragen und Antwortoptionen in `items.yaml` | cs-Fassung enthält die NCI-Korrektur vom 11.11.2024 (u. a. Item 53b „VYČERPANOST“); von uns nicht muttersprachlich geprüft |
| SRC-PROCTCAE-CS-CERT | Certified Translation (Czech) der PRO-CTCAE Item Library Version 1, NCI/RWS Lifesciences, ISPOR-Methodik, unterzeichnet 29.01.2018 (PDF-Scan, SHA-256 `63201831a880215284b7f2dfdad1a2b2b2bab25db448db2c544d26c985d6bee9`) | https://healthcaredelivery.cancer.gov/pro-ctcae/certificates/pro-ctcae/pro-ctcae_cert_czech.pdf (abgerufen 2026-10-17) | ganze Seite | B | Übersetzungsmethode: zwei Vorwärtsübersetzungen, Abstimmung, Rückübersetzung, Prüfung durch tschechischsprachige Ärztin/Pflegekraft, linguistische Validierung mit Patient:innen | Scan nur per OCR gelesen (Datum/Name optisch nicht gegengelesen) |
| SRC-PROCTCAE-DE | NCI PRO-CTCAE Items – German (Universal), Item Library Version 1.0, NCI/NIH, Version date 7/20/2023 (PDF, 379 539 Byte, SHA-256 `44a0396fc64233d662adf8fee5f9694b0ae568f8d7ad1036fa39866eeb411fb4`) | https://healthcaredelivery.cancer.gov/pro-ctcae/instruments/pro-ctcae/pro-ctcae_german.pdf (abgerufen 2026-10-17; Datei **nicht** im Repo) | wie SRC-PROCTCAE-EN | B | offizieller deutscher Wortlaut der Fragen und Antwortoptionen in `items.yaml` (`de`) | Auf der NCI-Seite ohne Übersetzungszertifikat verlinkt; von uns nicht muttersprachlich geprüft; Nutzung nur unter SRC-PROCTCAE-TERMS |
| SRC-PROCTCAE-TERMS | PRO-CTCAE Terms of Use, NCI (healthcaredelivery.cancer.gov), Seite „Last updated 03 Apr 2026“ | https://healthcaredelivery.cancer.gov/pro-ctcae/terms_of_use.html (geöffnet 2026-10-17) | ganze Seite | B | Bedingungen siehe §11 | **Nutzung verlangt Registrierung der Studie und Zustimmung**; die Seite nennt nicht, wo registriert wird; keine Ausnahme für Prototypen/Hackathons |
| SRC-NCI-FATIGUE | Fatigue and Cancer – Side Effects, NCI (cancer.gov), Patienteninformation | https://www.cancer.gov/about-cancer/treatment/side-effects/fatigue | „Self-care“-Abschnitt | B | Tipps Erschöpfung (`advice.yaml`) | US-Regierungswerk, Quelle in UI ausweisen; Texte sind eigene gekürzte Fassung |
| SRC-NCI-NAUSEA-VOMITING | Nausea and Vomiting and Cancer – Side Effects, NCI | https://www.cancer.gov/about-cancer/treatment/side-effects/nausea-vomiting | „Tips for managing nausea and vomiting“ | B | Tipps Übelkeit/Erbrechen | s. o. |
| SRC-NCI-DIARRHEA | Diarrhea and Cancer – Side Effects, NCI | https://www.cancer.gov/about-cancer/treatment/side-effects/diarrhea | „Tips for managing diarrhea“ | B | Tipps Durchfall | s. o. |
| SRC-NCI-INFECTION | Infection and Neutropenia and Cancer Treatment – Side Effects, NCI | https://www.cancer.gov/about-cancer/treatment/side-effects/infection | „Ways to prevent infection“ | B | Tipps bei Fieber (Händewaschen, Menschenmengen meiden, Mund täglich prüfen) | Seite empfiehlt zusätzlich, vor fiebersenkenden Mitteln das Team zu fragen – bewusst **nicht** übernommen (Medikamentenbezug, MQ-T12-04) |
| SRC-NCI-PAIN | Pain and Cancer Treatment – Side Effects, NCI | https://www.cancer.gov/about-cancer/treatment/side-effects/pain | „Describing your pain“; „Complementary and integrative medicine practices“ | B | Tipps Schmerz (nicht-medikamentös) | Seite beschreibt hauptsächlich Medikamente – diese nicht übernommen |
| SRC-NCI-NERVE | Nerve Problems (Peripheral Neuropathy) and Cancer Treatment – Side Effects, NCI | https://www.cancer.gov/about-cancer/treatment/side-effects/nerve-problems | „Ways to prevent or manage problems related to nerve changes“ | B | Tipps Neuropathie | s. o. |
| SRC-NCI-SKIN-NAIL | Skin and Nail Changes and Cancer Treatment – Side Effects, NCI | https://www.cancer.gov/about-cancer/treatment/side-effects/skin-nail-changes | „Ways to prevent or manage mild skin and nail changes“ | B | Tipps Hautausschlag und Hand-Fuß-Haut | Übertragung auf Hand-Fuß-Haut ist Annahme (ANN-A1-09); die Seite nennt kein Hand-Fuß-Syndrom |
| SRC-NCI-MOUTH-THROAT | Mouth and Throat Problems and Cancer Treatment – Side Effects, NCI | https://www.cancer.gov/about-cancer/treatment/side-effects/mouth-throat | „Ways to prevent mouth and dental problems“; „Ways to manage mouth problems“ | B | Tipps Mund | s. o. |
| SRC-NCI-APPETITE | Weight Changes and Cancer – Side Effects, NCI (Seite „Appetite loss“) | https://www.cancer.gov/about-cancer/treatment/side-effects/appetite-loss | „Ways to manage appetite loss and weight loss“; Einleitung (Krebsarten mit höherem Risiko für Gewichtsverlust) | B | Tipps Appetit; Zusatzfrage Lunge (ANN-A1-08) | s. o. |
| SRC-NCI-PDQ-CARDIOPULM | Cardiopulmonary Syndromes (PDQ) – Patient Version, NCI | https://www.cancer.gov/about-cancer/treatment/side-effects/cardiopulmonary-pdq | „Dyspnea During Advanced Cancer“, Non-drug treatments | B | Tipps Atemnot (Lippenbremse, Ventilator, Entspannung); Zusatzfrage Lunge | PDQ: Inhalt frei als Text nutzbar, Quelle nennen |

Interne Quelle (Vorwissen, nur gelesen, nichts kopiert): `E:\rakathon\docs\science\challenge-research.md` (Zeile „PRO-CTCAE: Nutzungsbedingungen“)
und `limitations.md` (L-51). Eingetragen in `provenance/PROVENANCE.md` §3.

## 2. ANN-06 – Nutzungshinweis im CTCAE-PDF (Bericht)

- **PDF (312 Seiten) enthält keinen Urheberrechts-, Lizenz- oder Public-Domain-Hinweis.** Wörtlich nur: „Please note: CTCAE incorporates
  elements of the MedDRA terminology. For further details on MedDRA refer to the MedDRA MSSO Web site“ (S. 2); Titelblatt: NCI, NIH,
  U.S. DHHS; „Published July 22, 2025“. Die Einleitung enthält Grad-Definitionen (S. 2), aber keine Nutzungsbedingungen.
- **NCI-Webseite** (https://dctd.cancer.gov/research/ctep-trials/for-sites/adverse-events, geöffnet 2026-10-16): „If you would like to
  reproduce some or all of this content, see Reuse of NCI Information for guidance about copyright and permissions. In the case of
  permitted digital reproduction, please credit the National Cancer Institute as the source and link to the original NCI product using
  the original product's title.“ Die verlinkte Seite „Reuse of NCI Information“ wurde **nicht** geöffnet.
- **Folgerung (kein Rechtsurteil):** ANN-06 („US-Regierungswerk, Gradtexte dürfen mit Quellenangabe zitiert werden“) ist durch die NCI-Seite
  insoweit gestützt, als **Quellenangabe (NCI) und Link zum Originalprodukt verlangt** werden; das PDF selbst belegt ANN-06 nicht, und eine
  Public-Domain-Erklärung wurde nicht gefunden. **Umsetzung:** wo Gradtexte gezeigt oder exportiert werden (Cockpit, Bericht, FHIR),
  „Quelle: NCI CTCAE v6.0, NIH/NCI (dctd.cancer.gov)“ mit Titel ausweisen (`ctcae.yaml` → `source`). Mentor-/Rechtsentscheidung bleibt offen.
- **MedDRA-Codes:** das PDF enthält keine Codes; die LLT-Codes stammen aus der NCI-Excel (SRC-CTCAE-V6-XLSX). MedDRA ist lizenzpflichtige
  Terminologie (Eigentum der MSSO/ICH-Lizenzgeber). Die Codes werden hier nur als Bezeichner der NCI-Veröffentlichung geführt; die Frage,
  ob ihre Weitergabe im FHIR-Export lizenzrechtlich ausreicht, ist **Mentor-/Rechtsentscheidung (offen)**.
- **Abgleich:** Text jedes Grades und jeder Definition in `ctcae.yaml` wurde gegen die angegebene PDF-Seite geprüft (Leerraum und
  Silbentrennung normalisiert): 14 Begriffe, 0 Abweichungen. Werkzeug: Textextraktion des PDFs mit `pypdf` außerhalb des Repos
  (Skript im Scratchpad, **keine** Repo-Abhängigkeit, PDF nicht kopiert). Die Excel-Fassung enthält ein Blatt „Errata“ (3 Einträge, 2026-01-20,
  darunter Vomiting Grad 2); der Text der PDF-Fassung vom Januar 2026 stimmt für alle 14 Begriffe mit der Clean-Copy-Excel überein.

## 3. Annahmen und offene Mentor-Entscheidungen

| ID | Annahme / offener Punkt | Status |
|---|---|---|
| ANN-A1-01 | Die Fieberfrage nennt „38,0 °C oder höher“; die Zahl stammt aus CTCAE v6.0 *Fever* Grad 1 (S. 85) und ist **keine** validierte Alarmschwelle | Mentor-Entscheidung |
| ANN-A1-02 | Zuordnung Dyspnoe ↔ immunvermittelte Pneumonitis (Pembrolizumab) ist Annahme, keine SmPC-Aussage | Mentor-Entscheidung |
| ANN-A1-03 | `cycle_length_days` 14 (FOLFOX, Label „alle 2 Wochen“), 21 (Capecitabin 2 Wochen Einnahme + 1 Woche Pause; Pembrolizumab 200 mg alle 3 Wochen laut §4.8; Docetaxel „alle 3 Wochen“ nur aus Kombinationsangaben des Xeloda-SmPC, nicht aus dem Taxotere-Dosierungsabschnitt gelesen) | Demo-Annahme |
| ANN-A1-04 | Alle Regelparameter in `rules.yaml` sind Demo-Werte, **klinisch nicht validiert**; PRO-Werte 0–4 sind keine CTCAE-Grade | Mentor-Entscheidung |
| ANN-A1-05 | Fragen/Skalen sind eigene Formulierung in PRO-CTCAE-**Struktur** (DR-002, ANN-05); nicht gegen NCI-Texte abgeglichen (NCI-Items nicht geöffnet). Vorwissen `limitations.md` L-51 / `challenge-research.md`: PRO-CTCAE-Nutzungsbedingungen verbieten Anpassen/Übersetzen ohne NCI-Zustimmung ⇒ **im Pitch nicht als „PRO-CTCAE-basiert“ ausgeben**; „in Anlehnung an die PRO-CTCAE-Struktur, eigene Formulierung, nicht validiert“ | Claim offen (A4/A0) | **T-23 (17.10.): überholt für die 18 offiziellen Attribute (jetzt wörtlich aus der NCI-Item-Library, §11); gilt weiter für die 4 `own_wording`-Attribute.**
| ANN-A1-06 | cs-Texte (Items, Skalen, Regelbegründungen, Hinweise, CTCAE-Labels) sind **nicht muttersprachlich geprüft**; CTCAE-cs-Labels sind eigene Übersetzung, nicht die offizielle MedDRA-Übersetzung. Kein de geliefert (Vertrag verlangt cs/en) | Prüfung offen |
| ANN-A1-07 | `watch_notes` stützen sich (T-12, Vertrag v1.9) auf die **SPC aus der SÚKL-Datenbank**: für Xeloda, Keytruda, Taxotere die dort verlinkte EU-SPC der EMA (cs), für Oxaliplatin und Fluorouracil je eine nationale SPC (Beispielprodukt Accord; andere Hersteller können abweichen). Das US-Label (FDA) für Oxaliplatin bleibt nur für den Zeitverlauf der Neuropathie. Die Notizen sind Hinweise für Ärzt:innen, keine Therapie-, Dosis- oder Prognoseaussage | Claim-Stufe B |
| ANN-A1-08 | Zusatzfragen der Gruppe LUNG (Dušnost, Chuť k jídlu) sind eine Plausibilitätsannahme aus zwei NCI-Seiten (Tumor verlegt Atemwege; Lungenkrebs mit höherem Risiko für Gewichtsverlust), keine Leitlinienvorgabe. COLORECTAL, MELANOMA, BREAST haben bewusst **keine** Zusatzfragen (keine Quelle gefunden) – Anpassung dort nur über das Regime | Mentor-Entscheidung (MQ-T12-02) |
| ANN-A1-09 | Hautpflege-Tipps der NCI-Seite zu Haut- und Nagelveränderungen (feuchtigkeitsspendende Mittel, lauwarmes Duschen, bequeme Schuhe, Handschuhe) werden für Hand-Fuß-Haut übernommen; die Seite behandelt das Hand-Fuß-Syndrom nicht ausdrücklich | Annahme, Mentor-Entscheidung |
| ANN-A1-10 | Intervalle in `schedule.yaml` (täglich Zyklustag 1-10, sonst alle 2 Tage) sind **Demo-Werte ohne Quelle**; Basch et al. liefert nur den Hintergrund „regelmäßiges Reporting“, keine Intervalle (in der Studie wöchentliche Erinnerung, laut Sekundärquelle) | Demo-Annahme, von der Klinik festzulegen (MQ-T12-03) |
| ANN-A1-11 | `cycle_length_days` 28 für ENZALUTAMIDE, ABIRATERONE, PAZOPANIB, NIVOLUMAB (T-20) ist eine **Demo-Annahme** (Berichtsperiode für Zyklustag/Intervalle), keine SPC-Aussage: die SPC nennt für Enzalutamid, Abirateron und Pazopanib tägliche Einnahme ohne Zyklus und für Nivolumab Intervalle von 2 bzw. 4 Wochen (§4.2 Tabulka 14, PDF S. 10) | Demo-Annahme |
| ANN-A1-12 | Synonyme der Laiensprache cs/en/de je Symptom in `freetext.yaml` (T-22a): **eigene Annahme**, nicht muttersprachlich geprüft, nicht linguistisch oder klinisch validiert, Vollständigkeit unbekannt; nur die als „SPC“ markierten cs-Begriffe stammen aus `knowledge/items_draft.yaml` (`original_terms_cs`, SÚKL/EMA-SPC §4.8). Die de-Begriffe stammen von A2/A1 und sind nur gegengelesen | Mentor-/Klinikentscheidung |
| ANN-A1-13 | Auswahl der Warnwort-Gruppen `FT-W-01…07` in `freetext.yaml`: Fieber ab 38 und Atemnot folgen `advice.yaml escalation.always_acute_for`; Brustschmerz, Blut im Stuhl, Verwirrtheit, Fieber ab 38 sind Beispiele aus dem A0-Ticket, Bewusstseinsverlust/Krampf und Selbstverletzung Platzhaltergruppen von A2, Blut in Erbrochenem/Husten/Urin und „Ohnmacht“ Ergänzungen von A1. Alles Annahme, **kein fachlicher Standard**, klinisch nicht freigegeben | Mentor-/Klinikentscheidung |
| ANN-A1-14 | Der Wortlisten-Abgleich (`waechter/freetext/text.py`) kennt **keine Verneinung** und nur Wortanfänge im LETZTEN Wort eines Begriffs. Folge: Warnwörter sind Wendungen (kein nacktes „dušnost“/„horečk“), die Zahl 38 stammt aus `items.yaml` (ANN-A1-01, keine validierte Schwelle); Symptom-Vorschläge erscheinen auch bei Verneinung („dušnost nemám“) | Mentor-Entscheidung |
| ANN-A1-15 | `items.yaml` (T-23): 18 von 22 Attributen sind offizieller PRO-CTCAE-Wortlaut; `own_wording` bleiben diarrhea.severity, fever.presence, hand_foot.interference, rash.severity (kein Gegenstück bzw. andere Antwortart: Rash im Original nur Ja/Nein). Antwortoptionen der eigenen Attribute: Beeinträchtigung offiziell, Schwere (Průjem, Rash) alte eigene Beschriftung. **Der offizielle Rückblick ist 7 Tage** (im Wortlaut jeder Frage), unsere Meldungen sind täglich/alle 2 Tage ⇒ sich überlappende Zeiträume und gemischtes Fenster (Fieber fragt 24 h); Auswirkung auf Verlaufsregeln (R-DLT/R-TRD) ungeprüft | Mentor-/A0-Entscheidung |

## 4. Vertrag v1.1 und verbleibende Auslegungen

Vertrag v1.1 (A0, README §9) legt fest: **G-01** Median gerader Anzahl = Mittel der zwei mittleren Werte, Baseline-Fenster `[t − N·24 h, t)`,
Theil-Sen in Wert/Tag, Paare mit Δt = 0 verworfen · **G-02** Dedupe/Cooldown gilt nicht, wenn der neue Wert höher ist als der der offenen Meldung
desselben Tripels · **G-03** `expected.alerts` mit `attribute`, `level`, optional `hour`, Menge exakt · **G-04** Tagesgrenzen/`hour` in Europe/Prague,
`hour` fehlt ⇒ 9, ganze Tage = Differenz der Kalendertage · **G-14** Konto `patient2` = SYN-0002 · **G-19** R-MIS-01-Referenz =
`max(letzte Antwort mit ≥ 1 Wert, Zyklusstart)`. Das Orakel setzt diese Festlegungen um (Stand 16.10. nach Merge von `main`, af7de32).

Zur Sicherheit rechnet das Orakel die früher offenen Auslegungen **weiter als Varianten** und bricht ab, wenn das Szenario davon abhängt
(Fensteruntergrenze inklusiv/exklusiv; „Tage seit letzter Antwort“ als Bruchteil bzw. Kalendertage; Schwellenvergleich von Steigung und
Prognose mit ±0,02 Abstand = keine Entscheidung auf der Gleitkomma-Kante). Das Szenario ist robust gegen alle 8 Varianten. Nicht im Vertrag
geregelt und im Szenario vermieden: Gleichstand mehrerer Antworten zur selben Uhrzeit; Zyklusstart-Uhrzeit (Orakel: 00:00, ohne Wirkung, da
jede Patientin später antwortet).

## 5. Orakel – unabhängige Nachrechnung

`python challenge/content/tools/oracle.py` rechnet aus `rules.yaml` + `scenario.yaml` (nur Standardbibliothek + PyYAML, `fractions.Fraction`,
8 Auslegungsvarianten) und vergleicht mit `expected`; `python challenge/content/tools/build_scenario.py` erzeugt `scenario.yaml` und
schreibt `expected` aus dem Orakel. Der Test `test_oracle_reproduces_expected_and_is_interpretation_robust` prüft zusätzlich eine **von Hand
festgelegte** Erwartung (Tabelle unten), damit Orakel und Erwartung nicht dieselbe Fehlannahme teilen.

| Patientin | Regime | Erwartete Meldungen (Regel · Symptom.Attribut · Stufe · Tag, Stunde) | Ampel am Anker | Begründung (von Hand nachgerechnet) |
|---|---|---|---|---|
| SYN-0001 | FOLFOX | R-TRD-01 · peripheral_neuropathy.severity · gelb · Tag −5, 19 Uhr ; R-SEV-01 · diarrhea.severity · rot · Tag −1, 19 Uhr | rot | siehe unten |
| SYN-0002 (Konto `patient2`) | Pembrolizumab | – | grün | alle Werte ≤ 1; letzte Antwort Tag 0 07:00 (0,08 Tage) |
| SYN-0003 | Capecitabin | R-DLT-01 · hand_foot.severity · gelb · Tag −2, 20 Uhr | gelb | Schwere 0 → 2 |
| SYN-0004 | FOLFOX | – (R-MIS-01 nur Ampel) | grau | alle Werte ≤ 1; letzte Antwort Tag −5 18:00 (4,625 Tage, Kalendertage 5 > 3) |
| SYN-0005 | Docetaxel | R-URG-01 · fever.presence · rot · Tag 0, 7 Uhr | rot | Fieber = 1 an Tag 0 |

**SYN-0001, R-TRD-01 an Tag −5** (Schwere der Neuropathie; Antworten täglich 19:00, Lücke Tage −13/−12): Fenster −15…−5 enthält die Punkte
(−15,0) (−14,0) (−11,0) (−10,0) (−9,1) (−8,1) (−7,1) (−6,2) (−5,2) = 9 ≥ 4. Von den 36 Paarsteigungen sind 10 gleich 0, die sortierten
Positionen 18 und 19 sind beide 2/9 ≈ 0,222 ⇒ Median 0,222 ≥ 0,15; Prognose 2 + 5 · 0,222 = 3,11 ≥ 3; aktueller Wert 2 < 3 ⇒ feuert. An Tag −6
(9 Punkte, 13 Nullsteigungen) sind Positionen 18/19 = 1/7 ≈ 0,143, Prognose 2 + 5 · 0,143 = 2,71 < 3 ⇒ feuert nicht. Danach ist die Meldung offen
(Dedupe), R-DLT-01 feuert nicht, weil jeder Sprung 1 beträgt. **R-SEV-01 an Tag −1** (Durchfall, Schwere): Wert 3 ≥ 3 ⇒ feuert; R-DLT-01 nicht,
weil die 7 Basiswerte der Tage −8…−2 (1,1,1,2,2,2,2) den Median 2 haben (Delta 1 < 2); R-TRD-01 nicht, weil der aktuelle Wert 3 nicht < 3 ist.
Beide Meldungen sind im Seed offen ⇒ rot. G-02 (höherer Wert) löst im Szenario keine zweite Meldung aus: kein Tripel feuert später mit höherem Wert erneut. **SYN-0003, R-DLT-01 an Tag −2:** Basis Tage −9…−3 alles 0 (7 Werte, Median 0), Wert 2 ⇒ Delta 2 ≥ 2 und
2 ≥ 2 ⇒ feuert; R-SEV-01 nicht (2 < 3); Tag −1/0: gleiche Dreier-Kombination bereits offen (Dedupe).

## 6. Szenario – Eckdaten

5 Patient:innen (alle `SYN-000n`, `synthetic: true`, frei erfundene Namen/Diagnosetexte), Anker `2026-10-17T09:00:00+02:00`, 16–21 Antwortstage.
SYN-0001 (Konto `patient`): letzter Termin Tag −14, geplant Tag +1, 2 fehlende Tage (−13/−12) als Lücke, einzelne `null`-Antworten (übersprungen),
Antworten 19:00. SYN-0003: zwei Antworten per Telefon durch Pflegekraft (Kanal/`entered_by`). Das Szenario prüft Softwareverhalten
(Regeln, Rauschbremse, Ampel), **nicht** fachliche Güte.

## 7. T-12 – Rady pacientovi, Diagnose-Anpassung, Intervalle, Quellenprüfung (Vertrag v1.9, DR-020)

**Dateien:** `advice.yaml` (12 Symptome, 41 Tipps cs/en, Eskalation), `diagnoses.yaml` (4 Gruppen), `schedule.yaml`,
`regimens.yaml` (Quellen auf SÚKL-SPC), `scenario.yaml` (nur `diagnosis_code`, 5 Zeilen; erzeugt von `tools/build_scenario.py`).

**Tipps:** eigene, gekürzte cs/en-Formulierungen nach den NCI-Patienteninformationen (cancer.gov); keine Medikamente, keine Dosierungen,
keine Diagnose, keine Beruhigung, keine Reaktionszusage; getestet gegen drei Verbotslisten (Test T-01, Frontend-Liste `forbidden.ts`, A3-Regex)
plus eine Zusatzliste für Medikamente/Zusagen. Bewusst nicht übernommen: Medikamentenhinweise der NCI-Seiten (z. B. Loperamid, Schmerzmittel,
„vor fiebersenkenden Mitteln das Team fragen“). **Eskalation:** `acute` = Wortlaut der Klinikvorgabe als Handlungsanweisung („Při akutních obtížích
kontaktujte ambulanci nebo volejte 155.“); `general` = derselbe Satz plus Satz „Tyto rady jsou obecné a nenahrazují pokyny vašeho ošetřujícího týmu“
(eigener Zusatz, nicht von der Klinik); Telefonnummer der Ambulanz: Platzhalter `[telefon ambulance]`. **Nicht muttersprachlich geprüft,
nicht klinikfreigegeben.**

**SÚKL-Prüfung (2026-10-16):** Die Datenbank hat eine öffentliche JSON-Schnittstelle (`prehledy.sukl.cz/dlp/v1/…`, `prehledy.sukl.cz/prehledy/v1/…`),
mit der Registrierungen gesucht und die SPC-Dokumente abgerufen wurden. Gefunden: Xeloda 0027023, Keytruda 0209484, Taxotere 0167638
(SÚKL-Eintrag verlinkt jeweils die EMA-Seite `…/cs/documents/product-information/<name>-epar-product-information_cs.pdf`), Oxaliplatin Accord 0239968 (SPC 81375),
Fluorouracil Accord 0242250 (SPC 94827). Alle fünf PDFs wurden heruntergeladen (HTTP 200) und die zitierten Stellen im Text geprüft (pypdf, außerhalb des
Repos, Seitenzahlen = PDF-Seiten). **Nicht verifiziert:** die Weboberfläche `prehledy.sukl.cz/prehled_leciv.html` ist eine JavaScript-Anwendung; ein
fester Detail-URL-Aufbau wurde nicht geprüft, deshalb zitieren die Quellen die Dokument-URLs. SÚKL-Dokument-IDs können sich bei SPC-Aktualisierungen ändern.

### Basch et al. – Prüfung und Wortlaut (Claim-Stufe B)

Das Folienzitat der Klinik (Výzva 3: „pravidelné hlášení symptomů prodlužuje přežití“, Basch et al., JAMA 2017) ist **nicht aus dem Volltext** geprüft:
Das JAMA-Research-Letter-Volltext war nicht erreichbar (HTTP 403, PMC-Eintrag ohne Text). Der PubMed-Abstract nennt nur die Fragestellung („assesses overall survival
associated with electronic patient-reported symptom monitoring vs usual care during routine cancer treatment“). Die Zahlen des Briefs wurden in **zwei Sekundärquellen**
gelesen: UNC Gillings (sph.unc.edu/?p=294320: Median 31,2 vs. 26,0 Monate) und AJMC (ajmc.com, Median 31,2 vs. 26,0 Monate, P = .03; HR 0,832, 95 %-KI 0,696–0,995, nach ≥ 7 Jahren
Nachbeobachtung, 517 von 766 verstorben). Die **Notaufnahme-Aussage** stammt aus der Primärstudie (JCO 2016, Abstract über PubMed gelesen): 34 % vs. 41 % (P = .02);
Hospitalisierung 45 % vs. 49 % (P = .08, nicht signifikant). Studie: randomisiert, n = 766, **ein Zentrum**, fortgeschrittene solide Tumoren unter Chemotherapie,
Intervention mit wöchentlichen E-Mail-Erinnerungen und Pflege-Alerts bei schweren/zunehmenden Symptomen.

**Vorschlag Pitch (Stufe B, A4 nur mit diesem Wortlaut):** „In einer randomisierten Studie an einem Zentrum (766 Patient:innen mit fortgeschrittenen soliden Tumoren unter Chemotherapie;
Basch et al., J Clin Oncol 2016, JAMA 2017) hatten Patient:innen mit regelmäßigem elektronischem Symptom-Reporting weniger Notaufnahmebesuche (34 % statt 41 %) und in der Nachbeobachtung
ein längeres Gesamtüberleben (Median 31,2 statt 26,0 Monate). Das ist zitierte Evidenz; unser Prototyp prüft sie nicht und behauptet keinen solchen Nutzen.“
Nicht sagen: „bewiesen“, „unser System verlängert das Überleben“, „senkt Notaufnahmebesuche“ (Prototyp ohne Wirkungsnachweis; die Studie hatte Pflege-Reaktion auf Alerts).
Zahlen des Briefs vor der Abgabe, wenn möglich, im Volltext gegenprüfen (offen: Mentor/Mensch mit Zugang).

## 8. Mentorfragen T-12 (kurz)

| ID | Frage |
|---|---|
| MQ-T12-01 | Dürfen die Tipps und die Eskalation (cs/en) so angezeigt werden, oder soll die Klinik Wortlaut und Ambulanz-Telefonnummer freigeben? |
| MQ-T12-02 | Welche Zusatzfragen sind je Diagnose klinisch gewünscht (im Prototyp nur LUNG: Dušnost, Chuť k jídlu)? |
| MQ-T12-03 | Welches Fragebogen-Intervall gilt je Zyklusphase (Demo: täglich Tag 1-10, sonst alle 2 Tage)? |
| MQ-T12-04 | Soll bei Fieber ein Tipp zu fiebersenkenden Mitteln („vorher mit dem Team sprechen“) ergänzt werden? Bisher bewusst weggelassen (Medikamentenbezug). |

## 9. T-20 – Zielschemata C61/C64 und Szenario-Patient:innen SYN-0006/0007 (Vertrag v2.8 §13, DR-033)

**Dateien:** `regimens.yaml` (+ ENZALUTAMIDE, ABIRATERONE, PAZOPANIB, NIVOLUMAB), `diagnoses.yaml` (+ PROSTATE = C61, KIDNEY = C64),
`medications.yaml` (+ 4 Präparate, status `draft`), `scenario.yaml` (+ SYN-0006, SYN-0007; erzeugt von `tools/build_scenario.py`),
Quellen §1 (SRC-SUKL-XTANDI/ZYTIGA/VOTRIENT/OPDIVO). **SYN-0001…0005 sind unverändert** (Test: SHA-256 der kanonischen Darstellung).

**Herkunft der Profile:** Symptomschlüssel = Schlüssel aus `challenge/knowledge/ae_matrix.csv` (SmPC §4.8, Zeilen mit
`patient_reportable = yes` und vorhandenem Item), nach Häufigkeit absteigend, dann Kern-Items (Test
`test_t20_regimens_are_derived_from_knowledge_matrix` leitet die Profile erneut ab und vergleicht). Hinweise (`watch_notes`) beschreiben nur,
was in der SPC-Tabelle steht (Häufigkeitsklasse, Originalbegriff); keine Therapie-, Dosis- oder Prognoseaussage. Nebenwirkungen ohne Item
(Hypertonie, Hypokaliämie, Ödeme, Hitzewallungen, Knochenbrüche u. a.) erscheinen hier nicht (siehe `knowledge/items_draft.yaml`,
`staff_context.yaml`). Diagnosegruppen PROSTATE/KIDNEY haben bewusst keine Zusatzsymptome (keine inhaltliche Quelle geöffnet).
ICD-10-Bezeichnungen C61/C64 am 2026-10-17 über den WHO-Browser geöffnet.

**Datenmodell-Hinweis (an A0):** `triage.yaml` verlangt je Regime ein Blattprofil (`regimen without triage profile`, Lader
`waechter.triage.kb`). Für die vier neuen Regime fehlt es – nicht Teil dieses Tickets (A2-Datei, Vertrag v2.8 §13 „Triage-Profile placeholder“).

| Patientin | Regime / Diagnose | Erwartete Meldungen (Regel · Symptom.Attribut · Stufe · Tag, Stunde) | Ampel am Anker | Nachrechnung (eigenes Skript mit `fractions.Fraction`, unabhängig vom Orakel) |
|---|---|---|---|---|
| SYN-0006 | ENZALUTAMIDE / C61 (Hauptfall Prostata, ohne Konto) | R-TRD-01 · fatigue.severity · gelb · Tag −13, 19 Uhr ; R-URG-01 · fever.presence · rot · Tag 0, 7 Uhr | rot | siehe unten |
| SYN-0007 | PAZOPANIB / C64 (ohne Konto) | R-DLT-01 · diarrhea.severity · gelb · Tag −3, 19 Uhr ; R-DLT-01 · hand_foot.severity · gelb · Tag −1, 19 Uhr | gelb | siehe unten |

**SYN-0006, R-TRD-01 an Tag −13** (Schwere der Müdigkeit 0 bis Tag −18, 1 an Tag −17…−14, 2 ab Tag −13): Fenster −23…−13 enthält 8 Punkte (≥ 4);
28 Paarsteigungen, davon 9 gleich 0; Median = 1/4 ≥ 0,15; Prognose 2 + 5 · 0,25 = 3,25 ≥ 3; aktueller Wert 2 < 3 ⇒ feuert. An Tag −14: 7 Punkte,
Median 1/5, Prognose 1 + 5 · 0,2 = 2,0 < 3 ⇒ feuert nicht. Danach ist die Meldung offen (Dedupe). Beeinträchtigung (höchstens 1) und die übrigen
Symptome bleiben unter allen Schwellen; **R-URG-01** an Tag 0, 7 Uhr (Fieber = 1) ⇒ rot, die einzige rote Meldung. Verlaufsform: Stufenverlauf
`steps(−17, −13)`; schleichende Anstiege mit Plateau lösen nur dann auslegungsunabhängig aus, wenn die Steigung deutlich über 0,22 liegt (Orakel bricht sonst ab).
**SYN-0007, R-DLT-01:** Durchfall (Schwere) Tag −3: Basis Tage −10…−4 sieben Werte 0 (Median 0), Wert 2 ⇒ Delta 2 ≥ 2 und 2 ≥ 2 ⇒ feuert; Hand-Fuß (Schwere)
Tag −1: Basis sieben Werte 0, Wert 2 ⇒ feuert. R-TRD-01 feuert für beide nicht (Median-Steigung 0, an Tag 0 für Durchfall 1/10 < 0,15); R-SEV-01 nicht
(Werte ≤ 2); keine Meldung vom Typ R-URG-01. Das Szenario prüft Softwareverhalten, **nicht** fachliche Güte.

**Annahmen/Mentorfragen T-20:** ANN-A1-11 (`cycle_length_days` 28 = Berichtsperiode, keine SPC-Aussage). MQ-T20-01: Welche Zusatzfragen sind für C61/C64 klinisch
gewünscht (derzeit keine; Items außerhalb des Katalogs stehen in `knowledge/items_draft.yaml`)? MQ-T20-02: Soll die SPC-Kombination Abirateron + Prednison/Prednisolon
als eigenes Regime geführt werden (CLINICAL_TODO CT-002)?

## 10. T-22a – Freitext: Wortlisten und Warnwörter (`freetext.yaml`, Schema `FreeTextFile` von A2)

Stand: Sa 17.10.2026. **Vor dem Rakathon vorhanden:** nichts davon; Inhalt entstand im Wettbewerb (Ticket T-22a, Branch `feat/T-22a`, Format von A2 aus `feat/T-22` a7d3663).

- **Inhalt:** (a) 12 Einträge `synonyms` (je `symptom_key` aus `items.yaml`) mit cs-/en-/de-Wortanfängen der Laiensprache; (b) 7 Warnwort-Gruppen `FT-W-01…07` für den Sofort-Hinweis.
  Der Hinweis selbst ist der bestehende Wortlaut `advice.yaml escalation.acute` (Klinikvorgabe SRC-FNM-VYZVA3); `freetext.yaml` enthält keinen eigenen Patiententext. Ein LLM bestimmt
  nie eine Bewertung; Freitext fließt nie in Ampel oder Regeln.
- **Herkunft je Eintrag** (steht als Kommentar an jedem Eintrag in `freetext.yaml`): SPC-Begriff (`knowledge/items_draft.yaml original_terms_cs`, Claim-Stufe B, vom Test geprüft) ·
  Item-Label (ergänzt der Lader) · `advice.yaml always_acute_for` (Fieber, Atemnot) · Beispiel aus A0-Ticket · Platzhalter von A2 · Ergänzung A1 · sonst eigene Annahme (ANN-A1-12 / -13).
- **Status:** alles `placeholder`. Offene klinische Prüfpunkte: `knowledge/CLINICAL_TODO.md` CT-014…CT-017.
- **Tests:** `test_freetext.py` (Abdeckung 12/12, Dubletten, Mehrdeutigkeit gleich langer Begriffe, Mindestlängen, Verbotsliste/Diagnosebegriffe, 30 eingefrorene Beispiele gegen die
  echte Funktion `find_terms`) und `test_content_schema.py` (Schema `FreeTextFile`). Die Tests prüfen Softwareverhalten und Konsistenz, **nicht fachliche Güte**.
- **Bekannte Grenzen (als Beispiele sichtbar):** keine Verneinungserkennung; Umschreibungen außerhalb der Listen werden nicht erkannt („Na záchodě byla krev“); Temperaturen unter 38 lösen nichts aus.
- **Mentorfragen:** MQ-T22a-01: Welche Stichwörter gehören klinisch in die Sofort-Hinweis-Liste (Auswahl, Streichung der A1-Ergänzungen)? MQ-T22a-02: Ist der Hinweis Ambulanz/155 bei Gedanken an
  Selbstverletzung der passende Weg? MQ-T22a-03: cs/en/de muttersprachlich und klinisch prüfen lassen.
## 11. T-23 – Offizieller PRO-CTCAE-Wortlaut cs/en in `items.yaml` (Vorgabe des Menschen, über A0)

Stand: Sa 17.10.2026. **Vor dem Rakathon vorhanden:** `items.yaml` mit eigener Formulierung (T-01); **im Rakathon:** Ersatz durch den offiziellen Wortlaut (T-23).

- **Quellen** (Register §1): SRC-PROCTCAE-EN (Version date 5/11/2023), SRC-PROCTCAE-CS (11/11/2024), SRC-PROCTCAE-CS-CERT, SRC-PROCTCAE-TERMS. Abruf 2026-10-17; die PDFs liegen **außerhalb des Repos**
  (`C:\rk\tmp\a1\proctcae\`), weil die Bedingungen Kopien an Dritte untersagen. Beide Item-Library-PDFs sind ohne Login abrufbar.
- **Übernommen** (Item Library, Nummer = Item/Attribut): Fatigue 53a/b · Nausea 9a/b · Diarrhea 16a · Pain 48b/c · Numbness & tingling 39a/b · Hand-foot syndrome 30a · Mouth/throat sores 3a/b ·
  Vomiting 10a/b · Shortness of breath 19a/b · Decreased appetite 8a/b = **18 Attribute**, dazu Einleitungssatz („Rückblick 7 Tage“) und Standard-Antwortoptionen. Pain 48a (Häufigkeit) nutzen wir nicht.
- **Eigene Formulierung** (`wording: own_wording`, nicht als PRO-CTCAE auszugeben): fever (nicht in der Bibliothek; „Chills“ 74 ist ein anderes Symptom), diarrhea.severity, hand_foot.interference, rash.severity (Original: Ja/Nein 24a).
  Die Symptom-Überschriften (`label`) sind eigene Überschriften.
- **Wortgleichheit geprüft:** alle 36 offiziellen Fragen (cs+en) und beide Einleitungssätze kommen in beiden PDFs wörtlich vor, verglichen mit drei Extraktoren (`pdftotext -layout`, `pdftotext` raw, `pypdf`; Leerraum
  normalisiert): 0 Abweichungen. Antwortoptionen je Item gegen den Seitentext geprüft; bei Nausea/Vomiting/Pain steht die fünfte Option im Textfluss versetzt (Layout), Zuordnung per Wortlaut, **nicht** per Seitenbild.
  **Seitenbild-Abgleich: NOT RUN** (`pdftoppm` im Lauf abgestürzt). Der übernommene Wortlaut ist per SHA-256 in `test_items_official.py` eingefroren: `2dc053d0c6bfe6cb8399d28a6d1273949f4591f0b2678f7ffba01cec2f8f1031`.
- **Rückblick (DR-041, Vorgabe des Menschen):** zu Therapiebeginn und bei Regimewechsel (erster Fragebogen nach Beginn der Therapie bzw. eines anderen `regimen_id`; ein neuer Zyklus desselben Regimes setzt NICHT zurück, Therapien mit `cycle_start` in der Zukunft zählen nicht, A0-Entscheid DR-041) gilt der offizielle Wortlaut mit „7 Tage“ (`question`, `recall_period`, wording `official`);
  danach täglicher Takt (`schedule.yaml` default 1 Tag, alle Regime) mit `question_daily`/`recall_period_daily`: derselbe Satz, **nur** „7 dnů“ → „24 hodin“ bzw. „7 days“ → „24 hours“ (wording `adapted_recall`), Antwortoptionen identisch.
  **Das ist eine Abweichung vom validierten Wortlaut** (der Rückblick der validierten Skala ist 7 Tage); die Tagesvariante ist nicht validiert (CLINICAL_TODO CT-018). Eigene Items (fever …) haben keine Tagesvariante.
  Je Antwort gespeichert (Migration w010; die Sprache `wa_responses.lang` legt T-22/A2 in w008 an): `wa_responses.recall` (initial_7d | daily_24h), `wa_answers.wording` (official | adapted_recall | own); im FHIR-Export als meta.tag
  `urn:waechter:question-language` / `urn:waechter:recall-period` und `urn:waechter:question-wording` (official | adapted_recall | own; an der Observation der Wert der Antwort, an der QuestionnaireResponse je vorkommender Wert; keine eigene Extension, weil der HAPI-Standardlauf sie nicht kennt, A3 T-23). Regeln und Triage behandeln alle Varianten gleich.
- **cs-Grammatik der Antwortoptionen:** im Original je Item verschieden (Žádná/Žádné/Žádný, Mírná/Mírné/Mírný, Závažná/Závažné/Závažný) ⇒ Standard `scale_labels` = weibliche Form, abweichende Formen als `options` am Attribut
  (neue Vertragsfelder `wording`, `pro_ctcae`, `options`).
- **Nutzungsbedingungen** (SRC-PROCTCAE-TERMS, sinngemäß, geöffnet 2026-10-17): „PRO-CTCAE® and Ped-PRO-CTCAE® are freely available for all to use“; Nutzung nach **Registrierung der Studie und Zustimmung zu den Terms**; kein Anpassen, Ändern,
  Kürzen, Zusammenfassen, Ableiten oder Übersetzen ohne schriftliche NCI-Zustimmung; keine Weitergabe, Veröffentlichung, Lizenzierung oder Bereitstellung an Dritte ohne schriftliche Zustimmung (Ausnahme: Behörden/Journals für registrierte Studien);
  kein Verkauf; nicht für Diagnose, Prognose oder Therapie bestimmt; Markenhinweis auf allen Kopien; Veröffentlichungen nennen die Registrierung und verweisen auf die PRO-CTCAE-Website; Freistellung der NCI von Ansprüchen.
- **Markenhinweis** (wie im Dokument, steht in `items.yaml wording_note`): „The PRO-CTCAE® items and information herein were developed by the Division of Cancer Control and Population Sciences in the NATIONAL CANCER INSTITUTE at the NATIONAL INSTITUTES OF HEALTH, in Bethesda, Maryland, U.S.A. Use of the PRO-CTCAE® is subject to NCI's Terms of Use.“
- **Lizenzhinweis für den Pitch (A4):** „Fragen im offiziellen Wortlaut der NCI PRO-CTCAE Item Library (cs: tschechische NCI-Übersetzung), unverändert und mit Nummer; 4 Fragen sind unsere eigene Formulierung und so markiert; als Software-Demo nicht validiert; nicht für Diagnose oder Therapie.“ **Nicht** behaupten: Studie bei NCI registriert, PRO-CTCAE-validiertes Produkt, Gleichwertigkeit mit dem Original.
- **Restrisiko (A0/Mensch):** (1) Die Registrierung der Studie wurde nicht durchgeführt (die Seite nennt keinen Ort); die Übernahme folgt der Auslegung von A0. (2) Das Repo enthält den Wortlaut – wer es weitergibt, gibt „Kopien an Dritte“ weiter (Jury, öffentliches Repo?).
  (3) Wir halten die wörtliche Übernahme einer Auswahl von 18 Attributen (Markenhinweis angehängt) nicht für eine Kürzung der Items; eine juristische Prüfung fand nicht statt.
- **Mentorfragen:** MQ-T23-01: Registrierung/Zustimmung bei NCI einholen? MQ-T23-02: 7-Tage-Rückblick des Originals mit täglichen Meldungen vereinbar, oder Zustimmung zu einem 24-h-Zeitraum beantragen? MQ-T23-03: Rash und Průjem-Schwere auf offizielles Format
  (Ja/Nein bzw. nur Häufigkeit) umstellen, damit alle Attribute offiziell sind?
## 12. T-33 – SÚKL-Index für die Arzneimittelsuche (`sukl_index.csv`)

Stand: Sa 17.10.2026.

- **Quelle:** Databáze léčivých přípravků (DLP), Státní ústav pro kontrolu léčiv (SÚKL), Open Data, Datenstand
  **25.09.2026** (Dateien `dlp_*.csv`, Gültigkeit laut `dlp_platnost.csv` 01.10.–31.10.2026), Portal https://opendata.sukl.cz
  (Datensatz DLP). Lokale Kopie **außerhalb des Repos**: `C:\rk\tmp\a1\kb\dlp\` (Abruf 2026-10-17). Format: CSV, cp1250, Trennzeichen `;`.
- **Erzeugung:** `python challenge/content/tools/build_sukl_index.py C:\rk\tmp\a1\kb\dlp` (nur Standardbibliothek) aus
  `dlp_lecivepripravky.csv` (+ `dlp_organizace.csv` für den Zulassungsinhaber). Spalten: `sukl_code` (KOD_SUKL), `name` (NAZEV),
  `strength` (SILA), `package` (DOPLNEK), `atc` (ATC_WHO), `form` (FORMA, Kurzcode), `holder` (DRZ/ZEMDRZ → Organisationsname).
- **Auswahl:** nur `REG` ∈ {R, B} (registriert bzw. nach Änderung noch verkehrsfähig, `dlp_stavyreg.csv`) **und** `DODAVKY = 1`
  (im Meldezeitraum geliefert = vermarktet): **9 112 Packungen**, 0,9 MB (von 69 847 Zeilen). Nicht gelieferte, aber registrierte Packungen
  fehlen bewusst (Größe < 5 MB; Suche nach dem Vermarkteten).
- **Lizenz:** SÚKL stellt die DLP als offene Daten (Otevřená data SÚKL) zur freien Weiterverwendung bereit; bei Weitergabe ist
  **SÚKL als Quelle mit Datenstand** zu nennen. Den genauen Wortlaut der Nutzungsbedingungen hat dieser Lauf **nicht** erneut geöffnet
  (NOT RUN: kein Webzugriff im Lauf) – vor einer Veröffentlichung prüfen (A0/Mensch). Damit ist der Vorbehalt „Lizenz ungeklärt“ aus
  `medications.yaml` (Delta v2.1 Δ6) für die Identifikationsdaten durch die Open-Data-Bereitstellung abgelöst, sofern die Prüfung das bestätigt.
- **Verwendung:** nur Identifikation (Name, kódSÚKL, ATC, Stärke, Form). Treffer haben `status: sukl_only`, **kein** Therapieprofil, keine
  Regime, kein SPC-Link; der Index bestimmt nie Fragen, Ampel oder Regeln. Kuratiert bleiben nur die Präparate der Demo-Regime (`medications.yaml`).


## 12. T-27a – Deutsche Texte (`de`) in items/ctcae/diagnoses/regimens/medications (Meldung des Menschen: unübersetzte Texte im Frontend)

Stand: Sa 17.10.2026. Ursache: die Inhaltsdateien hatten nur `cs`/`en`, das Backend fiel für `de` auf Englisch zurück. Jetzt hat jeder `LocalizedText` in den fünf Dateien `cs`, `en`, `de`
(Test `test_i18n_de.py`: 173 Texte, nicht leer, kein Sprachschlüssel zu viel). A2b ergänzt advice/triage/rules/schedule.

| Bereich | `de` | Herkunft |
| --- | --- | --- |
| items.yaml – 18 offizielle Attribute (Frage, Tagesvariante), Einleitungssatz 7 Tage/24 Stunden, Standard- und `options`-Skalen der offiziellen Items | **offizieller NCI-Wortlaut** (SRC-PROCTCAE-DE, Version date 7/20/2023), wörtlich; je Attribut `pro_ctcae`-Nummer | Abgleich: alle 18 Fragen + Einleitungssatz kommen in der deutschen PDF wörtlich vor, verglichen mit drei Extraktoren (`pdftotext -layout`, raw, `pypdf`; Leerraum normalisiert): 0 Abweichungen. Skalen: Häufigkeit Nie · Selten · Gelegentlich · Häufig · Fast immer; Schwere und Beeinträchtigung Gar nicht · Ein wenig · Mäßig · Ziemlich · Sehr (in der deutschen Fassung für beide gleich). **Seitenbild-Abgleich: NOT RUN** (wie §11). SHA-256 des deutschen Wortlauts, eingefroren in `test_items_official.py`: `f4224fc44db9959d8b9538937ea24e666a943d4ce52af1945b0d0503ab3b2710` |
| items.yaml – Tagesvariante (`question_daily`, `recall_period_daily`) | wie §11: derselbe Satz, **nur** „7 Tage“ → „24 Stunden“ (Einleitung „in den letzten sieben Tagen“ → „in den letzten 24 Stunden“) | `adapted_recall`, Abweichung vom validierten Wortlaut (CLINICAL_TODO CT-018) |
| items.yaml – eigene Items (fever, diarrhea.severity, hand_foot.interference, rash.severity) mit Optionen Keine · Leicht · Mittel · Stark · Sehr stark (Durchfall, Hautausschlag) | de: eigene Übersetzung, nicht offiziell | aus der eigenen cs/en-Formulierung abgeleitet; nicht muttersprachlich geprüft; Fieber folgt der cs-Fassung (24 Stunden) |
| items.yaml – Symptom-Überschriften (`label`) | de: eigene Übersetzung, nicht offiziell | Begriffe an die offiziellen deutschen Symptomnamen angelehnt (z. B. MÜDIGKEIT, ÜBELKEIT, DURCHFALL, KURZATMIGKEIT, APPETITMANGEL); nicht Teil des Instruments |
| ctcae.yaml – `label` (14 Begriffe) | de: eigene Übersetzung, nicht offiziell | nur die Beschriftung; **Definitionen und Gradtexte bleiben englisch-offiziell** (CTCAE v6.0 liegt nicht offiziell auf Deutsch vor, keine Übersetzung der Gradtexte) |
| diagnoses.yaml – `label` (6 Gruppen) | de: eigene Übersetzung, nicht offiziell | deutsche Standardbegriffe; ICD-10-Zuordnung unverändert |
| regimens.yaml – `label` (8 Regime) und `watch_notes[].text` (33 Hinweise) | de: eigene Übersetzung, nicht offiziell | Übersetzung aus dem englischen Text (Quelle der Aussage unverändert: SPC/Fachinformation laut `source_id`); keine inhaltliche Ergänzung; Claim-Stufe B wie cs/en |
| medications.yaml – `inn` (10 Wirkstoffe) und `source_note` | de: eigene Übersetzung, nicht offiziell | deutsche INN-Schreibweise, klein wie cs/en (z. B. capecitabin, enzalutamid, abirateron); Handelsnamen/SÚKL-Kennungen unverändert |

- **Markenhinweis/Fußzeile:** unverändert (Fußzeile steht schon auf cs/en/de, §11). Die deutschen Fragen unterliegen denselben NCI-Bedingungen wie cs/en (SRC-PROCTCAE-TERMS, Restrisiko §11).
- **Lizenzhinweis für den Pitch (A4):** „Fragen im offiziellen Wortlaut der NCI PRO-CTCAE Item Library (cs und de: NCI-Übersetzungen), unverändert und mit Nummer; 4 Fragen sind unsere eigene Formulierung und so markiert; nicht validiert; nicht für Diagnose oder Therapie.“
- **Grenzen:** Alle `de`-Texte, die nicht aus der NCI-Fassung stammen, sind **nicht muttersprachlich geprüft** und nicht klinisch/linguistisch validiert; sie ändern keine Regel, keinen Wert und keine Auswertung (Werte 0–4 sprachunabhängig).
- **Mentorfrage MQ-T27a-01:** deutsche Übersetzung der Watch-Notes und Diagnose-/CTCAE-Beschriftungen durch eine deutschsprachige Fachperson prüfen lassen (aktuell Eigenübersetzung).
