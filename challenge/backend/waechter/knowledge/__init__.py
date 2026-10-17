"""Wissensbasis-Pipeline (T-19): SmPC-Text ⇒ Extraktion ⇒ deterministischer Prüfer ⇒ FHIR R4.

Nur öffentliche Arzneimittel-Fachinformationen (lokale Dateien, die der Mensch bereitstellt) und die
manuell belegte `ae_matrix.csv`. Kein Zugriff auf Rakathon-Datensätze, kein Netz in diesem Paket
(das Sprachmodell wird nur über den Adapter `waechter.llm.adapters` erreicht und nur auf Wunsch),
keine Patientendaten. Ein Sprachmodell liefert Entwürfe; was nicht belegt ist, kommt nicht in FHIR.
"""
