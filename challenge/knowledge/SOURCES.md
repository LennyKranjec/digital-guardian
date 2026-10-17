# SOURCES – Quellen der Wissensbasis C61/C64 (T-KB, Owner A1)

Stand: Sa 17.10.2026. Zugriffsdatum aller Quellen: **2026-10-17**. Claim-Stufe aller Aussagen: **B** (zitierte externe Evidenz, im Prototyp
ungetestet); ausgenommen ist die Software-Aggregation (Stufe A: Tests in `test_knowledge_provenance.py`). Alles `draft | unverified` bis zur
klinischen Freigabe (siehe `CLINICAL_TODO.md`). Vollständig gelesen heißt: der genannte Abschnitt 4.8 wurde im Volltext (Tabelle + Fußnoten) geöffnet.
Die Quelldateien liegen **nicht im Repo** (Größe, Urheberrecht); wiederbeschaffbar über die URLs; Prüfsumme je Datei unten.

## 1. Quellenregister

| SRC-ID | Quelle | URL / Fundort | SHA-256 der abgerufenen Datei | Gestützt | Einschränkung |
|---|---|---|---|---|---|
| SRC-KB-SUKL-DLP | SÚKL Databáze léků – Open Data „DLP20260925“ (Tabellen `dlp_lecivepripravky`, `dlp_atc`), Gültigkeit 01.10.–31.10.2026, SÚKL | https://opendata.sukl.cz/soubory/SOD20260925/DLP20260925.zip (Seite https://opendata.sukl.cz/?q=katalog/databaze-lecivych-pripravku-dlp) | `4b5e646aa9fb62eb99002226af4a0a8cff0d66992c28646df4fd80fa4e76a0c2` (ZIP, 9 529 608 B) | ATC-Code, ATC-Klasse (englisch), INN (= ATC-Substanzname), kódSÚKL, Registrierungsnummer, Registrierungsverfahren der 30 Wirkstoffe in `drugs/substances.yaml` | nur Identifikation (Delta v2.1 C7), nie Regel; Lizenz der Open Data nicht geprüft (nur wenige Kennungen übernommen, ZIP nicht im Repo) |
| SRC-KB-SUKL-API | SÚKL öffentliche Schnittstelle `prehledy.sukl.cz/dlp/v1/dokumenty-metadata/<kódSÚKL>` (Dokument-Links) | https://prehledy.sukl.cz/dlp/v1/dokumenty-metadata/0194246 (u. a.) | – | Zuordnung kódSÚKL → SPC-Dokument (Xtandi, Zytiga, Votrient, Opdivo, Sutent: EMA-PDF; Lanbica: SÚKL-Dokument 86543) | Antwort kann sich ändern; die Suchfunktion der Schnittstelle filtert nicht (ignoriert Parameter) |
| SRC-KB-XTANDI | Xtandi (enzalutamid) – Souhrn údajů o přípravku, EU-SPC (cs), EMA, 97 S.; kódSÚKL 0194246 | https://www.ema.europa.eu/cs/documents/product-information/xtandi-epar-product-information_cs.pdf | `e728ff8e4ee5ea44d5ef06919659e0bca7e84163ecf48dcfcf77fb67f16351f7` | §4.8, Tabulka 1 (PDF S. 8–9), vollständig gelesen | Dokument ohne Versionsdatum im Text; Stand = Abruf |
| SRC-KB-ZYTIGA | Zytiga (abirateron) – EU-SPC (cs), EMA, 78 S.; kódSÚKL 0168443 | https://www.ema.europa.eu/cs/documents/product-information/zytiga-epar-product-information_cs.pdf | `79ad8cccf4ca9738cbc5563fc4a080a7f8d566ae8373f000953c9156bb3dee2f` | §4.8, Tabulka 1 (PDF S. 7–8), vollständig gelesen; Originaltext „aktutní selhání jater“ (Tippfehler im Dokument) wörtlich übernommen | wie oben |
| SRC-KB-LANBICA | Lanbica 50 mg (bikalutamid), SPC, SÚKL-Dokument 86543, 7 S.; kódSÚKL 0176030 (Generikum) | https://prehledy.sukl.cz/prehledy/v1/dokumenty/86543 | `30696714388ca666838794eb010e46b8dc9c613b49dae83f7ffaa7d8befc660e` | §4.8, Tabulka 1 (PDF S. 4–5), vollständig gelesen (Tabelle per Bildlesung) | Generikum eines Herstellers; kein Original im CZ-Register (CT-003); Textextraktion der Tabelle ist verschoben, deshalb Bildlesung |
| SRC-KB-VOTRIENT | Votrient (pazopanib) – EU-SPC (cs), EMA, 57 S.; kódSÚKL 0167725 | https://www.ema.europa.eu/cs/documents/product-information/votrient-epar-product-information_cs.pdf | `e1f40a1c2be9dd6124280a0b45894c45088f80ab70af1a87a28c6ac6fcf2c411` | §4.8, **Tabulka 2 (RCC, n = 1149)** (PDF S. 12–16), vollständig gelesen | Tabulka 3 (Weichteilsarkom, S. 17–19) **nicht extrahiert** (CT-006) |
| SRC-KB-OPDIVO | Opdivo (nivolumab) – EU-SPC (cs), EMA, 310 S.; kódSÚKL 0210772 | https://www.ema.europa.eu/cs/documents/product-information/opdivo-epar-product-information_cs.pdf | `b4c6e40e73a8bcfdb58a2cc7734da66e61e67e50a0670530a826108865ae63f1` | §4.8, **Tabulka 18 (Monotherapie)** (PDF S. 26–27), vollständig gelesen | Kombinationstabellen 19/20 (S. 30–36) **nicht extrahiert** (CT-006); Auffälligkeit Muskuloskelettal (CT-007) |
| SRC-KB-SUTENT | Sutent (sunitinib) – EU-SPC (cs), EMA, 71 S.; kódSÚKL 0027190 | https://www.ema.europa.eu/cs/documents/product-information/sutent-epar-product-information_cs.pdf | `747b75f697fa762c1c6a465ec222ddd02d4ba61a5842f0adaf19325ad4adcced` | §4.8, Tabulka 1 (PDF S. 11–13), vollständig gelesen | gepoolt über GIST, MRCC, pNET |
| SRC-KB-CTCAE-V6 | Common Terminology Criteria for Adverse Events (CTCAE) v6.0, NCI/NIH/DHHS, veröffentlicht 2025-07-22 (PDF-Stand Januar 2026, 312 S.), Datei vom Menschen `CTCAEv6_Jan2026.pdf` | https://dctd.cancer.gov/research/ctep-trials/for-sites/adverse-events/ctcae-v6.pdf | `caf21bbe99d466c008e0af263ff29c990c763b32193803e0cc80916d5d976a2a` | Begriffsnamen (`ctcae_v6_terms.txt`: nur Namen + Seitenzahl, keine Gradtexte) | Heuristik-Extraktion, bis ~18 Begriffe fehlen möglicherweise (CT-005); Nutzungshinweis siehe `challenge/content/SOURCES.md` §2 (Quellenangabe NCI verlangt, kein Rechtsurteil) |
| SRC-KB-DATASET-COUNTS | `dataset_counts.yaml` (A0, 16.10.2026, nur Aggregate, Zellen < 5 unterdrückt) | `challenge/knowledge/dataset_counts.yaml` | – | Auswahl der 6 Wirkstoffe für Schritt 2 (Enzalutamid 43, Bicalutamid 38, Abirateron 21; Pazopanib 21, Nivolumab 13, Sunitinib 10 Nennungen im Freitext) | Nennung im Freitext ≠ Gabe (CT-010); **keine** Rohdaten des Rakathon-Datensatzes gelesen oder gespeichert |

## 2. Methode (ehrlich)

- **Keine medizinischen Inhalte aus dem Gedächtnis.** Alle AE-Zeilen stammen aus den SPC-Tabellen oben; INN, ATC und kódSÚKL aus dem
  SÚKL-Register. Die Wirkstoffliste (30) und die Klassenzuordnung sind die **ungeprüfte Startliste des Menschen** (CT-001).
- **Extraktion:** Zellinhalt der 4.8-Tabellen maschinell aus den PDF-Tabellen gelesen (PyMuPDF `find_tables`, Fußnoten-Hochzahlen anhand des
  Superscript-Flags entfernt; `pdftotext` zur Kontrolle der Reihenfolge), Termtrennung nach Komma/Zeilenumbruch, danach von A1 geprüft und
  korrigiert (Wortumbrüche, Zellzuordnung). Die Bicalutamid-Tabelle wurde per Bildlesung übertragen. `extraction = llm:claude-sonnet-5.5` für
  alle Zeilen, weil das Mapping (CTCAE, `patient_reportable`, `pro_item`) vom LLM stammt. Das Werkzeug liegt außerhalb des Repos
  (`C:\rk\tmp\a1\kb\tools`); `aggregate.py` (im Repo) liest nur `ae_matrix.csv` und `substances.yaml`.
- **Wörtliche Prüfung:** jeder `original_term` kommt (ohne Leerraum, Groß-/Kleinschreibung ignoriert) auf der zitierten PDF-Seite vor
  (533 Zeilen, 0 Abweichungen). Jeder verwendete CTCAE-Term (191) steht im PDF auf der in `ctcae_v6_terms.txt` genannten Seite.
- **KI-assistierte Zuordnung, klinisch zu prüfen:** `ctcae_v6_term`, `patient_reportable` und `pro_item` sind Zuordnungen durch KI-Assistenz (CLINICAL_TODO CT-004), keine klinisch geprüften Aussagen.
- **Status:** `verified` = Wortlaut/Häufigkeit gegen die Quellseite geprüft **und** CTCAE-v6-Term aus dem PDF zugeordnet; `unverified` =
  sonst (Grund: kein eindeutiger CTCAE-Term; Zeilen stehen in `CLINICAL_TODO.md`). `verified` bedeutet Herkunft belegt, **nicht** klinisch freigegeben.
- **Frequenzklassen** sind die MedDRA-Konvention der SPC (velmi časté ≥ 1/10 … není známo); `section` nennt Tabelle, Organklasse und PDF-Seite.
  PDF-Seite = Seitenzahl im Dokument (gleich dem Seitenfuß).
- **Aggregation** (`aggregate.py`): deterministisch, ohne Zeitstempel; Tests prüfen Wiederholbarkeit und dass die eingecheckten Dateien dem
  Ergebnis entsprechen. Synthetische/abgeleitete Tabellen prüfen Softwareverhalten, nicht fachliche Güte.

## 3. Nicht verwendet / nicht geprüft

- EAU-/ESMO-Leitlinien: **nicht geöffnet** (Klassenzuordnung ungeprüft, CT-001).
- Rohdaten des Rakathon-Datensatzes: **nicht gelesen** (nur `dataset_counts.yaml`).
- Englische EMA-SPC zum Gegenprüfen der tschechischen Fassung: nicht geöffnet (CT-007).
- PRO-CTCAE und andere geschützte Instrumente: nicht kopiert, kein Wortlaut verwendet (`items_draft.yaml`: `TODO_OFFICIAL_WORDING`).
