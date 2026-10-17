"""Rollen, Konten und Konfigurationsarten (Vertrag v1)."""

from typing import Final

ROLE_PATIENT: Final = "patient"
ROLE_CLINICIAN: Final = "clinician"
ROLE_ADMIN: Final = "admin"  # Plattformrolle

CONFIG_KIND_RULES: Final = "rules"
CONFIG_KIND_REPORT: Final = "report"
CONFIG_KINDS: Final = (CONFIG_KIND_RULES, CONFIG_KIND_REPORT)

CONTENT_DIR_ENV: Final = "WAECHTER_CONTENT_DIR"
