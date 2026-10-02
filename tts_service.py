"""tts_service.py — Myanmar text-to-speech engine for scene audio.

Two engines are supported and selected automatically:

``edge``
    Microsoft Edge neural voices ``my-MM-ThihaNeural`` (male) and
    ``my-MM-NilarNeural`` (female). Pitch / rate / volume are applied natively
    by the service, so no audio post-processing is required. This is the
    recommended engine for recap narration.

``gtts``
    Google Translate TTS for ``lang='my'``. Pitch, speed and loudness are then
    applied with FFmpeg (``asetrate`` + ``atempo`` + ``volume``) and, when
    FFmpeg is unavailable, with a pure-Python ``pydub`` fallback.

Public API
----------
* :func:`list_voices` / :func:`voice_display_name`
* :func:`synthesize` — one text block ➜ one MP3 file
* :func:`preview_voice` — short sample for the "အသံနမူနာ" button
* :func:`generate_scenes_audio` — sequential S1.mp3 … Sn.mp3 generation
* :func:`build_zip` / :func:`audio_duration` / :func:`engine_status`
"""

from __future__ import annotations

import asyncio
import io
import math
import re
import shutil
import subprocess
import tempfile
import threading
import time
import zipfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

# --------------------------------------------------------------------------- #
# Voice catalogue
# --------------------------------------------------------------------------- #

VOICES: Dict[str, Dict[str, str]] = {
    "Thiha (သီဟ)": {
        "display": "Thiha (သီဟ) — အမျိုးသားအသံ",
        "gender": "Male",
        "edge_voice": "my-MM-ThihaNeural",
        "gtts_lang": "my",
        "gtts_tld": "com",
    },
    "Nilar (နီလာ)": {
        "display": "Nilar (နီလာ) — အမျိုးသမီးအသံ",
        "gender": "Female",
        "edge_voice": "my-MM-NilarNeural",
        "gtts_lang": "my",
        "gtts_tld": "com",
    },
}

DEFAULT_VOICE = "Thiha (သီဟ)"
ENGINES = ("auto", "edge", "gtts")
QUALITY_PROFILES: Dict[str, Dict[str, str]] = {
    "economy": {"label": "64 kbps", "bitrate": "64k"},
    "standard": {"label": "128 kbps", "bitrate": "128k"},
    "high": {"label": "192 kbps", "bitrate": "192k"},
}
TTS_PARAMETER_MIN = 0
TTS_PARAMETER_MAX = 100
GTTS_NETWORK_TIMEOUT_SECONDS = 120
GTTS_CHUNK_MAX_CHARS = 90
GTTS_CHUNK_DELAY_SECONDS = 0.35

#: Burmese digit normalisation so captions from mixed sources still read well.
_DIGIT_MAP = str.maketrans("၀၁၂၃၄၅၆၇၈၉", "0123456789")


class TTSError(Exception):
    """Raised when no TTS engine could produce audio."""


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #

def list_voices() -> List[str]:
    """Return the selectable voice keys."""
    return list(VOICES.keys())


def voice_display_name(name: str) -> str:
    """Return the Burmese friendly label for *name*."""
    return VOICES.get(name, VOICES[DEFAULT_VOICE])["display"]


def voice_gender(name: str) -> str:
    """Return ``Male`` / ``Female`` for *name*."""
    return VOICES.get(name, VOICES[DEFAULT_VOICE])["gender"]


def quality_bitrate(quality: str) -> str:
    """Return the MP3 bitrate for a quality profile."""
    return QUALITY_PROFILES.get(str(quality).lower(), QUALITY_PROFILES["standard"])["bitrate"]


def _clamp_parameter(value: float, name: str) -> float:
    """Clamp public TTS controls to the documented 0–100 range."""
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise TTSError(f"{name} တန်ဖိုး မမှန်ပါ။ 0 မှ 100 အတွင်း ထည့်ပါ။") from exc
    return max(TTS_PARAMETER_MIN, min(TTS_PARAMETER_MAX, numeric))


def clean_text_for_speech(text: str) -> str:
    """Normalise text so the TTS engines pronounce it correctly."""
    value = (text or "").strip()
    if not value:
        return ""
    value = re.sub(r"^\s*S\s*\d+\s*[:：]\s*", "", value)          # drop "S1:" prefix
    value = re.sub(r"```.*?```", " ", value, flags=re.DOTALL)      # drop code fences
    value = re.sub(r"[*_#>`~]+", " ", value)                       # drop markdown marks
    value = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", value)            # links -> label
    value = value.replace("&", " နှင့် ")
    value = re.sub(r"[\u200b\u200c\u200d\ufeff]", "", value)
    value = re.sub(r"[ \t\u00a0]+", " ", value)
    value = re.sub(r"\n{2,}", "\n", value)
    return value.strip()


def chunk_text_for_tts(text: str, max_chars: int = GTTS_CHUNK_MAX_CHARS) -> List[str]:
    """Split Burmese narration into request-sized chunks without breaking words.

    The split order is deliberately conservative:

    1. paragraphs,
    2. Burmese/Latin sentence endings (``။ ! ?``),
    3. whitespace boundaries,
    4. hard character slices only for a single oversized token.

    Keeping each request below ``max_chars`` reduces the chance of upstream
    TTS request limits and makes rate limiting easier to control. The returned
    chunks preserve all input text apart from whitespace normalisation.
    """
    value = clean_text_for_speech(text)
    if not value:
        return []
    try:
        limit = int(max_chars)
    except (TypeError, ValueError) as exc:
        raise TTSError("TTS စာသားအပိုင်းအရွယ်အစား မမှန်ပါ။") from exc
    if limit < 20:
        raise TTSError("TTS စာသားအပိုင်းအရွယ်အစားသည် အနည်းဆုံး 20 စာလုံး ဖြစ်ရပါမည်။")

    # First create sentence-like units. Burmese uses ။ frequently, but keep
    # Latin punctuation too because transcripts may be mixed-language.
    units: List[str] = []
    for paragraph in re.split(r"\n+", value):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        units.extend(
            part.strip()
            for part in re.split(r"(?<=[။!?])\s+", paragraph)
            if part.strip()
        )

    chunks: List[str] = []
    current = ""

    def flush() -> None:
        nonlocal current
        if current:
            chunks.append(current.strip())
            current = ""

    for unit in units:
        if len(unit) <= limit:
            candidate = f"{current} {unit}".strip() if current else unit
            if current and len(candidate) > limit:
                flush()
            current = f"{current} {unit}".strip() if current else unit
            continue

        # A sentence itself is too large: pack words into bounded pieces.
        if current:
            flush()
        remaining = unit
        while len(remaining) > limit:
            cut = remaining.rfind(" ", 0, limit + 1)
            if cut < 1:
                cut = limit
            chunks.append(remaining[:cut].strip())
            remaining = remaining[cut:].strip()
        current = remaining

    flush()
    return [chunk for chunk in chunks if chunk]


def _run_async(coro_factory: Callable[[], Any], timeout: float = 120.0) -> Any:
    """Run an async coroutine factory in a dedicated thread with its own loop.

    Streamlit's script thread sometimes already owns an event loop, so the
    coroutine is always created *inside* the worker thread.
    """
    box: Dict[str, Any] = {}

    def worker() -> None:
        try:
            box["result"] = asyncio.run(coro_factory())
        except BaseException as exc:  # noqa: BLE001 - forwarded to caller
            box["error"] = exc

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    thread.join(timeout=timeout)
    if thread.is_alive():
        raise TTSError("အသံဖန်တီးခြင်း အချိန်ကျော်လွန်သွားပါသည် (timeout)။")
    if "error" in box:
        raise box["error"]
    return box.get("result")


def _hz_to_semitones(hz: float) -> float:
    """Approximate a Hz pitch offset as semitones (relative to a 220 Hz base)."""
    return 12.0 * math.log2(1.0 + max(float(hz), 0.0) / 220.0)


def _split_atempo(factor: float) -> List[float]:
    """Split a tempo factor into FFmpeg-compatible atempo steps (0.5 – 2.0)."""
    factor = max(0.05, min(20.0, float(factor)))
    steps: List[float] = []
    while factor > 2.0:
        steps.append(2.0)
        factor /= 2.0
    while factor < 0.5:
        steps.append(0.5)
        factor /= 0.5
    steps.append(factor)
    return steps


def ffmpeg_available() -> bool:
    """True when both ``ffmpeg`` and ``ffprobe`` are on the PATH."""
    return bool(shutil.which("ffmpeg")) and bool(shutil.which("ffprobe"))


def engine_status() -> Dict[str, Any]:
    """Report which engines and helpers are usable in the current runtime."""
    status: Dict[str, Any] = {"edge": False, "gtts": False, "ffmpeg": ffmpeg_available(), "pydub": False}
    try:
        import edge_tts  # noqa: F401

        status["edge"] = True
    except Exception:
        status["edge"] = False
    try:
        import gtts  # noqa: F401

        status["gtts"] = True
    except Exception:
        status["gtts"] = False
    try:
        import pydub  # noqa: F401

        status["pydub"] = True
    except Exception:
        status["pydub"] = False
    return status


def audio_duration(path: str | Path) -> Optional[float]:
    """Return the duration of an audio file in seconds (``None`` if unknown)."""
    target = Path(path)
    if not target.exists():
        return None
    if shutil.which("ffprobe"):
        try:
            result = subprocess.run(
                [
                    "ffprobe", "-v", "error", "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1", str(target),
                ],
                capture_output=True, text=True, timeout=60,
            )
            return round(float(result.stdout.strip()), 2)
        except Exception:
            pass
    try:  # pragma: no cover - depends on pydub/ffmpeg availability
        from pydub import AudioSegment

        return round(len(AudioSegment.from_file(str(target))) / 1000.0, 2)
    except Exception:
        return None


def _probe_sample_rate(path: Path, fallback: int = 24000) -> int:
    """Return the source sample rate using ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-select_streams", "a:0",
                "-show_entries", "stream=sample_rate",
                "-of", "default=noprint_wrappers=1:nokey=1", str(path),
            ],
            capture_output=True, text=True, timeout=60,
        )
        return int(result.stdout.strip())
    except Exception:
        return fallback


# --------------------------------------------------------------------------- #
# Audio post-processing (gTTS path)
# --------------------------------------------------------------------------- #

def _ffmpeg_effects(
    src: Path, dst: Path, speed: float, volume: float, pitch_hz: float, bitrate: str = "128k"
) -> None:
    """Apply pitch / speed / volume with a single FFmpeg filter chain."""
    rate = _probe_sample_rate(src)
    pitch_factor = 2.0 ** (_hz_to_semitones(pitch_hz) / 12.0)   # asetrate resampling
    speed_factor = max(0.25, 1.0 + float(speed) / 100.0)

    filters = [f"asetrate={int(max(rate * pitch_factor, 4000))}", f"aresample={rate}"]
    for step in _split_atempo(speed_factor / pitch_factor):
        filters.append(f"atempo={step:.5f}")

    gain_db = (float(volume) / 100.0) * 12.0
    if abs(gain_db) > 0.05:
        filters.append(f"volume={gain_db:.2f}dB")

    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(src), "-filter:a", ",".join(filters),
            "-c:a", "libmp3lame", "-b:a", bitrate, str(dst),
        ],
        check=True, capture_output=True, timeout=300,
    )


def _pydub_effects(src: Path, dst: Path, speed: float, volume: float, bitrate: str = "128k") -> None:
    """Pure-pydub fallback (speed + volume only; pitch is left unchanged)."""
    from pydub import AudioSegment

    segment = AudioSegment.from_file(str(src))
    speed_factor = max(0.5, 1.0 + float(speed) / 100.0)
    if abs(speed_factor - 1.0) > 0.01:
        segment = segment.speedup(playback_speed=speed_factor, chunk_size=100, crossfade=20)
    gain_db = (float(volume) / 100.0) * 12.0
    if abs(gain_db) > 0.05:
        segment = segment.apply_gain(gain_db)
    segment.export(str(dst), format="mp3", bitrate=bitrate)


def _concat_mp3_parts(parts: Sequence[Path], output: Path) -> str:
    """Concatenate raw gTTS MP3 parts, preferring FFmpeg and falling back to pydub."""
    if not parts:
        raise TTSError("ပေါင်းစပ်ရန် gTTS အပိုင်းဖိုင် မရှိပါ။")

    if len(parts) == 1:
        shutil.copyfile(parts[0], output)
        return "single"

    if ffmpeg_available():
        list_path = output.with_suffix(".concat.txt")
        try:
            # concat demuxer paths are quoted; temporary paths are local and
            # generated by tempfile, but escape single quotes defensively.
            entries = "\n".join(
                f"file '{str(part).replace(chr(39), chr(39) + chr(92) + chr(39) + chr(39))}'"
                for part in parts
            )
            list_path.write_text(entries + "\n", encoding="utf-8")
            subprocess.run(
                [
                    "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                    "-f", "concat", "-safe", "0", "-i", str(list_path),
                    "-c", "copy", str(output),
                ],
                check=True, capture_output=True, timeout=300,
            )
            return "ffmpeg-concat"
        except Exception:
            pass
        finally:
            list_path.unlink(missing_ok=True)

    try:
        from pydub import AudioSegment

        merged = AudioSegment.empty()
        for part in parts:
            merged += AudioSegment.from_file(str(part), format="mp3")
        merged.export(str(output), format="mp3", bitrate="128k")
        return "pydub-concat"
    except Exception as exc:
        raise TTSError(f"gTTS အပိုင်းဖိုင်များ ပေါင်းစပ်၍မရပါ — {exc}") from exc


def apply_audio_effects(
    src: Path, dst: Path, speed: float, volume: float, pitch_hz: float, bitrate: str = "128k"
) -> str:
    """Post-process *src* into *dst*; returns the helper that succeeded."""
    if ffmpeg_available():
        try:
            _ffmpeg_effects(src, dst, speed, volume, pitch_hz, bitrate)
            return "ffmpeg"
        except Exception:
            pass
    try:
        _pydub_effects(src, dst, speed, volume, bitrate)
        return "pydub"
    except Exception:
        shutil.copyfile(src, dst)
        return "none"


# --------------------------------------------------------------------------- #
# Engines
# --------------------------------------------------------------------------- #

def _transcode_bitrate(src: Path, dst: Path, bitrate: str) -> str:
    """Re-encode an existing MP3 at the selected bitrate."""
    if not ffmpeg_available():
        shutil.copyfile(src, dst)
        return "source-bitrate"
    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-i", str(src), "-c:a", "libmp3lame", "-b:a", bitrate, str(dst),
            ],
            check=True, capture_output=True, timeout=300,
        )
        return f"ffmpeg-{bitrate}"
    except Exception:
        shutil.copyfile(src, dst)
        return "source-bitrate"

def _edge_synthesize(
    text: str, out_path: Path, voice: str, pitch: float, speed: float, volume: float, quality: str
) -> Dict[str, Any]:
    """Generate speech with the Microsoft Edge neural TTS service."""
    try:
        import edge_tts
    except ImportError as exc:
        raise TTSError("edge-tts မထည့်သွင်းရသေးပါ — pip install edge-tts") from exc

    edge_voice = VOICES.get(voice, VOICES[DEFAULT_VOICE])["edge_voice"]
    params = {
        "rate": f"+{int(speed)}%",
        "volume": f"+{int(volume)}%",
        "pitch": f"+{int(pitch)}Hz",
    }

    def build(with_params: bool):
        try:
            return edge_tts.Communicate(text, edge_voice, **params) if with_params else edge_tts.Communicate(text, edge_voice)
        except TypeError:
            return None

    communicate = build(True)
    native_params = communicate is not None
    if communicate is None:
        communicate = build(False)
    if communicate is None:  # pragma: no cover - defensive
        raise TTSError("edge-tts ကို စတင်၍မရပါ။")

    try:
        _run_async(lambda: communicate.save(str(out_path)))
    except Exception as exc:  # noqa: BLE001
        raise TTSError(f"Edge TTS ချို့ယွင်းချက် — {exc}") from exc

    if not out_path.exists() or out_path.stat().st_size < 512:
        raise TTSError("Edge TTS မှ ဖိုင်အလွတ် ပြန်လာပါသည်။")

    bitrate = quality_bitrate(quality)
    applied = "edge-native"
    if not native_params:  # older edge-tts: post-process instead
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_src = out_path.with_suffix(".raw.mp3")
            shutil.move(str(out_path), str(tmp_src))
            applied = apply_audio_effects(tmp_src, out_path, speed, volume, pitch, bitrate)
            Path(tmp_src).unlink(missing_ok=True)
    else:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_src = Path(tmp_dir) / "edge_native.mp3"
            shutil.move(str(out_path), str(tmp_src))
            bitrate_effect = _transcode_bitrate(tmp_src, out_path, bitrate)
            applied = f"edge-native; {bitrate_effect}"

    return {
        "path": str(out_path), "engine": "edge", "voice": edge_voice,
        "params": {**params, "quality": quality, "bitrate": bitrate}, "effects": applied,
    }


def _gtts_synthesize(
    text: str, out_path: Path, voice: str, pitch: float, speed: float, volume: float, quality: str
) -> Dict[str, Any]:
    """Generate speech with Google Translate TTS, then shape it with FFmpeg."""
    try:
        from gtts import gTTS
    except ImportError as exc:
        raise TTSError("gTTS မထည့်သွင်းရသေးပါ — pip install gTTS") from exc

    meta = VOICES.get(voice, VOICES[DEFAULT_VOICE])
    chunks = chunk_text_for_tts(text)
    if not chunks:
        raise TTSError("gTTS ပြောင်းရန် စာသား မရှိပါ။")

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_root = Path(tmp_dir)
        parts: List[Path] = []
        for index, chunk in enumerate(chunks, start=1):
            part_path = tmp_root / f"part_{index:04d}.mp3"
            try:
                gTTS(
                    text=chunk,
                    lang=meta["gtts_lang"],
                    tld=meta.get("gtts_tld", "com"),
                    slow=False,
                    timeout=GTTS_NETWORK_TIMEOUT_SECONDS,
                ).save(str(part_path))
            except Exception as exc:  # noqa: BLE001
                raise TTSError(f"gTTS အပိုင်း {index}/{len(chunks)} ချို့ယွင်းချက် — {exc}") from exc

            if not part_path.exists() or part_path.stat().st_size < 512:
                raise TTSError(f"gTTS အပိုင်း {index}/{len(chunks)} မှ ဖိုင်အလွတ် ပြန်လာပါသည်။")
            parts.append(part_path)
            if index < len(chunks):
                time.sleep(GTTS_CHUNK_DELAY_SECONDS)

        combined_path = tmp_root / "combined_raw.mp3"
        concat_method = _concat_mp3_parts(parts, combined_path)
        bitrate = quality_bitrate(quality)
        applied = apply_audio_effects(combined_path, out_path, speed, volume, pitch, bitrate)

    return {
        "path": str(out_path),
        "engine": "gtts",
        "voice": meta["gtts_lang"],
        "params": {
            "speed": speed,
            "volume": volume,
            "pitch_hz": pitch,
            "quality": quality,
            "bitrate": bitrate,
            "chunks": len(chunks),
            "chunk_max_chars": GTTS_CHUNK_MAX_CHARS,
            "chunk_delay_seconds": GTTS_CHUNK_DELAY_SECONDS,
        },
        "effects": f"{applied}; {concat_method}",
    }


# --------------------------------------------------------------------------- #
# Public synthesis API
# --------------------------------------------------------------------------- #

def synthesize(
    text: str,
    out_path: str | Path,
    voice: str = DEFAULT_VOICE,
    pitch: float = 5,
    speed: float = 43,
    volume: float = 16,
    quality: str = "standard",
    engine: str = "auto",
) -> Dict[str, Any]:
    """Convert *text* to an MP3 file at *out_path*.

    Raises :class:`TTSError` when every candidate engine fails.
    """
    speech_text = clean_text_for_speech(text)
    if not speech_text:
        raise TTSError("အသံဖန်တီးရန် စာသား မရှိပါ။")

    # Keep the service safe when called outside the Streamlit sliders.
    pitch = _clamp_parameter(pitch, "Pitch")
    speed = _clamp_parameter(speed, "Speed")
    volume = _clamp_parameter(volume, "Volume")
    quality = str(quality or "standard").lower()
    if quality not in QUALITY_PROFILES:
        quality = "standard"

    target = Path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    engine = (engine or "auto").lower()
    order: Sequence[str] = ("edge", "gtts") if engine == "auto" else (engine,)

    errors: List[str] = []
    for candidate in order:
        try:
            if candidate == "edge":
                return _edge_synthesize(speech_text, target, voice, pitch, speed, volume, quality)
            if candidate == "gtts":
                return _gtts_synthesize(speech_text, target, voice, pitch, speed, volume, quality)
            raise TTSError(f"မသိသော engine — {candidate}")
        except Exception as exc:  # noqa: BLE001 - try the next engine
            errors.append(f"{candidate}: {exc}")
            continue

    raise TTSError("အသံဖန်တီးခြင်း မအောင်မြင်ပါ — " + " | ".join(errors))


def preview_voice(
    text: str,
    output_dir: str | Path,
    voice: str = DEFAULT_VOICE,
    pitch: float = 5,
    speed: float = 43,
    volume: float = 16,
    quality: str = "standard",
    engine: str = "auto",
) -> Dict[str, Any]:
    """Render a short sample clip for the voice-preview button."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "_preview.mp3"
    result = synthesize(
        text, target, voice=voice, pitch=pitch, speed=speed, volume=volume,
        quality=quality, engine=engine,
    )
    result["duration"] = audio_duration(target)
    return result


def generate_scenes_audio(
    scenes: Sequence[Any],
    output_dir: str | Path,
    voice: str = DEFAULT_VOICE,
    pitch: float = 5,
    speed: float = 43,
    volume: float = 16,
    quality: str = "standard",
    engine: str = "auto",
    prefix: str = "S",
    overwrite: bool = True,
    on_progress: Optional[Callable[[int, int, Dict[str, Any]], None]] = None,
) -> List[Dict[str, Any]]:
    """Sequentially render one MP3 per scene (``S1.mp3``, ``S2.mp3`` …).

    Returns one result dictionary per scene with ``ok``, ``path``, ``engine``,
    ``duration``, ``size_kb`` and ``error`` fields.
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    items: List[Dict[str, Any]] = [s if isinstance(s, dict) else {"text": str(s)} for s in (scenes or [])]
    total = len(items)
    results: List[Dict[str, Any]] = []

    for index, scene in enumerate(items, start=1):
        label = f"{prefix}{index}"
        target = out_dir / f"{label}.mp3"
        text_value = (scene.get("text") or "").strip()
        record: Dict[str, Any] = {
            "index": index,
            "label": label,
            "text": text_value,
            "path": str(target),
            "ok": False,
            "engine": None,
            "effects": None,
            "duration": None,
            "size_kb": None,
            "error": None,
        }

        try:
            if not text_value:
                raise TTSError("စာသား အလွတ်ဖြစ်နေပါသည်။")

            if overwrite or not target.exists():
                info = synthesize(
                    text_value, target, voice=voice, pitch=pitch, speed=speed, volume=volume,
                    quality=quality, engine=engine,
                )
                record["engine"] = info.get("engine")
                record["effects"] = info.get("effects")

            if target.exists() and target.stat().st_size > 512:
                record["ok"] = True
                record["duration"] = audio_duration(target)
                record["size_kb"] = round(target.stat().st_size / 1024, 1)
            else:
                record["error"] = "ဖိုင် မဖန်တီးနိုင်ပါ။"
        except Exception as exc:  # noqa: BLE001 - keep going for the other scenes
            record["error"] = str(exc)

        results.append(record)
        if on_progress:
            try:
                on_progress(index, total, record)
            except Exception:
                pass

    return results


# --------------------------------------------------------------------------- #
# Packaging helpers
# --------------------------------------------------------------------------- #

def build_zip(paths: Sequence[str | Path], names: Optional[Sequence[str]] = None) -> bytes:
    """Bundle audio files into an in-memory ZIP archive."""
    buffer = io.BytesIO()
    used: Dict[str, int] = {}
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for position, raw_path in enumerate(paths or []):
            path = Path(raw_path)
            if not path.exists():
                continue
            arcname = names[position] if names and position < len(names) else path.name
            # Guarantee unique entry names, even when several folders are merged.
            if arcname in used:
                used[arcname] += 1
                stem, suffix = path.stem, path.suffix or ".mp3"
                arcname = f"{stem}_{used[arcname]}{suffix}"
            else:
                used[arcname] = 0
            archive.write(path, arcname=arcname)
    buffer.seek(0)
    return buffer.getvalue()


def cleanup_outputs(output_dir: str | Path, pattern: str = "*.mp3") -> int:
    """Delete generated audio files (used by the "ရှင်းလင်းရန်" button)."""
    out_dir = Path(output_dir)
    if not out_dir.exists():
        return 0
    removed = 0
    for path in out_dir.glob(pattern):
        try:
            path.unlink()
            removed += 1
        except OSError:
            continue
    return removed


def total_duration(results: Sequence[Dict[str, Any]]) -> float:
    """Sum the durations of successfully generated scene files."""
    return round(sum(float(item.get("duration") or 0) for item in results or []), 2)


def format_duration(seconds: Optional[float]) -> str:
    """Format seconds as ``M:SS`` (or ``H:MM:SS``) for the UI."""
    if not seconds:
        return "0:00"
    total = int(round(float(seconds)))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"
