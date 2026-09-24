import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from scipy.io import wavfile

import capture_clip

SCRATCH = Path(tempfile.gettempdir()) / 'hermes_test_scratch'
SCRATCH.mkdir(parents=True, exist_ok=True)


class CaptureClipTests(unittest.TestCase):
    def test_uses_hermes_scratch_even_when_tmpdir_is_system_temp(self):
        with tempfile.TemporaryDirectory(dir=SCRATCH) as root, \
             patch.dict(os.environ, {'LOCALAPPDATA': root, 'TMPDIR': 'C:/Windows/Temp'}):
            expected = Path(root) / 'hermes' / 'cache' / 'scratch'
            expected.mkdir(parents=True)
            self.assertEqual(capture_clip.scratch_directory(), expected)

    def test_saves_bounded_float_wav_in_local_scratch(self):
        samples = np.array([0.0, 0.25, -0.25], dtype=np.float32)
        with tempfile.TemporaryDirectory(dir=SCRATCH) as scratch:
            path = capture_clip.save_clip(samples, scratch)
            self.assertEqual(path.parent, Path(scratch))
            rate, readback = wavfile.read(path)
            self.assertEqual(rate, capture_clip.AUDIO_RATE)
            np.testing.assert_array_equal(readback, samples)

    def test_rejects_more_than_twenty_five_seconds(self):
        samples = np.zeros(25 * 48000 + 1, dtype=np.float32)
        with tempfile.TemporaryDirectory(dir=SCRATCH) as scratch:
            with self.assertRaises(ValueError):
                capture_clip.save_clip(samples, scratch)
            self.assertEqual(list(Path(scratch).iterdir()), [])

    def test_invalid_duration_never_starts_recording(self):
        with patch.object(sys, 'argv', ['capture_clip.py', '--seconds', '26']), \
             patch('capture_clip.record') as record:
            with self.assertRaises(SystemExit):
                capture_clip.main()
            record.assert_not_called()

    def test_fifteen_second_capture_is_accepted(self):
        samples = np.zeros(15 * 48000, dtype=np.float32)
        with tempfile.TemporaryDirectory(dir=SCRATCH) as root, \
             patch.dict(os.environ, {'LOCALAPPDATA': root}), \
             patch.object(sys, 'argv', ['capture_clip.py', '--seconds', '15']), \
             patch('capture_clip.find_device', side_effect=[7, 8]), \
             patch('capture_clip.validate_devices'), \
             patch('capture_clip.record', return_value=samples) as record, \
             patch('builtins.input', return_value=''):
            scratch = Path(root) / 'hermes' / 'cache' / 'scratch'
            scratch.mkdir(parents=True)
            capture_clip.main()
            record.assert_called_once_with(7, 15)
            self.assertEqual(len(list(scratch.glob('neuro_clip_*.wav'))), 1)

    def test_twenty_five_second_capture_is_accepted(self):
        samples = np.zeros(25 * 48000, dtype=np.float32)
        with tempfile.TemporaryDirectory(dir=SCRATCH) as root, \
             patch.dict(os.environ, {'LOCALAPPDATA': root}), \
             patch.object(sys, 'argv', ['capture_clip.py', '--seconds', '25']), \
             patch('capture_clip.find_device', side_effect=[7, 8]), \
             patch('capture_clip.validate_devices'), \
             patch('capture_clip.record', return_value=samples) as record, \
             patch('builtins.input', return_value=''):
            scratch = Path(root) / 'hermes' / 'cache' / 'scratch'
            scratch.mkdir(parents=True)
            capture_clip.main()
            record.assert_called_once_with(7, 25)
            self.assertEqual(len(list(scratch.glob('neuro_clip_*.wav'))), 1)

    def test_waits_for_enter_then_records_only_isolated_source(self):
        samples = np.zeros(5 * 48000, dtype=np.float32)
        with tempfile.TemporaryDirectory(dir=SCRATCH) as root, \
             patch.dict(os.environ, {'LOCALAPPDATA': root}), \
             patch.object(sys, 'argv', ['capture_clip.py']), \
             patch('capture_clip.find_device', side_effect=[7, 8]) as find_device, \
             patch('capture_clip.validate_devices') as validate, \
             patch('capture_clip.record', return_value=samples) as record, \
             patch('builtins.input', return_value='') as enter:
            scratch = Path(root) / 'hermes' / 'cache' / 'scratch'
            scratch.mkdir(parents=True)
            capture_clip.main()
            enter.assert_called_once()
            record.assert_called_once_with(7, 5)
            validate.assert_called_once_with(7, 8)
            self.assertEqual(find_device.call_args_list[0].args,
                             ('Voicemeeter Out B1', 'input'))
            paths = list(Path(scratch).glob('neuro_clip_*.wav'))
            self.assertEqual(len(paths), 1)


if __name__ == '__main__':
    unittest.main()
