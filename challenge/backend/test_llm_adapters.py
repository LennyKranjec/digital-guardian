"""LLM-Adapter: Textbaustein, Cache, OpenAI-kompatibles Gateway (gemockt), Fallbacks, Schlüssel.

Kein Test nutzt das Netz: `conftest.py` ersetzt `adapters._urlopen` standardmäßig durch eine Sperre.
"""

import io
import json
import logging
import urllib.error
from email.message import Message
from pathlib import Path
from typing import Any

import pytest

from waechter.llm import adapters
from waechter.llm.adapters import (
    AdapterUnavailable,
    CachedAdapter,
    OpenAiAdapter,
    TemplateAdapter,
    generate,
    requested_mode,
    select_adapter,
    template_text,
)
from waechter.llm.facts import Fact, FactSet
from waechter.llm.verifier import verify

KEY = "sk-test-geheim-0815"
MODEL = "test-deployment"


def fact_set() -> FactSet:
    facts = [
        Fact("ther-1", "therapy", "Therapy: FOLFOX; cycle day 5."),
        Fact("visit-1", "visit", "Last visit: 2026-10-11."),
        Fact(
            "resp-1", "response", "Last response with values: 2026-10-17; days without response: 0."
        ),
        Fact(
            "alert-1",
            "alert",
            "Open alert (red), rule R-SEV-01: Nausea reached 3; created 2026-10-17.",
        ),
        *[
            Fact(f"obs-{i}", "observation", f"Symptom {i}, latest value: {i}.", role="latest")
            for i in range(1, 9)
        ],
        Fact("obs-100", "observation", "Symptom 1, first value: 1.", role="first"),
        Fact("assess-1", "assessment", "Clinician assessment 2026-10-17: Nausea grade 2."),
    ]
    return FactSet(facts=facts, lang="en", hash="h", unknown_topics=[])


class FakeResponse:
    def __init__(self, payload: Any, status: int = 200) -> None:
        self._raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        self.status = status

    def read(self) -> bytes:
        return self._raw

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None


class FakeGateway:
    """Ersetzt `urlopen`: protokolliert Anfragen, antwortet je Pfad aus einer Tabelle."""

    def __init__(self, routes: dict[str, Any]) -> None:
        self.routes = routes
        self.calls: list[dict[str, Any]] = []

    def __call__(self, request: Any, timeout: float) -> FakeResponse:
        path = request.full_url.split("/v1", 1)[-1]
        self.calls.append(
            {
                "path": path,
                "headers": {k.lower(): v for k, v in request.header_items()},
                "body": json.loads(request.data),
                "timeout": timeout,
            }
        )
        outcome = self.routes[path]
        if isinstance(outcome, BaseException):
            raise outcome
        return FakeResponse(outcome)


def http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        "https://gateway.invalid/v1/x",
        code,
        "x",
        Message(),
        io.BytesIO(b'{"error":"DeploymentNotFound"}'),
    )


@pytest.fixture
def openai_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(adapters.ENV_MODE, "openai")
    monkeypatch.setenv(adapters.ENV_BASE_URL, "https://gateway.invalid/v1")
    monkeypatch.setenv(adapters.ENV_API_KEY, KEY)
    monkeypatch.setenv(adapters.ENV_MODEL, MODEL)


def install(monkeypatch: pytest.MonkeyPatch, routes: dict[str, Any]) -> FakeGateway:
    gateway = FakeGateway(routes)
    monkeypatch.setattr(adapters, "_urlopen", gateway)
    return gateway


# --- Textbaustein ---------------------------------------------------------------------------


def test_template_text_is_deterministic_and_fully_verifiable() -> None:
    facts = fact_set()
    first, second = template_text(facts), template_text(facts)
    assert first == second
    result = verify(first, facts.mapping())
    assert result.dropped == 0
    assert len(result.sentences) >= 5
    assert all(sentence.refs for sentence in result.sentences)


def test_template_limits_observations_and_skips_first_and_highest_values() -> None:
    text = template_text(fact_set())
    assert "[obs-100]" not in text
    assert text.count("[obs-") == adapters.MAX_TEMPLATE_OBSERVATIONS


def test_template_is_the_default_and_reports_fallback_mode() -> None:
    assert requested_mode() == "template"
    result = generate(fact_set(), "prompt", "key")
    assert (result.mode, result.generator, result.model) == ("fallback", "template-v1", None)


def test_port_complete_builds_one_sentence_per_context_line() -> None:
    result = TemplateAdapter().complete("p", {"ther-1": "Therapy: A.", "visit-1": "Visit: B."})
    assert result.text == "Therapy: A [ther-1]. Visit: B [visit-1]."
    assert result.generator == "template-v1"
    assert result.source_fields == ("ther-1", "visit-1")


@pytest.mark.parametrize("value", ["", "bogus", "TEMPLATE", "azure", "anthropic"])
def test_unknown_modes_mean_template(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv(adapters.ENV_MODE, value)
    assert requested_mode() == "template"
    assert isinstance(select_adapter(), TemplateAdapter)


# --- Cache ----------------------------------------------------------------------------------


def test_cached_adapter_reads_the_recorded_answer(
    content_copy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(adapters.ENV_MODE, "cached")
    cache = content_copy / "llm_cache"
    cache.mkdir()
    (cache / "abc123.json").write_text(
        json.dumps({"text": "Therapy: FOLFOX [ther-1].", "model": "recorded-model"}),
        encoding="utf-8",
    )
    result = generate(fact_set(), "prompt", "abc123")
    assert (result.mode, result.generator, result.model) == (
        "cached",
        "cached:recorded-model",
        "recorded-model",
    )
    assert result.text == "Therapy: FOLFOX [ther-1]."


def test_missing_or_broken_cache_falls_back_to_the_template(
    content_copy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(adapters.ENV_MODE, "cached")
    assert generate(fact_set(), "p", "nothing").mode == "fallback"
    cache = content_copy / "llm_cache"
    cache.mkdir()
    (cache / "broken.json").write_text("{not json", encoding="utf-8")
    (cache / "empty.json").write_text("{}", encoding="utf-8")
    assert generate(fact_set(), "p", "broken").mode == "fallback"
    assert generate(fact_set(), "p", "empty").mode == "fallback"
    with pytest.raises(AdapterUnavailable):
        CachedAdapter(cache).generate(fact_set(), "p", "nothing")


# --- OpenAI-kompatibles Gateway (gemockt) ---------------------------------------------------


def test_openai_uses_the_responses_endpoint_with_api_key_header_only(
    openai_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    gateway = install(
        monkeypatch,
        {
            "/responses": {
                "output": [
                    {"content": [{"type": "output_text", "text": "Therapy: FOLFOX [ther-1]."}]}
                ]
            }
        },
    )
    result = generate(fact_set(), "the prompt", "key")
    assert (result.mode, result.generator, result.model) == ("live", f"openai:{MODEL}", MODEL)
    assert result.text == "Therapy: FOLFOX [ther-1]."
    (call,) = gateway.calls
    assert call["path"] == "/responses"
    assert call["body"] == {"model": MODEL, "input": "the prompt", "store": False}
    assert call["headers"]["api-key"] == KEY
    assert "authorization" not in call["headers"]
    assert not {"ocp-apim-subscription-key"} & set(call["headers"])
    assert 0 < call["timeout"] <= 20


def test_openai_accepts_output_text_shortcut(
    openai_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    install(monkeypatch, {"/responses": {"output_text": "Direct [ther-1]."}})
    assert generate(fact_set(), "p", "k").text == "Direct [ther-1]."


@pytest.mark.parametrize("code", [400, 404, 405, 501])
def test_openai_falls_back_to_chat_completions_when_responses_is_not_available(
    openai_env: None, monkeypatch: pytest.MonkeyPatch, code: int
) -> None:
    gateway = install(
        monkeypatch,
        {
            "/responses": http_error(code),
            "/chat/completions": {"choices": [{"message": {"content": "Chat [ther-1]."}}]},
        },
    )
    result = generate(fact_set(), "p", "k")
    assert (result.mode, result.text) == ("live", "Chat [ther-1].")
    assert [c["path"] for c in gateway.calls] == ["/responses", "/chat/completions"]
    chat = gateway.calls[1]
    assert chat["body"]["temperature"] == 0
    assert chat["body"]["messages"] == [{"role": "user", "content": "p"}]
    assert chat["headers"]["api-key"] == KEY


def test_openai_empty_responses_text_tries_chat_completions(
    openai_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    gateway = install(
        monkeypatch,
        {
            "/responses": {"output": []},
            "/chat/completions": {"choices": [{"message": {"content": "Chat [ther-1]."}}]},
        },
    )
    assert generate(fact_set(), "p", "k").mode == "live"
    assert len(gateway.calls) == 2


def test_deployment_not_found_on_both_endpoints_means_template(
    openai_env: None, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    install(monkeypatch, {"/responses": http_error(404), "/chat/completions": http_error(404)})
    caplog.set_level(logging.DEBUG)
    result = generate(fact_set(), "p", "k")
    assert (result.mode, result.generator) == ("fallback", "template-v1")
    assert result.text == template_text(fact_set())
    assert KEY not in caplog.text


@pytest.mark.parametrize(
    "failure",
    [
        TimeoutError(),
        urllib.error.URLError("unreachable"),
        ConnectionResetError(),
        http_error(401),
        http_error(429),
        http_error(500),
    ],
)
def test_network_and_server_failures_mean_template_without_second_attempt(
    openai_env: None, monkeypatch: pytest.MonkeyPatch, failure: BaseException
) -> None:
    gateway = install(
        monkeypatch,
        {"/responses": failure, "/chat/completions": {"choices": []}},
    )
    result = generate(fact_set(), "p", "k")
    assert result.mode == "fallback"
    assert [c["path"] for c in gateway.calls] == [
        "/responses"
    ]  # kein Zweitversuch bei Netz/401/5xx


@pytest.mark.parametrize("raw", [b"<html>", b"[]", b'"text"', b"{}"])
def test_garbage_answers_mean_template(
    openai_env: None, monkeypatch: pytest.MonkeyPatch, raw: bytes
) -> None:
    install(monkeypatch, {"/responses": raw, "/chat/completions": raw})
    assert generate(fact_set(), "p", "k").mode == "fallback"


def test_incomplete_openai_configuration_means_template(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(adapters.ENV_MODE, "openai")
    monkeypatch.setenv(adapters.ENV_API_KEY, KEY)  # Basis-URL und Modell fehlen
    assert generate(fact_set(), "p", "k").mode == "fallback"


def test_unsupported_url_scheme_is_rejected(
    openai_env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(adapters.ENV_BASE_URL, "file:///etc/passwd")
    gateway = install(monkeypatch, {})
    assert generate(fact_set(), "p", "k").mode == "fallback"
    assert gateway.calls == []


def test_the_key_never_appears_in_repr_logs_or_errors(
    openai_env: None, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    adapter = OpenAiAdapter("https://gateway.invalid/v1", KEY, MODEL, None)
    assert KEY not in repr(adapter)
    install(monkeypatch, {"/responses": http_error(401)})
    with pytest.raises(AdapterUnavailable) as caught:
        adapter.generate(fact_set(), "p", "k")
    assert KEY not in str(caught.value)
    generate(fact_set(), "p", "k")
    assert KEY not in caplog.text


# --- Aufzeichnung ---------------------------------------------------------------------------


def test_record_mode_writes_a_cache_file_that_the_cached_adapter_can_replay(
    openai_env: None, content_copy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(adapters.ENV_RECORD, "1")
    install(monkeypatch, {"/responses": {"output_text": "Recorded [ther-1]."}})
    assert generate(fact_set(), "prompt", "rec-key").mode == "live"
    target = content_copy / "llm_cache" / "rec-key.json"
    record = json.loads(target.read_text(encoding="utf-8"))
    assert record["text"] == "Recorded [ther-1]."
    assert record["model"] == MODEL
    assert KEY not in target.read_text(encoding="utf-8")  # nie der Schlüssel in der Cache-Datei
    monkeypatch.setenv(adapters.ENV_MODE, "cached")
    replay = generate(fact_set(), "prompt", "rec-key")
    assert (replay.mode, replay.text) == ("cached", "Recorded [ther-1].")


def test_without_record_flag_nothing_is_written(
    openai_env: None, content_copy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install(monkeypatch, {"/responses": {"output_text": "Live [ther-1]."}})
    generate(fact_set(), "p", "no-record")
    assert not (content_copy / "llm_cache").exists()


def test_tests_never_reach_the_network() -> None:
    with pytest.raises(AssertionError, match="network access"):
        adapters._urlopen("https://example.invalid", timeout=1)
