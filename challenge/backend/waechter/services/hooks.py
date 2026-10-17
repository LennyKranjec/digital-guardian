"""Hook-Punkte der Fachlogik. Hier hängen spätere Tickets ein, ohne `responses.py` zu ändern."""

from sqlalchemy.orm import Session

from waechter.models import Response
from waechter.services import alerts


def on_response_saved(session: Session, response: Response) -> None:
    """Läuft in derselben Transaktion nach dem Speichern einer **neuen** Antwort (nicht bei Replay).

    Wertet die Antwort mit den versionierten Regeln aus (T-04a); Meldungen und Benachrichtigungen
    entstehen in derselben Transaktion wie die Antwort.
    """
    alerts.evaluate_response(session, response)
