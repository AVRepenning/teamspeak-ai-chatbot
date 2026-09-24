# 🎙️ Jimmy — Autonomous TeamSpeak AI Voice Bot

An autonomous, low-latency, self-hosted Danish voice chatbot designed to live in your TeamSpeak voice channel. Jimmy continuously monitors channel audio, detects when he is addressed, transcribes the spoken Danish question, queries an AI intelligence engine, and speaks his reply back into the channel in Danish.

---

## 🚀 Key Features

* **Hands-Free Autonomous Pipeline:** No manual "Enter-to-record" keys. Jimmy streams channel audio in real time with continuous Voice Activity Detection (VAD) and trailing silence segmentation.
* **Local Danish Speech Recognition (STT):** Powered by `faster-whisper` running locally on CPU (`int8`), seeded with acoustic prompt biasing (`initial_prompt="Hej Jimmy! Her er Jimmy i TeamSpeak."`) for rapid, high-accuracy Danish transcription.
* **Resilient Smart Trigger Detection:**
  * Triggers on any natural greeting: *"Hej Jimmy"*, *"Hey Jimmy"*, *"Dav Jimmy"*, *"Hallo Jimmy"*, *"Øh hej Jimmy"*.
  * Triggers on just his name: *"Jimmy, hvad synes du?"*.
  * Handles phonetic variations (`Jimmy`, `Jimi`, `Jimmie`, `Jamie`, `Gimmy`, `Jensen`).
  * **Completely ignores normal gaming chatter** when his name is not called.
* **Instant Audio Chime (Earcon):** Plays a subtle, pleasant two-tone acknowledgment chime (*ding-ding*) the millisecond he hears his name, giving immediate feedback that he is listening and processing.
* **Pluggable Multi-Backend AI Engine:**
  * **OpenRouter:** Blazing fast cloud intelligence (`google/gemini-2.5-flash`, `openai/gpt-4o-mini`, `anthropic/claude-3.5-haiku`, etc.) with sub-second response times.
  * **Local LM Studio:** 100% private, self-hosted, offline AI running on your own PC via `http://localhost:1234/v1`.
  * **OpenAI API:** Direct integration with GPT-4o-mini and OpenAI TTS voices (`fable`, `echo`, `onyx`, `alloy`).
  * **Automatic Failover:** If a primary cloud engine is unreachable or out of quota, Jimmy automatically falls back to your local LM Studio without dropping the question or crashing.
* **Echo-Free Audio Isolation:** Isolated virtual audio topology using Voicemeeter and VB-CABLE with software mute-locks during speech playback, ensuring zero feedback loops and zero bleed with your personal microphone or desktop audio.

---

## 🎧 Audio Architecture & Signal Routing

```
                     +---------------------------------------+
                     |        TeamSpeak Voice Channel        |
                     +---------------------------------------+
                            | (Channel Voice)     ^ (Jimmy's Voice)
                            v                     |
              +----------------------------+  +----------------------------+
              |   Voicemeeter Virtual In   |  |   CABLE Output (VB-Audio)  |
              | (TS3 Playback Destination) |  |   (TS3 Capture Device)     |
              +----------------------------+  +----------------------------+
                            | (Bus B1)            ^ (Virtual Wire)
                            v                     |
              +----------------------------+  +----------------------------+
              |    Voicemeeter Out B1      |  |    CABLE Input (VB-Audio)  |
              |    (Python Audio Source)   |  |    (Python Audio Sink)     |
              +----------------------------+  +----------------------------+
                            |                             ^
                            v                             |
+---------------------------------------------------------------------------------------+
|  JIMMY VOICE BOT PIPELINE (autonomous_bot.py)                                        |
|                                                                                       |
|  1. Continuous Audio Ingestion (44.1 kHz, ring buffer with 500ms pre-roll)            |
|  2. Voice Activity Detection (Energy & trailing silence segmentation)                 |
|  3. Local Danish Whisper STT (CPU int8, prompt biased to "Hej Jimmy")                 |
|  4. Smart Trigger Matcher ("Hey Jimmy", "Hej Jimmy", "Jimmy ...")                     |
|  5. Instant Audio Chime Feedback (plays acknowledgment chime into channel)             |
|  6. AI Engine (OpenRouter / Local LM Studio / OpenAI / Gemini)                        |
|  7. Danish TTS Synthesis (da-DK-JeppeNeural / OpenAI Fable)                           |
|  8. Echo-Free Playback into CABLE Input (drops incoming audio while speaking)         |
+---------------------------------------------------------------------------------------+
```

---

## 🛠️ Prerequisites

1. **Windows 10 / 11**
2. **TeamSpeak 3 Client** (used as the dedicated bot instance alongside your main TeamSpeak 6 client).
3. **VB-Audio Virtual Cable (VB-CABLE)**
4. **VB-Audio Voicemeeter**
5. **Python 3.10+** (recommended: Python 3.12 managed via `uv`)

---

## ⚙️ Quick Setup Guide

### 1. TeamSpeak 3 Client Configuration
In your TeamSpeak 3 Client, open **Tools &rarr; Options** (`Alt + P`):
* **Playback:** Set **Playback Device** to:  
  `Voicemeeter Input (VB-Audio Voicemeeter VAIO)`
* **Capture:** Set **Capture Device** to:  
  `CABLE Output (VB-Audio Virtual Cable)`  
  Set transmission to **Continuous Transmission** (or Voice Activation at `-50 dB`).

### 2. Voicemeeter Setup
In Voicemeeter on your desktop:
* Under the **VIRTUAL INPUTS** section (*Voicemeeter VAIO*), click the **`B`** (or `B1`) button so it turns **green**. This routes channel audio into `Voicemeeter Out B1` for Python.

### 3. Environment Configuration
Copy `.env.example` to `.env`:
```powershell
Copy-Item .env.example .env
```
Open `.env` and configure your preferred provider:
```env
# OpenRouter (Recommended)
OPENROUTER_API_KEY=sk-or-v1-your-key-here
OPENROUTER_MODEL=google/gemini-2.5-flash

# Local LM Studio (Optional 100% offline)
LM_STUDIO_URL=http://localhost:1234/v1

# OpenAI API (Optional)
OPENAI_API_KEY=sk-proj-your-key-here
OPENAI_VOICE=fable
```

### 4. Install Dependencies
```powershell
uv venv .venv --python 3.12
.venv\Scripts\activate
uv pip install numpy scipy sounddevice faster-whisper requests edge-tts av
```

---

## ▶️ Running Jimmy

Start Jimmy with a single command:
```powershell
.\start_jimmy.bat
```
or directly via Python:
```powershell
.venv\Scripts\python.exe -u autonomous_bot.py
```

Once running, Jimmy will automatically verify the connection, monitor the voice channel, and respond whenever you address him!

---

## 🧹 Project Inventory & Total Cleanup

This project strictly documents every file, registry entry, and driver. To see the complete list or wipe all traces from the computer:
* See [`PROJECT-INVENTORY-AND-CLEANUP.md`](PROJECT-INVENTORY-AND-CLEANUP.md) for the single-command wipeout script.

---

## 📄 License
MIT License.
