"""Shwe Khit AI Studio / Recap Voice Pro — Streamlit application (Burmese UI).

Workflow
--------
1. **စာသားထုတ်ယူခြင်း** — pull a YouTube transcript, translate + split it into
   Burmese scenes with Gemini / OpenAI.
2. **အသံထိန်းချုပ်မှု** — choose a voice (Thiha / Nilar) and tune pitch, speed
   and volume, then preview the sound.
3. **အသံဖိုင် ဖန်တီးခြင်း** — after an explicit confirmation click, render
   ``S1.mp3``, ``S2.mp3`` … sequentially into ``outputs/``.

Run locally::

    streamlit run app.py
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path

import streamlit as st

from services import ai_service, config_service, transcript_service, tts_service
from services.ai_service import AIError
from services.transcript_service import TranscriptError
from services.tts_service import TTSError

# --------------------------------------------------------------------------- #
# Constants & page setup
# --------------------------------------------------------------------------- #

BASE_DIR = Path(__file__).resolve().parent
CONFIG_FILE = BASE_DIR / "config.json"

APP_NAME = "Shwe Khit AI Studio"
APP_SUBTITLE = "Recap Voice Pro — မြန်မာစာသားမှ စကားသံအထိ အလိုအလျောက် ဖန်တီးစနစ်"

st.set_page_config(
    page_title="Shwe Khit AI Studio / Recap Voice Pro",
    page_icon="🎙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --------------------------------------------------------------------------- #
# Styling — modern dark theme with neon accents and Burmese typography
# --------------------------------------------------------------------------- #

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+Myanmar:wght@400;500;600;700&family=Padauk:wght@400;700&family=Inter:wght@400;600;800&display=swap');

:root {
    --sk-bg:        #0B0F14;
    --sk-bg-2:      #0E141C;
    --sk-panel:     #111823;
    --sk-panel-2:   #16202E;
    --sk-border:    #22304A;
    --sk-accent:    #00E5A0;
    --sk-accent-2:  #7C5CFF;
    --sk-warn:      #FFB020;
    --sk-danger:    #FF5C7A;
    --sk-text:      #E8EEF7;
    --sk-muted:     #8FA3BF;
}

html, body, [class*="css"], .stApp, .stMarkdown, p, li, label, span, div {
    font-family: 'Noto Sans Myanmar', 'Padauk', 'Inter', 'Segoe UI', sans-serif !important;
}

/* Keep Streamlit's Material icon ligatures intact (the Burmese font rule above
   would otherwise render icons as their literal names, e.g. "keyboard_double…"). */
span[data-testid="stIconMaterial"],
[data-testid="stIconMaterial"],
.material-symbols-rounded,
.material-symbols-outlined,
.material-icons,
[class*="material-symbols"] {
    font-family: 'Material Symbols Rounded', 'Material Symbols Outlined', 'Material Icons' !important;
}

.stApp {
    background:
        radial-gradient(1200px 600px at 12% -8%, rgba(0,229,160,0.10), transparent 60%),
        radial-gradient(1000px 520px at 92% 4%, rgba(124,92,255,0.12), transparent 62%),
        linear-gradient(180deg, var(--sk-bg) 0%, var(--sk-bg-2) 100%) !important;
    color: var(--sk-text) !important;
}

.block-container { padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1250px; }
#MainMenu, footer { visibility: hidden; }

/* ---------- Header ---------- */
.sk-header {
    border: 1px solid var(--sk-border);
    background: linear-gradient(135deg, rgba(17,24,35,0.95), rgba(22,32,46,0.85));
    border-radius: 18px;
    padding: 22px 26px;
    margin-bottom: 18px;
    box-shadow: 0 0 0 1px rgba(0,229,160,0.06), 0 18px 45px rgba(0,0,0,0.45);
}
.sk-title {
    font-size: 2.0rem; font-weight: 800; letter-spacing: .2px; margin: 0;
    background: linear-gradient(90deg, #00E5A0 0%, #7C5CFF 65%, #4FD1FF 100%);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
}
.sk-subtitle { color: var(--sk-muted); font-size: .98rem; margin-top: 6px; }
.sk-badge {
    display: inline-block; padding: 4px 12px; border-radius: 999px; font-size: .74rem;
    font-weight: 700; letter-spacing: .6px; margin-right: 8px;
    border: 1px solid rgba(0,229,160,.45); color: #7DF3CE; background: rgba(0,229,160,.10);
}
.sk-badge.purple { border-color: rgba(124,92,255,.5); color: #C0AEFF; background: rgba(124,92,255,.12); }

/* ---------- Panels ---------- */
div[data-testid="stVerticalBlockBorderWrapper"] {
    background: linear-gradient(180deg, rgba(17,24,35,.92), rgba(14,20,28,.92));
    border: 1px solid var(--sk-border) !important;
    border-radius: 16px !important;
    padding: 6px 10px 12px 10px !important;
    box-shadow: 0 10px 30px rgba(0,0,0,.35);
}
.sk-step-title { font-size: 1.16rem; font-weight: 700; color: #D8E4F5; margin: 2px 0 2px 0; }
.sk-step-sub { color: var(--sk-muted); font-size: .86rem; margin-bottom: 10px; }

/* ---------- Scene cards ---------- */
.sk-scene {
    display: flex; gap: 12px; align-items: flex-start;
    background: linear-gradient(90deg, rgba(0,229,160,.07), rgba(124,92,255,.05));
    border: 1px solid var(--sk-border);
    border-left: 3px solid var(--sk-accent);
    border-radius: 12px; padding: 12px 14px; margin-bottom: 9px;
}
.sk-scene-tag {
    min-width: 46px; text-align: center; font-weight: 800; font-size: .82rem;
    color: #04140E; background: linear-gradient(135deg, #00E5A0, #00B37E);
    border-radius: 8px; padding: 4px 8px; box-shadow: 0 0 14px rgba(0,229,160,.35);
}
.sk-scene-text { color: var(--sk-text); font-size: 1rem; line-height: 1.75; white-space: pre-wrap; }

/* ---------- Status dots ---------- */
.sk-status { display: flex; align-items: center; gap: 8px; font-size: .86rem; color: var(--sk-muted); margin-bottom: 4px; }
.sk-dot { width: 9px; height: 9px; border-radius: 50%; display: inline-block; }
.sk-dot.on  { background: #00E5A0; box-shadow: 0 0 10px rgba(0,229,160,.9); }
.sk-dot.off { background: #FF5C7A; box-shadow: 0 0 10px rgba(255,92,122,.7); }
.sk-dot.idle{ background: #FFB020; box-shadow: 0 0 10px rgba(255,176,32,.7); }

/* ---------- Buttons ---------- */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {
    border-radius: 12px !important;
    font-weight: 700 !important;
    border: 1px solid rgba(0,229,160,.35) !important;
    transition: all .15s ease-in-out;
}
.stButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {
    background: linear-gradient(135deg, #00E5A0 0%, #00B37E 100%) !important;
    color: #04140E !important;
    box-shadow: 0 0 20px rgba(0,229,160,.45);
    border: none !important;
}
.stButton > button[kind="primary"]:hover, .stFormSubmitButton > button[kind="primary"]:hover {
    box-shadow: 0 0 32px rgba(0,229,160,.85); transform: translateY(-1px);
}
.stButton > button[kind="secondary"] {
    background: rgba(22,32,46,.9) !important; color: var(--sk-text) !important;
}
.stButton > button[kind="secondary"]:hover { border-color: var(--sk-accent) !important; color: #7DF3CE !important; }
.stDownloadButton > button {
    background: linear-gradient(135deg, #7C5CFF 0%, #4B32C3 100%) !important;
    color: #FFFFFF !important; border: none !important;
    box-shadow: 0 0 16px rgba(124,92,255,.4);
}
.stDownloadButton > button:hover { box-shadow: 0 0 26px rgba(124,92,255,.8); }

/* ---------- Inputs ---------- */
.stTextInput input, .stTextArea textarea, .stNumberInput input {
    background: #0C131C !important; color: var(--sk-text) !important;
    border: 1px solid var(--sk-border) !important; border-radius: 10px !important;
}
.stTextInput input:focus, .stTextArea textarea:focus { border-color: var(--sk-accent) !important; }
div[data-baseweb="select"] > div { background: #0C131C !important; border-color: var(--sk-border) !important; }
div[data-baseweb="popover"] li { background: #0C131C !important; color: var(--sk-text) !important; }

/* ---------- Sliders / progress / audio ---------- */
.stSlider [data-baseweb="slider"] div[role="slider"] { background: #00E5A0 !important; box-shadow: 0 0 12px rgba(0,229,160,.8); }
.stProgress > div > div > div > div { background: linear-gradient(90deg, #00E5A0, #7C5CFF) !important; }
audio { width: 100%; border-radius: 10px; filter: invert(0.92) hue-rotate(160deg) saturate(1.1); }

/* ---------- Sidebar ---------- */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0C131C 0%, #0A0F16 100%) !important;
    border-right: 1px solid var(--sk-border);
}
section[data-testid="stSidebar"] .sk-side-title { font-size: 1.02rem; font-weight: 800; color: #7DF3CE; }
.sk-divider { height: 1px; background: linear-gradient(90deg, transparent, var(--sk-border), transparent); margin: 14px 0; }
.sk-hint { color: var(--sk-muted); font-size: .78rem; line-height: 1.6; }
.sk-gate {
    border: 1px dashed rgba(0,229,160,.5); background: rgba(0,229,160,.06);
    border-radius: 14px; padding: 14px 16px; margin-bottom: 12px;
    color: #BFEFDD; font-size: .92rem;
}
.sk-footer { color: var(--sk-muted); font-size: .8rem; text-align: center; margin-top: 26px; }
</style>
"""

st.markdown(CSS, unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# Session state
# --------------------------------------------------------------------------- #

def init_state() -> None:
    """Create every session-state key used by the app exactly once."""
    defaults = {
        "config": config_service.load_config(CONFIG_FILE),
        "transcript": "",
        "transcript_meta": {},
        "scenes": [],
        "scenes_raw": "",
        "ai_meta": {},
        "audio_results": [],
        "audio_signature": None,
        "preview_bytes": None,
        "preview_meta": {},
        "flash": None,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)

    # Reuse a transcript.txt left by a previous run or uploaded with the app.
    # This is useful when a YouTube video has captions disabled.
    if not st.session_state.get("transcript"):
        saved_path = config_service.ensure_dirs(st.session_state["config"])["transcript_path"]
        saved_text = transcript_service.load_transcript(saved_path)
        if saved_text:
            st.session_state["transcript"] = saved_text
            st.session_state["transcript_meta"] = {
                "language": "saved file",
                "saved_to": str(saved_path),
                "chars": len(saved_text),
            }


def flash(kind: str, message: str) -> None:
    """Store a one-shot notification shown on the next render."""
    st.session_state["flash"] = {"kind": kind, "message": message}


def render_flash() -> None:
    """Display and clear the pending notification."""
    pending = st.session_state.get("flash")
    if not pending:
        return
    {"success": st.success, "warning": st.warning, "error": st.error, "info": st.info}.get(
        pending.get("kind", "info"), st.info
    )(pending.get("message", ""))
    st.session_state["flash"] = None


def paths() -> dict:
    """Resolve the output folder and transcript file paths."""
    return config_service.ensure_dirs(st.session_state["config"])


# --------------------------------------------------------------------------- #
# Header
# --------------------------------------------------------------------------- #

def render_header() -> None:
    """Render the neon gradient application header."""
    cfg = st.session_state["config"]
    version = cfg.get("app", {}).get("version", "1.0.0")
    st.markdown(
        f"""
        <div class="sk-header">
            <div>
                <span class="sk-badge">PRO</span>
                <span class="sk-badge purple">v{version}</span>
                <span class="sk-badge">မြန်မာ UI</span>
            </div>
            <h1 class="sk-title">{APP_NAME}</h1>
            <div class="sk-subtitle">{APP_SUBTITLE}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_footer() -> None:
    """Render the footer line."""
    cfg = st.session_state["config"]
    if not cfg.get("ui", {}).get("show_footer", True):
        return
    st.markdown(
        '<div class="sk-footer">Shwe Khit AI Studio / Recap Voice Pro · '
        "Streamlit · Gemini / OpenAI · edge-tts + gTTS</div>",
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------- #
# Sidebar — manual configuration
# --------------------------------------------------------------------------- #

def render_sidebar() -> dict:
    """Render all manual configuration controls and return the live config."""
    cfg = st.session_state["config"]
    ai_cfg = cfg.setdefault("ai", {})
    tts_cfg = cfg.setdefault("tts", {})
    tr_cfg = cfg.setdefault("transcript", {})
    status = tts_service.engine_status()

    with st.sidebar:
        st.markdown('<div class="sk-side-title">⚙️ ဆက်တင်များ (Manual Configuration)</div>', unsafe_allow_html=True)
        st.markdown('<div class="sk-hint">ဤနေရာတွင် ထည့်သွင်းထားသော တန်ဖိုးများကို <code>config.json</code> သို့ သိမ်းဆည်းနိုင်ပါသည်။</div>', unsafe_allow_html=True)
        st.markdown('<div class="sk-divider"></div>', unsafe_allow_html=True)

        # ---------- AI provider ----------
        st.markdown("**🤖 AI ဝန်ဆောင်မှု**")
        provider_options = ["gemini", "openai"]
        ai_cfg["provider"] = st.selectbox(
            "AI Provider",
            provider_options,
            index=provider_options.index(ai_cfg.get("provider", "gemini"))
            if ai_cfg.get("provider", "gemini") in provider_options
            else 0,
            key="sb_provider",
            help="ဇာတ်ကွက် ဖန်တီးရာတွင် အသုံးပြုမည့် AI ဝန်ဆောင်မှု",
        )

        gemini_from_secret = config_service.secret_source("gemini_api_key") == "secrets"
        openai_from_secret = config_service.secret_source("openai_api_key") == "secrets"

        ai_cfg["gemini_api_key"] = st.text_input(
            "Gemini API Key",
            value=ai_cfg.get("gemini_api_key", ""),
            type="password",
            key="sb_gemini_key",
            help="Streamlit secrets တွင် GEMINI_API_KEY ထားရှိပါက အလိုအလျောက် အသုံးပြုပါမည်။",
        )
        ai_cfg["gemini_model"] = st.text_input(
            "Gemini Model", value=ai_cfg.get("gemini_model", "gemini-3.8-flash"), key="sb_gemini_model"
        )
        ai_cfg["openai_api_key"] = st.text_input(
            "OpenAI API Key",
            value=ai_cfg.get("openai_api_key", ""),
            type="password",
            key="sb_openai_key",
        )
        ai_cfg["openai_model"] = st.text_input(
            "OpenAI Model", value=ai_cfg.get("openai_model", "gpt-4o-mini"), key="sb_openai_model"
        )
        ai_cfg["openai_base_url"] = st.text_input(
            "OpenAI Base URL (optional)",
            value=ai_cfg.get("openai_base_url", ""),
            key="sb_openai_base",
            placeholder="https://api.openai.com/v1",
        )

        with st.expander("🎛️ AI အဆင့်မြင့် ဆက်တင်", expanded=False):
            ai_cfg["temperature"] = st.slider(
                "Temperature", 0.0, 1.0, float(ai_cfg.get("temperature", 0.4)), 0.05, key="sb_temp"
            )
            ai_cfg["max_scene_chars"] = st.slider(
                "တစ်ဇာတ်ကွက် အများဆုံး စာလုံးအရေအတွက်",
                80, 400, int(ai_cfg.get("max_scene_chars", 220)), 10, key="sb_scene_chars",
            )
            ai_cfg["max_output_tokens"] = st.slider(
                "Max Output Tokens", 1024, 32768, int(ai_cfg.get("max_output_tokens", 8192)), 512, key="sb_max_tokens"
            )
            ai_cfg["translate_to_burmese"] = st.checkbox(
                "မြန်မာဘာသာသို့ ပြန်ဆိုရန်", value=bool(ai_cfg.get("translate_to_burmese", True)), key="sb_translate"
            )
            ai_cfg["allow_offline_fallback"] = st.checkbox(
                "AI မရပါက Offline စနစ်ဖြင့် ဆက်လုပ်ရန်",
                value=bool(ai_cfg.get("allow_offline_fallback", True)),
                key="sb_offline",
            )

        if st.button("🔌 AI ချိတ်ဆက်မှု စမ်းသပ်ရန်", key="sb_test_ai", use_container_width=True):
            with st.spinner("စမ်းသပ်နေသည်..."):
                result = ai_service.test_connection(cfg)
            (st.success if result["ok"] else st.error)(result["message"])

        if gemini_from_secret or openai_from_secret:
            st.caption("🔒 API Key ကို Streamlit Secrets မှ ရယူထားပါသည်။")

        st.markdown('<div class="sk-divider"></div>', unsafe_allow_html=True)

        # ---------- TTS ----------
        st.markdown("**🔊 TTS ဆက်တင်များ**")
        engine_options = ["auto", "edge", "gtts"]
        tts_cfg["engine"] = st.selectbox(
            "TTS Engine",
            engine_options,
            index=engine_options.index(tts_cfg.get("engine", "auto"))
            if tts_cfg.get("engine", "auto") in engine_options
            else 0,
            key="sb_engine",
            help="auto = Edge Neural အသံကို ဦးစားပေး၊ မရပါက gTTS သို့ ပြောင်း",
        )

        voices = tts_service.list_voices()
        default_voice = tts_cfg.get("voice", tts_service.DEFAULT_VOICE)
        tts_cfg["voice"] = st.radio(
            "အသံ ရွေးချယ်ရန်",
            voices,
            index=voices.index(default_voice) if default_voice in voices else 0,
            format_func=tts_service.voice_display_name,
            key="sb_voice",
        )

        tts_cfg["pitch"] = st.slider("Pitch — အသံအနိမ့်အမြင့် (%)", 0, 100, int(tts_cfg.get("pitch", 5)), key="sb_pitch")
        tts_cfg["speed"] = st.slider("Speed — အသံအမြန်နှုန်း (%)", 0, 100, int(tts_cfg.get("speed", 43)), key="sb_speed")
        tts_cfg["volume"] = st.slider("Volume — အသံကျယ်ပမာဏ (%)", 0, 100, int(tts_cfg.get("volume", 16)), key="sb_volume")
        quality_options = ["economy", "standard", "high"]
        quality_labels = {
            "economy": "အခြေခံ — 64 kbps (ဖိုင်သေး)",
            "standard": "စံ — 128 kbps (အကြံပြု)",
            "high": "မြင့် — 192 kbps (အရည်အသွေးကောင်း)",
        }
        current_quality = tts_cfg.get("quality", "standard")
        tts_cfg["quality"] = st.selectbox(
            "အသံဖိုင် အရည်အသွေး",
            quality_options,
            index=quality_options.index(current_quality) if current_quality in quality_options else 1,
            format_func=lambda value: quality_labels[value],
            key="sb_quality",
            help="MP3 encoding bitrate ကို သတ်မှတ်ပါသည်။ မြင့်လေ ဖိုင်အရွယ်အစား ကြီးလေ ဖြစ်ပါသည်။",
        )

        with st.expander("📁 ဖိုင် လမ်းကြောင်း ဆက်တင်", expanded=False):
            tts_cfg["output_dir"] = st.text_input(
                "အသံဖိုင် သိမ်းဆည်းမည့် Folder", value=tts_cfg.get("output_dir", "outputs"), key="sb_outdir"
            )
            tts_cfg["file_prefix"] = st.text_input(
                "ဖိုင်အမည် ရှေ့ဆက် (S1, S2 …)", value=tts_cfg.get("file_prefix", "S"), key="sb_prefix"
            )
            tr_cfg["auto_save_filename"] = st.text_input(
                "စာသားဖိုင် အမည်", value=tr_cfg.get("auto_save_filename", "transcript.txt"), key="sb_trfile"
            )
            langs = st.text_input(
                "ဦးစားပေး ဘာသာစကားများ (ကော်မာဖြင့် ခြားပါ)",
                value=", ".join(tr_cfg.get("preferred_languages", ["my", "en"])),
                key="sb_langs",
            )
            tr_cfg["preferred_languages"] = [item.strip() for item in langs.split(",") if item.strip()]

        # ---------- System status ----------
        st.markdown('<div class="sk-divider"></div>', unsafe_allow_html=True)
        st.markdown("**🩺 စနစ် အခြေအနေ**")
        for label, is_on, extra in (
            ("Edge Neural အသံ (အကြံပြု)", status["edge"], ""),
            ("gTTS အသံ", status["gtts"], ""),
            ("FFmpeg အသံ ပြုပြင်စနစ်", status["ffmpeg"], ""),
            ("pydub", status["pydub"], ""),
        ):
            css_class = "on" if is_on else "off"
            text = "အသင့်" if is_on else "မရနိုင်"
            st.markdown(
                f'<div class="sk-status"><span class="sk-dot {css_class}"></span>{label}: <b>{text}</b>{extra}</div>',
                unsafe_allow_html=True,
           st.markdown('<div class="sk-divider"></div>', unsafe_allow_html=True)

        col_save, col_reset = st.columns(2)
        if col_save.button("💾 သိမ်းဆည်းရန်", key="sb_save", use_container_width=True, type="primary"):
            try:
                config_service.save_config(cfg, CONFIG_FILE)
                flash("success", "✅ ဆက်တင်များကို config.json သို့ သိမ်းဆည်းပြီးပါပြီ။")
            except config_service.ConfigError as exc:
                flash("error", f"❌ {exc}")
            st.rerun()

        if col_reset.button("♻️ မူရင်း", key="sb_reset", use_container_width=True):
            st.session_state["config"] = config_service.load_config(CONFIG_FILE)
            for key in list(st.session_state.keys()):
                if key.startswith("sb_"):
                    st.session_state.pop(key, None)
            flash("info", "♻️ ဆက်တင်များကို မူလတန်ဖိုးသို့ ပြန်လည်သတ်မှတ်ပြီးပါပြီ။")
            st.rerun()

        st.markdown(
            '<div class="sk-hint">💡 API Key များကို config.json တွင် ထည့်သိမ်းပါက '
            "မျှဝေမည့် repository တွင် မတင်မိစေရန် သတိပြုပါ။ Streamlit Cloud တွင် Secrets ကို "
            "အသုံးပြုပါ။</div>",
            unsafe_allow_html=True,
        )

    st.session_state["config"] = cfg
    return cfg


# --------------------------------------------------------------------------- #
# Step 1 — transcript + AI scenes
# --------------------------------------------------------------------------- #

def render_step1(cfg: dict, runtime_paths: dict) -> None:
    """Render the YouTube transcript extraction and AI scene panel."""
    ai_cfg = cfg.get("ai", {})
    transcript_path: Path = runtime_paths["transcript_path"]

    with st.container(border=True):
        st.markdown('<div class="sk-step-title">၁။ YouTube စာသားထုတ်ယူခြင်း နှင့် AI ဇာတ်ကွက် ဖန်တီးခြင်း</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="sk-step-sub">YouTube လင့်ခ် ထည့်သွင်းပြီး စာသားထုတ်ယူပါ။ ထို့နောက် AI ဖြင့် '
            "မြန်မာဘာသာသို့ ပြန်ဆိုကာ S1, S2, S3 … ဇာတ်ကွက်များအဖြစ် ခွဲထုတ်ပါမည်။</div>",
            unsafe_allow_html=True,
        )

        url_col, opt_col = st.columns([3, 1])
        youtube_url = url_col.text_input(
            "YouTube Video URL",
            key="yt_url",
            placeholder="https://www.youtube.com/watch?v=XXXXXXXXXXX",
        )
        opt_col.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
        manual_mode = opt_col.checkbox("စာသားကို ကိုယ်တိုင်ထည့်ရန်", key="manual_mode")

        btn_extract, btn_ai, btn_clear = st.columns([1, 1, 1])
        extract_clicked = btn_extract.button(
            "📥 စာသားထုတ်ယူရန်", key="btn_extract", use_container_width=True, type="primary"
        )
        ai_clicked = btn_ai.button("🤖 AI ဖြင့် ဇာတ်ကွက် ဖန်တီးရန်", key="btn_ai", use_container_width=True)
        clear_clicked = btn_clear.button("🧹 ရှင်းလင်းရန်", key="btn_clear", use_container_width=True)

        if clear_clicked:
            st.session_state["transcript"] = ""
            st.session_state["transcript_meta"] = {}
            st.session_state["scenes"] = []
            st.session_state["scenes_raw"] = ""
            st.session_state["ai_meta"] = {}
            st.session_state.pop("scene_editor", None)
            flash("info", "🧹 စာသားနှင့် ဇာတ်ကွက်များကို ရှင်းလင်းပြီးပါပြီ။")
            st.rerun()
       # ---------------- transcript extraction ---------------- #
        if extract_clicked:
            if manual_mode or not youtube_url.strip():
                flash("warning", "⚠️ လင့်ခ် ထည့်သွင်းပါ (သို့) စာသားကို ကိုယ်တိုင် ကူးထည့်ပါ။")
            else:
                with st.spinner("📥 YouTube မှ စာသား ထုတ်ယူနေသည်..."):
                    try:
                        data = transcript_service.fetch_transcript(
                            youtube_url, cfg.get("transcript", {}).get("preferred_languages")
                        )
                        text = transcript_service.clean_transcript_text(
                            data["text"], dedupe=bool(cfg.get("transcript", {}).get("dedupe_lines", True))
                        )
                        transcript_service.save_transcript(
                            text,
                            transcript_path,
                            video_id=data.get("video_id", ""),
                            language=data.get("language", ""),
                            is_generated=data.get("is_generated", False),
                        )
                        st.session_state["transcript"] = text
                        st.session_state["transcript_meta"] = {
                            "video_id": data.get("video_id", ""),
                            "language": data.get("language", ""),
                            "is_generated": data.get("is_generated", False),
                            "segments": len(data.get("segments", [])),
                            "saved_to": str(transcript_path),
                            "chars": len(text),
                        }
                        st.session_state.pop("scene_editor", None)
                        flash("success", f"✅ စာသား ထုတ်ယူပြီးပါပြီ — {len(text):,} စာလုံး · transcript.txt သိမ်းဆည်းပြီး။")
                    except TranscriptError as exc:
                        flash("error", f"❌ {exc}")
                    except Exception as exc:  # noqa: BLE001
                        flash("error", f"❌ မမျှော်လင့်သော ချို့ယွင်းချက် — {exc}")
                st.rerun()

        if st.button("📂 သိမ်းထားသော transcript.txt မှ စာသားဖတ်ရန်", key="btn_load_saved_transcript", use_container_width=True):
            saved_text = transcript_service.load_transcript(transcript_path)
            if saved_text:
                st.session_state["transcript"] = saved_text
                st.session_state["transcript_meta"] = {
                    "language": "saved file",
                    "saved_to": str(transcript_path),
                    "chars": len(saved_text),
                }
                st.session_state.pop("scene_editor", None)
                flash("success", f"✅ transcript.txt မှ စာသား {len(saved_text):,} စာလုံး ဖတ်ယူပြီးပါပြီ။")
            else:
                flash("warning", "⚠️ transcript.txt မတွေ့ပါ (သို့) စာသားအလွတ်ဖြစ်နေပါသည်။")
            st.rerun()

        # ---------------- manual / uploaded transcript ---------------- #
        if manual_mode:
            uploaded = st.file_uploader(
                "စာသားဖိုင် တင်ရန် (.txt / .srt / .vtt)", type=["txt", "srt", "vtt"], key="tr_upload"
            )
            pasted = st.text_area(
                "စာသားကို ဤနေရာတွင် ကူးထည့်ပါ", height=150, key="tr_paste",
                placeholder="ဗီဒီယို၏ မူရင်းစာသားကို ဤနေရာတွင် ကူးထည့်ပါ...",
            )
            if st.button("✅ စာသား အတည်ပြုရန်", key="btn_manual_save", use_container_width=True):
                content = ""
                if uploaded is not None:
                    content = transcript_service.parse_subtitle_content(
                        uploaded.getvalue().decode("utf-8", errors="ignore"), uploaded.name
                    )
                elif pasted.strip():
                    content = transcript_service.clean_transcript_text(pasted)
                if content:
                    st.session_state["transcript"] = content
                    st.session_state["transcript_meta"] = {"language": "manual", "chars": len(content)}
                    transcript_service.save_transcript(content, transcript_path, video_id="", language="manual")
                    st.session_state.pop("scene_editor", None)
                    flash("success", f"✅ စာသား {len(content):,} စာလုံး အတည်ပြုပြီးပါပြီ။")
                else:
                    flash("warning", "⚠️ စာသား မတွေ့ပါ။")
                st.rerun()

        st.markdown("**📝 AI Prompt / ကိုယ်ပိုင်ညွှန်ကြားချက်**")
        st.caption("transcript.txt ထဲရှိစာသားကို ဘယ်လိုပြန်ရေး၊ ဘယ်လိုခွဲ၊ ဘယ်လိုအသံဖတ်စာသားပုံစံလုပ်မည်ကို ဒီနေရာတွင် ရေးပါ။ Gemini mode တွင်သာ အသုံးပြုပါမည်။")
        custom_prompt = st.text_area(
            "သင့် Prompt",
            key="custom_scene_prompt",
            height=120,
            placeholder=(
                "ဥပမာ — မြန်မာစကားပြောသံ သဘာဝကျအောင် ပြန်ရေးပါ။ "
                "ဇာတ်ကွက်တစ်ခုလျှင် ၂ ကြောင်းထက်မပိုစေဘဲ suspense ရှိအောင် ရေးပါ။ "
                "S1, S2, S3 ပုံစံဖြင့်သာ ထုတ်ပေးပါ။"
            ),
            help="မူရင်း system prompt ကို မဖျက်ဘဲ သင့်ညွှန်ကြားချက်ကို ထပ်ပေါင်းပေးပါမည်။",
        )

        # ---------------- AI scene generation ---------------- #
        if ai_clicked:
            transcript = st.session_state.get("transcript", "").strip()
            if not transcript:
                flash("warning", "⚠️ စာသား မရှိသေးပါ။ အရင်ဦးစွာ စာသားထုတ်ယူပါ။")
            else:
                progress_placeholder = st.empty()
                with st.spinner("🤖 AI ဖြင့် ဇာတ်ကွက်များ ဖန်တီးနေသည်..."):
                    try:
                        result = ai_service.generate_scenes(
                            transcript,
                            cfg,
                            progress=lambda msg: progress_placeholder.info(msg),
                            extra_instruction=custom_prompt,
                        )
                        st.session_state["scenes"] = result["scenes"]
                        st.session_state["scenes_raw"] = result["raw"]
                        st.session_state["ai_meta"] = {
                            "provider": result["provider"],
                            "mode": result["mode"],
                            "notes": result["notes"],
                            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
           }
                       st.session_state.pop("scene_editor", None)
                        progress_placeholder.empty()
                        if result["mode"] == "offline":
                            flash("warning", f"⚠️ {result['notes']}")
                        else:
                            flash("success", f"✅ ဇာတ်ကွက် {len(result['scenes'])} ခု ဖန်တီးပြီးပါပြီ။")
                    except AIError as exc:
                        progress_placeholder.empty()
                        flash("error", f"❌ {exc}")
                    except Exception as exc:  # noqa: BLE001
                        progress_placeholder.empty()
                        flash("error", f"❌ မမျှော်လင့်သော ချို့ယွင်းချက် — {exc}")
                st.rerun()

        render_flash()

        # ---------------- current transcript preview ---------------- #
        transcript = st.session_state.get("transcript", "")
        meta = st.session_state.get("transcript_meta", {})
        if transcript:
            stat_cols = st.columns(4)
            stat_cols[0].metric("စာလုံး အရေအတွက်", f"{len(transcript):,}")
            stat_cols[1].metric("ဘာသာစကား", str(meta.get("language") or "—"))
            stat_cols[2].metric("ခန့်မှန်း ကြာချိန်", f"{transcript_service.estimate_duration_minutes(transcript)} မိနစ်")
            stat_cols[3].metric("ဇာတ်ကွက်", f"{len(st.session_state.get('scenes', []))} ခု")

            with st.expander("📄 မူရင်းစာသား (transcript.txt) ကြည့်ရန်", expanded=False):
                st.text_area("မူရင်းစာသား", value=transcript, height=220, key="tr_view", disabled=True)
                st.download_button(
                    "⬇️ transcript.txt ဒေါင်းလုဒ်",
                    data=transcript.encode("utf-8"),
                    file_name="transcript.txt",
                    mime="text/plain",
                    key="dl_transcript",
                )
                if meta.get("saved_to"):
                    st.caption(f"💾 သိမ်းဆည်းထားသည် — {meta['saved_to']}")

        # ---------------- scene list ---------------- #
        scenes = st.session_state.get("scenes", [])
        if scenes:
            ai_meta = st.session_state.get("ai_meta", {})
            provider_label = str(ai_meta.get("provider", "")).upper()
            mode_label = "AI ဘာသာပြန်" if ai_meta.get("mode") == "ai" else "Offline ခွဲထုတ်မှု"
            st.markdown(
                f'<div class="sk-step-sub">🎬 ဇာတ်ကွက် {len(scenes)} ခု · {provider_label} · {mode_label} · '
                f'{ai_meta.get("created_at", "")}</div>',
                unsafe_allow_html=True,
            )
            if ai_meta.get("notes"):
                st.warning(ai_meta["notes"])

            for scene in scenes:
                st.markdown(
                    f'<div class="sk-scene"><div class="sk-scene-tag">{scene["label"]}</div>'
                    f'<div class="sk-scene-text">{scene["text"]}</div></div>',
                    unsafe_allow_html=True,
                )

            with st.expander("✏️ ဇာတ်ကွက်များ တည်းဖြတ်ရန် (S1: … ပုံစံ)", expanded=False):
                edited = st.text_area(
                    "ဇာတ်ကွက် စာသား",
                    value=ai_service.scenes_to_text(scenes),
                    height=320,
                    key="scene_editor",
                    label_visibility="collapsed",
                )
                if st.button("✅ တည်းဖြတ်ချက် အတည်ပြုရန်", key="btn_apply_edit", type="primary"):
                    updated = ai_service.scenes_from_text(edited)
                    if updated:
                        st.session_state["scenes"] = updated
                        st.session_state["scenes_raw"] = ai_service.scenes_to_text(updated)
                        flash("success", f"✅ ဇာတ်ကွက် {len(updated)} ခု အသစ်ပြန်လည် သတ်မှတ်ပြီးပါပြီ။")
                    else:
                        flash("warning", "⚠️ ဇာတ်ကွက် မတွေ့ပါ။")
                    st.rerun()
                st.download_button(
                    "⬇️ ဇာတ်ကွက် စာသားဖိုင် ဒေါင်းလုဒ်",
                    data=ai_service.scenes_to_text(scenes).encode("utf-8"),
                    file_name="scenes.txt",
                    mime="text/plain",
                    key="dl_scenes",
                )
        else:
            st.info("ℹ️ ဇာတ်ကွက်များ မရှိသေးပါ။ စာသားထုတ်ယူပြီး AI ဖြင့် ဇာတ်ကွက် ဖန်တီးပါ။")


# --------------------------------------------------------------------------- #
# Step 2 — TTS control panel
# --------------------------------------------------------------------------- #

def render_step2(cfg: dict, runtime_paths: dict) -> None:
    """Render the voice / pitch / speed / volume control panel with preview."""
    tts_cfg = cfg.get("tts", {})
    output_dir: Path = runtime_paths["output_dir"]

    with st.container(border=True):
        st.markdown('<div class="sk-step-title">၂။ အသံ ထိန်းချုပ်မှု ခုံ (TTS Control Panel)</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="sk-step-sub">အသံရွေးချယ်ပြီး Pitch / Speed / Volume ကို ချိန်ညှိပါ။ '
            "ပြီးလျှင် အသံနမူနာကို နားထောင်စစ်ဆေးပါ။</div>",
            unsafe_allow_html=True,
        )

        voices = tts_service.list_voices()
        current_voice = tts_cfg.get("voice", tts_service.DEFAULT_VOICE)

        col_a, col_b = st.columns([1, 1])
        with col_a:
            st.markdown(
                f'<div class="sk-scene"><div class="sk-scene-tag">🎙️</div>'
                f'<div class="sk-scene-text"><b>{tts_service.voice_display_name(current_voice)}</b><br>'
                f'<span class="sk-hint">လိင်: {tts_service.voice_gender(current_voice)} · '
                f'Engine: {tts_cfg.get("engine", "auto")}</span></div></div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div class="sk-status"><span class="sk-dot on"></span>Pitch: <b>{tts_cfg.get("pitch", 5)}%</b>'
                f' &nbsp;|&nbsp; Speed: <b>{tts_cfg.get("speed", 43)}%</b>'
                f' &nbsp;|&nbsp; Volume: <b>{tts_cfg.get("volume", 16)}%</b>'
                f' &nbsp;|&nbsp; Quality: <b>{tts_service.QUALITY_PROFILES.get(tts_cfg.get("quality", "standard"), tts_service.QUALITY_PROFILES["standard"])["label"]}</b></div>',
                unsafe_allow_html=True,
            )
        with col_b:
            st.markdown('<div class="sk-hint">💡 ဆက်တင်များကို ဘယ်ဘက် Sidebar မှ ချိန်ညှိနိုင်ပါသည်။ '
                        "Speed 40–50% သည် Recap အသံဖတ်ရန် အသင့်တော်ဆုံးဖြစ်သည်။</div>", unsafe_allow_html=True)

        preview_text = st.text_area(
            "အသံနမူနာ အတွက် စာသား (ကိုယ်တိုင် ပြင်နိုင်သည်)",
            value=tts_cfg.get("preview_text", ""),
            height=90,
            key="preview_text",
        )

        preview_col, info_col = st.columns([1, 2])
        if preview_col.button(
            "🔊 အသံနမူနာနားထောင်ရန်", key="btn_preview", use_container_width=True, type="primary"
        ):
            with st.spinner("🔊 အသံနမူနာ ဖန်တီးနေသည်..."):
                try:
                    info = tts_service.preview_voice(
                        preview_text,
                        output_dir,
                        voice=current_voice,
                        pitch=tts_cfg.get("pitch", 5),
                        speed=tts_cfg.get("speed", 43),
                        volume=tts_cfg.get("volume", 16),
                        quality=tts_cfg.get("quality", "standard"),
                        engine=tts_cfg.get("engine", "auto"),
                    )
                    audio_path = Path(info["path"])
                    st.session_state["preview_bytes"] = audio_path.read_bytes()
                    st.session_state["preview_meta"] = {
                        "engine": info.get("engine"),
                        "effects": info.get("effects"),
                        "duration": tts_service.format_duration(info.get("duration")),
                        "voice": tts_service.voice_display_name(current_voice),
                    }
                except TTSError as exc:
                    flash("error", f"❌ {exc}")
                except Exception as exc:  # noqa: BLE001
                    flash("error", f"❌ မမျှော်လင့်သော ချို့ယွင်းချက် — {exc}")
            st.rerun()

        if st.session_state.get("preview_bytes"):
            meta = st.session_state.get("preview_meta", {})
            info_col.markdown(
                f'<div class="sk-status"><span class="sk-dot on"></span>'
                f'{meta.get("voice", "")} · Engine: <b>{meta.get("engine", "")}</b> · '
                f'Effects: <b>{meta.get("effects", "")}</b> · ကြာချိန်: <b>{meta.get("duration", "")}</b></div>',
                unsafe_allow_html=True,
            )
            st.audio(st.session_state["preview_bytes"], format="audio/mp3")
            st.download_button(
                "⬇️ အသံနမူနာ ဒေါင်းလုဒ်",
                data=st.session_state["preview_bytes"],
                file_name="voice_preview.mp3",
                mime="audio/mpeg",
                key="dl_preview",
            )

        render_flash()
       # --------------------------------------------------------------------------- #
# Step 3 — sequential audio generation with a strict confirmation gate
# --------------------------------------------------------------------------- #

def render_step3(cfg: dict, runtime_paths: dict) -> None:
    """Render the confirmation gate and the sequential audio engine."""
    tts_cfg = cfg.get("tts", {})
    output_dir: Path = runtime_paths["output_dir"]
    scenes = st.session_state.get("scenes", [])
    results = st.session_state.get("audio_results", [])

    with st.container(border=True):
        st.markdown('<div class="sk-step-title">၃။ အသံဖိုင် အဆင့်ဆင့် ဖန်တီးခြင်း (Sequential Audio Engine)</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="sk-step-sub">အတည်ပြု ခလုတ်ကို နှိပ်မှသာ အသံဖိုင် ဖန်တီးခြင်း စတင်ပါမည်။ '
            "ဖိုင်များကို outputs/ folder အတွင်း S1.mp3, S2.mp3 … အဖြစ် အစဉ်လိုက် ဖန်တီးပါမည်။</div>",
            unsafe_allow_html=True,
        )

        st.markdown(
            f'<div class="sk-gate">⚠️ <b>အတည်ပြုချက် လိုအပ်သည်</b> — ဇာတ်ကွက် '
            f'<b>{len(scenes)}</b> ခုအတွက် အသံဖိုင် <b>{len(scenes)}</b> ဖိုင် ဖန်တီးပါမည်။ '
            f'အသံ: <b>{tts_service.voice_display_name(tts_cfg.get("voice"))}</b> · '
            f'Pitch {tts_cfg.get("pitch", 5)}% · Speed {tts_cfg.get("speed", 43)}% · Volume {tts_cfg.get("volume", 16)}% · '
            f'Quality {tts_service.QUALITY_PROFILES.get(tts_cfg.get("quality", "standard"), tts_service.QUALITY_PROFILES["standard"])["label"]}</div>',
            unsafe_allow_html=True,
        )

        gate_col, zip_col = st.columns([2, 1])
        start_clicked = gate_col.button(
            "🚀 စာသားမှ အသံဖိုင်သို့ ပြောင်းလဲရန် အသင့်ပါ",
            key="btn_generate",
            type="primary",
            use_container_width=True,
            disabled=not scenes,
        )

        if not scenes:
            st.info("ℹ️ အသံဖိုင် ဖန်တီးရန် အရင်ဦးစွာ ဇာတ်ကွက်များ ဖန်တီးပါ (အဆင့် ၁)။")

        # ---------------- generation ---------------- #
        if start_clicked and scenes:
            progress_bar = st.progress(0, text="အသံဖိုင် ပြောင်းလဲနေသည်... 0%")
            status_line = st.empty()
            started = time.time()

            def on_progress(done: int, total: int, record: dict) -> None:
                percent = int(round(done * 100 / max(total, 1)))
                progress_bar.progress(
                    min(percent, 100), text=f"အသံဖိုင် ပြောင်းလဲနေသည်... {percent}%"
                )
                icon = "✅" if record.get("ok") else "❌"
                detail = (
                    f"{record['label']}.mp3 · {record.get('duration') or 0}s · {record.get('engine') or '-'}"
                    if record.get("ok")
                    else f"{record['label']}.mp3 — {record.get('error')}"
                )
                status_line.markdown(f"{icon} ဇာတ်ကွက် {done}/{total} — {detail}")

            try:
                generated = tts_service.generate_scenes_audio(
                    scenes,
                    output_dir,
                    voice=tts_cfg.get("voice", tts_service.DEFAULT_VOICE),
                    pitch=tts_cfg.get("pitch", 5),
                    speed=tts_cfg.get("speed", 43),
                    volume=tts_cfg.get("volume", 16),
                    quality=tts_cfg.get("quality", "standard"),
                    engine=tts_cfg.get("engine", "auto"),
                    prefix=tts_cfg.get("file_prefix", "S"),
                    overwrite=True,
                    on_progress=on_progress,
                )
                st.session_state["audio_results"] = generated
                st.session_state["audio_signature"] = time.time()
                ok_count = sum(1 for item in generated if item["ok"])
                elapsed = round(time.time() - started, 1)
                progress_bar.progress(100, text="အသံဖိုင် ပြောင်းလဲနေသည်... 100%")
                if ok_count == len(generated):
                    flash("success", f"🎉 အသံဖိုင် {ok_count} ဖိုင် ဖန်တီးပြီးပါပြီ ({elapsed} စက္ကန့်)။")
                else:
                    flash("warning", f"⚠️ ဖိုင် {ok_count}/{len(generated)} ဖိုင် အောင်မြင်ပါသည်။ ကျန်ဖိုင်များကို ပြန်ကြိုးစားပါ။")
            except TTSError as exc:
                flash("error", f"❌ {exc}")
            except Exception as exc:  # noqa: BLE001
                flash("error", f"❌ မမျှော်လင့်သော ချို့ယွင်းချက် — {exc}")
            st.rerun()

        results = st.session_state.get("audio_results", [])

        # ---------------- results ---------------- #
        if results:
            ok_items = [item for item in results if item.get("ok")]
            stat_cols = st.columns(4)
            stat_cols[0].metric("အောင်မြင်သော ဖိုင်", f"{len(ok_items)}/{len(results)}")
            stat_cols[1].metric("စုစုပေါင်း ကြာချိန်", tts_service.format_duration(tts_service.total_duration(ok_items)))
            stat_cols[2].metric("Engine", (ok_items[0].get("engine") if ok_items else "—") or "—")
            stat_cols[3].metric("သိမ်းဆည်းရာ", str(output_dir.name))

            if ok_items:
                zip_bytes = tts_service.build_zip(
                    [item["path"] for item in ok_items], [f"{item['label']}.mp3" for item in ok_items]
                )
                st.download_button(
                    f"📦 အသံဖိုင် {len(ok_items)} ဖိုင် ZIP ဒေါင်းလုဒ်",
                    data=zip_bytes,
                    file_name="shwe_khit_voice_outputs.zip",
                    mime="application/zip",
                    key="dl_zip",
                    use_container_width=True,
                )

            st.markdown('<div class="sk-divider"></div>', unsafe_allow_html=True)

            for item in results:
                row = st.container()
                with row:
                    head, player, action = st.columns([1, 4, 1])
                    if item.get("ok"):
                        head.markdown(
                            f'<div class="sk-scene-tag">{item["label"]}</div>', unsafe_allow_html=True
                        )
                        audio_file = Path(item["path"])
                        if audio_file.exists():
                            player.audio(audio_file.read_bytes(), format="audio/mp3")
                        player.caption(
                            f"⏱ {tts_service.format_duration(item.get('duration'))} · "
                            f"{item.get('size_kb')} KB · {item.get('engine')} · {audio_file.name}"
                        )
                        if audio_file.exists():
                            action.download_button(
                                "⬇️ ဒေါင်းလုဒ်",
                                data=audio_file.read_bytes(),
                                file_name=f"{item['label']}.mp3",
                                mime="audio/mpeg",
                                key=f"dl_{item['label']}",
                                use_container_width=True,
                            )
                    else:
                        head.markdown('<div class="sk-scene-tag" style="background:#FF5C7A">✕</div>', unsafe_allow_html=True)
                        player.error(f"{item['label']} — {item.get('error')}")

            st.markdown('<div class="sk-divider"></div>', unsafe_allow_html=True)
            clean_col, rerun_col = st.columns(2)
            if clean_col.button("🧹 outputs ဖိုင်များ ရှင်းလင်းရန်", key="btn_cleanup", use_container_width=True):
                removed = tts_service.cleanup_outputs(output_dir)
                st.session_state["audio_results"] = []
                st.session_state["preview_bytes"] = None
                flash("info", f"🧹 ဖိုင် {removed} ဖိုင် ရှင်းလင်းပြီးပါပြီ။")
                st.rerun()
            rerun_col.markdown(
                '<div class="sk-hint">🔄 ဆက်တင်ပြောင်းပြီး ပြန်ဖန်တီးလိုပါက '
                "အထက်ရှိ အတည်ပြု ခလုတ်ကို ထပ်မံနှိပ်ပါ — ဖိုင်များ အသစ်ပြန်လည် ဖန်တီးပါမည်။</div>",
                unsafe_allow_html=True,
            )
        else:
            st.caption("📂 ဖန်တီးပြီးသော အသံဖိုင်များကို ဤနေရာတွင် ဖွင့်နားထောင်နိုင်ပြီး ဒေါင်းလုဒ် ရယူနိုင်ပါမည်။")

        render_flash()


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def main() -> None:
    """Compose the whole application."""
    init_state()
    cfg = render_sidebar()
    runtime_paths = paths()

    render_header()
    render_step1(cfg, runtime_paths)
    render_step2(cfg, runtime_paths)
    render_step3(cfg, runtime_paths)
    render_footer()


try:
    main()
except config_service.ConfigError as exc:  # configuration problems are fatal but friendly
    st.error(f"⚙️ ဆက်တင် ဖိုင်ဆိုင်ရာ ချို့ယွင်းချက် — {exc}")
    st.stop()
   
