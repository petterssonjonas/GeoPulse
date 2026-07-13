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
    ("local", "Local"),
    ("custom_api", "Custom API"),
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


def _provider_is_local_backend(provider: str) -> bool:
    return provider in {"ollama", "llama_cpp", "lm_studio"}


def _resolve_openai_api_key(config: dict) -> str:
    api_key = config.get("api_key", "") or ""
    if api_key:
        return api_key
    return ""


def _resolve_codex_access_token() -> str:
    try:
        from providers.codex import get_codex_access_token
        return get_codex_access_token()
    except Exception:
        return ""


def _resolve_optional_provider_field(config: dict, *keys: str) -> str:
    for key in keys:
        value = config.get(key, "")
        if isinstance(value, str):
            value = value.strip()
            if value:
                return value
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
        LM_STUDIO_DEFAULT_BASE_URL,
    )

    provider = config.get("provider", "local")
    if provider == "local":
        provider = config.get("local_backend", "ollama")
        if not _provider_is_local_backend(provider):
            provider = "ollama"

    if provider == "custom_api":
        provider = "custom"
    model = config.get("model", "qwen3:8b")
    api_key = _resolve_openai_api_key(config)
    local_base_url = config.get("local_base_url", OLLAMA_DEFAULT_BASE_URL) or OLLAMA_DEFAULT_BASE_URL
    custom_api_base_url = config.get("custom_base_url", OPENAI_DEFAULT_BASE_URL) or OPENAI_DEFAULT_BASE_URL
    local_api_key = config.get("local_api_key", "") or ""
    custom_api_key = config.get("custom_api_key", "") or ""
    temperature = config.get("temperature", 0.3)
    variant = _resolve_optional_provider_field(config, "variant", "model_variant")
    reasoning_effort = _resolve_optional_provider_field(config, "reasoningEffort", "reasoning_effort")

    if provider == "ollama":
        base_url = local_base_url
        api_key = local_api_key
    elif provider == "llama_cpp":
        if not local_base_url:
            local_base_url = config.get("base_url", LLAMA_CPP_DEFAULT_BASE_URL) or LLAMA_CPP_DEFAULT_BASE_URL
        base_url = local_base_url
        api_key = local_api_key
    elif provider == "lm_studio":
        if not local_base_url:
            local_base_url = config.get("base_url", LM_STUDIO_DEFAULT_BASE_URL) or LM_STUDIO_DEFAULT_BASE_URL
        base_url = local_base_url
        api_key = local_api_key
    elif provider == "openai":
        base_url = config.get("base_url", OPENAI_DEFAULT_BASE_URL)
    elif provider == "anthropic":
        base_url = config.get("base_url", ANTHROPIC_DEFAULT_BASE_URL)
    elif provider == "custom":
        api_key = custom_api_key
        base_url = custom_api_base_url
    elif provider == "codex":
        api_key = _resolve_codex_access_token() or api_key
        base_url = config.get("base_url", OPENAI_DEFAULT_BASE_URL)

    if provider == "ollama":
        from providers.ollama import OllamaProvider
        return OllamaProvider(model=model, base_url=base_url, temperature=temperature)

    if provider == "openai":
        from providers.openai_compat import OpenAIProvider
        return OpenAIProvider(
            model=model,
            api_key=api_key,
            base_url=base_url,
            variant=variant,
            reasoning_effort=reasoning_effort,
            temperature=temperature,
            fallback_to_codex_cache=False,
        )

    if provider == "anthropic":
        from providers.anthropic import AnthropicProvider
        return AnthropicProvider(
            model=model,
            api_key=api_key,
            base_url=base_url,
            temperature=temperature,
        )

    if provider == "llama_cpp":
        from providers.openai_compat import OpenAIProvider
        return OpenAIProvider(
            model=model,
            api_key=api_key,
            base_url=base_url,
            variant=variant,
            reasoning_effort=reasoning_effort,
            temperature=temperature,
            fallback_to_codex_cache=False,
        )

    if provider == "lm_studio":
        from providers.openai_compat import OpenAIProvider
        return OpenAIProvider(
            model=model,
            api_key=api_key,
            base_url=base_url,
            variant=variant,
            reasoning_effort=reasoning_effort,
            temperature=temperature,
            fallback_to_codex_cache=False,
        )

    if provider == "codex":
        if not reasoning_effort:
            from providers.codex import get_codex_model_reasoning_level

            default_reasoning = get_codex_model_reasoning_level(model)
            if default_reasoning:
                reasoning_effort = default_reasoning
        from providers.openai_compat import OpenAIProvider
        return OpenAIProvider(
            model=model,
            api_key=api_key,
            base_url=base_url,
            variant=variant,
            reasoning_effort=reasoning_effort,
            temperature=temperature,
            fallback_to_codex_cache=False,
        )

    if provider == "custom":
        from providers.custom import CustomProvider
        return CustomProvider(
            model=model,
            api_key=api_key,
            base_url=base_url,
            backend=resolve_custom_backend(config),
            variant=variant,
            reasoning_effort=reasoning_effort,
            temperature=temperature,
        )

    raise ValueError(f"Unknown LLM provider: {provider}")
