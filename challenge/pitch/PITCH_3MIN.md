# PITCH_3MIN – Finale So 18.10.2026 14:00 (3 Minuten, keine Fragen) · A4, Tickets P-01 bis P-03

Sprache gesprochen: **Englisch** (START §6). Gliederung = Klinik-Folien Výzva 3: Problém a cíl · Vstupní data · Dotazník · Rady pacientovi ·
Upozornění týmu · „Co reálně chceme“ · Transparenz. Jede Aussage trägt eine Claim-ID `[CL-xx]` (nicht mitsprechen; `CLAIMS.md` gilt).

**Zeitbudget:** gesprochener Text ≈ 130 Wörter/Minute (bewusst langsam gerechnet). Zählung des gesprochenen Textes: siehe Ende der Datei.
Die Zeitmarken sind **berechnet, nicht gemessen** – die gemessene Probe mit Stoppuhr folgt (Ticket 2, nach Integration 4b).
Der Text ist ohne Folien lesbar. Die Live-Passage ist die Demo-Kurzfassung (Runbook „3-Minuten-Kurzpfad“); fällt die Demo aus, läuft
derselbe Text über die statischen Screenshots (Runbook „Rückfall 90 s“).

> **Demo-Fall (A0-Entscheid Q1):** Der Pitch zeigt **SYN-0002 (synthetisch, Melanom, Pembrolizumab; grün → rot)** – den Pfad, den A3 mit echtem Backend und
> Browser belegt hat (E2E-1). Ein Prostata-Fall (SYN-0006, Enzalutamid) darf **höchstens als Halbsatz ohne Live-Sendung** vorkommen und nur, wenn T-20b + Integration 4b +
> A3 PASS vorliegen (CL-27); sonst entfällt er. Im gesprochenen Text steht er bewusst nicht.

---

## 0:00 – 0:27 · Problem und Ziel (Problém a cíl)

*Folie 1: Zitat Basch (Wortlaut CL-01, **inkl. medianer Überlebenszeit 31,2 statt 26 Monate** – steht nur auf der Folie, wird nicht gesprochen) + Klinikzitat (cs) + Fußnote „Quelle: Abstract/Sekundärquellen, Volltext nicht geprüft“.*

“Side effects can torment cancer patients for weeks before the next visit. In a randomized single-centre trial of 766 chemotherapy patients, regular electronic symptom reporting went with fewer emergency visits – 34 instead of 41 percent. Cited evidence; our prototype does not test it. The clinic's brief: *nikoli o každé drobnosti* – immediate word on serious effects, not every minor thing.” `[CL-01, CL-02]`

## 0:27 – 0:45 · Eingangsdaten (Vstupní data)

*Folie 2: vier Kästchen: SPC (SÚKL) → Therapieprofile · CTCAE v6.0 → ärztliche Aufnahme · PRO-CTCAE (NCI, Registrierung ausstehend) → Fragetexte · Datensatz → nur Zählungen.*

“Inputs, as briefed: SÚKL product information for therapy profiles, CTCAE version 6 for physician grading, the official PRO-CTCAE wording for the patient's questions – NCI registration pending. From the shared dataset we took counts only; its documentation says therapy is free text, not structured data.” `[CL-03, CL-04, CL-29, CL-05]`

## 0:45 – 1:55 · Live-Beleg: Fragebogen · Rat · Warnung (Dotazník · Rady · Upozornění)

*Wechsel auf die App (Telefon links, Arbeitsliste rechts). Sätze entsprechen dem Runbook. Maximal 70 s – bei Überlauf CTCAE-Schritt streichen.*

“Live, synthetic data. A synthetic melanoma patient on pembrolizumab opens the check-in: one question per card, tailored to therapy – about five or six instead of fourteen to seventeen, in simulated sessions. Fever: yes. First on screen: *kontaktujte ambulanci nebo volejte 155* – the clinic's instruction, no reassurance. On the physician's list the case is red, on top; only red notifies at once. Open it: rule, threshold, values, each with evidence. One click: FHIR R4, zero validator errors.” `[CL-06, CL-07, CL-10, CL-11, CL-12, CL-15, CL-16, CL-04, CL-18]`

## 1:55 – 2:20 · „Co reálně chceme“ – Rauschbremse und Sicherheitsböden

*Folie 3: Regelkarte (Screenshot) mit Schloss-Symbol und Banner „Umsetzungstreue geprüft (Baum = Regelwerk)“.*

“Serious, not every minor thing – our answer: a noise brake and safety floors. Repeats stay quiet, a relapse alerts, fever always floors to red. The compiled decision tree equals the rulebook at every grid point, with zero under-triage in twelve thousand synthetic sessions. Faithful implementation of placeholder rules, not clinical validation.” `[CL-13, CL-14]`

## 2:20 – 2:40 · Rolle der KI

“A language model in the EU data zone drafts the summary; a deterministic checker keeps only sentences backed by exactly one fact – in our runs it dropped up to a third of the Czech sentences. If the gateway fails, a fixed template takes over. Research prototypes: documents become FHIR drafts, and free text becomes proposed follow-up questions. Document drafts enter the export only after a physician confirms; from free text, only the patient's own answer counts. A model never sets a colour, a level or a grade.” `[CL-21, CL-30, CL-31]`

## 2:40 – 3:00 · Transparenz und Nutzen für FN Motol

*Folie 4: Tabelle „vorher / während“ aus `TRANSPARENCY.md` (Zahlen dort, vor Abgabe neu gezählt).*

“Before the Rakathon: a neutral platform – login, audit log, design system – no domain logic. During these 24 hours: all of challenge/ – [N_FILES] files, [N_COMMITS] commits, [N_FIXES] marked platform fixes – written by AI agents under human direction. Next: your review of thresholds and tips; until then, everything clinical is a placeholder.” `[CL-23, CL-19, CL-20, CL-28]`

---

## Platzhalter vor dem Sprechen füllen (A0 / A3)

| Platzhalter | Quelle | Wert am 17.10. ~10:35 (Tag freeze-poc, main 7462294, A4-Zählung) – **vor Abgabe nach dem letzten Merge neu zählen** |
|---|---|---|
| `[N_FILES]` | `grep -c "^| challenge/.*| challenge | during-event |" provenance/TABLE.md` | 442 |
| `[N_COMMITS]` | `git rev-list --count pre-rakathon..HEAD -- challenge` | 323 |
| `[N_FIXES]` | `git log --oneline --grep "^platform-fix:" pre-rakathon..HEAD \| wc -l` | 6 (Liste in `provenance/PROVENANCE.md` §5) |

## Wortzählung (gesprochener Text, ohne Zeitmarken/Regie/Claim-Klammern)

Gezählt mit `python` (Leerzeichen-Split, Platzhalter mit den Werten oben ersetzt, Sternchen entfernt; Stand P-03 final):

| Abschnitt | Wörter |
|---|---|
| 0:00 – 0:27 | 61 |
| 0:27 – 0:45 | 45 |
| 0:45 – 1:55 | 78 |
| 1:55 – 2:20 | 52 |
| 2:20 – 2:40 | 83 |
| 2:40 – 3:00 | 54 |
| **Summe** | **373** |

**373 Wörter ≈ 2:52 bei 130 Wörtern/min (≈ 2:29 bei 150) – berechnet, nicht gemessen.** Die Live-Passage enthält Klickpausen: 70 s sind für 78 gesprochene
Wörter vorgesehen (≈ 36 s Sprechzeit + Klicks/Ladezeit). **Gemessene Probe: ausstehend (macht der Mensch ab 11:00)** – nicht behaupten, dass 3:00 eingehalten sind, bevor die Stoppuhr-Probe vorliegt.

**Was P-03 geändert hat (gegenüber 375 Wörtern):** + offizieller PRO-CTCAE-Wortlaut im Eingangsabsatz (CL-29), + Dokumente ⇒ FHIR und Freitext-Vorschläge als Forschungsprototypen im KI-Absatz (CL-30, CL-31);
gekürzt: Überlebensangabe (steht nur auf Folie 1), Satz „The physician decides; the system never proposes a grade“ (CL-04/CL-16 bleiben in Runbook/Q&A), „up to two million per profile“, Nutzensatz „For FN Motol: an explainable skeleton, FHIR export, drug search“.

**Reserve ist knapp.** Weitere Kürzungsreihenfolge, falls die gemessene Probe über 3:00 liegt (Wörter, die ohne Verlust einer Pflichtaussage entfallen können):
1. KI-Absatz: „in our runs it dropped up to a third of the Czech sentences“ (−13) – CL-21 bleibt belegt, nur ohne Zahl.
2. Schluss: „Next: your review of thresholds and tips;“ (−8).
3. Live-Passage: „One click: FHIR R4, zero validator errors.“ (−7) – CL-18 bleibt im Runbook (Schritt F).
**Nicht streichen:** „single-centre“ und „Cited evidence; our prototype does not test it.“ (Pflichtvorbehalt CL-01), „NCI registration pending“ (CL-29), „Document drafts enter the export only after a physician confirms; from free text, only the patient's own answer counts“ (CL-30/CL-31; A0-Korrektur bddfbf3), „until then, everything clinical is a placeholder“.

## Nicht im gesprochenen Pitch (bewusst)

Module je Wirkstoffklasse (CL-32), Baseline/„Beobachtete Symptome“ (CL-33): PWR, nicht live belegt, in Q&A 21/22 und im Runbook-Block „Zusatzbausteine“. Nachverfolgung am Folgetag (T-26, CL-34): Roadmap. Bei Bedarf Zusatzsatz „Baseline and tracked symptoms follow a therapy change.“ (+9, `[CL-33]`) – nicht empfohlen.

## Was **nicht** gesagt wird (bewusst)

Keine klinische Validierung · keine Zeitersparnis, Marktgröße, Nutzerstimme · keine „KI erkennt“-Aussage · keine Aussage, ein Modell bewerte oder entscheide etwas (nur Entwurf der Kurzfassung, Dokumentenentwurf, Vorschlag zur Freitext-Zuordnung; Übernahme nur durch ärztliche Bestätigung bzw. Antwort der Patientin) · „NCI-registriert/validiert“ für PRO-CTCAE ·
kein Live-IRIS-Push · kein „unser System verlängert das Überleben“ · kein Fehlalarm-Prozentsatz. Siehe `CLAIMS.md` §8.
