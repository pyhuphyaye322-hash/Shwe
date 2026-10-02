"""transcript_service.py — YouTube transcript extraction and transcript I/O.

The module works with every recent release of ``youtube-transcript-api``:

* **>= 1.0** exposes the instance API ``YouTubeTranscriptApi().fetch(...)``.
* **< 1.0** exposes the class API ``YouTubeTranscriptApi.get_transcript(...)``.

Both are attempted, and a helpful Burmese error message is produced when a
video simply has no captions available.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

VIDEO_ID_RE = re.compile(
    r"""(?x)
    (?:v=|/v/|youtu\.be/|/embed/|/shorts/|/live/|/watch\?.*?v=)
    (?P<id>[A-Za-z0-9_-]{11})
    """
)

BARE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

DEFAULT_LANGUAGES: Tuple[str, ...] = ("my", "en", "en-US", "en-GB", "th", "hi", "zh-Hans")


class TranscriptError(Exception):
    """Raised when a transcript cannot be retrieved or parsed."""


# --------------------------------------------------------------------------- #
# URL / ID helpers
# --------------------------------------------------------------------------- #

def extract_video_id(url_or_id: str) -> str:
    """Return the 11-character YouTube video id from a URL or a bare id."""
    value = (url_or_id or "").strip()
    if not value:
        raise TranscriptError("YouTube လင့်ခ် ထည့်သွင်းပေးပါ။")

    if BARE_ID_RE.match(value):
        return value

    match = VIDEO_ID_RE.search(value)
    if match:
        return match.group("id")

    raise TranscriptError(
        "YouTube လင့်ခ် ပုံစံမမှန်ပါ။ ဥပမာ — https://www.youtube.com/watch?v=XXXXXXXXXXX"
    )


def watch_url(video_id: str) -> str:
    """Return the canonical watch URL for *video_id*."""
    return f"https://www.youtube.com/watch?v={video_id}"


# --------------------------------------------------------------------------- #
# Transcript retrieval
# --------------------------------------------------------------------------- #

def _normalise_segments(segments: Iterable[Any]) -> List[Dict[str, Any]]:
    """Convert SDK-specific snippet objects into plain dictionaries."""
    normalised: List[Dict[str, Any]] = []
    for segment in segments or []:
        if isinstance(segment, dict):
            text = segment.get("text", "")
            start = segment.get("start", 0.0)
            duration = segment.get("duration", 0.0)
        else:  # dataclass style (youtube-transcript-api >= 1.0)
            text = getattr(segment, "text", "")
            start = getattr(segment, "start", 0.0)
            duration = getattr(segment, "duration", 0.0)
        text = (text or "").replace("\n", " ").strip()
        if text:
            normalised.append({"text": text, "start": float(start or 0), "duration": float(duration or 0)})
    return normalised


def fetch_transcript(
    url_or_id: str,
    preferred_languages: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Fetch the transcript of a YouTube video.

    Returns a dictionary with ``video_id``, ``language``, ``is_generated``,
    ``segments`` and the joined ``text``.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise TranscriptError(
            "youtube-transcript-api မထည့်သွင်းရသေးပါ — pip install youtube-transcript-api"
        ) from exc

    video_id = extract_video_id(url_or_id)
    languages = list(preferred_languages or DEFAULT_LANGUAGES)

    errors: List[str] = []
    api = None
    try:
        api = YouTubeTranscriptApi()
    except Exception:
        api = None

    # --- New instance API (youtube-transcript-api >= 1.0) ------------------ #
    if api is not None and hasattr(api, "fetch"):
        try:
            fetched = api.fetch(video_id, languages=languages)
            segments = _normalise_segments(getattr(fetched, "snippets", fetched))
            if segments:
                return {
                    "video_id": video_id,
                    "language": getattr(fetched, "language_code", None) or languages[0],
                    "is_generated": bool(getattr(fetched, "is_generated", False)),
                    "segments": segments,
                    "text": clean_transcript_text(" ".join(s["text"] for s in segments)),
                }
        except Exception as exc:  # noqa: BLE001 - SDK raises many types
            errors.append(f"fetch: {exc}")
        try:  # last resort: let the SDK pick any available language
            fetched = api.fetch(video_id)
            segments = _normalise_segments(getattr(fetched, "snippets", fetched))
            if segments:
                return {
                    "video_id": video_id,
                    "language": getattr(fetched, "language_code", None) or "auto",
                    "is_generated": bool(getattr(fetched, "is_generated", False)),
                    "segments": segments,
                    "text": clean_transcript_text(" ".join(s["text"] for s in segments)),
                }
        except Exception as exc:  # noqa: BLE001
            errors.append(f"fetch(auto): {exc}")

    # --- Legacy class API (youtube-transcript-api < 1.0) -------------------- #
    if hasattr(YouTubeTranscriptApi, "get_transcript"):
        for attempt in (languages, None):
            try:
                if attempt is None:
                    raw = YouTubeTranscriptApi.get_transcript(video_id)
                else:
                    raw = YouTubeTranscriptApi.get_transcript(video_id, languages=attempt)
                segments = _normalise_segments(raw)
                if segments:
                    return {
                        "video_id": video_id,
                        "language": (attempt or ["auto"])[0],
                        "is_generated": False,
                        "segments": segments,
                        "text": clean_transcript_text(" ".join(s["text"] for s in segments)),
                    }
            except Exception as exc:  # noqa: BLE001
                errors.append(f"get_transcript: {exc}")

    # --- Build a helpful failure message ---------------------------------- #
    available = _list_available_languages(video_id)
    hint = (
        "ဤဗီဒီယိုအတွက် စာတန်းထိုး (caption) မရနိုင်ပါ။ စာတန်းထိုး ဖွင့်ထားခြင်း သို့မဟုတ် "
        "မူရင်းစာသားကို ကိုယ်တိုင် ကူးထည့်ခြင်းဖြင့် ဆက်လက်ဆောင်ရွက်နိုင်ပါသည်။"
    )
    if available:
        hint += " ရနိုင်သော ဘာသာစကားများ — " + ", ".join(available[:8])
    detail = " | ".join(errors[:3]) if errors else "unknown error"
    raise TranscriptError(f"{hint}\n(အသေးစိတ်: {detail})")


def _list_available_languages(video_id: str) -> List[str]:
    """Best-effort listing of the transcript languages YouTube offers."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        try:
            api = YouTubeTranscriptApi()
            if hasattr(api, "list"):
                listing = api.list(video_id)
                return [getattr(t, "language_code", str(t)) for t in listing]
        except Exception:
            pass
        if hasattr(YouTubeTranscriptApi, "list_transcripts"):
            listing = YouTubeTranscriptApi.list_transcripts(video_id)
            return [getattr(t, "language_code", str(t)) for t in listing]
    except Exception:
        return []
    return []


# --------------------------------------------------------------------------- #
# Text cleaning / transcript files
# --------------------------------------------------------------------------- #

def clean_transcript_text(text: str, dedupe: bool = True) -> str:
    """Collapse whitespace and optionally drop duplicated caption lines."""
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t\u00a0]+", " ", text)

    if dedupe:
        seen_previous: Optional[str] = None
        kept: List[str] = []
        for raw_line in text.split("\n"):
            line = raw_line.strip()
            if not line:
                continue
            if line == seen_previous:
                continue
            kept.append(line)
            seen_previous = line
        text = "\n".join(kept) if kept else text

    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def build_transcript_file(text: str, video_id: str = "", language: str = "", is_generated: bool = False) -> str:
    """Build the ``transcript.txt`` payload (with a small Burmese header)."""
    header = [
        "# Shwe Khit AI Studio — transcript.txt",
        f"# video: {watch_url(video_id) if video_id else '-'}",
        f"# language: {language or '-'}{' (auto-generated)' if is_generated else ''}",
        "# ---------------------------------------------------------------",
        "",
    ]
    return "\n".join(header) + (text or "").strip() + "\n"


def strip_transcript_header(text: str) -> str:
    """Remove the leading ``#`` comment block added by :func:`build_transcript_file`."""
    if not text:
        return ""
    lines = text.splitlines()
    index = 0
    while index < len(lines) and (lines[index].startswith("#") or not lines[index].strip()):
        index += 1
    return "\n".join(lines[index:]).strip()


def save_transcript(text: str, path: str | Path, **header_fields: Any) -> Path:
    """Write *text* to *path* (UTF-8) and return the path."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = build_transcript_file(text, **header_fields)
    target.write_text(payload, encoding="utf-8")
    return target


def load_transcript(path: str | Path) -> str:
    """Read a transcript file, tolerating a missing file."""
    target = Path(path)
    if not target.exists():
        return ""
    return strip_transcript_header(target.read_text(encoding="utf-8"))


def parse_subtitle_content(content: str, filename: str = "") -> str:
    """Convert uploaded ``.srt`` / ``.vtt`` / ``.txt`` content into plain text."""
    text = (content or "").replace("\ufeff", "")
    name = (filename or "").lower()

    if name.endswith((".srt", ".vtt")) or "-->" in text or text.lstrip().upper().startswith("WEBVTT"):
        lines: List[str] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.upper().startswith("WEBVTT") or line.isdigit() or "-->" in line:
                continue
            if line.startswith(("NOTE", "Kind:", "Language:")):
                continue
            lines.append(line)
        text = " ".join(lines)

    return clean_transcript_text(text)


def estimate_duration_minutes(text: str, words_per_minute: int = 150) -> float:
    """Rough speaking-time estimate used in the UI summary card."""
    words = len([w for w in re.split(r"\s+", text or "") if w])
    if words == 0:
        return 0.0
    return round(words / max(words_per_minute, 1), 2)
