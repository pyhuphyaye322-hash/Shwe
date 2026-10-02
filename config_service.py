"""config_service.py — configuration loading, merging and saving.

Responsibilities
----------------
* Keep a single source of truth for every tunable value in ``config.json``.
* Merge a user's partial ``config.json`` over safe built-in defaults so the
  application never crashes because a key is missing.
* Provide path helpers (output folder, transcript file) and secret masking.
* Optionally read API keys from ``st.secrets`` so that Streamlit Cloud
  deployments do not need keys committed to the repository.
"""

from __future__ import annotations

import copy
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

# --------------------------------------------------------------------------- #
# Defaults
# --------------------------------------------------------------------------- #

DEFAULT_CONFIG: Dict[str, Any] = {
    "app": {
        "name": "Shwe Khit AI Studio / Recap Voice Pro",
        "version": "1.0.0",
        "tagline": "မြန်မာစကားသံ Recap အလိုအလျောက် ဖန်တီးစနစ်",
        "language": "my",
    },
    "ai": {
        "provider": "gemini",
        "gemini_api_key": "",
        "gemini_model": "gemini-3.8-flash",
        "openai_api_key": "",
        "openai_model": "gpt-4o-mini",
        "openai_base_url": "",
        "temperature": 0.4,
        "max_output_tokens": 8192,
        "max_scene_chars": 220,
        "translate_to_burmese": True,
        "allow_offline_fallback": True,
    },
    "transcript": {
        "preferred_languages": ["my", "en", "en-US", "en-GB", "th", "hi", "zh-Hans"],
        "auto_save_filename": "transcript.txt",
        "dedupe_lines": True,
    },
    "tts": {
        "engine": "auto",
        "voice": "Thiha (သီဟ)",
        "quality": "standard",
        "pitch": 5,
        "speed": 43,
        "volume": 16,
        "output_dir": "outputs",
        "file_prefix": "S",
        "preview_text": (
            "မင်္ဂလာပါ။ ရှေးခေတ် AI စတူဒီယိုမှ ကြိုဆိုပါတယ်။ ဒီအသံနမူနာကို "
            "နားထောင်ပြီး သင့်လိုအပ်ချက်နှင့် ကိုက်ညီမှု ရှိမရှိ စစ်ဆေးပေးပါ။"
        ),
        "max_scene_chars": 600,
    },
    "ui": {
        "theme": "dark",
        "accent_color": "#00E5A0",
        "accent_secondary": "#7C5CFF",
        "show_footer": True,
    },
}

#: Streamlit secret names that may override ``config.json`` values.
SECRET_KEY_MAP = {
    "gemini_api_key": ("GEMINI_API_KEY", "gemini_api_key"),
    "openai_api_key": ("OPENAI_API_KEY", "openai_api_key"),
}


class ConfigError(Exception):
    """Raised when ``config.json`` cannot be read or parsed."""


# --------------------------------------------------------------------------- #
# Path helpers
# --------------------------------------------------------------------------- #

def project_root() -> Path:
    """Absolute path of the project root (the folder containing ``app.py``)."""
    return Path(__file__).resolve().parent.parent


def resolve_path(value: str | os.PathLike[str]) -> Path:
    """Resolve *value* against the project root when it is relative."""
    path = Path(value).expanduser()
    return path if path.is_absolute() else (project_root() / path)


def ensure_dirs(config: Dict[str, Any]) -> Dict[str, Path]:
    """Create (if needed) and return the runtime folders used by the app."""
    output_dir = resolve_path(config.get("tts", {}).get("output_dir", "outputs"))
    output_dir.mkdir(parents=True, exist_ok=True)

    transcript_name = config.get("transcript", {}).get("auto_save_filename", "transcript.txt")
    transcript_path = resolve_path(transcript_name)
    transcript_path.parent.mkdir(parents=True, exist_ok=True)

    return {"output_dir": output_dir, "transcript_path": transcript_path}


# --------------------------------------------------------------------------- #
# Load / save
# --------------------------------------------------------------------------- #

def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Recursively merge *override* into a copy of *base*."""
    result = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def get_secret(*names: str, default: str = "") -> str:
    """Return the first available Streamlit secret among *names* (or *default*)."""
    try:  # pragma: no cover - depends on the Streamlit runtime
        import streamlit as st

        secrets = getattr(st, "secrets", None)
        if secrets is None:
            return default
        for name in names:
            try:
                if name in secrets:
                    value = secrets[name]
                    if value:
                        return str(value)
            except Exception:
                continue
    except Exception:
        pass
    return default


def load_config(path: Optional[str | os.PathLike[str]] = None) -> Dict[str, Any]:
    """Load ``config.json`` merged over :data:`DEFAULT_CONFIG`.

    A missing file is not an error — defaults are returned. A malformed file
    raises :class:`ConfigError` so the UI can show a helpful Burmese message.
    """
    config_path = Path(path) if path else (project_root() / "config.json")
    raw: Dict[str, Any] = {}

    if config_path.exists():
        try:
            text = config_path.read_text(encoding="utf-8")
            raw = json.loads(text) if text.strip() else {}
        except json.JSONDecodeError as exc:
            raise ConfigError(
                f"config.json ဖိုင်ဖတ်၍မရပါ (JSON ပုံစံမမှန်ပါ) — {exc}"
            ) from exc
        except OSError as exc:
            raise ConfigError(f"config.json ဖိုင်ဖွင့်၍မရပါ — {exc}") from exc
        if not isinstance(raw, dict):
            raise ConfigError("config.json ၏ အဓိကအပိုင်းသည် JSON object ဖြစ်ရပါမည်။")

    config = _deep_merge(DEFAULT_CONFIG, raw)

    # Streamlit secrets win over whatever is stored in the JSON file.
    for field, secret_names in SECRET_KEY_MAP.items():
        secret_value = get_secret(*secret_names)
        if secret_value:
            config["ai"][field] = secret_value

    return config


def save_config(config: Dict[str, Any], path: Optional[str | os.PathLike[str]] = None) -> Path:
    """Atomically write *config* to disk and return the written path."""
    config_path = Path(path) if path else (project_root() / "config.json")
    config_path.parent.mkdir(parents=True, exist_ok=True)

    payload = json.dumps(config, ensure_ascii=False, indent=2) + "\n"
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=str(config_path.parent), delete=False
        ) as tmp:
            tmp.write(payload)
            tmp_path = Path(tmp.name)
        tmp_path.replace(config_path)
    except OSError as exc:
        raise ConfigError(f"config.json သိမ်းဆည်း၍မရပါ — {exc}") from exc

    return config_path


# --------------------------------------------------------------------------- #
# Small utilities used by the UI
# --------------------------------------------------------------------------- #

def mask_secret(value: str, keep: int = 4) -> str:
    """Return a masked representation of an API key for display purposes."""
    if not value:
        return "—"
    value = str(value)
    if len(value) <= keep:
        return "•" * len(value)
    return f"{value[:keep]}{'•' * 8}{value[-2:]}"


def secret_source(field: str) -> str:
    """Return ``'secrets'`` when the value comes from ``st.secrets``."""
    names = SECRET_KEY_MAP.get(field)
    if not names:
        return "config"
    return "secrets" if get_secret(*names) else "config"


def config_summary(config: Dict[str, Any]) -> Dict[str, Any]:
    """Compact, UI friendly summary of the active configuration."""
    tts = config.get("tts", {})
    ai = config.get("ai", {})
    return {
        "provider": ai.get("provider", "gemini"),
        "model": ai.get("gemini_model") if ai.get("provider") == "gemini" else ai.get("openai_model"),
        "voice": tts.get("voice"),
        "engine": tts.get("engine"),
        "pitch": tts.get("pitch"),
        "speed": tts.get("speed"),
        "volume": tts.get("volume"),
    }
