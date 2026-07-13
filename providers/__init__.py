"""LLM provider abstraction and factory."""
from typing import Iterator, List, Dict, Optional


class LLMProvider:
    def chat(self, messages: List[Dict], stream: bool = False) -> str:
        raise NotImplementedError

    def stream_chat(self, messages: List[Dict]) -> Iterator[str]:
        raise NotImplementedError

    def list_models(self) -> List[str]:
        return []


PROVIDER_OPTIONS = [
    ("ollama", "Ollama (local)"),
    ("openai", "OpenAI-compatible"),
    ("anthropic", "Anthropic"),
    ("llama_cpp", "llama.cpp"),
    ("custom", "Custom provider"),
]

CUSTOM_BACKENDS = [
    ("openai", "OpenAI-compatible"),
    ("anthropic", "Anthropic"),
]


def get_provider_options() -> List[str]:
    return [name for name, _ in PROVIDER_OPTIONS]


def get_provider_label(provider_id: str) -> str:
    for p_id, label in PROVIDER_OPTIONS:
        if p_id == provider_id:
            return label
    return provider_id


def resolve_custom_backend(config: dict) -> str:
    backend = config.get("custom_backend", "openai")
    if backend in {b for b, _ in CUSTOM_BACKENDS}:
        return backend
    return "openai"


def _resolve_openai_api_key(config: dict) -> str:
    api_key = config.get("api_key", "") or ""
    if api_key:
        return api_key
    try:
        from providers.codex import get_codex_access_token
        return get_codex_access_token()
    except Exception:
        return ""


def create_provider(config: Optional[dict] = None) -> LLMProvider:
    if config is None:
        from storage.config import Config
        config = Config.llm()

    from storage.config import (
        OLLAMA_DEFAULT_BASE_URL,
        OPENAI_DEFAULT_BASE_URL,
        ANTHROPIC_DEFAULT_BASE_URL,
        LLAMA_CPP_DEFAULT_BASE_URL,
    )

    provider = config.get("provider", "ollama")
    model = config.get("model", "qwen3:8b")
    api_key = _resolve_openai_api_key(config)
    base_url = config.get("base_url", OLLAMA_DEFAULT_BASE_URL) or OLLAMA_DEFAULT_BASE_URL
    temperature = config.get("temperature", 0.3)

    if provider == "ollama":
        from providers.ollama import OllamaProvider
        return OllamaProvider(model=model, base_url=base_url, temperature=temperature)

    if provider == "openai":
        from providers.openai_compat import OpenAIProvider
        return OpenAIProvider(
            model=model,
            api_key=api_key,
            base_url=config.get("base_url", OPENAI_DEFAULT_BASE_URL),
            temperature=temperature,
        )

    if provider == "anthropic":
        from providers.anthropic import AnthropicProvider
        return AnthropicProvider(
            model=model,
            api_key=api_key,
            base_url=config.get("base_url", ANTHROPIC_DEFAULT_BASE_URL),
            temperature=temperature,
        )

    if provider == "llama_cpp":
        from providers.openai_compat import OpenAIProvider
        return OpenAIProvider(
            model=model,
            api_key=api_key,
            base_url=config.get("base_url", LLAMA_CPP_DEFAULT_BASE_URL),
            temperature=temperature,
        )

    if provider == "custom":
        from providers.custom import CustomProvider
        return CustomProvider(
            model=model,
            api_key=api_key,
            base_url=config.get("base_url", OPENAI_DEFAULT_BASE_URL),
            backend=resolve_custom_backend(config),
            temperature=temperature,
        )

    raise ValueError(f"Unknown LLM provider: {provider}")
