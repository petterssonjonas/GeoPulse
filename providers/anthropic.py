"""Anthropic Claude provider."""
import json
import requests
from typing import Iterator, List, Dict
from providers import LLMProvider


class AnthropicProvider(LLMProvider):
    def __init__(self, model: str = "claude-sonnet-4-6", api_key: str = "",
                 temperature: float = 0.3):
        self.model = model
        self.api_key = api_key
        self.temperature = temperature
        self.base_url = "https://api.anthropic.com/v1"

    @property
    def _headers(self):
        return {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

    def _extract_system(self, messages):
        system = None
        filtered = []
        for m in messages:
            if m["role"] == "system":
                system = m["content"]
            else:
                filtered.append(m)
        return system, filtered

    def chat(self, messages: List[Dict], stream: bool = False) -> str:
        system, msgs = self._extract_system(messages)
        payload = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": msgs,
            "temperature": self.temperature,
        }
        if system:
            payload["system"] = system
        resp = requests.post(
            f"{self.base_url}/messages", headers=self._headers, json=payload, timeout=120,
        )
        resp.raise_for_status()
        data = resp.json()
        content = (data.get("content") or [{}])[0].get("text")
        return content if isinstance(content, str) else (str(content) if content else "")

    def stream_chat(self, messages: List[Dict]) -> Iterator[str]:
        system, msgs = self._extract_system(messages)
        payload = {
            "model": self.model,
            "max_tokens": 4096,
            "messages": msgs,
            "temperature": self.temperature,
            "stream": True,
        }
        if system:
            payload["system"] = system
        resp = requests.post(
            f"{self.base_url}/messages", headers=self._headers, json=payload,
            stream=True, timeout=120,
        )
        resp.raise_for_status()
        for line in resp.iter_lines():
            if line and line.startswith(b"data: "):
                try:
                    data = json.loads(line[6:])
                    if data.get("type") == "content_block_delta":
                        yield data.get("delta", {}).get("text", "")
                except (json.JSONDecodeError, KeyError):
                    continue
