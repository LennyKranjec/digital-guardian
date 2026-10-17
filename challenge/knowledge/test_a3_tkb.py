# ruff: noqa: E501
"""A3-Zweitleser und Gegenproben zu T-KB (Wissensbasis C61/C64).

1. **Zweitleser-Protokoll:** Häufigkeitsklassen ganzer Quellseiten, vom Zweitleser aus dem Seitenbild
   abgelesen (Lanbica S. 4, Votrient S. 15 und 16, Sutent S. 11) und gegen `ae_matrix.csv` verglichen.
2. **Struktur:** Pflichtfelder, erlaubte Werte, Quellen-Hosts, Wirkstoff-/Regime-Kennungen.
3. **Datenschutz:** `dataset_counts.yaml` nur Aggregate, Zellen < 5 unterdrückt.
"""

import csv
import re
import unicodedata
from pathlib import Path
from typing import Any

import pytest
import yaml

KB = Path(__file__).resolve().parent
ROWS = list(csv.DictReader((KB / "ae_matrix.csv").open(encoding="utf-8")))
FREQUENCIES = {"very common", "common", "uncommon", "rare", "very rare", "not known"}


def norm(text: str) -> str:
    return re.sub(r"[\s\-­]+", "", unicodedata.normalize("NFKC", text).lower())


def page_rows(substance: str, page: int) -> list[dict[str, str]]:
    return [
        r
        for r in ROWS
        if r["substance_id"] == substance and r["section"].endswith(f"PDF S. {page}")
    ]


def compare(
    substance: str, page: int, table: dict[str, str]
) -> tuple[list[Any], list[str], list[str]]:
    """(abweichende Klassen, Zeilen ohne Eintrag im Bild, Bildeinträge ohne Zeile)."""
    want = {norm(term): cls for cls, terms in table.items() for term in terms.split("|")}
    rows = page_rows(substance, page)
    wrong: list[Any] = []
    extra: list[str] = []
    seen: set[str] = set()
    for row in rows:
        term = norm(row["original_term"])
        key = next((k for k in want if k == term or k.startswith(term) or term.startswith(k)), None)
        if key is None:
            extra.append(row["original_term"])
            continue
        seen.add(key)
        if want[key] != row["frequency_class"]:
            wrong.append((row["original_term"], row["frequency_class"], want[key]))
    missing = sorted(k for k in want if k not in seen)
    return wrong, extra, missing


# --- 1. Zweitleser-Protokoll (aus dem Seitenbild abgelesen) -----------------------------------

LANBICA_4 = {
    "very common": "anémie|závrať|návaly horka|bolest břicha|zácpa|nauzea|hematurie|gynekomastie a pocit pnutí v prsu",
    "uncommon": "hypersenzitivita|angioedém|kopřivka|intersticiální plicní onemocnění",
    "common": "snížená chuť k jídlu|snížení libida|deprese|somnolence|infarkt myokardu|srdeční selhání|dyspepsie|flatulence|hepatotoxicita|žloutenka|hypertransaminázémie|alopecie|hirsutismus/obnovení růstu vlasů|suchá kůže|vyrážka",
    "rare": "jaterní selhání|fotosenzitivní reakce",
    "not known": "prodloužení qt intervalu",
}
VOTRIENT_15 = {
    "very common": "změna barvy vlasů|syndrom palmoplantární erytrodysestezie|alopecie|vyrážka|proteinurie|únava",
    "common": "hyperbilirubinemie|porucha jaterních funkcí|hepatotoxicita|hypopigmentace kůže|suchá kůže|pruritus|erytém|depigmentace kůže|hyperhidróza|artralgie|myalgie|svalové spasmy|zánět sliznic|astenie|otok|bolest na hrudi",
    "uncommon": "ikterus|poškození jater způsobené léky|jaterní selhání|poruchy nehtů|exfoliace kůže|fotosenzitivní reakce|erytematózní vyrážka|poruchy kůže|makulární vyrážka|svědící vyrážka|vezikulární vyrážka|generalizovaný pruritus|generalizovaná vyrážka|papulózní vyrážka|plantární erytém|muskuloskeletální bolest|krvácení do močových cest|menoragie|vaginální krvácení|metroragie|zimnice|onemocnění sliznice",
    "not known": "kožní vřed",
}
VOTRIENT_16 = {
    "very common": "zvýšení hladiny alt|zvýšení hladiny ast",
    "common": "snížení tělesné hmotnosti|zvýšení hladiny bilirubinu v krvi|zvýšení hladiny kreatininu v krvi|zvýšení lipázy|snížení počtu bílých krvinek|zvýšení tsh v krvi|zvýšení hladiny amylázy|zvýšení gmt|zvýšení krevního tlaku|zvýšení urey v krvi|abnormální výsledky vyšetření jaterních funkcí",
    "uncommon": "zvýšení hladin jaterních enzymů|pokles hladiny glukózy v krvi|prodloužení qt intervalu|zvýšení hladin aminotransferáz|abnormální výsledky vyšetření funkce štítné žlázy|zvýšení diastolického krevního tlaku|zvýšení systolického krevního tlaku",
}
SUTENT_11 = {
    "very common": "neutropenie|trombocytopenie|anemie|leukopenie|hypotyreóza|snížená chuť k jídlu|insomnie|závrať|bolest hlavy|poruchy chuti|hypertenze|dyspnoe|epistaxe|kašel",
    "common": "virové infekce|respirační infekce|absces|mykotické infekce|infekce močových cest|kožní infekce|sepse|lymfopenie|dehydratace|hypoglykemie|deprese|periferní neuropatie|parestézie|hypestézie|hyperestézie|periorbitální otok|otok očních víček|zvýšené slzení|ischemie myokardu|snížení ejekční frakce|hluboká žilní trombóza|návaly horka|zarudnutí|plicní embolie|pleurální efuze|hemoptýza|námahová dušnost|orofaryngeální bolest|překrvení nosní sliznice|sucho v nose",
    "uncommon": "nekrotizující fasciitida|bakteriální infekce|pancytopenie|hypersenzitivita|hypertyreóza|krvácení do mozku|cévní mozková příhoda|tranzitorní ischemická ataka|městnavé srdeční selhání|infarkt myokardu|srdeční selhání|kardiomyopatie|perikardiální efúze|prodloužený interval qt na elektrokardiogramu|nádorové krvácení|krvácení do plic|respirační selhání",
    "rare": "trombotická mikroangiopatie|angioedém|zánět štítné žlázy|syndrom lýzy tumoru|syndrom posteriorní reverzibilní encefalopatie|selhání levé komory|torsade de pointes",
    "not known": "hyperamonemická encefalopatie|aneurysmata a arteriální disekce",
}


@pytest.mark.parametrize(
    ("substance", "page", "table"),
    [
        ("BICALUTAMIDE", 4, LANBICA_4),
        ("PAZOPANIB", 16, VOTRIENT_16),
        ("SUNITINIB", 11, SUTENT_11),
    ],
)
def test_a3_second_reader_frequency_classes_match_the_page_image(
    substance: str, page: int, table: dict[str, str]
) -> None:
    wrong, extra, missing = compare(substance, page, table)
    assert wrong == [], wrong
    assert extra == [], extra
    assert missing == [], missing


def test_a3_second_reader_votrient_page_15_matches_and_the_ambiguous_row_is_unverified() -> None:
    """„Kožní vřed†“ (Block „Méně časté“, Zahlenspalten „není známo“) darf nicht als verified gelten."""
    wrong, extra, missing = compare("PAZOPANIB", 15, VOTRIENT_15)
    assert [w[0] for w in wrong] == ["Kožní vřed"]  # Blocketikett uncommon, Zahlen: nicht bekannt
    assert (extra, missing) == ([], [])
    row = next(r for r in page_rows("PAZOPANIB", 15) if r["original_term"] == "Kožní vřed")
    assert row["status"] == "unverified"
    assert not row["ctcae_v6_term"]
    todo = (KB / "CLINICAL_TODO.md").read_text(encoding="utf-8")
    assert "Kožní vřed" in todo


# --- 2. Struktur --------------------------------------------------------------------------------

HOSTS = {"www.ema.europa.eu", "prehledy.sukl.cz", "opendata.sukl.cz"}


def test_a3_matrix_rows_are_complete_and_consistent() -> None:
    assert len(ROWS) == 533
    keys = set()
    for row in ROWS:
        assert row["frequency_class"] in FREQUENCIES, row
        assert re.search(r"PDF S\. \d+$", row["section"]), row
        assert row["retrieved"] == "2026-10-17"
        assert re.match(r"https://([^/]+)/", row["document_url"]), row
        host = re.match(r"https://([^/]+)/", row["document_url"])
        assert host is not None
        assert host.group(1) in HOSTS, row["document_url"]
        assert row["original_term"].strip()
        assert row["document"].strip()
        assert row["extraction"].startswith(("llm:", "manual"))
        if row["status"] == "verified":
            assert row["ctcae_v6_term"], row  # verified nur mit CTCAE-Term (ANN-KB-03)
        else:
            assert row["status"] == "unverified"
            assert not row["ctcae_v6_term"], row
        key = (row["substance_id"], norm(row["original_term"]), row["section"])
        assert key not in keys, f"doppelte Zeile {key}"
        keys.add(key)


def test_a3_substances_and_regimens_reference_each_other() -> None:
    substances = yaml.safe_load((KB / "drugs" / "substances.yaml").read_text(encoding="utf-8"))
    items = substances.get("substances") or substances
    ids = {s["id"] for s in items}
    assert len(ids) == 30
    atc = re.compile(r"^[A-Z]\d{2}[A-Z]{2}\d{2}$")
    for substance in items:
        codes = substance.get("atc") or []
        for code in [codes] if isinstance(codes, str) else codes:
            assert atc.match(code), substance
    assert {r["substance_id"] for r in ROWS} <= ids
    for name in ("c61.yaml", "c64.yaml"):
        text = (KB / "regimens" / name).read_text(encoding="utf-8")
        mentioned = set(re.findall(r"\b[A-Z][A-Z0-9_]{4,}\b", text)) & ids
        assert mentioned, name


def test_a3_items_draft_invents_no_question_wording() -> None:
    draft = yaml.safe_load((KB / "items_draft.yaml").read_text(encoding="utf-8"))
    for item in draft["items"]:
        for key in ("text_cs", "text_de", "text_en"):
            assert item[key] == "TODO_OFFICIAL_WORDING", item["key"]
        assert item["label_de"] == "TODO"
        assert item["status"] in {"draft", "unverified"}


# --- 3. Datenschutz -----------------------------------------------------------------------------


def walk(node: Any, path: str = "") -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            out += walk(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            out += walk(value, f"{path}[{index}]")
    else:
        out.append((path, node))
    return out


def test_a3_dataset_counts_are_aggregates_with_small_cells_suppressed() -> None:
    counts = yaml.safe_load((KB / "dataset_counts.yaml").read_text(encoding="utf-8"))
    assert counts["k_suppression"] == 5
    small = [
        (p, v)
        for p, v in walk(counts)
        if isinstance(v, int)
        and not isinstance(v, bool)
        and 1 <= v <= 4
        and "k_suppression" not in p
    ]
    assert small == [], f"Zellen < 5 nicht unterdrückt: {small}"
    text = (KB / "dataset_counts.yaml").read_text(encoding="utf-8")
    assert not re.search(r"\bSYN-\d|\b\d{6}/\d{3,4}\b|@", text), (
        "Pseudonym/Kennung/Mail in den Zählungen"
    )


def test_a3_knowledge_files_contain_no_patient_identifiers() -> None:
    for path in KB.rglob("*"):
        if path.suffix in {".csv", ".yaml", ".md", ".txt", ".py"}:
            text = path.read_text(encoding="utf-8")
            assert not re.search(r"\b\d{6}/\d{3,4}\b", text), path.name  # Rodné číslo
