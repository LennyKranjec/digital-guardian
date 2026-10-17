"""Dokumente ⇒ FHIR (T-21, Proof of Concept): hochgeladener Text ⇒ Kandidaten ⇒ Prüfer ⇒ Entwurf.

Ein Extraktor (deterministischer Regex-Extraktor `template` oder ein Sprachmodell über den
bestehenden Adapter) liefert nur **Kandidaten**. Der deterministische Prüfer (`check`) lässt einen
Kandidaten nur zu, wenn das Zitat wörtlich im Dokument steht, der Code in einer Allow-Liste
steht und Code, Wert, Einheit und Datum belegt sind. Danach ist alles ein
Entwurf; erst die ärztliche Bestätigung je Ressource bringt sie in den Patientenexport.
Kein Netz in diesem Paket (das Sprachmodell läuft nur über `waechter.llm.adapters`), keine
Diagnose, keine Bewertung durch ein Modell.
"""
