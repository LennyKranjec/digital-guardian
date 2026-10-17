"""Baut `challenge/content/sukl_index.csv` aus der SÚKL-Open-Data-Datenbank DLP (T-33).

Nur Standardbibliothek. Eingabe: Verzeichnis mit `dlp_lecivepripravky.csv` (cp1250,
Trennzeichen `;`) und optional `dlp_organizace.csv` (Zulassungsinhaber).
Ausgabe: UTF-8-CSV mit den Spalten
`sukl_code,name,strength,package,atc,form,holder`.

Auswahl (nur aktuell gültige und vermarktete Packungen):
- `REG` in {R, B}: registriert bzw. nach Änderung noch verkehrsfähig (`dlp_stavyreg.csv`);
- `DODAVKY == 1`: im letzten Meldezeitraum geliefert (vermarktet).

Der Index dient nur der Identifikation eines Präparats; er bestimmt nie Fragen, Ampel oder Regeln.

Aufruf: python challenge/content/tools/build_sukl_index.py <dlp-verzeichnis> [ausgabe.csv]
"""

import csv
import sys
from pathlib import Path

ENCODING = "cp1250"
VALID_REG = {"R", "B"}
COLUMNS = ["sukl_code", "name", "strength", "package", "atc", "form", "holder"]
DEFAULT_OUT = Path(__file__).resolve().parents[1] / "sukl_index.csv"


def _read(path: Path) -> list[dict[str, str]]:
    with path.open(encoding=ENCODING, newline="") as handle:
        return list(csv.DictReader(handle, delimiter=";"))


def _holders(directory: Path) -> dict[tuple[str, str], str]:
    path = directory / "dlp_organizace.csv"
    if not path.exists():
        return {}
    return {(row["ZKR_ORG"], row["ZEM"]): row["NAZEV"].strip() for row in _read(path)}


def build(directory: Path) -> list[list[str]]:
    holders = _holders(directory)
    rows: list[list[str]] = []
    for row in _read(directory / "dlp_lecivepripravky.csv"):
        if row["REG"] not in VALID_REG or row["DODAVKY"].strip() != "1":
            continue
        holder = holders.get((row["DRZ"], row["ZEMDRZ"]), row["DRZ"])
        rows.append(
            [
                row["KOD_SUKL"].strip(),
                row["NAZEV"].strip(),
                row["SILA"].strip(),
                row["DOPLNEK"].strip(),
                row["ATC_WHO"].strip(),
                row["FORMA"].strip(),
                holder,
            ]
        )
    rows.sort(key=lambda r: r[0])
    return rows


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    directory = Path(argv[1])
    out = Path(argv[2]) if len(argv) > 2 else DEFAULT_OUT
    rows = build(directory)
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(COLUMNS)
        writer.writerows(rows)
    print(f"{out}: {len(rows)} Zeilen, {out.stat().st_size} Bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
