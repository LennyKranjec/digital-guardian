"""T-27a (Owner A1): jede lokalisierte Beschriftung/jeder lokalisierte Text in items/ctcae/diagnoses/regimens/medications hat cs, en UND de (nicht leer).

Hintergrund: ohne `de` fiel das Backend auf Englisch zurück (Meldung des Menschen: unübersetzte Texte im Frontend). Geprüft wird Vollständigkeit,
nicht sprachliche Güte; nicht muttersprachlich geprüfte Übersetzungen sind in SOURCES.md §12 gekennzeichnet.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

CONTENT = Path(__file__).resolve().parent
FILES = ("items", "ctcae", "diagnoses", "regimens", "medications")


def _localized(node: Any, path: str = ""):
    """Alle Mappings mit `cs` und `en` (= LocalizedText) samt Pfad."""
    if isinstance(node, dict):
        if "cs" in node and "en" in node:
            yield path, node
        for key, value in node.items():
            yield from _localized(value, f"{path}/{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _localized(value, f"{path}[{index}]")


@pytest.mark.parametrize("name", FILES)
def test_every_localized_text_has_cs_en_de(name: str) -> None:
    data = yaml.safe_load((CONTENT / f"{name}.yaml").read_text(encoding="utf-8"))
    found = list(_localized(data))
    assert found, f"{name}.yaml enthält keine lokalisierten Texte?"
    for path, text in found:
        for lang in ("cs", "en", "de"):
            value = text.get(lang)
            assert isinstance(value, str) and value.strip(), (
                f"{name}.yaml{path}: `{lang}` fehlt oder ist leer"
            )
        assert set(text) == {"cs", "en", "de"}, (
            f"{name}.yaml{path}: unerwartete Sprachschlüssel {sorted(text)}"
        )


def test_german_is_not_a_copy_of_the_english_text_where_it_matters() -> None:
    """Fragen, Skalen und Watch-Notes dürfen nicht unübersetzt (gleich englisch) bleiben; Eigennamen (INN, Regime) sind ausgenommen."""
    items = yaml.safe_load((CONTENT / "items.yaml").read_text(encoding="utf-8"))
    for path, text in _localized(items):
        assert text["de"] != text["en"], f"items.yaml{path}: de == en"
    regimens = yaml.safe_load((CONTENT / "regimens.yaml").read_text(encoding="utf-8"))
    for regimen in regimens["regimens"]:
        for note in regimen.get("watch_notes", []):
            assert note["text"]["de"] != note["text"]["en"], (regimen["id"], note["symptom_key"])


def test_sources_md_marks_the_german_texts() -> None:
    text = (CONTENT / "SOURCES.md").read_text(encoding="utf-8")
    assert "## 12. T-27a" in text
    for needle in (
        "de: eigene Übersetzung, nicht offiziell",
        "pro-ctcae_german.pdf",
        "nicht muttersprachlich geprüft",
    ):
        assert needle in text, needle
