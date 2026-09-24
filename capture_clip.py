"""Consent-only, one-shot capture from Neuro's isolated TeamSpeak return.

Never starts a recording until Enter. Saves at most twenty-five seconds locally; no
Hermes request, transcription, or playback. Delete the WAV after diagnosis.
"""
import argparse
import os
import tempfile
from pathlib import Path

import numpy as np
from scipy.io import wavfile

from bot import AUDIO_RATE, find_device, record, validate_devices


def scratch_directory():
    local_appdata = os.getenv('LOCALAPPDATA')
    if not local_appdata:
        raise ValueError('LOCALAPPDATA mangler.')
    path = Path(local_appdata) / 'hermes' / 'cache' / 'scratch'
    if not path.is_dir():
        raise ValueError('Hermes scratch-mappen findes ikke.')
    return path


def save_clip(samples, directory):
    """Store a bounded mono float WAV only inside the designated scratch dir."""
    samples = np.asarray(samples)
    if samples.ndim != 1 or not 0 < samples.size <= 25 * AUDIO_RATE:
        raise ValueError('Optagelsen skal være mono og højst 25 sekunder.')
    scratch = Path(directory)
    if not scratch.is_dir():
        raise ValueError('Scratch-mappen findes ikke.')
    fd, filename = tempfile.mkstemp(prefix='neuro_clip_', suffix='.wav', dir=scratch)
    os.close(fd)
    path = Path(filename)
    try:
        wavfile.write(path, AUDIO_RATE, samples.astype(np.float32))
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path


def main():
    p = argparse.ArgumentParser(description='Én aftalt lokal Neuro-lydprøve; ingen svar.')
    p.add_argument('--seconds', type=int, default=5)
    args = p.parse_args()
    if not 1 <= args.seconds <= 25:
        p.error('Varigheden skal være 1–25 sekunder.')
    try:
        scratch = scratch_directory()
    except ValueError as exc:
        p.error(str(exc))
    source = find_device('Voicemeeter Out B1', 'input')
    sink = find_device('CABLE Input', 'output')
    validate_devices(source, sink)
    print('Klar. Ingen optagelse før Enter; ingen Hermes- eller TTS-kald.', flush=True)
    input('Enter = optag højst 25 sekunder ... ')
    samples = record(source, args.seconds)
    saved = save_clip(samples, scratch)
    print(f'Midlertidig lokal WAV: {saved}', flush=True)


if __name__ == '__main__':
    main()
