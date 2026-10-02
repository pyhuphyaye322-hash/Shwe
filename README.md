# 🎙️ Shwe Khit AI Studio / Recap Voice Pro

> **မြန်မာစာသားမှ စကားသံအထိ အလိုအလျောက် ဖန်တီးစနစ်**
> YouTube စာသားထုတ်ယူ → AI ဖြင့် မြန်မာဘာသာပြန် ဇာတ်ကွက်ခွဲ → အသံဖိုင် (S1.mp3, S2.mp3 …) ဖန်တီး

A production-ready **Streamlit** web application with a modern dark theme and a fully
Burmese (မြန်မာ) interface. Built with a clean, modular service layer so every
component can be tested and replaced independently.

![Application UI](docs/ui_top.png)

---

## ✨ အဓိက လုပ်ဆောင်ချက်များ (Features)

| အဆင့် | လုပ်ဆောင်ချက် | ရှင်းလင်းချက် |
|---|---|---|
| **၁** | YouTube စာသားထုတ်ယူခြင်း | `youtube_transcript_api` ဖြင့် စာတန်းထိုး ထုတ်ယူပြီး `transcript.txt` အလိုအလျောက် သိမ်းဆည်း |
| **၁** | AI ဇာတ်ကွက် ဖန်တီးခြင်း | Gemini / OpenAI ဖြင့် မြန်မာဘာသာပြန်ပြီး `S1: … S2: … S3: …` ပုံစံ ဇာတ်ကွက်များ ခွဲထုတ် |
| **၂** | အသံ ထိန်းချုပ်မှု ခုံ | Thiha (သီဟ) / Nilar (နီလာ) အသံရွေးချယ်မှု + Pitch / Speed / Volume slider |
| **၂** | 🔊 အသံနမူနာ | လက်ရှိ ဆက်တင်ဖြင့် နမူနာအသံ ဖန်တီးပြီး audio player တွင် နားထောင် |
| **၃** | အတည်ပြုချက် တံခါး | **ခလုတ်နှိပ်မှသာ** အသံဖိုင် ဖန်တီးခြင်း စတင် — အလိုအလျောက် မစတင်ပါ |
| **၃** | အဆင့်ဆင့် ဖန်တီးခြင်း | `outputs/S1.mp3`, `S2.mp3` … အစဉ်လိုက် ဖန်တီး + Progress bar (`အသံဖိုင် ပြောင်းလဲနေသည်... X%`) |
| **၃** | နားထောင်ခြင်း / ဒေါင်းလုဒ် | ဇာတ်ကွက်တစ်ခုချင်း audio player + MP3 ဒေါင်းလုဒ် + ZIP အစုလိုက် ဒေါင်းလုဒ် |

**အသံ အင်ဂျင် နှစ်မျိုး**

* **Edge Neural (အကြံပြု)** — `my-MM-ThihaNeural` (အမျိုးသား) နှင့် `my-MM-NilarNeural` (အမျိုးသမီး)။ Pitch / Speed / Volume ကို native အနေဖြင့် တိကျစွာ ထိန်းချုပ်နိုင်။
* **gTTS (အရန်)** — Edge မရနိုင်ပါက အလိုအလျောက် ပြောင်းလဲအသုံးပြု။ Pitch / Speed / Volume ကို FFmpeg (`asetrate` + `atempo` + `volume`) ဖြင့် ပြုပြင်။

gTTS အတွက် စာသားကို မြန်မာဝါကျအဆုံး (`။`) နှင့် whitespace အတိုင်း sentence-aware ခွဲပြီး Google request limit အောက်ဖြစ်သော **90 စာလုံးအပိုင်းများ**အဖြစ် တစ်ပိုင်းချင်း generate လုပ်ပါသည်။ အပိုင်းတစ်ခုနှင့်တစ်ခုကြား 0.35 စက္ကန့် ခေတ္တနားပြီး MP3 အပိုင်းများကို FFmpeg ဖြင့် ပြန်ပေါင်းကာ pitch / speed / volume ပြုပြင်ပါသည်။

---

## 📁 Project Structure

```
shwe_khit_ai_studio/
├── app.py                     # Streamlit UI — မြန်မာ dark theme, အဆင့် ၃ ဆင့်
├── config.json                # ဆက်တင်များ (API key, TTS parameters, voice)
├── requirements.txt           # Python dependencies
├── packages.txt               # Streamlit Cloud apt dependency (ffmpeg)
├── README.md                  # ဤဖိုင် — deployment လမ်းညွှန်
├── smoke_test.py              # Service layer စမ်းသပ်မှု (python3 smoke_test.py)
├── .streamlit/
│   └── config.toml            # Dark theme + server ဆက်တင်
├── docs/                      # UI screenshot များ
├── outputs/                   # ဖန်တီးထားသော အသံဖိုင်များ (S1.mp3, S2.mp3 …)
└── services/
    ├── __init__.py
    ├── ai_service.py          # Gemini / OpenAI ဇာတ်ကွက် ဖန်တီးမှု + parser
    ├── config_service.py      # config.json load / save / secrets
    ├── transcript_service.py  # YouTube transcript + ဖိုင် I/O + SRT/VTT parser
    └── tts_service.py         # edge-tts + gTTS, FFmpeg audio effects, ZIP
```

---

## 🚀 ကိုယ်ပိုင် ကွန်ပျူတာတွင် Run ခြင်း (Local)

```bash
git clone https://github.com/<your-username>/shwe_khit_ai_studio.git
cd shwe_khit_ai_studio

python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# FFmpeg (gTTS အင်ဂျင် အသုံးပြုပါက လိုအပ်သည်)
#   Ubuntu/Debian : sudo apt-get install -y ffmpeg
#   macOS         : brew install ffmpeg
#   Windows       : https://www.gyan.dev/ffmpeg/builds/

streamlit run app.py
```

Browser တွင် `http://localhost:8501` ကို ဖွင့်ပါ။

Service layer ကို စမ်းသပ်ရန် (API key မလိုအပ်ပါ):

```bash
python3 smoke_test.py
```

---

## ⚙️ ဆက်တင် ပြင်ဆင်ခြင်း (config.json & Sidebar)

`config.json` ကို တိုက်ရိုက် ပြင်နိုင်သလို **Sidebar** မှလည်း ချိန်ညှိပြီး
**💾 သိမ်းဆည်းရန်** ခလုတ်ဖြင့် ပြန်လည်သိမ်းဆည်းနိုင်ပါသည်။

| Key | Default | ရှင်းလင်းချက် |
|---|---|---|
| `ai.provider` | `gemini` | `gemini` သို့မဟုတ် `openai` |
| `ai.gemini_api_key` | `""` | Google AI Studio API key |
| `ai.gemini_model` | `gemini-3.8-flash` | Gemini model အမည် |
| `ai.openai_api_key` | `""` | OpenAI (သို့) OpenAI-compatible key |
| `ai.openai_model` | `gpt-4o-mini` | OpenAI model အမည် |
| `ai.openai_base_url` | `""` | တခြား compatible endpoint (optional) |
| `ai.max_scene_chars` | `220` | တစ်ဇာတ်ကွက် အများဆုံး စာလုံးအရေအတွက် |
| `ai.allow_offline_fallback` | `true` | AI မရပါက offline ခွဲထုတ်စနစ် သုံး/မသုံး |
| `transcript.preferred_languages` | `["my","en",…]` | စာတန်းထိုး ဘာသာစကား ဦးစားပေးစဉ် |
| `tts.engine` | `auto` | `auto` / `edge` / `gtts` |
| `tts.voice` | `Thiha (သီဟ)` | `Thiha (သီဟ)` သို့မဟုတ် `Nilar (နီလာ)` |
| `tts.quality` | `standard` | Sidebar မှ `economy` (64 kbps) / `standard` (128 kbps) / `high` (192 kbps) |
| `tts.pitch` | `5` | 0–100 (%) |
| `tts.speed` | `43` | 0–100 (%) — Recap အသံဖတ်ရန် 40–50% အသင့်တော်ဆုံး |
| `tts.volume` | `16` | 0–100 (%) |
| `tts.output_dir` | `outputs` | အသံဖိုင် သိမ်းဆည်းမည့် folder |
| `tts.file_prefix` | `S` | ဖိုင်အမည် ရှေ့ဆက် (S1.mp3, S2.mp3 …) |

**API Key ရယူရန်**

* Gemini — <https://aistudio.google.com/app/apikey>
* OpenAI — <https://platform.openai.com/api-keys>

---

## 🌐 GitHub သို့ တင်ခြင်း (Push to GitHub)

```bash
cd shwe_khit_ai_studio
git init
git add .
git commit -m "feat: Shwe Khit AI Studio / Recap Voice Pro (Burmese TTS web app)"
git branch -M main
git remote add origin https://github.com/<your-username>/shwe_khit_ai_studio.git
git push -u origin main
```

> ⚠️ **အရေးကြီး** — API Key များကို `config.json` တွင် ထည့်ပြီး commit မတင်ပါနှင့်။
> `.gitignore` တွင် `outputs/`, `transcript.txt`, `*.mp3`, `.streamlit/secrets.toml` ကို ဖယ်ထားပြီးဖြစ်သည်။
> Key များကို **Streamlit Secrets** ဖြင့် ထည့်သွင်းပါ။

---

## ☁️ Streamlit Cloud တွင် Deploy လုပ်ခြင်း

1. <https://share.streamlit.io> သို့ ဝင်ပြီး **GitHub အကောင့်ဖြင့်** ချိတ်ဆက်ပါ။
2. **“New app”** → **“Deploy a public app from GitHub”** ကို ရွေးပါ။
3. အောက်ပါအတိုင်း ဖြည့်ပါ:

   | Field | တန်ဖိုး |
   |---|---|
   | Repository | `<your-username>/shwe_khit_ai_studio` |
   | Branch | `main` |
   | **Main file path** | `app.py` |
   | App URL | လိုချင်သော subdomain (ဥပမာ `shwe-khit-ai-studio`) |

4. **“Advanced settings…”** → **Secrets** တွင် အောက်ပါအတိုင်း ထည့်ပါ (TOML ပုံစံ):

   ```toml
   GEMINI_API_KEY = "AIza...your-gemini-key..."
   OPENAI_API_KEY = "sk-...your-openai-key..."
   ```

   > App သည် `st.secrets` မှ key များကို အလိုအလျောက် ဖတ်ယူပါမည် (Sidebar တွင် 🔒 အမှတ်အသား ပြပါမည်)။

5. **Deploy!** ကို နှိပ်ပါ။ ပထမဆုံး build အတွက် ၂–၅ မိနစ် ကြာနိုင်ပါသည်။
6. `packages.txt` တွင် `ffmpeg` ပါရှိပြီးဖြစ်၍ Streamlit Cloud သည် FFmpeg ကို အလိုအလျောက်
   ထည့်သွင်းပေးပါမည် (gTTS အင်ဂျင်၏ Pitch/Speed/Volume ပြုပြင်မှုအတွက် လိုအပ်သည်)။

### Deploy ပြီးနောက် စစ်ဆေးရန်

* Sidebar → **🩺 စနစ် အခြေအနေ** တွင် Edge / gTTS / FFmpeg အားလုံး **အသင့်** ဖြစ်နေရမည်။
* Sidebar → **🔌 AI ချိတ်ဆက်မှု စမ်းသပ်ရန်** နှိပ်ပြီး ချိတ်ဆက်မှု အောင်မြင်ကြောင်း စစ်ပါ။
* အဆင့် ၁ တွင် YouTube လင့်ခ်တစ်ခု ထည့်ပြီး စာသားထုတ်ယူကြည့်ပါ။

---

## 🩺 ပြဿနာ ဖြေရှင်းခြင်း (Troubleshooting)

| ပြဿနာ | အကြောင်းရင်း / ဖြေရှင်းနည်း |
|---|---|
| `ဤဗီဒီယိုအတွက် စာတန်းထိုး (caption) မရနိုင်ပါ` | ဗီဒီယိုတွင် caption မရှိခြင်း၊ သို့မဟုတ် YouTube မှ cloud IP ကို ပိတ်ထားခြင်း။ **“စာသားကို ကိုယ်တိုင်ထည့်ရန်”** ကို အသုံးပြုပြီး `.srt` / `.txt` တင်နိုင်ပါသည်။ |
| Edge အသံ မထွက်ခြင်း | Internet ပိတ်ထားခြင်း သို့မဟုတ် `edge-tts` မထည့်ရသေးခြင်း။ App သည် **gTTS** သို့ အလိုအလျောက် ပြောင်းပါမည် (`tts.engine = auto`)。 |
| အသံဖိုင် ပြောင်းလဲမှု နှေးခြင်း | Edge Neural အသံသည် gTTS ထက် အနည်းငယ် နှေးသည်။ `outputs/` ရှိ ဖိုင်များကို ပြန်လည်အသုံးပြုနိုင်ရန် ဖိုင်များ မဖျက်ပါနှင့်။ |
| `Gemini API ခေါ်ယူမှု မအောင်မြင်ပါ` | API Key မှန်ကန်မှု၊ quota နှင့် model အမည်ကို စစ်ပါ။ မရပါက `allow_offline_fallback` ဖြင့် ဆက်လုပ်နိုင်ပါသည်။ |
| `ffmpeg: command not found` | `sudo apt-get install -y ffmpeg` (local)၊ Streamlit Cloud တွင် `packages.txt` ရှိကြောင်း စစ်ပါ။ |
| မြန်မာစာ ပုံပျက်ခြင်း | Browser တွင် Noto Sans Myanmar font ရနိုင်ကြောင်း စစ်ပါ (App သည် Google Fonts မှ အလိုအလျောက် ဆွဲချပါသည်)။ |

---

## 🧱 နည်းပညာ (Tech Stack)

`Python 3.11+` · `Streamlit` · `youtube-transcript-api` · `google-generativeai` ·
`openai` · `edge-tts` · `gTTS` · `pydub` · `FFmpeg`

---

## 📜 License

MIT — လွတ်လပ်စွာ အသုံးပြု၊ ပြင်ဆင်၊ ဖြန့်ဝေနိုင်ပါသည်။
