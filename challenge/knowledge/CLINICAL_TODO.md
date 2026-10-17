# CLINICAL_TODO – offene klinische Prüfpunkte der Wissensbasis C61/C64 (T-KB, Owner A1)

Stand: Sa 17.10.2026. Alles in `challenge/knowledge/` ist `draft | placeholder | unverified`, bis die Klinik freigibt. Keine Diagnose,
keine Therapieempfehlung. Jede Zeile, die nicht vollständig belegt ist, steht hier (Test `test_knowledge_provenance.py` prüft die Abdeckung).
Der Abschnitt zwischen den GENERATED-Markern wird von `aggregate.py` erzeugt (nicht von Hand ändern).

## Manuelle Punkte (Mentor-/Klinik-Entscheidung)

| ID | Punkt | Betrifft |
|---|---|---|
| CT-001 | Die Wirkstoffliste und die Klassenzuordnung (C61: GnRH, Androgenrezeptor-Inhibitoren, Abirateron, Taxane, PARP-Inhibitoren, Radioligand/Radium; C64: VEGFR-TKI, Checkpoint-Inhibitoren, mTOR, HIF-2α) sind die **ungeprüfte Startliste des Menschen**. Sie wurde nicht gegen EAU/ESMO-Leitlinien geprüft; die Klassenbezeichnungen in `class_de` sind keine Quellenaussage. | `drugs/substances.yaml` |
| CT-002 | Kombinationsschemata (z. B. mit Androgenentzug, Ipilimumab, Cabozantinib) sind **nicht angelegt**; die `regimens/*.yaml` enthalten je Einzelwirkstoff eine Komponente. `label_de` = TODO, `core_profile` leer bis Schritt 4. Zusammensetzung klinisch festzulegen. | `regimens/c61.yaml`, `regimens/c64.yaml` |
| CT-003 | Bicalutamid: im CZ-Register wurde kein Originalpräparat (Casodex) gefunden; die SPC stammt von einem Generikum (Lanbica 50 mg). Andere Hersteller können abweichen. | `ae_matrix.csv` (BICALUTAMIDE) |
| CT-004 | `patient_reportable`, `pro_item` und die Zuordnung zum CTCAE-v6-Term sind **Annahmen von A1** (LLM-Zuordnung aus dem tschechischen SPC-Begriff). CTCAE-Term nur bei eindeutiger Entsprechung, sonst leer + `unverified`. Ob ein Symptom patientenberichtbar ist (z. B. Blutungen, Halluzinationen, akute Reaktionen) und welcher Fragebogen-Schlüssel passt, ist klinisch zu entscheiden. `custom` = noch kein Item in `challenge/content/items.yaml`. | `ae_matrix.csv`, `items_draft.yaml`, `staff_context.yaml` |
| CT-005 | `ctcae_v6_terms.txt` ist eine Heuristik-Extraktion aus dem PDF (832 Begriffe; das PDF hat 849–851 Definitionsblöcke): bis zu ~18 Begriffe fehlen möglicherweise. Ein fehlender Begriff führt nur dazu, dass eine Zeile ohne CTCAE-Term bleibt (nie zu einem falschen Term); jeder verwendete Term wurde gegen die PDF-Seite geprüft (191 Terme, 0 Abweichungen). | `ctcae_v6_terms.txt` |
| CT-006 | **Umfang der AE-Extraktion (nicht extrahiert):** Votrient Tabelle 3 (Weichteilsarkom, nur RCC-Tabelle 2 extrahiert); Opdivo Tabellen 19/20 (Kombinationen mit Ipilimumab, Chemotherapie, Cabozantinib, Brentuximab, AVD – nur Monotherapie, Tabelle 18); alle Fließtexte „Popis vybraných nežádoucích účinků“ (Prozentzahlen, Laborwerte); Sutent Tabelle 1 vereint GIST, MRCC, pNET. Häufigkeitsklassen gelten für die jeweilige Tabelle, nicht für C61/C64 getrennt. | `ae_matrix.csv` |
| CT-007 | Opdivo Tabelle 18 (Muskuloskelettal): im tschechischen Dokument stehen die Häufigkeitszeilen in der Reihenfolge „Méně časté (muskuloskeletální bolest, artralgie) / Časté (artritida) / Méně časté (polymyalgia rheumatica)“; wörtlich übernommen. Gegen die englische EMA-SPC prüfen, ob eine Übersetzungs- oder Satzabweichung vorliegt. | `ae_matrix.csv` (NIVOLUMAB) |
| CT-008 | Häufigkeitsklasse `not known` (Spontanmeldungen nach Zulassung) bedeutet „nicht bestimmbar“, nicht „selten“. `max_frequency_class` ordnet `not known` unter `very rare`. Ob diese Rangfolge für die Priorisierung taugt, klinisch entscheiden. | `symptom_class_matrix.csv`, `ae_by_ctcae.csv` |
| CT-009 | Dokumentstand: die EMA-PDFs tragen im Text kein Versionsdatum; Abrufdatum 2026-10-17, SHA-256 in `SOURCES.md`. SPC werden aktualisiert; vor Einsatz erneut abrufen. | `SOURCES.md` |
| CT-010 | `dataset_counts.yaml` zählt Nennungen im Freitext (keine Aussage über Gabe, Zeitpunkt, Dauer) und dient nur der Priorisierung der Extraktion – nie Fragen, Ampel oder Regeln. | `dataset_counts.yaml` |
| CT-011 | Extraktion: Zellentext maschinell aus den PDF-Tabellen gelesen (PyMuPDF, Werkzeug außerhalb des Repos), Bicalutamid-Tabelle per Bildlesung; Zuordnung und Mapping durch LLM (`llm:claude-sonnet-5.5`). Die wörtliche Prüfung (Term kommt auf der zitierten Seite vor) ist bei kurzen Termen schwach: Stichprobe gegen das Original empfohlen (A3/Klinik). | `ae_matrix.csv` |
| CT-012 | Nicht muttersprachlich geprüft: `class_de`, alle `label_de: TODO`; Fragetexte (`text_*`) sind `TODO_OFFICIAL_WORDING` – kein geschütztes Instrument kopiert, kein Wortlaut aus dem Gedächtnis. | `items_draft.yaml`, `substances.yaml` |
| CT-013 | **Widerspruch in der Quelle (A3 T-KB F-01):** Votrient-SPC (cs) S. 15, Tabelle 2, „Kožní vřed†“ steht im Block „Méně časté“, trägt in allen Zahlenspalten aber „není známo“ (Fußnote †: Meldung nach Zulassung). Zeile von verified auf **unverified** gesetzt, CTCAE-Zuordnung (vorher „Skin ulceration“, KI-assistiert) entfernt wie bei allen unverified-Zeilen (Häufigkeitsklasse bleibt Blockzuordnung `uncommon`, ungesichert); klinisch bzw. gegen die englische SPC zu klären. | `ae_matrix.csv` (PAZOPANIB, Kožní vřed) |
| CT-014 | **Freitext-Wortlisten (T-22a):** Synonyme der Laiensprache cs/en/de in `freetext.yaml` sind Annahme von A1 (nur die als SPC markierten cs-Begriffe stammen aus `items_draft.yaml`), nicht muttersprachlich/klinisch geprüft, Vollständigkeit unbekannt. Ein falscher Treffer ordnet nur eine Frage als Vorschlag zu. | `challenge/content/freetext.yaml` |
| CT-015 | **Warnwörter (T-22a):** Auswahl und Umfang der Sofort-Hinweis-Gruppen `FT-W-01…07` klinisch festlegen (Beispiele von A0, Platzhalter von A2, Ergänzungen von A1: Blut in Erbrochenem/Husten/Urin, Ohnmacht). Weitere Kandidaten offen: Nasenbluten, starke Bauchschmerzen, Schwellung. Fieber nutzt die Zahl 38 aus `items.yaml` (ANN-A1-01, keine validierte Schwelle). | `challenge/content/freetext.yaml` |
| CT-016 | **Selbstverletzung (FT-W-05):** ob der Klinikhinweis (Ambulanz/155) für Gedanken an Selbstverletzung der passende Weg ist oder eine Krisenlinie nötig ist, klinisch klären. Mehrdeutige Stichwörter („na prsou“, „zmaten/confused“, „bleeding“) können Fehltreffer auslösen. | `challenge/content/freetext.yaml` |
| CT-017 | **Keine Verneinung im Wortlisten-Abgleich (T-22a):** „dušnost nemám“ schlägt als Symptom-Vorschlag an; Warnwörter sind deshalb Wendungen statt nackter Symptomwörter. Wer Verneinung erkennen soll (LLM-Prüfer, Regel), ist Produktentscheidung. | `challenge/content/freetext.yaml`, `challenge/backend/waechter/freetext/` |
| CT-018 | **PRO-CTCAE-Wortlaut (T-23, DR-040/DR-041):** (1) Der offizielle Wortlaut (NCI Item Library, cs 11/11/2024, en 5/11/2023) wird OHNE NCI-Registrierung der Studie verwendet; Risiko trägt der Mensch (Registrierungspflicht und Weitergabeverbot laut Terms of Use, siehe `SOURCES.md` §11). (2) Der tägliche Takt fragt mit „24 Stunden“ statt dem validierten „7 Tage“ (`adapted_recall`, nur die Zeitangabe ersetzt): nicht validiert; klinisch klären, ob Tages- und 7-Tage-Antworten vergleichbar auswertbar sind (Variante steht an jeder Antwort). (3) Rash (Original nur Ja/Nein), Průjem-Schwere, Hand-Fuß-Beeinträchtigung und Fieber sind eigene Formulierung (`own_wording`). | `challenge/content/items.yaml` |
| CT-019 | **Deutsche Texte (T-27a):** Fragen/Antwortoptionen der 18 offiziellen Attribute stammen aus der offiziellen NCI-Fassung (German, 7/20/2023, ohne Übersetzungszertifikat verlinkt, unverändert); alle übrigen `de`-Texte (Überschriften, eigene Items, CTCAE-/Diagnose-/Regime-/Wirkstoff-Beschriftungen, Watch-Notes) sind Eigenübersetzungen, nicht muttersprachlich/klinisch geprüft (`SOURCES.md` §12). Deutschsprachige Fachperson prüfen lassen. | `challenge/content/*.yaml` |

## Maschinell erzeugt: unverifizierte Zeilen und Wirkstoffe ohne AE-Zeilen

<!-- BEGIN GENERATED (aggregate.py) -->

### CT-U-ABIRATERONE – unverifizierte AE-Zeilen (7)
Grund: kein eindeutiger CTCAE-v6-Term aus dem PDF zuordenbar (ctcae_v6_term leer) – siehe CT-004.
- tachykardie (common; S. 8)
- jiné arytmie (uncommon; S. 8)
- alergická alveolitida (rare; S. 8)
- zvýšení ALT a/nebo zvýšení AST (very common; S. 8)
- fulminantní hepatitida (rare; S. 8)
- vyrážka (common; S. 8)
- myopatie (uncommon; S. 8)

### CT-U-BICALUTAMIDE – unverifizierte AE-Zeilen (12)
Grund: kein eindeutiger CTCAE-v6-Term aus dem PDF zuordenbar (ctcae_v6_term leer) – siehe CT-004.
- Hypersenzitivita (uncommon; S. 4)
- angioedém (uncommon; S. 4)
- Intersticiální plicní onemocnění (uncommon; S. 4)
- Hepatotoxicita (common; S. 4)
- žloutenka (common; S. 4)
- hypertransaminázémie (common; S. 4)
- hirsutismus/obnovení růstu vlasů (common; S. 4)
- vyrážka (common; S. 4)
- Gynekomastie a pocit pnutí v prsu (very common; S. 4)
- Astenie (very common; S. 5)
- otok (very common; S. 5)
- Bolest na hrudi (common; S. 5)

### CT-U-ENZALUTAMIDE – unverifizierte AE-Zeilen (13)
Grund: kein eindeutiger CTCAE-v6-Term aus dem PDF zuordenbar (ctcae_v6_term leer) – siehe CT-004.
- edém jazyka (not known; S. 9)
- edém rtů (not known; S. 9)
- edém faryngu (not known; S. 9)
- syndrom neklidných nohou (common; S. 9)
- syndrom posteriorní reverzibilní encefalopatie (not known; S. 9)
- ischemická choroba srdeční (common; S. 9)
- zvýšené jaterní enzymy (uncommon; S. 9)
- vyrážka (not known; S. 9)
- svalové spasmy (not known; S. 9)
- svalová slabost (not known; S. 9)
- bolest bradavky (common; S. 9)
- citlivost prsu (common; S. 9)
- astenie (very common; S. 9)

### CT-U-NIVOLUMAB – unverifizierte AE-Zeilen (33)
Grund: kein eindeutiger CTCAE-v6-Term aus dem PDF zuordenbar (ctcae_v6_term leer) – siehe CT-004.
- histiocytární nekrotizující lymfadenitida (Kikuchiho lymfadenitida) (rare; S. 26)
- hemofagocytující lymfohistiocytóza (not known; S. 26)
- hypersensitivita (včetně anafylaktické reakce) (common; S. 26)
- sarkoidóza (uncommon; S. 26)
- rejekce transplantovaného solidního orgánu (not known; S. 26)
- diabetická ketoacidóza (rare; S. 26)
- periferní neuropatie (common; S. 26)
- polyneuropatie (uncommon; S. 26)
- autoimunitní neuropatie (včetně parézy n. facialis a n. abducens) (uncommon; S. 26)
- překryvný syndrom myokarditida-myozitida-myasthenia gravis (uncommon; S. 26)
- demyelinizace (rare; S. 26)
- myastenický syndrom (rare; S. 26)
- Vogtův-Koyanagiho-Haradův syndrom (not known; S. 27)
- tachykardie (common; S. 27)
- onemocnění perikardu (uncommon; S. 27)
- arytmie (včetně ventrikulární arytmie) (uncommon; S. 27)
- infiltrace plic (uncommon; S. 27)
- celiakie (rare; S. 27)
- cholestáza (uncommon; S. 27)
- vyrážka (very common; S. 27)
- vitiligo (common; S. 27)
- erytém (common; S. 27)
- psoriáza (uncommon; S. 27)
- rosacea (uncommon; S. 27)
- lichen sclerosus (not known; S. 27)
- jiná lichenoidní onemocnění (not known; S. 27)
- muskuloskeletální bolest (uncommon; S. 27)
- polymyalgia rheumatica (uncommon; S. 27)
- Sjögrenův syndrom (rare; S. 27)
- myopatie (rare; S. 27)
- selhání ledvin (včetně akutní poruchy funkce ledvin) (common; S. 27)
- bolest na hrudi (common; S. 27)
- edém (common; S. 27)

### CT-U-PAZOPANIB – unverifizierte AE-Zeilen (56)
Grund: kein eindeutiger CTCAE-v6-Term aus dem PDF zuordenbar (ctcae_v6_term leer) – siehe CT-004.
- Infekce (s neutropenií nebo bez neutropenie) (common; S. 12)
- Polycytemie (uncommon; S. 13)
- Hypestezie (uncommon; S. 13)
- Syndrom zadní reverzibilní encefalopatie (rare; S. 13)
- Změna barvy řas (uncommon; S. 13)
- Bradykardie (uncommon; S. 13)
- Kardiální dysfunkce (uncommon; S. 13)
- Ischemie myokardu (uncommon; S. 13)
- Návaly horka se zrudnutím (common; S. 14)
- Hypertenzní krize (uncommon; S. 14)
- Krvácení (uncommon; S. 14)
- Aneurysmata a arteriální disekce (rare; S. 14)
- Dysfonie (common; S. 14)
- Hemoptýza (common; S. 14)
- Vředy v ústech (common; S. 14)
- Rektální krvácení (uncommon; S. 14)
- Gastrointestinální krvácení (uncommon; S. 14)
- Zvýšená střevní peristaltika (uncommon; S. 14)
- Anální krvácení (uncommon; S. 14)
- Enterokutánní píštěl (uncommon; S. 14)
- Porucha jaterních funkcí (common; S. 15)
- Hepatotoxicita (common; S. 15)
- Ikterus (uncommon; S. 15)
- Poškození jater způsobené léky (uncommon; S. 15)
- Vyrážka (very common; S. 15)
- Erytém (common; S. 15)
- Depigmentace kůže (common; S. 15)
- Exfoliace kůže (uncommon; S. 15)
- Erytematózní vyrážka (uncommon; S. 15)
- Poruchy kůže (uncommon; S. 15)
- Makulární vyrážka (uncommon; S. 15)
- Svědící vyrážka (uncommon; S. 15)
- Vezikulární vyrážka (uncommon; S. 15)
- Generalizovaná vyrážka (uncommon; S. 15)
- Papulózní vyrážka (uncommon; S. 15)
- Plantární erytém (uncommon; S. 15)
- Kožní vřed (uncommon; S. 15)
- Svalové spasmy (common; S. 15)
- Muskuloskeletální bolest (uncommon; S. 15)
- Proteinurie (very common; S. 15)
- Krvácení do močových cest (uncommon; S. 15)
- Metroragie (uncommon; S. 15)
- Zánět sliznic (common; S. 15)
- Astenie (common; S. 15)
- Otok (common; S. 15)
- Bolest na hrudi (common; S. 15)
- Onemocnění sliznice (uncommon; S. 15)
- Zvýšení krevního tlaku (common; S. 16)
- Zvýšení urey v krvi (common; S. 16)
- Abnormální výsledky vyšetření jaterních funkcí (common; S. 16)
- Zvýšení hladin jaterních enzymů (uncommon; S. 16)
- Pokles hladiny glukózy v krvi (uncommon; S. 16)
- Zvýšení hladin aminotransferáz (uncommon; S. 16)
- Abnormální výsledky vyšetření funkce štítné žlázy (uncommon; S. 16)
- Zvýšení diastolického krevního tlaku (uncommon; S. 16)
- Zvýšení systolického krevního tlaku (uncommon; S. 16)

### CT-U-SUNITINIB – unverifizierte AE-Zeilen (62)
Grund: kein eindeutiger CTCAE-v6-Term aus dem PDF zuordenbar (ctcae_v6_term leer) – siehe CT-004.
- Virové infekce (common; S. 11)
- Respirační infekce (common; S. 11)
- Absces (common; S. 11)
- Mykotické infekce (common; S. 11)
- Nekrotizující fasciitida (uncommon; S. 11)
- Bakteriální infekce (uncommon; S. 11)
- Pancytopenie (uncommon; S. 11)
- Hypersenzitivita (uncommon; S. 11)
- Angioedém (rare; S. 11)
- Periferní neuropatie (common; S. 11)
- Hypestézie (common; S. 11)
- Hyperestézie (common; S. 11)
- Syndrom posteriorní reverzibilní encefalopatie (rare; S. 11)
- Hyperamonemická encefalopatie (not known; S. 11)
- Otok očních víček (common; S. 11)
- Ischemie myokardu (common; S. 11)
- Snížení ejekční frakce (common; S. 11)
- Kardiomyopatie (uncommon; S. 11)
- Selhání levé komory (rare; S. 11)
- Torsade de pointes (rare; S. 11)
- Hluboká žilní trombóza (common; S. 11)
- Zarudnutí (common; S. 11)
- Aneurysmata a arteriální disekce (not known; S. 11)
- Plicní embolie (common; S. 11)
- Hemoptýza (common; S. 11)
- Sucho v nose (common; S. 11)
- Krvácení do trávicího traktu (common; S. 12)
- Břišní diskomfort (common; S. 12)
- Rektální krvácení (common; S. 12)
- Krvácení dásní (common; S. 12)
- Vředy v ústech (common; S. 12)
- Cheilitida (common; S. 12)
- Glosodynie (common; S. 12)
- Nepříjemný pocit v ústech (common; S. 12)
- Gastrointestinální perforace (uncommon; S. 12)
- Abnormální funkce jater (uncommon; S. 12)
- Kožní diskolorace (very common; S. 12)
- Vyrážka (very common; S. 12)
- Odlupování kůže (common; S. 12)
- Kožní reakce (common; S. 12)
- Puchýře (common; S. 12)
- Erytém (common; S. 12)
- Akné (common; S. 12)
- Kožní léze (common; S. 12)
- Dermatitida (common; S. 12)
- Pyoderma gangrenosum (rare; S. 12)
- Muskuloskeletální bolest (common; S. 12)
- Svalové spasmy (common; S. 12)
- Svalová slabost (common; S. 12)
- Píštěl (uncommon; S. 12)
- Myopatie (rare; S. 12)
- Renální selhání (common; S. 12)
- Proteinurie (common; S. 12)
- Krvácení do močového traktu (uncommon; S. 12)
- Zánět sliznice (very common; S. 12)
- Otok (very common; S. 12)
- Bolest na hrudi (common; S. 12)
- Porucha hojení (uncommon; S. 12)
- Pokles počtu trombocytů (common; S. 13)
- Pokles hemoglobinu (common; S. 13)
- Zvýšený krevní tlak (common; S. 13)
- Zvýšená kreatinfosfokináza v krvi (uncommon; S. 13)

### CT-U-OHNE-AE – Wirkstoffe ohne AE-Zeilen (24)
Grund: Schritt-2-Umfang war SmPC 4.8 für die 6 laut Datensatz häufigsten Wirkstoffe; alle weiteren sind `unverified` (keine AE-Zeile).
- APALUTAMIDE
- AVELUMAB
- AXITINIB
- BELZUTIFAN
- CABAZITAXEL
- CABOZANTINIB
- DAROLUTAMIDE
- DEGARELIX
- DOCETAXEL
- EVEROLIMUS
- GOSERELIN
- IPILIMUMAB
- LENVATINIB
- LEUPRORELIN
- LUTETIUM-VIPIVOTIDE
- NIRAPARIB
- OLAPARIB
- PEMBROLIZUMAB
- RADIUM-223
- RELUGOLIX
- SORAFENIB
- TALAZOPARIB
- TEMSIROLIMUS
- TRIPTORELIN

<!-- END GENERATED -->
