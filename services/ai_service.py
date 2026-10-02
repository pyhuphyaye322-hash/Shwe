"""ai_service.py — transcript ➜ Burmese scene script generation.

Supported providers
-------------------
* **Gemini** via ``google-generativeai`` (primary).
* **OpenAI** via the official ``openai`` SDK (any OpenAI-compatible base URL).
* **Offline** heuristic splitter, used as a safety net when no API key is
  configured or when the provider call fails and the user allows fallback.

The public entry point is :func:`generate_scenes`, which always returns the
same structure regardless of provider::

    {
        "scenes": [{"id": 1, "label": "S1", "text": "..."}, ...],
        "raw": "S1: ...\\nS2: ...",
        "provider": "gemini",
        "mode": "ai" | "offline",
        "notes": "optional warning text",
    }
"""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional

# Matches:  S1:  |  S 1 :  |  S1 -  |  S1။  |  Scene 1:  |  ဇာတ်ကွက် 1:
SCENE_LINE_RE = re.compile(
    r"^\s*(?:S|Scene|ဇာတ်ကွက်)\s*[#\-]?\s*(\d+)\s*[:：\-–—။]\s*(.*)$",
    re.IGNORECASE,
)

# Fallback matcher for lines such as "S1" alone on a line, text on the next.
SCENE_BARE_RE = re.compile(r"^\s*(?:S|Scene)\s*[#\-]?\s*(\d+)\s*$", re.IGNORECASE)

SENTENCE_SPLIT_RE = re.compile(r"(?<=[။!?\.])\s+")


class AIError(Exception):
    """Raised when scene generation fails for every configured provider."""


# --------------------------------------------------------------------------- #
# Prompt construction
# --------------------------------------------------------------------------- #

PROMPT_TEMPLATE = """You are a professional video-recap scriptwriter and a native-level Burmese (Myanmar) translator.

TASK
1. Read the raw YouTube transcript provided at the end.
2. Translate and rewrite it into natural, spoken Burmese (မြန်မာစကားပြေ) suitable for a recap voice-over.
3. Split the result into numbered scenes. Each scene is one self-contained narration block of at most {max_chars} Burmese characters (usually 1-3 sentences).

OUTPUT FORMAT — follow EXACTLY:
S1: <Burmese text>
S2: <Burmese text>
S3: <Burmese text>

STRICT RULES
- Output ONLY the S-lines. No headings, no markdown, no bullet points, no explanations, no timestamps, no English.
- Every line starts with "S", then the scene number, then a colon, e.g. "S7:".
- Numbering starts at S1 and increases by exactly 1 with no gaps.
- Write Burmese only. Keep names, numbers and brand names accurate; transliterate foreign names into Burmese script.
- Never invent facts that are absent from the transcript; never drop key plot points.
- Use Burmese punctuation only ("။" and "၊"). No Chinese, Japanese or full-width punctuation.
- Do not repeat the same sentence in two consecutive scenes.

{extra_instruction}

TRANSCRIPT
\"\"\"
{transcript}
\"\"\"
"""


def build_scene_prompt(
    transcript: str,
    max_chars: int = 220,
    translate_to_burmese: bool = True,
    extra_instruction: str = "",
) -> str:
    """Build the instruction prompt sent to the LLM."""
    instruction = extra_instruction.strip()
    if not translate_to_burmese:
        instruction = (
            "The transcript is already Burmese. Do NOT translate; only rewrite and split it into scenes. "
            + instruction
        ).strip()

    return PROMPT_TEMPLATE.format(
        max_chars=int(max_chars),
        transcript=(transcript or "").strip(),
        extra_instruction=instruction,
    )


# --------------------------------------------------------------------------- #
# Scene parsing
# --------------------------------------------------------------------------- #

def parse_scenes(raw: str) -> List[Dict[str, Any]]:
    """Parse an ``S1: ...`` block into a list of scene dictionaries."""
    if not raw:
        return []

    scenes: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None

    for line in raw.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        stripped = line.strip()
        if not stripped:
            if current and current["text"]:
                continue
            continue

        match = SCENE_LINE_RE.match(stripped)
        if not match:
            bare = SCENE_BARE_RE.match(stripped)
            if bare:
                if current:
                    scenes.append(current)
                current = {"id": int(bare.group(1)), "label": f"S{int(bare.group(1))}", "text": ""}
                continue
            if current is not None:
                current["text"] = f"{current['text']} {stripped}".strip()
            continue

        if current:
            scenes.append(current)
        number = int(match.group(1))
        current = {"id": number, "label": f"S{number}", "text": match.group(2).strip()}

    if current:
        scenes.append(current)

    # Drop empties and renumber sequentially so audio files never skip a number.
    cleaned = [s for s in scenes if s.get("text")]
    for index, scene in enumerate(cleaned, start=1):
        scene["id"] = index
        scene["label"] = f"S{index}"

    return cleaned


def scenes_to_text(scenes: List[Dict[str, Any]]) -> str:
    """Render scenes back into the canonical ``S1: ...`` text block."""
    lines = []
    for index, scene in enumerate(scenes or [], start=1):
        text = (scene.get("text") or "").strip() if isinstance(scene, dict) else str(scene).strip()
        lines.append(f"S{index}: {text}")
    return "\n".join(lines)


def scenes_from_text(text: str) -> List[Dict[str, Any]]:
    """Parse a user-edited ``S1: ...`` block back into scene dictionaries."""
    scenes = parse_scenes(text)
    if scenes:
        return scenes
    # Plain text without S-markers: split into paragraphs as scenes.
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text or "") if b.strip()]
    return [{"id": i, "label": f"S{i}", "text": b} for i, b in enumerate(blocks, start=1)]


# --------------------------------------------------------------------------- #
# Offline fallback
# --------------------------------------------------------------------------- #

def offline_scenes(transcript: str, max_chars: int = 220) -> List[Dict[str, Any]]:
    """Split raw transcript text into scene-sized chunks without an LLM."""
    text = re.sub(r"\s+", " ", (transcript or "")).strip()
    if not text:
        return []

    sentences = [s.strip() for s in SENTENCE_SPLIT_RE.split(text) if s.strip()]
    if not sentences:
        sentences = [text]

    scenes: List[Dict[str, Any]] = []
    buffer = ""
    for sentence in sentences:
        candidate = f"{buffer} {sentence}".strip()
        if buffer and len(candidate) > max_chars:
            scenes.append({"id": len(scenes) + 1, "label": f"S{len(scenes) + 1}", "text": buffer})
            buffer = sentence
        else:
            buffer = candidate

    if buffer:
        scenes.append({"id": len(scenes) + 1, "label": f"S{len(scenes) + 1}", "text": buffer})

    # Hard-split any oversized scene on word boundaries.
    final: List[Dict[str, Any]] = []
    for scene in scenes:
        text_value = scene["text"]
        while len(text_value) > max_chars * 2:
            cut = text_value.rfind(" ", 0, max_chars * 2)
            cut = cut if cut > 0 else max_chars * 2
            final.append({"id": len(final) + 1, "label": "", "text": text_value[:cut].strip()})
            text_value = text_value[cut:].strip()
        if text_value:
            final.append({"id": len(final) + 1, "label": "", "text": text_value})

    for index, scene in enumerate(final, start=1):
        scene["id"] = index
        scene["label"] = f"S{index}"
    return final


# --------------------------------------------------------------------------- #
# Provider calls
# --------------------------------------------------------------------------- #

def _gemini_generate(prompt: str, config: Dict[str, Any]) -> str:
    """Call the Gemini API through ``google-generativeai``."""
    ai_cfg = config.get("ai", {})
    api_key = (ai_cfg.get("gemini_api_key") or "").strip()
    if not api_key:
        raise AIError("Gemini API Key ထည့်သွင်းမထားပါ။")

    model_name = ai_cfg.get("gemini_model") or "gemini-2.0-flash"
    temperature = float(ai_cfg.get("temperature", 0.4))
    max_tokens = int(ai_cfg.get("max_output_tokens", 8192))

    try:
        import google.generativeai as genai
    except ImportError:
        return _gemini_generate_new_sdk(prompt, api_key, model_name, temperature, max_tokens)

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(
        model_name,
        generation_config={"temperature": temperature, "max_output_tokens": max_tokens},
    )
    try:
        response = model.generate_content(prompt)
    except Exception as exc:  # noqa: BLE001 - provider raises many types
        raise AIError(f"Gemini API ခေါ်ယူမှု မအောင်မြင်ပါ — {exc}") from exc

    text = _extract_gemini_text(response)
    if not text:
        raise AIError("Gemini မှ စာသားပြန်မလာပါ (blocked ဖြစ်နိုင်ပါသည်)။")
    return text


def _extract_gemini_text(response: Any) -> str:
    """Safely pull text out of a Gemini response object."""
    try:
        text = getattr(response, "text", None)
        if text:
            return str(text)
    except Exception:
        pass
    try:
        candidates = getattr(response, "candidates", None) or []
        chunks: List[str] = []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            for part in getattr(content, "parts", []) or []:
                part_text = getattr(part, "text", "")
                if part_text:
                    chunks.append(str(part_text))
        return "\n".join(chunks)
    except Exception:
        return ""


def _gemini_generate_new_sdk(
    prompt: str, api_key: str, model_name: str, temperature: float, max_tokens: int
) -> str:
    """Fallback path using the newer ``google-genai`` package, if installed."""
    try:
        from google import genai  # type: ignore
    except ImportError as exc:
        raise AIError(
            "Gemini SDK မထည့်သွင်းရသေးပါ — pip install google-generativeai"
        ) from exc

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config={"temperature": temperature, "max_output_tokens": max_tokens},
        )
        text = getattr(response, "text", "") or ""
        if not text:
            raise AIError("Gemini မှ စာသားပြန်မလာပါ။")
        return text
    except AIError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise AIError(f"Gemini API ခေါ်ယူမှု မအောင်မြင်ပါ — {exc}") from exc


def _openai_generate(prompt: str, config: Dict[str, Any]) -> str:
    """Call an OpenAI-compatible chat completion endpoint."""
    ai_cfg = config.get("ai", {})
    api_key = (ai_cfg.get("openai_api_key") or "").strip()
    if not api_key:
        raise AIError("OpenAI API Key ထည့်သွင်းမထားပါ။")

    model_name = ai_cfg.get("openai_model") or "gpt-4o-mini"
    base_url = (ai_cfg.get("openai_base_url") or "").strip() or None
    temperature = float(ai_cfg.get("temperature", 0.4))
    max_tokens = int(ai_cfg.get("max_output_tokens", 8192))

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise AIError("OpenAI SDK မထည့်သွင်းရသေးပါ — pip install openai") from exc

    try:
        client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a Burmese voice-over scriptwriter. "
                        "You always answer strictly in the requested S1/S2/S3 line format."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        content = response.choices[0].message.content or ""
        if not content.strip():
            raise AIError("OpenAI မှ စာသားပြန်မလာပါ။")
        return content
    except AIError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise AIError(f"OpenAI API ခေါ်ယူမှု မအောင်မြင်ပါ — {exc}") from exc


def test_connection(config: Dict[str, Any]) -> Dict[str, Any]:
    """Ping the configured provider with a tiny prompt; used by the sidebar."""
    provider = (config.get("ai", {}).get("provider") or "gemini").lower()
    prompt = "Reply with exactly: OK"
    try:
        if provider == "openai":
            _openai_generate(prompt, config)
        else:
            _gemini_generate(prompt, config)
        return {"ok": True, "message": f"{provider.upper()} ချိတ်ဆက်မှု အောင်မြင်ပါသည်။"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "message": str(exc)}


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def generate_scenes(
    transcript: str,
    config: Dict[str, Any],
    progress: Optional[Callable[[str], None]] = None,
    extra_instruction: str = "",
) -> Dict[str, Any]:
    """Turn a raw transcript into a Burmese scene list.

    Parameters
    ----------
    transcript:
        Raw transcript text.
    config:
        Full application configuration dictionary.
    progress:
        Optional callback receiving short Burmese status strings.
    extra_instruction:
        Optional extra instruction appended to the LLM prompt.
    """
    transcript = (transcript or "").strip()
    if not transcript:
        raise AIError("စာသား မရှိပါ။ အရင်ဦးစွာ YouTube စာသားကို ထုတ်ယူပါ။")

    ai_cfg = config.get("ai", {})
    provider = (ai_cfg.get("provider") or "gemini").lower()
    max_chars = int(ai_cfg.get("max_scene_chars", 220))
    allow_offline = bool(ai_cfg.get("allow_offline_fallback", True))
    translate = bool(ai_cfg.get("translate_to_burmese", True))

    # Keep the prompt within a sane size for very long videos.
    trimmed = transcript if len(transcript) <= 48000 else transcript[:48000]

    prompt = build_scene_prompt(
        trimmed,
        max_chars=max_chars,
        translate_to_burmese=translate,
        extra_instruction=extra_instruction,
    )

    if progress:
        progress(f"🤖 {provider.upper()} ဖြင့် ဇာတ်ကွက်များ ဖန်တီးနေသည်...")

    raw = ""
    notes = ""
    try:
        raw = _openai_generate(prompt, config) if provider == "openai" else _gemini_generate(prompt, config)
    except Exception as exc:  # noqa: BLE001
        if not allow_offline:
            raise AIError(str(exc)) from exc
        notes = f"AI ဖြင့် မဖန်တီးနိုင်ပါ ({exc}) — Offline စနစ်ဖြင့် ခွဲထုတ်ပေးထားသည်။"

    scenes = parse_scenes(raw) if raw else []
    mode = "ai"

    if not scenes:
        if not allow_offline:
            raise AIError("AI မှ ဇာတ်ကွက် မထုတ်ပေးနိုင်ပါ။ ထပ်မံကြိုးစားပါ။")
        scenes = offline_scenes(trimmed, max_chars=max_chars)
        mode = "offline"
        if not notes:
            notes = "AI မဖွင့်ထားသဖြင့် Offline စနစ်ဖြင့် ဇာတ်ကွက်များ ခွဲထုတ်ထားသည် (ဘာသာပြန်မပါဝင်ပါ)။"

    if not scenes:
        raise AIError("ဇာတ်ကွက် ဖန်တီး၍ မရပါ။ စာသားကို စစ်ဆေးပါ။")

    if progress:
        progress(f"✅ ဇာတ်ကွက် {len(scenes)} ခု ဖန်တီးပြီးပါပြီ။")

    return {
        "scenes": scenes,
        "raw": scenes_to_text(scenes),
        "provider": provider if mode == "ai" else "offline",
        "mode": mode,
        "notes": notes,
    }
