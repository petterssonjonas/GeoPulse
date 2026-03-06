"""LLM provider abstraction with factory."""
from typing import Iterator, List, Dict


class LLMProvider:
    def chat(self, messages: List[Dict], stream: bool = False) -> str:
        raise NotImplementedError

    def stream_chat(self, messages: List[Dict]) -> Iterator[str]:
        raise NotImplementedError


def create_provider(config: dict = None) -> LLMProvider:
    if config is None:
        from storage.config import Config
        config = Config.llm()

    from storage.config import OLLAMA_DEFAULT_BASE_URL
    provider = config.get("provider", "ollama")
    model = config.get("model", "qwen3:8b")
    api_key = config.get("api_key", "")
    base_url = config.get("base_url", OLLAMA_DEFAULT_BASE_URL)
    temperature = config.get("temperature", 0.3)

    if provider == "ollama":
        from providers.ollama import OllamaProvider
        return OllamaProvider(model=model, base_url=base_url, temperature=temperature)
    elif provider == "openai":
        from providers.openai_compat import OpenAIProvider
        return OpenAIProvider(model=model, api_key=api_key, base_url=base_url, temperature=temperature)
    elif provider == "anthropic":
        from providers.anthropic import AnthropicProvider
        return AnthropicProvider(model=model, api_key=api_key, temperature=temperature)
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")
