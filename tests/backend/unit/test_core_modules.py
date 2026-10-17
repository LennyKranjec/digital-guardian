"""Kleine Kernbausteine: Konfigurations-Loader, Settings, Uhr, Ports und Mock-Adapter."""

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import Field

from app.adapters.memory_notifier import MemoryNotifier
from app.adapters.mock_llm import MockLlm
from app.core.clock import FrozenClock
from app.core.config_loader import ConfigError, load_yaml_model
from app.core.pydantic_base import StrictModel
from app.core.settings import Settings
from app.ports.llm import LlmPort
from app.ports.notifier import Notice, Notifier


class Sample(StrictModel):
    name: str = Field(min_length=1)
    limit: int


def test_config_loader_accepts_valid_file(tmp_path: Path) -> None:
    path = tmp_path / "ok.yaml"
    path.write_text("name: demo\nlimit: 3\n", encoding="utf-8")
    assert load_yaml_model(path, Sample) == Sample(name="demo", limit=3)


def test_config_loader_names_file_and_field_but_never_values(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("name: demo\nlimit: geheim-wert\nextra: 1\n", encoding="utf-8")
    with pytest.raises(ConfigError) as error:
        load_yaml_model(path, Sample)
    message = str(error.value)
    assert "bad.yaml" in message
    assert "limit" in message
    assert "extra" in message
    assert "geheim-wert" not in message


def test_config_loader_rejects_missing_and_broken_files(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="cannot be read"):
        load_yaml_model(tmp_path / "missing.yaml", Sample)
    broken = tmp_path / "broken.yaml"
    broken.write_text("a: [1, 2\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="invalid YAML"):
        load_yaml_model(broken, Sample)


def test_settings_validate_log_level_and_frozen_clock() -> None:
    assert Settings(_env_file=None, log_level="debug").log_level == "DEBUG"
    with pytest.raises(ValueError, match="LOG_LEVEL"):
        Settings(_env_file=None, log_level="loud")
    with pytest.raises(ValueError, match="production"):
        Settings(
            _env_file=None, app_env="production", app_frozen_now=datetime(2026, 1, 1, tzinfo=UTC)
        )
    with pytest.raises(ValueError, match="timezone"):
        Settings(_env_file=None, app_frozen_now=datetime(2026, 1, 1))


def test_frozen_clock_returns_the_fixed_instant() -> None:
    moment = datetime(2026, 10, 14, 8, 0, tzinfo=UTC)
    assert FrozenClock(moment).now() == moment


def test_mock_llm_is_deterministic_and_lists_its_sources() -> None:
    llm: LlmPort = MockLlm()
    first = llm.complete("Kurztext", {"b": "2", "a": "1"})
    assert first == llm.complete("Kurztext", {"a": "1", "b": "2"})
    assert first.source_fields == ("a", "b")
    assert first.text.startswith("[Entwurf] Kurztext")


def test_memory_notifier_collects_notices() -> None:
    notifier: Notifier = MemoryNotifier()
    now = datetime(2026, 10, 14, 8, 0, tzinfo=UTC)
    notifier.notify(Notice(subject_id=None, kind="demo", text="Hallo"), now)
    assert isinstance(notifier, MemoryNotifier)
    assert notifier.sent == [(now, Notice(None, "demo", "Hallo"))]
