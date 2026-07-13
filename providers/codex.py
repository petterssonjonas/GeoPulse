"""Codex auth helpers used for model discovery and token-based OpenAI-compatible calls."""
import json
import logging
import shutil
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

CODEX_AUTH_PATH = Path.home() / ".codex" / "auth.json"
CODEX_MODELS_CACHE = Path.home() / ".codex" / "models_cache.json"
REASONING_LEVEL_FALLBACKS = ["none", "low", "medium", "high", "xhigh"]


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


def is_codex_cli_available(binary_name: str = "codex") -> bool:
    """Return True when the Codex CLI executable is available."""
    return bool(shutil.which(binary_name))


def is_codex_available(auth_path: Path = CODEX_AUTH_PATH) -> bool:
    """Return True when Codex CLI and a stored auth token are both present."""
    return bool(is_codex_cli_available() and get_codex_access_token(auth_path))


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


def get_codex_model_reasoning_level(model_slug: str, cache_path: Optional[Path] = None) -> str:
    """Return default reasoning level for a Codex model slug."""
    model_slug = (model_slug or "").strip()
    if not model_slug:
        return ""

    cache_file = cache_path or CODEX_MODELS_CACHE
    try:
        with open(cache_file, encoding="utf-8") as f:
            data = json.load(f)
        for model in data.get("models", []) if isinstance(data, dict) else []:
            if not isinstance(model, dict):
                continue
            slug = model.get("slug")
            if slug != model_slug:
                continue
            level = model.get("default_reasoning_level")
            if isinstance(level, str) and level:
                return level
    except FileNotFoundError:
        return ""
    except Exception as exc:
        logger.debug("Failed reading Codex model reason level: %s", exc)
    return ""


def get_codex_model_reasoning_levels(model_slug: str, cache_path: Optional[Path] = None) -> List[str]:
    """Return supported reasoning levels for a Codex model slug."""
    model_slug = (model_slug or "").strip()
    if not model_slug:
        return []

    cache_file = cache_path or CODEX_MODELS_CACHE
    try:
        with open(cache_file, encoding="utf-8") as f:
            data = json.load(f)

        models = data.get("models", []) if isinstance(data, dict) else []
        for model in models:
            if not isinstance(model, dict):
                continue
            if model.get("slug") != model_slug:
                continue

            raw_levels = model.get("supported_reasoning_levels", [])
            if not isinstance(raw_levels, list):
                break

            levels = []
            for entry in raw_levels:
                level = None
                if isinstance(entry, str):
                    level = entry
                elif isinstance(entry, dict):
                    level = (
                        entry.get("effort")
                        or entry.get("level")
                        or entry.get("name")
                        or entry.get("value")
                    )
                if not isinstance(level, str):
                    continue
                level = level.strip()
                if level and level not in levels:
                    levels.append(level)

            if levels:
                return levels
    except FileNotFoundError:
        return []
    except Exception as exc:
        logger.debug("Failed reading Codex model reasoning levels: %s", exc)
    return []
