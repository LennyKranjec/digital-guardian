"""Allow-Listen der Dokumentenpipeline: ICD-10-Präfixe, Arzneimittel (ATC/kód SÚKL), Laborwerte.

ICD-10 und Arzneimittel stammen aus den Inhaltsdateien (`diagnoses.yaml`, `medications.yaml`);
die Laborliste ist versioniert (`LABS_VERSION`) und **klinisch nicht freigegeben** (Platzhalter,
LOINC-Codes aus dem öffentlichen Standardwissen, nicht gegen eine lizenzierte Quelle geprüft).
Was hier nicht steht, kann nie ein Kandidat sein.
"""

import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Final

from waechter.content import Content

LABS_VERSION: Final = "labs-v1"
LOINC_SYSTEM: Final = "http://loinc.org"
UCUM_SYSTEM: Final = "http://unitsofmeasure.org"

ICD_CODE: Final = re.compile(r"[A-TV-Z]\d{2}(?:\.\d{1,2})?")
#: Wert und Einheit direkt hinter dem Namen eines Laborwerts (Extraktor und Prüfer teilen es)
LAB_TAIL: Final = r"[\s:=;,|\t]*(?P<value>\d+(?:[.,]\d+)?)[\s;,|\t]*(?P<unit>[^\s;,|\t]+)"


def norm_unit(unit: str) -> str:
    """Vergleichsform einer Einheit: klein, ohne Leerraum, µ ⇒ u, ohne führendes x (Mal-Zeichen)."""
    text = unit.strip().lower().replace("µ", "u").replace("μ", "u").replace(" ", "")
    text = text.replace("**", "^").replace("*", "^")
    return text.lstrip("x" + chr(0xD7))


@dataclass(frozen=True)
class LabTest:
    key: str
    loinc: str
    display: str
    aliases: tuple[str, ...]
    #: normierte Einheit ⇒ UCUM-Code
    units: dict[str, str]


_C9 = {"10^9/l": "10*9/L", "/nl": "/nL"}

LABS: Final[tuple[LabTest, ...]] = (
    LabTest(
        "hemoglobin",
        "718-7",
        "Hemoglobin",
        ("hemoglobin", "haemoglobin", "hemoglobín", "hämoglobin", "hgb", "hb"),
        {"g/l": "g/L", "g/dl": "g/dL"},
    ),
    LabTest(
        "platelets",
        "777-3",
        "Platelets",
        ("platelets", "thrombocytes", "trombocyty", "thrombozyten", "plt"),
        dict(_C9),
    ),
    LabTest(
        "leukocytes",
        "6690-2",
        "Leukocytes",
        ("leukocytes", "leucocytes", "leukocyty", "leukozyten", "wbc"),
        dict(_C9),
    ),
    LabTest(
        "neutrophils",
        "751-8",
        "Neutrophils",
        ("neutrophils", "neutrofily", "neutrophile", "anc"),
        dict(_C9),
    ),
    LabTest(
        "creatinine",
        "2160-0",
        "Creatinine",
        ("creatinine", "kreatinin"),
        {"umol/l": "umol/L", "mg/dl": "mg/dL"},
    ),
    LabTest(
        "alt",
        "1742-6",
        "Alanine aminotransferase",
        ("alt", "gpt", "alat"),
        {"u/l": "U/L", "ukat/l": "ukat/L"},
    ),
    LabTest(
        "ast",
        "1920-8",
        "Aspartate aminotransferase",
        ("ast", "got", "asat"),
        {"u/l": "U/L", "ukat/l": "ukat/L"},
    ),
    LabTest(
        "bilirubin",
        "1975-2",
        "Bilirubin total",
        ("bilirubin",),
        {"umol/l": "umol/L", "mg/dl": "mg/dL"},
    ),
    LabTest(
        "crp",
        "1988-5",
        "C-reactive protein",
        ("crp",),
        {"mg/l": "mg/L", "mg/dl": "mg/dL"},
    ),
    LabTest(
        "potassium", "2823-3", "Potassium", ("potassium", "kalium", "draslík"), {"mmol/l": "mmol/L"}
    ),
    LabTest("sodium", "2951-2", "Sodium", ("sodium", "natrium", "sodík"), {"mmol/l": "mmol/L"}),
    LabTest(
        "glucose",
        "2345-7",
        "Glucose",
        ("glucose", "glukose", "glukóza", "glykémie"),
        {"mmol/l": "mmol/L", "mg/dl": "mg/dL"},
    ),
)


@lru_cache(maxsize=64)
def _lab_regex(aliases: tuple[str, ...]) -> re.Pattern[str]:
    names = "|".join(re.escape(a) for a in sorted(aliases, key=len, reverse=True))
    return re.compile(rf"(?<!\w)(?:{names})(?!\w){LAB_TAIL}", re.IGNORECASE)


def lab_pattern(lab: LabTest) -> re.Pattern[str]:
    """Muster „<Name> <Wert> <Einheit>“ eines Laborwerts (Gruppen `value`, `unit`)."""
    return _lab_regex(lab.aliases)


@dataclass(frozen=True)
class Medication:
    medication_id: str
    atc: str
    sukl_code: str | None
    display: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class AllowLists:
    icd_prefixes: frozenset[str]
    medications: tuple[Medication, ...]
    labs: tuple[LabTest, ...] = LABS

    def medication_by_code(self, code: str) -> Medication | None:
        wanted = code.strip().upper()
        return next(
            (m for m in self.medications if m.atc.upper() == wanted or m.sukl_code == wanted), None
        )

    def lab_by_loinc(self, code: str) -> LabTest | None:
        return next((lab for lab in self.labs if lab.loinc == code.strip()), None)

    def icd_allowed(self, code: str) -> bool:
        return bool(ICD_CODE.fullmatch(code)) and code[:3] in self.icd_prefixes


def from_content(content: Content) -> AllowLists:
    """Allow-Listen aus dem geladenen Inhalt; fehlende Dateien ⇒ leere Liste (nichts erlaubt)."""
    prefixes: set[str] = set()
    if content.diagnoses is not None:
        for group in content.diagnoses.get("diagnoses", []):
            prefixes.update(str(p) for p in group.get("icd10_prefixes", []))
    medications: list[Medication] = []
    if content.medications is not None:
        for entry in content.medications.get("medications", []):
            atc = entry.get("atc")
            if not atc:
                continue
            names: list[str] = []
            inn = entry.get("inn") or {}
            names.extend(str(v) for v in inn.values())
            if entry.get("trade_name"):
                names.append(str(entry["trade_name"]))
            names.extend(str(s) for s in entry.get("synonyms", []))
            medications.append(
                Medication(
                    medication_id=str(entry["id"]),
                    atc=str(atc),
                    sukl_code=str(entry["sukl_code"]) if entry.get("sukl_code") else None,
                    display=str(inn.get("en") or inn.get("cs") or entry.get("trade_name") or atc),
                    aliases=tuple(dict.fromkeys(n for n in names if len(n) >= 4)),
                )
            )
    return AllowLists(frozenset(prefixes), tuple(medications))
