"""T-23: `options` am Attribut überschreibt die Standard-Antwortbeschriftung.

Beispiel: grammatische Form im offiziellen cs-Wortlaut (Žádná/Žádné/Žádný).
"""

from types import SimpleNamespace
from typing import Any

from waechter.services.fhir_export import _scale_label
from waechter.services.questionnaire import option_labels, options_for

STANDARD = [{"cs": "Žádná", "en": "None"}, {"cs": "Mírná", "en": "Mild"}]
NEUTER = [{"cs": "Žádné", "en": "None"}, {"cs": "Mírné", "en": "Mild"}]


def _content() -> Any:
    items = {
        "scale_labels": {
            "severity": STANDARD,
            "frequency": [{"cs": "Nikdy", "en": "Never"}, {"cs": "Občas", "en": "Sometimes"}],
        },
        "items": [
            {"symptom_key": "fatigue", "attributes": [{"attribute": "severity"}]},
            {
                "symptom_key": "vomiting",
                "attributes": [
                    {"attribute": "severity", "options": NEUTER},
                    {"attribute": "frequency"},
                ],
            },
        ],
    }
    return SimpleNamespace(items=items)


def test_item_options_override_the_standard_scale() -> None:
    content = _content()
    assert option_labels(content, "severity", "vomiting") == NEUTER
    assert option_labels(content, "severity", "fatigue") == STANDARD
    assert option_labels(content, "severity") == STANDARD  # ohne Symptom: Standard
    assert (
        option_labels(content, "frequency", "vomiting")
        == content.items["scale_labels"]["frequency"]
    )  # Attribut ohne options


def test_options_for_localizes_the_overridden_labels() -> None:
    content = _content()
    assert options_for(content, "severity", "cs", "vomiting") == [
        {"value": 0, "label": "Žádné"},
        {"value": 1, "label": "Mírné"},
    ]
    assert options_for(content, "severity", "en", "vomiting")[1] == {"value": 1, "label": "Mild"}
    assert options_for(content, "severity", "cs", "fatigue")[0] == {"value": 0, "label": "Žádná"}


def test_fhir_answer_label_uses_the_same_override() -> None:
    content = _content()
    assert _scale_label(content, "severity", 0, "cs", "vomiting") == "Žádné"
    assert _scale_label(content, "severity", 0, "cs", "fatigue") == "Žádná"
    assert _scale_label(content, "severity", 0, "cs") == "Žádná"
    assert (
        _scale_label(content, "severity", 9, "cs", "vomiting") == "9"
    )  # außerhalb der Skala unverändert
