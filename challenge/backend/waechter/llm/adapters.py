"""LLM-Adapter der Kurzfassung hinter dem Plattform-Port `LlmPort` (Vertrag README §4, DR-008).

Wahl über die Umgebung `WAECHTER_LLM`:
- `template` (Standard): deterministischer Textbaustein aus den Fakten, Modus `fallback`, kein Netz.
- `cached`: aufgezeichnete Antwort aus `<Inhaltsordner>/llm_cache/<cache_key>.json` (Offline-Demo);
  fehlt sie, gilt `template`.
- `openai`: OpenAI-v1-kompatibles Gateway (`WAECHTER_LLM_BASE_URL`, `WAECHTER_LLM_API_KEY`,
  `WAECHTER_LLM_MODEL`), nur Standardbibliothek, Header ausschließlich `api-key`, Timeout 20 s
  gesamt. `POST {base}/responses` `{model, input, store: false}`, Rückfall
  `POST {base}/chat/completions`.
  Jeder Fehler (HTTP, Zeitüberschreitung, Netz, ungültige Antwort) führt zu `template`.
  `WAECHTER_LLM_RECORD=1` schreibt eine erfolgreiche Live-Antwort zusätzlich als Cache-Datei.

Der Schlüssel steht nur in der Umgebung, wird nie geloggt und taucht in keiner Fehlermeldung auf.
Die Adapter bestimmen nie eine Ampel, Stufe oder einen Grad; sie liefern nur Textentwürfe.
"""

import json
import logging
import os
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal, Protocol

from app.ports.llm import LlmResult
from waechter.content import content_dir
from waechter.llm.facts import Fact, FactSet

logger = logging.getLogger("waechter.llm")

ENV_MODE: Final = "WAECHTER_LLM"
ENV_BASE_URL: Final = "WAECHTER_LLM_BASE_URL"
ENV_API_KEY: Final = "WAECHTER_LLM_API_KEY"
ENV_MODEL: Final = "WAECHTER_LLM_MODEL"
ENV_RECORD: Final = "WAECHTER_LLM_RECORD"
TEMPLATE_GENERATOR: Final = "template-v1"
TIMEOUT_SECONDS: Final = 20.0
MAX_TEMPLATE_OBSERVATIONS: Final = 6
Mode = Literal["live", "cached", "fallback"]

#: Indirektion, damit Tests das Netz ersetzen können (in Tests wird nie ein Netz benutzt)
_urlopen = urllib.request.urlopen


class AdapterUnavailable(RuntimeError):
    """Der Adapter kann keinen Entwurf liefern (nicht konfiguriert, Fehler, Zeitüberschreitung)."""


@dataclass(frozen=True)
class Generated:
    text: str
    generator: str
    model: str | None
    mode: Mode


class Adapter(Protocol):
    """Port-kompatibel (`LlmPort.complete`) plus Fakten-Zugang für Aufzeichnung und Auswahl."""

    mode: Mode
    model: str | None

    def generate(self, facts: FactSet, prompt: str, cache_key: str) -> LlmResult: ...


def _sentence(fact: Fact) -> str:
    return f"{fact.text.rstrip('.')} [{fact.id}]."


def template_text(facts: FactSet) -> str:
    """Deterministischer Textbaustein: ein Satz je ausgewähltem Fakt, jeder mit Beleg."""
    chosen: list[Fact] = []
    observations = 0
    for fact in facts.facts:
        if fact.kind == "free_text":
            if fact.role != "relevant":  # nur Freitexte mit Vorschlag oder Warnwort
                continue
        elif fact.kind == "observation":
            if fact.role != "latest" or observations >= MAX_TEMPLATE_OBSERVATIONS:
                continue
            observations += 1
        chosen.append(fact)
    return " ".join(_sentence(f) for f in chosen)


class TemplateAdapter:
    mode: Mode = "fallback"
    model: str | None = None

    def generate(self, facts: FactSet, prompt: str, cache_key: str) -> LlmResult:
        return LlmResult(
            text=template_text(facts),
            generator=TEMPLATE_GENERATOR,
            source_fields=tuple(f.id for f in facts.facts),
        )

    def complete(self, prompt: str, context: Mapping[str, str]) -> LlmResult:
        """`LlmPort`: ein Satz je Kontextzeile (Schlüssel = Fakt-ID)."""
        text = " ".join(f"{value.rstrip('.')} [{key}]." for key, value in context.items())
        return LlmResult(text=text, generator=TEMPLATE_GENERATOR, source_fields=tuple(context))


class CachedAdapter:
    mode: Mode = "cached"

    def __init__(self, directory: Path) -> None:
        self._directory = directory
        self.model: str | None = None

    def generate(self, facts: FactSet, prompt: str, cache_key: str) -> LlmResult:
        path = self._directory / f"{cache_key}.json"
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            text = str(record["text"])
            self.model = str(record.get("model") or "recorded")
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise AdapterUnavailable("no cached answer") from error
        return LlmResult(
            text=text,
            generator=f"cached:{self.model}",
            source_fields=tuple(f.id for f in facts.facts),
        )

    def complete(self, prompt: str, context: Mapping[str, str]) -> LlmResult:
        raise AdapterUnavailable("cached adapter needs a cache key")


def _extract_responses_text(data: Mapping[str, Any]) -> str:
    direct = data.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct
    parts: list[str] = []
    for item in data.get("output") or []:
        for content in (item.get("content") or []) if isinstance(item, dict) else []:
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                parts.append(content["text"])
    return "\n".join(parts)


def _extract_chat_text(data: Mapping[str, Any]) -> str:
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return ""
    return content if isinstance(content, str) else ""


class OpenAiAdapter:
    mode: Mode = "live"

    def __init__(self, base_url: str, api_key: str, model: str, record_to: Path | None) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.model: str | None = model
        self._record_to = record_to

    def __repr__(self) -> str:  # nie den Schlüssel preisgeben
        return f"OpenAiAdapter(model={self.model!r})"

    def _post(self, path: str, payload: Mapping[str, Any], deadline: float) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        if not url.startswith(("https://", "http://")):
            raise AdapterUnavailable("unsupported url scheme")
        request = urllib.request.Request(  # noqa: S310 - Schema oben geprüft, URL aus Admin-Konfiguration
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"api-key": self._api_key, "Content-Type": "application/json"},
            method="POST",
        )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AdapterUnavailable("timeout")
        try:
            with _urlopen(request, timeout=remaining) as response:
                raw = response.read()
        except urllib.error.HTTPError as error:
            raise AdapterUnavailable(f"http {error.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise AdapterUnavailable(type(error).__name__) from None
        try:
            data = json.loads(raw)
        except ValueError:
            raise AdapterUnavailable("invalid json") from None
        if not isinstance(data, dict):
            raise AdapterUnavailable("invalid json")
        return data

    def _call(self, prompt: str) -> str:
        deadline = time.monotonic() + TIMEOUT_SECONDS
        model = self.model or ""
        try:
            data = self._post(
                "/responses", {"model": model, "input": prompt, "store": False}, deadline
            )
            text = _extract_responses_text(data)
            if text.strip():
                return text
        except AdapterUnavailable as error:
            if str(error) not in {"http 400", "http 404", "http 405", "http 501"}:
                raise
        data = self._post(
            "/chat/completions",
            {"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0},
            deadline,
        )
        text = _extract_chat_text(data)
        if not text.strip():
            raise AdapterUnavailable("empty answer")
        return text

    def generate(self, facts: FactSet, prompt: str, cache_key: str) -> LlmResult:
        text = self._call(prompt)
        if self._record_to is not None:
            self._record(cache_key, facts, text)
        return LlmResult(
            text=text,
            generator=f"openai:{self.model}",
            source_fields=tuple(f.id for f in facts.facts),
        )

    def complete(self, prompt: str, context: Mapping[str, str]) -> LlmResult:
        return LlmResult(
            text=self._call(prompt),
            generator=f"openai:{self.model}",
            source_fields=tuple(context),
        )

    def _record(self, cache_key: str, facts: FactSet, text: str) -> None:
        """Offline-Demo: Live-Antwort ablegen (ohne Schlüssel, nur synthetische Fakten)."""
        if self._record_to is None:
            return
        try:
            self._record_to.mkdir(parents=True, exist_ok=True)
            target = self._record_to / f"{cache_key}.json"
            record = {
                "text": text,
                "model": self.model,
                "facts_hash": facts.hash,
                "lang": facts.lang,
            }
            temporary = target.with_suffix(".tmp")
            temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(target)
        except OSError:
            logger.warning("llm cache could not be written")


def requested_mode() -> str:
    """Konfigurierter Modus; unbekannte Werte gelten als `template`."""
    value = os.environ.get(ENV_MODE, "template").strip().lower()
    return value if value in {"template", "cached", "openai"} else "template"


def select_adapter() -> Adapter:
    mode = requested_mode()
    if mode == "cached":
        return CachedAdapter(content_dir() / "llm_cache")
    if mode == "openai":
        base = os.environ.get(ENV_BASE_URL, "").strip()
        key = os.environ.get(ENV_API_KEY, "").strip()
        model = os.environ.get(ENV_MODEL, "").strip()
        if not (base and key and model):
            raise AdapterUnavailable("openai adapter not configured")
        record = os.environ.get(ENV_RECORD, "").strip().lower() in {"1", "true", "yes"}
        return OpenAiAdapter(base, key, model, content_dir() / "llm_cache" if record else None)
    return TemplateAdapter()


def generate(facts: FactSet, prompt: str, cache_key: str) -> Generated:
    """Entwurf über den konfigurierten Adapter; jeder Fehler ⇒ Textbaustein (`fallback`)."""
    try:
        adapter = select_adapter()
        result = adapter.generate(facts, prompt, cache_key)
    except AdapterUnavailable as error:
        logger.warning("llm adapter unavailable (%s); using template", error)
        fallback = TemplateAdapter().generate(facts, prompt, cache_key)
        return Generated(fallback.text, fallback.generator, None, "fallback")
    return Generated(result.text, result.generator, adapter.model, adapter.mode)


def template_draft(facts: FactSet, prompt: str, cache_key: str) -> Generated:
    """Textbaustein als Entwurf (Rückfall, wenn ein Sprachmodell keinen belegten Satz lieferte)."""
    fallback = TemplateAdapter().generate(facts, prompt, cache_key)
    return Generated(fallback.text, fallback.generator, None, "fallback")
