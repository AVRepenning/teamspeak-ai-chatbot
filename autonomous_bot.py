"""Autonomous TeamSpeak Voice Bot - Jimmy.

Features:
- Whisper STT with acoustic keyword biasing (initial_prompt="Hej Jimmy!")
- Smart flexible wake-word detection (supports greetings, bare name, and phonetic variants)
- Instant subtle audio chime upon detecting his name
- OpenRouter AI (Google Gemini 2.5 Flash / OpenAI / Claude) with LM Studio & Gemini fallback
- High-quality Danish speech synthesis into TeamSpeak 3
- Echo-free audio isolation
"""
import asyncio
import collections
import io
import os
import re
import socket
import sys
import time
from pathlib import Path

import av
import edge_tts
import numpy as np
import requests
from scipy.signal import resample_poly
import sounddevice as sd
from faster_whisper import WhisperModel

AUDIO_RATE = 44100
STT_RATE = 16000
VAD_THRESHOLD = 0.005  # Calibrated for Voicemeeter Out B1
SILENCE_DURATION = 0.7  # Seconds of silence to trigger end-of-speech
MIN_SPEECH_DURATION = 0.5  # Ignore clicks shorter than this
MAX_SPEECH_DURATION = 15.0  # Cap on question length

# Load .env if present
env_file = Path(__file__).parent / ".env"
if env_file.is_file():
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemini-2.5-flash")
LM_STUDIO_URL = os.getenv("LM_STUDIO_URL", "http://localhost:1234/v1")


def generate_chime(rate=AUDIO_RATE):
    """Generate a subtle, pleasant two-tone acknowledgment chime (0.2s)."""
    t1 = np.linspace(0, 0.08, int(0.08 * rate), False)
    t2 = np.linspace(0, 0.12, int(0.12 * rate), False)
    c1 = 0.15 * np.sin(2 * np.pi * 587.33 * t1) * np.linspace(1, 0.3, len(t1))
    c2 = 0.15 * np.sin(2 * np.pi * 880.00 * t2) * np.linspace(1, 0.0, len(t2))
    return np.concatenate([c1, c2]).astype(np.float32)


CHIME_AUDIO = generate_chime()


def ensure_ts3_connected():
    """Verify TeamSpeak 3 is running and Jimmy is connected to the server."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(2.0)
        s.connect(("127.0.0.1", 25639))
        s.recv(1024)
        s.sendall(b"auth apikey=5O78-MMZ0-V0TI-7WC0-78NP-WRD0\n")
        s.recv(1024)
        s.sendall(b"clientlist\n")
        time.sleep(0.2)
        resp = s.recv(4096).decode("utf-8")
        if "Jimmy" not in resp:
            print("Connecting Jimmy to TeamSpeak server...")
            s.sendall(b"connect address=192.168.0.63:9987 nickname=Jimmy\n")
            time.sleep(1.0)
        s.close()
        print("TeamSpeak 3 client: Ready (Jimmy connected)")
    except Exception as e:
        print(f"Notice: TS3 ClientQuery check ({e})")


def find_audio_devices():
    """Find MME endpoints for Voicemeeter Out B1 (input) and CABLE Input (output)."""
    input_dev = None
    output_dev = None
    for i, d in enumerate(sd.query_devices()):
        name = d["name"].lower()
        api = sd.query_hostapis(d["hostapi"])["name"]
        if "voicemeeter out b1" in name and d["max_input_channels"] > 0:
            if api == "MME":
                input_dev = i
            elif input_dev is None:
                input_dev = i
        if "cable input" in name and d["max_output_channels"] > 0:
            if api == "MME":
                output_dev = i
            elif output_dev is None:
                output_dev = i
    return input_dev, output_dev


def clean_for_tts(text):
    """Clean text for speech synthesis and console display."""
    if not text:
        return ""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"[*_#`~]", "", text)
    text = re.sub(r"[\U00010000-\U0010ffff]", "", text)
    text = re.sub(r"[\u2600-\u27bf]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def directed(text):
    """Smart, resilient trigger detection for Jimmy.
    
    Accepts 'Jimmy' (or phonetic spellings 'Jimi', 'Jimmie', 'Jamie', 'Gimmy', 'Jensen')
    anywhere in the first 4 words, with or without Danish greetings.
    """
    text = text.strip()
    words = text.split()
    if not words:
        return ""
    
    target_idx = -1
    name_patterns = [r"^jimm?y$", r"^jimi$", r"^jimmie$", r"^jamie$", r"^gimm?y$", r"^jensen$"]
    for i in range(min(5, len(words))):
        clean_word = re.sub(r"[^\w]", "", words[i].lower())
        if any(re.match(p, clean_word) for p in name_patterns):
            target_idx = i
            break
            
    if target_idx != -1:
        prefix_words = [re.sub(r"[^\w]", "", w.lower()) for w in words[:target_idx]]
        allowed_prefixes = {"hey", "hej", "dav", "davs", "hallo", "yo", "hi", "god", "goddag", "mojn", "øh", "øhm", "hør", "så"}
        if all(w in allowed_prefixes for w in prefix_words):
            question = " ".join(words[target_idx + 1:]).lstrip(" ,:!?.-")
            return question if question else "Hvad så?"
            
    return ""


def ask_openrouter(question, history, key=OPENROUTER_KEY, model=OPENROUTER_MODEL):
    """Query OpenRouter API for lightning-fast multi-model replies."""
    messages = []
    for h in history[-6:]:
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": question})

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://teamspeak.bot",
        "X-Title": "Jimmy TeamSpeak Bot",
    }
    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": 250,
        "temperature": 0.7,
    }
    r = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=15)
    r.raise_for_status()
    raw = r.json()["choices"][0]["message"]["content"].strip()
    answer = clean_for_tts(raw)
    history.extend([{"role": "user", "content": question}, {"role": "assistant", "content": answer}])
    return answer


def ask_lm_studio(question, history, url=LM_STUDIO_URL):
    """Query local LM Studio OpenAI-compatible endpoint."""
    messages = []
    for h in history[-6:]:
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": question})

    payload = {
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 800,
        "stream": False,
    }
    r = requests.post(f"{url.rstrip('/')}/chat/completions", json=payload, timeout=60)
    r.raise_for_status()
    data = r.json()
    msg = data["choices"][0]["message"]
    raw_answer = msg.get("content") or ""
    answer = clean_for_tts(raw_answer)
    if not answer and msg.get("reasoning_content"):
        answer = clean_for_tts(msg["reasoning_content"])
    if not answer:
        answer = "Ja, jeg lytter! Hvad kan jeg hjælpe med?"

    history.extend([{"role": "user", "content": question}, {"role": "assistant", "content": answer}])
    return answer


def ask_ai(question, history):
    """Route question to best available provider (OpenRouter -> LM Studio -> Gemini)."""
    if OPENROUTER_KEY:
        try:
            ans = ask_openrouter(question, history)
            return ans, f"OpenRouter ({OPENROUTER_MODEL})"
        except Exception as e:
            print(f"[OpenRouter notice ({e}) - trying LM Studio]")

    try:
        ans = ask_lm_studio(question, history)
        return ans, "LM Studio (Local)"
    except Exception as lm_err:
        gemini_key = os.getenv("GEMINI_API_KEY")
        if gemini_key:
            try:
                # Direct Gemini fallback
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={gemini_key}"
                contents = [{"role": "user", "parts": [{"text": question}]}]
                r = requests.post(url, json={"contents": contents}, headers={"Content-Type": "application/json"}, timeout=15)
                raw = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                ans = clean_for_tts(raw)
                return ans, "Gemini 2.5 Flash"
            except Exception:
                pass
        raise RuntimeError(f"All AI backends failed: {lm_err}")


async def synthesize_speech(text, voice="da-DK-JeppeNeural"):
    """Convert Danish text to audio frames via edge-tts."""
    comm = edge_tts.Communicate(text, voice)
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        tmp_name = tmp.name
    try:
        await comm.save(tmp_name)
        chunks = []
        resampler = av.AudioResampler(format="flt", layout="mono", rate=AUDIO_RATE)
        with av.open(tmp_name) as container:
            for frame in container.decode(audio=0):
                for converted in resampler.resample(frame):
                    chunks.append(converted.to_ndarray().reshape(-1))
            for converted in resampler.resample(None):
                chunks.append(converted.to_ndarray().reshape(-1))
        return np.concatenate(chunks).astype(np.float32) if chunks else np.array([], dtype=np.float32)
    finally:
        if os.path.exists(tmp_name):
            try:
                os.remove(tmp_name)
            except OSError:
                pass


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    print("=" * 60)
    print("  JIMMY - HIGH-PERFORMANCE TEAMSPEAK VOICE BOT")
    print("=" * 60)
    ensure_ts3_connected()

    in_dev, out_dev = find_audio_devices()
    if in_dev is None or out_dev is None:
        sys.exit(f"Error: Required audio devices not found. (In: {in_dev}, Out: {out_dev})")
    print(f"Audio Source (Hearing): device {in_dev} ({sd.query_devices(in_dev)['name']})")
    print(f"Audio Sink   (Speaking): device {out_dev} ({sd.query_devices(out_dev)['name']})")

    if OPENROUTER_KEY:
        print(f"AI Engine: OpenRouter [{OPENROUTER_MODEL}]")
    else:
        print("AI Engine: Local LM Studio fallback")

    print("Loading local Danish Whisper model with acoustic prompt bias...")
    model = WhisperModel("small", device="cpu", compute_type="int8", download_root=r"D:\AI\cache\whisper")
    print("Whisper STT ready.")

    chunk_size = int(0.1 * AUDIO_RATE)  # 100ms frames
    pre_roll_chunks = int(0.5 / 0.1)
    pre_roll_buffer = collections.deque(maxlen=pre_roll_chunks)

    history = []
    is_speaking = False

    print("\n>>> JIMMY IS LIVE AND LISTENING! <<<")
    print("Call him with: 'Hej Jimmy', 'Hey Jimmy', 'Jimmy ...' (with instant audio chime)")
    print("Press Ctrl+C to stop.\n")

    stream = sd.InputStream(device=in_dev, channels=1, samplerate=AUDIO_RATE, dtype="float32")
    stream.start()

    try:
        while True:
            # 1. Wait for speech onset
            speech_frames = []
            while True:
                frame, _ = stream.read(chunk_size)
                if is_speaking:
                    continue
                rms = float(np.sqrt(np.mean(np.square(frame))))
                pre_roll_buffer.append(frame)
                if rms >= VAD_THRESHOLD:
                    speech_frames.extend(pre_roll_buffer)
                    break

            # 2. Accumulate speech until silence
            print("[Lytter...]", end="\r", flush=True)
            silence_chunks = 0
            max_silence_chunks = int(SILENCE_DURATION / 0.1)
            max_total_chunks = int(MAX_SPEECH_DURATION / 0.1)

            while True:
                frame, _ = stream.read(chunk_size)
                speech_frames.append(frame)
                rms = float(np.sqrt(np.mean(np.square(frame))))
                if rms < VAD_THRESHOLD:
                    silence_chunks += 1
                    if silence_chunks >= max_silence_chunks:
                        break
                else:
                    silence_chunks = 0

                if len(speech_frames) >= max_total_chunks:
                    break

            clip = np.concatenate(speech_frames).squeeze()
            duration = len(clip) / AUDIO_RATE
            if duration < MIN_SPEECH_DURATION:
                continue

            # 3. Transcribe with Whisper (biased with initial_prompt)
            speech_16k = resample_poly(clip, STT_RATE, AUDIO_RATE).astype(np.float32)
            t0 = time.time()
            segs, _ = model.transcribe(
                speech_16k,
                language="da",
                vad_filter=True,
                beam_size=1,
                initial_prompt="Hej Jimmy! Her er Jimmy i TeamSpeak.",
            )
            text = " ".join(s.text.strip() for s in segs).strip()
            stt_time = time.time() - t0

            if not text:
                continue

            print(f"[Hørt ({duration:.1f}s, STT {stt_time:.2f}s)]: \"{text}\"")

            # 4. Check trigger phrase
            question = directed(text)
            if not question:
                continue

            print(f">>> Henvendt til Jimmy: \"{question}\"")

            # 5. Play instant chime acknowledging name
            is_speaking = True
            sd.play(CHIME_AUDIO, samplerate=AUDIO_RATE, device=out_dev)

            # 6. Query AI in parallel
            t_ai = time.time()
            try:
                answer, provider = ask_ai(question, history)
                ai_time = time.time() - t_ai
                print(f"[Jimmy ({provider}, {ai_time:.2f}s)]: \"{answer}\"")
            except Exception as e:
                print(f"Fejl fra AI: {e}")
                is_speaking = False
                continue

            # 7. Speak reply into channel
            try:
                sd.wait()  # Wait for chime to finish
                audio_reply = asyncio.run(synthesize_speech(answer))
                if len(audio_reply) > 0:
                    sd.play(audio_reply, samplerate=AUDIO_RATE, device=out_dev, blocking=True)
            except Exception as e:
                print(f"Fejl ved taleafspilning: {e}")
            finally:
                time.sleep(0.2)
                pre_roll_buffer.clear()
                is_speaking = False
                print("[Klar til nyt spørgsmål]\n")

    except KeyboardInterrupt:
        print("\nJimmy stopper...")
    finally:
        stream.stop()
        stream.close()
        print("Bot stoppet pænt.")


if __name__ == "__main__":
    main()
