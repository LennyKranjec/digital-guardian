"""`MockLlm`: deterministischer Mock des `LlmPort` (kein Netz), gibt Prompt und Kontext zurück."""

from collections.abc import Mapping

from app.ports.llm import LlmResult


class MockLlm:
    generator = "mock-llm-v1"

    def complete(self, prompt: str, context: Mapping[str, str]) -> LlmResult:
        names = tuple(sorted(context))
        lines = [f"{name}: {context[name]}" for name in names]
        return LlmResult(
            text="\n".join([f"[Entwurf] {prompt}", *lines]),
            generator=self.generator,
            source_fields=names,
        )
