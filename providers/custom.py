"""Custom provider that wraps OpenAI-compatible or Anthropic backends."""
from typing import Optional

from providers import LLMProvider, CUSTOM_BACKENDS
from providers.anthropic import AnthropicProvider
from providers.openai_compat import OpenAIProvider


class CustomProvider(LLMProvider):
    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str,
        backend: str,
        variant: Optional[str] = None,
        reasoning_effort: Optional[str] = None,
        temperature: float = 0.3,
    ):
        if backend not in {b for b, _ in CUSTOM_BACKENDS}:
            raise ValueError(f"Unsupported custom backend: {backend}")

        self.backend = backend
        self.model = model
        if backend == "openai":
            self._provider = OpenAIProvider(
                model=model,
                api_key=api_key,
                base_url=base_url,
                variant=variant,
                reasoning_effort=reasoning_effort,
                temperature=temperature,
                fallback_to_codex_cache=False,
            )
        else:
            self._provider = AnthropicProvider(
                model=model,
                api_key=api_key,
                base_url=base_url,
                temperature=temperature,
            )

    def chat(self, messages, stream: bool = False):
        return self._provider.chat(messages, stream=stream)

    def stream_chat(self, messages):
        return self._provider.stream_chat(messages)

    def list_models(self):
        # Anthropic does not expose listable models in 3rd-party contexts.
        if self.backend == "anthropic":
            return []
        return self._provider.list_models()
