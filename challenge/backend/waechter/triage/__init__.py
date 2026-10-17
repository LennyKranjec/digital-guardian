"""Triage-Kern „SymptomAmpel“ (Vertrag `challenge/contract/triage.md`, v2.0): reine Bibliothek.

`kb` lädt und prüft die Wissensbasis, `parser` wertet Regelausdrücke sicher aus, `engine` bestimmt
Level, Reason-Codes und Schild-Treffer, `policy` wählt die nächste Frage bzw. den Stopp. Kein
Zugriff auf Datenbank, Uhr, Zufall oder LLM.
"""
