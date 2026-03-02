"""OpenAI-compatible API provider."""
import json
import requests
from typing import Iterator, List, Dict
from providers import LLMProvider


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
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def chat(self, messages: List[Dict], stream: bool = False) -> str:
        resp = requests.post(
            f"{self.base_url}/chat/completions",
            headers=self._headers,
            json={"model": self.model, "messages": messages, "temperature": self.temperature},
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

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
