"""OpenAI-compatible API provider."""
import json
import logging
import requests
from typing import Iterator, List, Dict
from providers import LLMProvider
from providers.codex import get_codex_cached_models

logger = logging.getLogger(__name__)

class OpenAIProvider(LLMProvider):
    def __init__(self, model: str, api_key: str,
                 base_url: str = "https://api.openai.com/v1",
                 temperature: float = 0.3):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature

    @property
    def _headers(self):
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _extract_models(self, payload: dict) -> List[str]:
        models = []
        source = payload.get("data") or payload.get("models") or []
        if isinstance(source, list):
            for item in source:
                if isinstance(item, dict):
                    model_id = item.get("id") or item.get("name")
                    if model_id:
                        models.append(model_id)
        if not models and isinstance(payload, dict):
            direct = payload.get("model")
            if isinstance(direct, str):
                models.append(direct)
        return models

    def list_models(self) -> List[str]:
        try:
            resp = requests.get(f"{self.base_url}/models", headers=self._headers, timeout=20)
            if resp.status_code == 401:
                models = get_codex_cached_models()
                if models:
                    return models
            resp.raise_for_status()
            return self._extract_models(resp.json() or {})
        except Exception as exc:
            logger.debug("OpenAI-compatible list_models failed: %s", exc)
        return get_codex_cached_models()

    def chat(self, messages: List[Dict], stream: bool = False) -> str:
        resp = requests.post(
            f"{self.base_url}/chat/completions",
            headers=self._headers,
            json={"model": self.model, "messages": messages, "temperature": self.temperature},
            timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content")
        return content if isinstance(content, str) else (str(content) if content else "")

    def stream_chat(self, messages: List[Dict]) -> Iterator[str]:
        resp = requests.post(
            f"{self.base_url}/chat/completions",
            headers=self._headers,
            json={"model": self.model, "messages": messages, "temperature": self.temperature, "stream": True},
            stream=True,
            timeout=120,
        )
        resp.raise_for_status()
        for line in resp.iter_lines():
            if line and line.startswith(b"data: "):
                data_str = line[6:]
                if data_str == b"[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                    delta = data["choices"][0]["delta"].get("content", "")
                    if delta:
                        yield delta
                except (json.JSONDecodeError, KeyError):
                    continue
