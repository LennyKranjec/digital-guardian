# Demo-Dokumente (synthetisch)

Zwei **erfundene** Dokumente für die Demo „Dokumente ⇒ FHIR“ (T-21). Sie enthalten keine Daten einer echten Person und stammen nicht
aus dem Wettbewerbsdatensatz. Entstanden **während** des Rakathons (Sa 17.10.2026).

| Datei | Inhalt | Erwartetes Ergebnis (Regelwerk `template-regex-v1`) |
|---|---|---|
| `arztbrief_SYN-0001.md` | Entlassbrief (cs) mit Diagnosen, Therapie und zwei Laborwerten | 5 Kandidaten (C50.9, Capecitabin, Docetaxel, Hämoglobin, Neutrophile); `I10` wird als „Code nicht in der Allow-Liste“ verworfen |
| `laborbefund_SYN-0001.csv` | Laborbefund als CSV | 7 Laborwerte (Hämoglobin, Thrombozyten, Leukozyten, Neutrophile, Kreatinin, ALT, CRP) |

Ablauf in der Oberfläche: Arbeitsliste ⇒ Patientin `SYN-0001` ⇒ Cockpit ⇒ Bereich **Dokumente** ⇒ Datei hochladen ⇒ Kandidaten mit Zitat
ansehen ⇒ einzelne Ressourcen **bestätigen** oder verwerfen ⇒ **FHIR-Bundle (JSON)** enthält nur Bestätigtes (mit Provenance).

Mit `WAECHTER_LLM=openai` (und Gateway-Konfiguration) schlägt statt des Regelwerks ein Sprachmodell Kandidaten vor; der deterministische Prüfer
lässt auch dann nur belegte Angaben zu. Ohne erreichbares Modell fällt der Lauf sichtbar auf das Regelwerk zurück.

Die Laborwerte sind **keine Messwerte einer Person und keine Bewertung**; die Laborliste (`labs-v1`) ist klinisch nicht freigegeben.
