# Verifikation T-KB (Wissensbasis C61/C64, Zweitleser-Stichprobe CT-011)

- Prüfer: A3 · Sa 17.10.2026, ~04:20 · Stufe: **VOLL** (Datenherkunft, Privacy, Zweitleser)
- Stand: `feat/T-KB` 0534a5b (Code 02e985d, 3539e1a) auf main (Branch `verify/T-KB`, nur `challenge/knowledge`)
- Ergebnis: **PASS_WITH_RISKS** (0 Critical/High/Medium, 1 Low; Zweitleser deckt ≈ 62 % der Häufigkeitsklassen ab, siehe NOT RUN)

## Ergebnis in Kürze

Die Matrix hält der unabhängigen Zweitlesung stand: alle 533 Originalbegriffe stehen auf der zitierten Seite (anderer Extraktor als A1), alle 191 CTCAE-Begriffe stehen in der NCI-Excel, und von 331 gegengelesenen Häufigkeitsklassen weicht keine ab, mit **einer** Auffälligkeit (Votrient „Kožní vřed“). Quellen-Hashes stimmen, keine Rohdaten, Aggregation reproduzierbar.

## Ausgeführte Befehle

| Prüfung | Ergebnis |
|---|---|
| SHA-256 der sechs Quell-PDF gegen `SOURCES.md` | 6 von 6 gleich (Xtandi, Zytiga, Lanbica, Votrient, Opdivo, Sutent) |
| Originalterm auf der zitierten PDF-Seite, `pdftotext -layout` + `-raw` (A1 nutzte PyMuPDF) | **533 von 533**, keine Seitenverschiebung |
| Häufigkeitsklassen aus dem **Seitenbild** abgelesen und mit der Matrix verglichen (ganze Seiten): Lanbica S. 4 (30 Zeilen), Votrient S. 15 (45) und S. 16 (20), Sutent S. 11 (70) | 165 Zeilen: 164 gleich, 1 Auffälligkeit (F-01) |
| Häufigkeitsklasse vor dem Begriff im Text (zeilenweise Tabellen) Xtandi/Zytiga, alle verified | 49 von 49 gleich |
| dasselbe für Opdivo Tabelle 18 (zeilenweise) | 117 von 121 gleich; 4 Heuristik-Fälle (3 Tabellenfortsetzung von der Vorseite, 1 Teilwort „bolest“) – kein Fehler erkennbar |
| CTCAE-Terme der Matrix gegen die NCI-Excel `ctcae-v6.0.xlsx` | 191 von 191; `verified` nie ohne CTCAE-Term, `unverified` nie mit Term |
| `aggregate.py` neu ausführen | alle vier abgeleiteten Dateien byte-gleich (reproduzierbar); liest nur `ae_matrix.csv` und `substances.yaml` |
| Neue Tests: `challenge/knowledge/test_a3_tkb.py` (9 Tests + 1 xfail), `challenge/backend/test_a3_tkb_sources.py` (2, optional mit `A3_KB_SOURCES`) | 32 passed + 1 xfailed (inkl. A1s 21 Tests); Lint/Format/mypy grün |
| Mutationsproben | Häufigkeit einer Sutent-Zeile geändert ⇒ Seitenbild-Test rot; Originalterm verfälscht ⇒ Quelltest rot; Dateien zurückgesetzt |
| Herkunft | nur neue Dateien in `challenge/knowledge`, keine Plattformänderung, keine Datensatz-Rohdaten |

## Befunde

| Nr | Schwere | Befund |
|---|---|---|
| F-01 | Low | Votrient S. 15 **„Kožní vřed†“** steht in der Zeile im Block „Méně časté“, trägt aber in **allen Zahlenspalten „není známo“** (Fußnote †: Meldung nach Zulassung). Die Matrix führt die Zeile als `verified` mit `uncommon`. Das ist eine Lesart (Blocketikett), keine klare Quellaussage. Beleg: `test_a3_tkb.py` (xfail strict, kippt, wenn die Zeile korrigiert oder auf `unverified` gesetzt wird). Kleinste Korrektur: Zeile auf `unverified` (oder `not known`) setzen und in `CLINICAL_TODO` aufnehmen (CT-004/CT-008). |

## Hinweise (keine Befunde)

- Der Text-Layer der Votrient-/Lanbica-PDF ist durcheinander (Zeilen und Zahlen entkoppelt); eine Maschinenprüfung der Häufigkeit ist dort nur über das Seitenbild möglich. Die Seitenbild-Lesung ist als Test-Protokoll im Repo (`test_a3_tkb.py`), damit sie wiederholbar ist.
- `dataset_counts.yaml`: nur Aggregate, keine Zelle 1–4, keine Pseudonyme, Kennungen oder Mailadressen; nennt Datensatzlauf und Herkunftssystem (Pseudonymisierung benannt). Für die Abgabe so lassen.
- Pitch-Wortlaut bleibt wie von A1/A0 vorgesehen: „Nebenwirkungsliste aus SPC-Tabellen für 6 Wirkstoffe, belegt je Zeile; klinisch nicht freigegeben“, **ohne** Aussage zur Vollständigkeit (Votrient-Sarkomtabelle, Opdivo-Kombinationen nicht extrahiert, CT-006).

## NOT RUN

- Häufigkeitsklassen der übrigen Seiten **nicht** unabhängig gegengelesen: Votrient S. 12–14 (78 Zeilen), Sutent S. 12–13 (94 Zeilen), Lanbica S. 5 (5 Zeilen), Opdivo 4 Heuristik-Fälle. Abdeckung insgesamt 331 von 533 Zeilen (≈ 62 %); Begriffsexistenz und CTCAE-Terme sind vollständig geprüft.
- Muttersprachliche Prüfung cs/de und klinische Prüfung (Zuordnung `patient_reportable`/`pro_item`): außerhalb des Auftrags (CT-004, CT-012).
- Gegenprüfung gegen die englischen EMA-SPC (CT-007): nicht geöffnet.
