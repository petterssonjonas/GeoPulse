"""Codex auth helpers used for model discovery and token-based OpenAI-compatible calls."""
import json
import logging
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

CODEX_AUTH_PATH = Path.home() / ".codex" / "auth.json"
CODEX_MODELS_CACHE = Path.home() / ".codex" / "models_cache.json"


def get_codex_access_token(auth_path: Path = CODEX_AUTH_PATH) -> str:
    """Return the Codex access token if present."""
    try:
        with open(auth_path, encoding="utf-8") as f:
            data = json.load(f)
        token = data.get("tokens", {}).get("access_token")
        if isinstance(token, str) and token:
            return token
    except FileNotFoundError:
        return ""
    except Exception as exc:
        logger.debug("Failed reading Codex auth.json: %s", exc)
    return ""


def get_codex_cached_models(cache_path: Optional[Path] = None) -> List[str]:
    """Return cached model slugs from Codex.

    We use this as a local discovery fallback to avoid blocking first-run UX when the
    API key is available but endpoint access is unreliable.
    """
    cache_file = cache_path or CODEX_MODELS_CACHE
    try:
        with open(cache_file, encoding="utf-8") as f:
            data = json.load(f)
        models = []
        for model in data.get("models", []) if isinstance(data, dict) else []:
            slug = model.get("slug")
            if not isinstance(slug, str) or not slug:
                continue
            if model.get("supported_in_api", True) is False:
                continue
            models.append(slug)
        return models
    except FileNotFoundError:
        return []
    except Exception as exc:
        logger.debug("Failed reading Codex models_cache.json: %s", exc)
    return []
