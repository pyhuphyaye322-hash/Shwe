"""Service layer for Shwe Khit AI Studio / Recap Voice Pro.

Modules
-------
config_service      : load / save / merge ``config.json`` settings.
transcript_service  : YouTube transcript extraction + transcript file I/O.
ai_service          : Gemini / OpenAI scene generation (Burmese translation).
tts_service         : Myanmar text-to-speech (edge-tts + gTTS fallback).
"""

from . import ai_service, config_service, transcript_service, tts_service

__all__ = [
    "ai_service",
    "config_service",
    "transcript_service",
    "tts_service",
]

__version__ = "1.0.0"
