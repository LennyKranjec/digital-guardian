"""Challenge-Plugin „Digitaler Wächter“: registriert Rollen, Konten, Modell, Seed und Routen.

`app.plugins` lädt nur diese Datei; das Paket `waechter/` daneben wird über `sys.path` erreichbar.
"""

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from app.registry import DemoAccount, Registry  # noqa: E402
from app.services.seed import DEMO_PASSWORD  # noqa: E402
from waechter.api import router  # noqa: E402
from waechter.constants import ROLE_CLINICIAN, ROLE_PATIENT  # noqa: E402
from waechter.documents_api import router as documents_router  # noqa: E402
from waechter.meta import waechter_meta  # noqa: E402
from waechter.models import WaechterBase  # noqa: E402
from waechter.services.seed import seed_scenario  # noqa: E402
from waechter.services.subject import resolve_patient_id  # noqa: E402
from waechter.services.triage import start_warmup  # noqa: E402


def register(registry: Registry) -> None:
    registry.add_role(ROLE_PATIENT, "Patient:in (eigene Daten)")
    registry.add_role(ROLE_CLINICIAN, "Klinisches Personal")
    registry.add_demo_account(DemoAccount("patient", DEMO_PASSWORD, ROLE_PATIENT, "patient"))
    registry.add_demo_account(DemoAccount("patient2", DEMO_PASSWORD, ROLE_PATIENT, "patient2"))
    registry.add_demo_account(DemoAccount("patient6", DEMO_PASSWORD, ROLE_PATIENT, "patient6"))
    registry.add_demo_account(DemoAccount("doctor", DEMO_PASSWORD, ROLE_CLINICIAN, "doctor"))
    registry.add_metadata(WaechterBase.metadata, migrations=HERE / "waechter" / "migrations")
    registry.set_subject_resolver(resolve_patient_id)
    registry.add_seed_step(seed_scenario)
    registry.add_meta_extension(waechter_meta)
    registry.add_router(router)
    registry.add_router(documents_router)
    start_warmup()  # Kompilate der Triage-Bäume im Hintergrund vorbereiten (einmal je Prozess)
