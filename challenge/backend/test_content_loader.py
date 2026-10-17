"""Inhaltslader: gültige Fixture ok; Verstöße nennen Datei und Feldpfad, nie Werte."""

from pathlib import Path
from typing import Any

import pytest
import yaml

from waechter import schema_check
from waechter.constants import CONTENT_DIR_ENV
from waechter.content import ContentError, content_dir, get_content, load_content


def _edit(directory: Path, filename: str, change: Any) -> None:
    path = directory / filename
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    change(data)
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


def _issues(directory: Path) -> list[str]:
    with pytest.raises(ContentError) as caught:
        load_content(directory)
    return [str(issue) for issue in caught.value.issues]


def test_valid_fixture_loads(fixture_content: Path) -> None:
    content = load_content(fixture_content)
    assert content.items["version"] == "items-v1"
    assert content.scenario["anchor"] == "2026-10-17T09:00:00+02:00"  # bleibt Zeichenkette
    assert {p["pseudonym"] for p in content.scenario["patients"]} >= {"SYN-0001"}


def test_missing_required_field_names_file_and_path(content_copy: Path) -> None:
    _edit(content_copy, "rules.yaml", lambda d: d["rules"][0].pop("rationale"))
    assert _issues(content_copy) == [
        "rules.yaml: $.rules[0].rationale: required field is missing",
    ]


def test_wrong_enum_names_file_and_path_but_not_the_value(content_copy: Path) -> None:
    _edit(content_copy, "rules.yaml", lambda d: d["rules"][0].update(level="PURPLE-SECRET"))
    issues = _issues(content_copy)
    assert issues == ["rules.yaml: $.rules[0].level: not one of the allowed values"]
    assert "PURPLE-SECRET" not in issues[0]


def test_additional_field_is_rejected(content_copy: Path) -> None:
    _edit(content_copy, "report.yaml", lambda d: d.update(surprise=1))
    assert _issues(content_copy) == ["report.yaml: $.surprise: additional field is not allowed"]


def test_wrong_type_pattern_and_range(content_copy: Path) -> None:
    def change(data: dict[str, Any]) -> None:
        data["patients"][0]["birth_year"] = "1970"
        data["patients"][0]["pseudonym"] = "nope"
        data["patients"][0]["responses"][0]["answers"]["nausea.severity"] = 9

    _edit(content_copy, "scenario.yaml", change)
    assert sorted(_issues(content_copy)) == sorted(
        [
            "scenario.yaml: $.patients[0].birth_year: wrong type, expected integer",
            "scenario.yaml: $.patients[0].pseudonym: does not match the required pattern",
            "scenario.yaml: $.patients[0].responses[0].answers.nausea.severity: above the maximum",
        ]
    )


def test_missing_file_and_invalid_yaml(content_copy: Path) -> None:
    (content_copy / "ctcae.yaml").unlink()
    (content_copy / "report.yaml").write_text("sections: [unclosed\n", encoding="utf-8")
    issues = _issues(content_copy)
    assert "ctcae.yaml: $: file is missing" in issues
    assert any(i.startswith("report.yaml: line ") and i.endswith("invalid YAML") for i in issues)


def test_cross_references_are_checked(content_copy: Path) -> None:
    _edit(
        content_copy,
        "scenario.yaml",
        lambda d: d["patients"][0].update(regimen_id="NO-SUCH"),
    )
    _edit(content_copy, "items.yaml", lambda d: d["items"][0].update(ctcae_terms=["CTCAE-NOPE"]))
    assert sorted(_issues(content_copy)) == [
        "items.yaml: $.items[0].ctcae_terms[0]: unknown CTCAE id",
        "scenario.yaml: $.patients[0].regimen_id: unknown regimen id",
    ]


def test_missing_directory_is_not_an_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(CONTENT_DIR_ENV, str(tmp_path / "does-not-exist"))
    assert get_content() is None


def test_default_content_dir_is_challenge_content(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(CONTENT_DIR_ENV)
    assert content_dir().parts[-2:] == ("challenge", "content")


def test_get_content_reloads_after_change(content_copy: Path) -> None:
    first = get_content()
    assert first is not None
    _edit(content_copy, "report.yaml", lambda d: d.update(since="days_14"))
    second = get_content()
    assert second is not None
    assert second.report["since"] == "days_14"


def test_schema_checker_core_keywords() -> None:
    schema: dict[str, Any] = {
        "type": "object",
        "required": ["a"],
        "properties": {"a": {"type": ["integer", "null"], "minimum": 0}, "b": {"const": True}},
        "additionalProperties": False,
    }
    root = schema
    assert schema_check.validate({"a": None, "b": True}, schema, root) == []
    assert schema_check.validate({"a": True}, schema, root)[0].message.startswith("wrong type")
    assert schema_check.validate({"a": -1, "c": 1}, schema, root)
    with pytest.raises(schema_check.UnsupportedSchema):
        schema_check.validate(1, {"oneOf": []}, root)
