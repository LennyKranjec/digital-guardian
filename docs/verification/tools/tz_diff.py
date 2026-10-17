"""A3-Gegenprüfung: `waechter.timeutil.to_prague` gegen die IANA-Daten (`zoneinfo`, braucht tzdata).

Aufruf (Referenz-venv): python docs/verification/tools/tz_diff.py <challenge/backend>
Prüft alle Viertelstunden der Jahre 1996–2040 und jeden Umstellzeitpunkt ±1 s: gleicher UTC-Versatz.
"""

import sys
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, sys.argv[1])
from waechter.timeutil import to_prague  # noqa: E402

prague = ZoneInfo("Europe/Prague")
start, end = datetime(1996, 1, 1, tzinfo=UTC), datetime(2041, 1, 1, tzinfo=UTC)
checked = bad = 0
t = start
while t < end:
    probes = [t]
    if t.minute == 0 and t.hour == 1:  # mögliche Umstellung 01:00 UTC
        probes += [t - timedelta(seconds=1), t + timedelta(seconds=1)]
    for probe in probes:
        checked += 1
        if to_prague(probe).utcoffset() != probe.astimezone(prague).utcoffset():
            bad += 1
            if bad <= 5:
                print("ABWEICHUNG", probe.isoformat())
    t += timedelta(minutes=15)
print(f"geprüft: {checked} Zeitpunkte, Abweichungen: {bad}")
sys.exit(1 if bad else 0)
