"""Ollama process lifecycle management."""
import json
import logging
import shutil
import subprocess
import time
import requests

logger = logging.getLogger(__name__)

RECOMMENDED_MODELS = [
    {"name": "qwen3:8b",    "vram": "~5 GB",  "desc": "Best balance of speed and quality (GPU)"},
    {"name": "qwen3:4b",    "vram": "~3 GB",  "desc": "Fast triage and lighter analysis"},
    {"name": "gemma3:4b",   "vram": "~3 GB",  "desc": "Good multilingual, compact"},
    {"name": "llama3.2:3b", "vram": "~2 GB",  "desc": "Fastest, works well on CPU"},
    {"name": "mistral:7b",  "vram": "~5 GB",  "desc": "Strong analytical reasoning"},
    {"name": "phi4-mini",   "vram": "~2.5 GB","desc": "Small but capable"},
    {"name": "qwen3:14b",   "vram": "~9 GB",  "desc": "Highest quality analysis (needs VRAM)"},
]


class OllamaManager:
    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url.rstrip("/")
        self._process = None

    def is_installed(self) -> bool:
        return shutil.which("ollama") is not None

    def is_running(self) -> bool:
        try:
            r = requests.get(f"{self.base_url}/", timeout=3)
            return r.status_code == 200
        except Exception:
            return False

    def start(self) -> bool:
        if self.is_running():
            return True
        if not self.is_installed():
            logger.error("Ollama binary not found in PATH")
            return False
        try:
            self._process = subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            for _ in range(20):
                time.sleep(0.5)
                if self.is_running():
                    logger.info("Ollama started successfully")
                    return True
            logger.error("Ollama failed to start within 10 seconds")
            return False
        except Exception as e:
            logger.error(f"Failed to start Ollama: {e}")
            return False

    def stop(self):
        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None
            logger.info("Ollama stopped")

    def list_models(self) -> list:
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=5)
            r.raise_for_status()
            return [m["name"] for m in r.json().get("models", [])]
        except Exception:
            return []

    def get_running_models(self) -> list:
        """Return names of models currently loaded in memory (via /api/ps)."""
        try:
            r = requests.get(f"{self.base_url}/api/ps", timeout=5)
            r.raise_for_status()
            return [m["name"] for m in r.json().get("models", [])]
        except Exception:
            return []

    def is_model_available(self, model: str) -> bool:
        models = self.list_models()
        return any(model == m or model == m.split(":")[0] for m in models)

    def pull_model(self, model: str, progress_cb=None) -> bool:
        """Pull a model with optional progress callback: cb(status, completed, total)."""
        try:
            resp = requests.post(
                f"{self.base_url}/api/pull",
                json={"name": model, "stream": True},
                stream=True,
                timeout=1800,
            )
            resp.raise_for_status()
            for line in resp.iter_lines():
                if line:
                    data = json.loads(line)
                    status = data.get("status", "")
                    if progress_cb:
                        progress_cb(status, data.get("completed", 0), data.get("total", 0))
                    if "error" in data:
                        logger.error(f"Pull error: {data['error']}")
                        return False
            return True
        except Exception as e:
            logger.error(f"Pull failed: {e}")
            return False
