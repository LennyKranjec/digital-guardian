"""A3-Gegenprüfung ctcae.yaml gegen NCI-Excel (Code, SOC, Term, Gradtexte, Definition) und CTCAE-PDF (Seite).

    python -X utf8 ctcae_check.py <ctcae.yaml> <ctcae-v6.0.xlsx> <CTCAEv6.pdf>      (Referenz-venv: openpyxl, pypdf, pyyaml)
Beides sind externe, nicht eingecheckte Dateien. Exit 1 bei Abweichung.
"""

import re
import sys

import openpyxl
import yaml
from pypdf import PdfReader


def squash(text: object) -> str:
    """Nur Buchstaben/Ziffern (PDF-Zeilenumbruch-Bindestriche sind von echten nicht unterscheidbar)."""
    return re.sub(r"[^0-9a-z<>=%/.,;()]", "", str(text or "").lower().replace(" ", " "))


def norm(text: object) -> str:
    s = str(text or "").replace("\xa0", " ").replace("\u2010", "-").replace("\u2011", "-").replace("\u2013", "-")
    s = re.sub(r"(\w)-\s+(\w)", r"\1\2", s)  # Silbentrennung im PDF
    return re.sub(r"\s+", " ", s).strip().lower()


ctcae = yaml.safe_load(open(sys.argv[1], encoding="utf-8"))
ws = openpyxl.load_workbook(sys.argv[2], read_only=True, data_only=True)["CTCAE v6.0 Clean Copy"]
rows = {}
for row in list(ws.iter_rows(values_only=True))[1:]:
    if row[0] is not None:
        rows[norm(row[2])] = row
pdf = PdfReader(sys.argv[3])
bad = checked = 0
for term in ctcae["terms"]:
    row = rows.get(norm(term["term_en"]))
    problems = []
    if row is None:
        problems.append("Begriff nicht in Excel")
    else:
        if str(row[0]).strip() != term["meddra_code"]:
            problems.append(f"MedDRA {term['meddra_code']} != Excel {row[0]}")
        if norm(row[1]) != norm(term["soc"]):
            problems.append("SOC weicht ab")
        for grade in "12345":
            excel = row[2 + int(grade)]
            has = str(excel or "").strip() not in {"", "-"}
            mine = term["grades"].get(grade)
            if has != (mine is not None) or (has and norm(excel) != norm(mine)):
                problems.append(f"Grad {grade} weicht von Excel ab")
        if str(row[8] or "").strip() not in {"", "-"} and norm(row[8]) != norm(term.get("definition_en")):
            problems.append("Definition weicht von Excel ab")
    pages = [int(n) for n in re.findall(r"S\.\s*(\d+)", term.get("locator", ""))]
    page_text = squash(" ".join(pdf.pages[p - 1].extract_text() for p in pages)) if pages else ""
    if not pages:
        problems.append("keine Seitenangabe")
    for grade, text in term["grades"].items():
        if squash(text) not in page_text:
            problems.append(f"Grad {grade}: Text nicht auf PDF-Seite {pages}")
    if term.get("definition_en") and squash(term["definition_en"]) not in page_text:
        problems.append(f"Definition nicht auf PDF-Seite {pages}")
    checked += 1
    bad += bool(problems)
    print(f"{term['id']:55s} {'OK' if not problems else 'ABWEICHUNG: ' + '; '.join(problems)}")
print(f"Begriffe: {checked}, mit Abweichung: {bad}")
sys.exit(1 if bad else 0)
