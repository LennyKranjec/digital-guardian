"""A3-Zweitleser T-KB, Quellprüfung (optional): `A3_KB_SOURCES=<Ordner>` und `pdftotext`.

Liegt außerhalb von `challenge/knowledge`, weil A1s Wächtertest dort `subprocess` verbietet.
"""

import csv
import hashlib
import os
import re
import shutil
import subprocess
import unicodedata
from pathlib import Path

import pytest

KB = Path(__file__).resolve().parents[1] / "knowledge"
ROWS = list(csv.DictReader((KB / "ae_matrix.csv").open(encoding="utf-8")))


def norm(text: str) -> str:
    return re.sub(r"[\s\-­]+", "", unicodedata.normalize("NFKC", text).lower())


SOURCES = os.environ.get("A3_KB_SOURCES")
FILES = {
    "ENZALUTAMIDE": "xtandi.pdf",
    "ABIRATERONE": "zytiga.pdf",
    "BICALUTAMIDE": "bicalutamid_lanbica.pdf",
    "PAZOPANIB": "votrient.pdf",
    "NIVOLUMAB": "opdivo.pdf",
    "SUNITINIB": "sutent.pdf",
}
needs_sources = pytest.mark.skipif(
    not SOURCES or shutil.which("pdftotext") is None,
    reason="A3_KB_SOURCES (Ordner mit den Quell-PDF) und pdftotext fehlen",
)


def extract(substance: str, number: int, mode: str) -> str:
    out = subprocess.run(  # noqa: S603 - feste Argumente, lokale Dateien
        [  # noqa: S607 - Werkzeug aus dem PATH
            "pdftotext",
            "-enc",
            "UTF-8",
            mode,
            "-f",
            str(number),
            "-l",
            str(number),
            str(Path(SOURCES or "") / FILES[substance]),
            "-",
        ],
        capture_output=True,
        check=True,
    )
    return out.stdout.decode("utf-8", "replace")


@needs_sources
def test_a3_source_files_have_the_hashes_listed_in_sources_md() -> None:
    sources = (KB / "SOURCES.md").read_text(encoding="utf-8")
    for name in FILES.values():
        digest = hashlib.sha256((Path(SOURCES or "") / name).read_bytes()).hexdigest()
        assert digest in sources, f"{name}: Hash {digest} nicht in SOURCES.md"


@needs_sources
def test_a3_every_original_term_stands_on_the_cited_page_with_a_second_extractor() -> None:
    missing: list[str] = []
    for row in ROWS:
        number = int(re.search(r"PDF S\. (\d+)$", row["section"]).group(1))  # type: ignore[union-attr]
        page = extract(row["substance_id"], number, "-layout") + extract(
            row["substance_id"], number, "-raw"
        )
        if norm(row["original_term"]) not in norm(page):
            missing.append(f"{row['substance_id']} S.{number}: {row['original_term']}")
    assert missing == [], missing[:10]
