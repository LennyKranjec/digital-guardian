"""Freitext der Patientin (T-22, Vertrag v2.9): Zuordnung als Vorschlag, Prüfer, Folgefragen.

Grundregel: Freitext erzeugt **nie** Antworten, Stufen oder Meldungen. Ein Adapter (`template`:
deterministischer Wortlisten-Abgleich, `openai`: Sprachmodell über `waechter.llm.adapters`) schlägt
Zuordnungen zu Symptomen des ganzen Katalogs vor (optional mit Vorschlagswert); der
deterministische Prüfer (`verify`) lässt nur Vorschläge mit wörtlichem Zitat, bekanntem Symptom und
Wert im Wertebereich durch. Jede geprüfte Zuordnung wird der Patientin als Folgefrage gestellt;
erst ihre Antwort (normale Antwort, `source = free_text_followup`) wirkt auf Regeln und Triage.
"""
