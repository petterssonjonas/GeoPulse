"""Ollama LLM provider."""
import json
import requests
from typing import Iterator, List, Dict
from providers import LLMProvider


class OllamaProvider(LLMProvider):
    def __init__(self, model: str, base_url: str = "http://localhost:11434",
                 temperature: float = 0.3):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature

    def chat(self, messages: List[Dict], stream: bool = False) -> str:
        resp = requests.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": self.temperature},
            },
            timeout=300,
        )
        resp.raise_for_status()
        content = resp.json().get("message", {}).get("content")
        return content if isinstance(content, str) else (str(content) if content else "")

    def stream_chat(self, messages: List[Dict]) -> Iterator[str]:
        resp = requests.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "messages": messages,
                "stream": True,
                "options": {"temperature": self.temperature},
            },
            stream=True,
            timeout=300,
        )
        resp.raise_for_status()
        for line in resp.iter_lines():
            if line:
                try:
                    data = json.loads(line)
                    if not data.get("done"):
                        yield data.get("message", {}).get("content", "")
                except json.JSONDecodeError:
                    continue
