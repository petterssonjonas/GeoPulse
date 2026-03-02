"""Configuration management with sensible defaults."""
import yaml
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "geopulse"
DATA_DIR = Path.home() / ".local" / "share" / "geopulse"
_PKG_DATA = Path(__file__).parent.parent / "data"

DEFAULT_CONFIG = {
    "llm": {
        "provider": "ollama",
        "model": "qwen3:8b",
        "triage_model": "",
        "base_url": "http://localhost:11434",
        "api_key": "",
        "temperature": 0.3,
    },
    "schedule": {
        "sentinel_interval_minutes": 15,
        "briefing_interval_minutes": 60,
        "breaking_threshold": 4,
        "max_articles_per_briefing": 20,
    },
    "notifications": {
        "enabled": True,
        "min_severity": 3,
    },
    "ollama": {
        "auto_start": True,
        "auto_stop": False,
    },
    "briefing": {
        "depth": "brief",   # "brief" or "extended"
    },
}

SEVERITY_KEYWORDS = {
    "critical": [
        "nuclear strike", "declaration of war", "coup", "assassination",
        "invasion", "missile attack", "state of emergency", "nuclear weapon",
    ],
    "high": [
        "military operation", "sanctions", "airstrikes", "troops deployed",
        "conflict", "explosion", "crisis", "escalation", "evacuation",
    ],
    "medium": [
        "negotiations", "summit", "statement", "agreement",
        "election", "protest", "warning", "threat",
    ],
}


def ensure_dirs():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def get_db_path() -> Path:
    ensure_dirs()
    return DATA_DIR / "geopulse.db"


def is_first_run() -> bool:
    return not (CONFIG_DIR / "config.yaml").exists()


def _deep_merge(base: dict, override: dict) -> dict:
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config() -> dict:
    config_path = CONFIG_DIR / "config.yaml"
    if config_path.exists():
        with open(config_path) as f:
            user = yaml.safe_load(f) or {}
        return _deep_merge(DEFAULT_CONFIG, user)
    return DEFAULT_CONFIG.copy()


def save_config(data: dict):
    ensure_dirs()
    with open(CONFIG_DIR / "config.yaml", "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def load_sources(tier: int = None) -> list:
    path = _PKG_DATA / "sources.yaml"
    if not path.exists():
        return []
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    sources = [s for s in data.get("sources", []) if s.get("enabled", True)]
    if tier is not None:
        sources = [s for s in sources if s.get("tier") == tier]
    return sources


def load_default_topics() -> list:
    path = _PKG_DATA / "topics.yaml"
    if not path.exists():
        return []
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    return data.get("topics", [])


class Config:
    """Singleton config accessor."""
    _data = None

    @classmethod
    def get(cls) -> dict:
        if cls._data is None:
            cls._data = load_config()
        return cls._data

    @classmethod
    def reload(cls) -> dict:
        cls._data = load_config()
        return cls._data

    @classmethod
    def save(cls, data: dict):
        cls._data = data
        save_config(data)

    @classmethod
    def update(cls, **sections):
        data = cls.get()
        data = _deep_merge(data, sections)
        cls.save(data)

    @classmethod
    def llm(cls) -> dict:
        return cls.get().get("llm", {})

    @classmethod
    def schedule(cls) -> dict:
        return cls.get().get("schedule", {})

    @classmethod
    def notifications(cls) -> dict:
        return cls.get().get("notifications", {})

    @classmethod
    def ollama_config(cls) -> dict:
        return cls.get().get("ollama", {})

    @classmethod
    def briefing_depth(cls) -> str:
        return cls.get().get("briefing", {}).get("depth", "brief")
