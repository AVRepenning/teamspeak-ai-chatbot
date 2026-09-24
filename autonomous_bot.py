"""Autonomous TeamSpeak Voice Bot - Jimmy.

Listens on Voicemeeter Out B1, detects Danish speech,
checks for trigger words ('Hey Jimmy', 'Hej Jimmy', 'Hey Jensen', 'Hej Jensen', 'Hey Bot', 'Hej Bot'),
queries local LM Studio (http://localhost:1234/v1) or Gemini fallback without system prompt,
and speaks replies into CABLE Input (TeamSpeak 3 virtual mic).
"""
import asyncio
import collections
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
SILENCE_DURATION = 0.8  # Seconds of silence to trigger end-of-speech
MIN_SPEECH_DURATION = 0.6  # Ignore clicks shorter than this
MAX_SPEECH_DURATION = 15.0  # Cap on question length

LM_STUDIO_URL = os.getenv("LM_STUDIO_URL", "http://localhost:1234/v1")

# Load .env if present
env_file = Path(__file__).parent / ".env"
if env_file.is_file():
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


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


def directed(text):
    """Check for wake word and return the user's question."""
    text = text.strip()
    match = re.match(r"^(?:hey|hej)[\s,\-]+(?:jimmy|jensen|bot)\b(?!\s+sama)", text, re.IGNORECASE)
    return text[match.end():].lstrip(" ,:!?") if match else ""


def ask_lm_studio(question, history, url=LM_STUDIO_URL):
    """Query local LM Studio OpenAI-compatible endpoint without system prompt."""
    messages = []
    for h in history[-6:]:
        messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": question})

    payload = {
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 250,
        "stream": False,
    }
    r = requests.post(f"{url.rstrip('/')}/chat/completions", json=payload, timeout=60)
    r.raise_for_status()
    data = r.json()
    answer = data["choices"][0]["message"]["content"].strip()
    history.extend([{"role": "user", "content": question}, {"role": "assistant", "content": answer}])
    return answer


def ask_gemini(question, history, key, model="gemini-2.5-flash"):
    """Query Gemini 2.5 Flash without custom system prompt."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    contents = []
    for h in history[-6:]:
        role = "model" if h["role"] == "assistant" else "user"
        contents.append({"role": role, "parts": [{"text": h["content"]}]})
    contents.append({"role": "user", "parts": [{"text": question}]})
    payload = {
        "contents": contents,
        "generationConfig": {
            "maxOutputTokens": 300,
            "thinkingConfig": {"thinkingBudget": 0},
            "temperature": 0.7,
        },
    }
    r = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=15)
    r.raise_for_status()
    answer = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    history.extend([{"role": "user", "content": question}, {"role": "assistant", "content": answer}])
    return answer


def ask_ai(question, history):
    """Try local LM Studio first, fall back to Gemini if LM Studio is offline."""
    try:
        ans = ask_lm_studio(question, history)
        return ans, "LM Studio (Local)"
    except Exception as lm_err:
        gemini_key = os.getenv("GEMINI_API_KEY")
        if gemini_key:
            try:
                ans = ask_gemini(question, history, gemini_key)
                return ans, "Gemini 2.5 Flash (Fallback)"
            except Exception as gem_err:
                raise RuntimeError(f"Both LM Studio ({lm_err}) and Gemini ({gem_err}) failed.")
        raise RuntimeError(f"LM Studio is not reachable at {LM_STUDIO_URL} ({lm_err})")


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
    print("=" * 60)
    print("  JIMMY - AUTONOMOUS TEAMSPEAK VOICE BOT (LOCAL AI READY)")
    print("=" * 60)
    ensure_ts3_connected()

    in_dev, out_dev = find_audio_devices()
    if in_dev is None or out_dev is None:
        sys.exit(f"Error: Required audio devices not found. (In: {in_dev}, Out: {out_dev})")
    print(f"Audio Source (Hearing): device {in_dev} ({sd.query_devices(in_dev)['name']})")
    print(f"Audio Sink   (Speaking): device {out_dev} ({sd.query_devices(out_dev)['name']})")

    # Check AI backend status
    try:
        r = requests.get(f"{LM_STUDIO_URL.rstrip('/')}/models", timeout=1.0)
        if r.status_code == 200:
            print(f"AI Backend: LM Studio ACTIVE at {LM_STUDIO_URL} (100% Local)")
        else:
            print(f"AI Backend: LM Studio returned HTTP {r.status_code}")
    except Exception:
        print(f"AI Backend: LM Studio not detected on port 1234. (Will use Gemini fallback if running)")

    print("Loading local Danish Whisper model...")
    model = WhisperModel("small", device="cpu", compute_type="int8", download_root=r"D:\AI\cache\whisper")
    print("Whisper STT ready on CPU int8.")

    # Rolling ring buffer for pre-roll (500ms)
    chunk_size = int(0.1 * AUDIO_RATE)  # 100ms frames
    pre_roll_chunks = int(0.5 / 0.1)
    pre_roll_buffer = collections.deque(maxlen=pre_roll_chunks)

    history = []
    is_speaking = False

    print("\n>>> JIMMY IS LIVE AND LISTENING IN THE CHANNEL! <<<")
    print("Call him with: 'Hej Jimmy, ...' or 'Hey Jimmy, ...'")
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
                    continue  # Ignore input while bot speaks
                rms = float(np.sqrt(np.mean(np.square(frame))))
                pre_roll_buffer.append(frame)
                if rms >= VAD_THRESHOLD:
                    # Speech started!
                    speech_frames.extend(pre_roll_buffer)
                    break

            # 2. Accumulate speech until silence
            print("[Lytter til tale...]", end="\r", flush=True)
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

            # Check total duration
            clip = np.concatenate(speech_frames).squeeze()
            duration = len(clip) / AUDIO_RATE
            if duration < MIN_SPEECH_DURATION:
                continue

            # 3. Transcribe with Whisper
            speech_16k = resample_poly(clip, STT_RATE, AUDIO_RATE).astype(np.float32)
            t0 = time.time()
            segs, _ = model.transcribe(speech_16k, language="da", vad_filter=True)
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

            # 5. Query AI Backend (LM Studio local default)
            t_ai = time.time()
            try:
                answer, provider = ask_ai(question, history)
                ai_time = time.time() - t_ai
                print(f"[Jimmy ({provider}, {ai_time:.2f}s)]: \"{answer}\"")
            except Exception as e:
                print(f"Fejl fra AI: {e}")
                continue

            # 6. Speak reply into channel
            is_speaking = True
            try:
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
