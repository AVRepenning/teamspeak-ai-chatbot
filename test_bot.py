import unittest
from unittest.mock import patch, Mock, AsyncMock
import sys
import types
import numpy as np
import bot


class BotTests(unittest.TestCase):
    def test_wake_word(self):
        self.assertEqual(bot.directed("Hey Bot, how's your day?"), "how's your day?")
        self.assertEqual(bot.directed('hey bot: How are you?'), 'How are you?')
        self.assertEqual(bot.directed('Hey - Bot! How are you?'), 'How are you?')
        self.assertEqual(bot.directed('Bot, how are you?'), '')
        self.assertEqual(bot.directed("Hey Neuro, how's your day?"), '')
        self.assertEqual(bot.directed("Neuro, how's your day?"), '')
        self.assertEqual(bot.directed('Hey Botany, how are you?'), '')
        self.assertEqual(bot.directed('Hey Bottle, how are you?'), '')
        self.assertEqual(bot.directed('Hey Bot Sama, how are you?'), '')
        self.assertEqual(bot.directed('The bot is here'), '')
        self.assertEqual(bot.directed('Hi Bot, how are you?'), '')

    def test_manual_question_accepts_transcript_only_when_explicitly_enabled(self):
        self.assertEqual(bot.should_answer('Nu, hvad laver du?', manual=True), 'Nu, hvad laver du?')
        self.assertEqual(bot.should_answer('Nu, hvad laver du?'), '')
        self.assertEqual(bot.should_answer('Nu, hvad laver du?', manual=True, diagnostic=True), '')
        self.assertEqual(bot.should_answer('  ', manual=True), '')

    def test_manual_cli_sends_transcribed_question_after_enter(self):
        fake_whisper = types.SimpleNamespace(WhisperModel=Mock())
        with patch.dict(sys.modules, {'faster_whisper': fake_whisper}), \
             patch.dict('os.environ', {'HERMES_BOT_KEY': 'test'}), \
             patch.object(sys, 'argv', ['bot.py', '--input', '1', '--output', '2', '--manual-question']), \
             patch('bot.validate_devices'), patch('bot.record', return_value=np.zeros(48000, dtype=np.float32)), \
             patch('bot.transcribe', return_value='Nu, hvad laver du?'), \
             patch('bot.ask_hermes', return_value='Jeg tester.' ) as ask, \
             patch('bot.speak', new_callable=AsyncMock), \
             patch('builtins.input', side_effect=['', EOFError]):
            bot.main()
        self.assertEqual(ask.call_args.args[0], 'Nu, hvad laver du?')

    def test_diagnostic_compares_same_clip_without_vad_and_never_replies(self):
        fake_whisper = types.SimpleNamespace(WhisperModel=Mock())
        clip = np.zeros(48000, dtype=np.float32)
        with patch.dict(sys.modules, {'faster_whisper': fake_whisper}), \
             patch.dict('os.environ', {'HERMES_BOT_KEY': 'test'}), \
             patch.object(sys, 'argv', ['bot.py', '--input', '1', '--output', '2', '--diagnose-input']), \
             patch('bot.validate_devices'), patch('bot.record', return_value=clip), \
             patch('bot.transcribe', side_effect=['Hej neuro, vejløro!', 'Hej neuro, hvad laver du?']) as transcribe, \
             patch('bot.ask_hermes') as ask, patch('bot.speak', new_callable=AsyncMock) as speak, \
             patch('builtins.input', return_value=''):
            bot.main()
        self.assertEqual(transcribe.call_count, 2)
        self.assertIs(transcribe.call_args_list[0].args[0], clip)
        self.assertIs(transcribe.call_args_list[1].args[0], clip)
        self.assertFalse(transcribe.call_args_list[1].kwargs['vad_filter'])
        ask.assert_not_called()
        speak.assert_not_called()

    @patch('bot.requests.post')
    def test_api_and_context(self, post):
        post.return_value.json.return_value = {'choices':[{'message':{'content':'Hej med jer.'}}]}
        history = []
        self.assertEqual(bot.ask_hermes('Hej', history, 'http://127.0.0.1:8642', 'test'), 'Hej med jer.')
        self.assertEqual(len(history), 2)
        kwargs = post.call_args.kwargs
        self.assertEqual(kwargs['headers']['Authorization'], 'Bearer test')
        self.assertEqual(kwargs['json']['messages'][1]['content'], 'Hej')

    @patch('bot.sd.query_devices')
    def test_refuses_real_mic(self, query):
        query.side_effect = [{'name':'Microphone (headset)','max_input_channels':1,'max_output_channels':0},
                             {'name':'Virtual cable input','max_input_channels':0,'max_output_channels':2}]
        with self.assertRaises(ValueError):
            bot.validate_devices(1, 2)

    def test_transcription_receives_16khz_audio(self):
        class Segment:
            text = ' Neuro, hej'
        model = Mock()
        model.transcribe.return_value = ([Segment()], None)
        self.assertEqual(bot.transcribe(np.zeros(48000, dtype=np.float32), model), 'Neuro, hej')
        self.assertEqual(len(model.transcribe.call_args.args[0]), 16000)
        self.assertEqual(model.transcribe.call_args.kwargs['language'], 'en')

    def test_english_reply_configuration(self):
        self.assertIn('Reply briefly in English', bot.SYSTEM)
        self.assertEqual(bot.speak.__defaults__[0], 'en-US-JennyNeural')

    def test_transcription_can_disable_vad_for_same_audio(self):
        model = Mock()
        model.transcribe.return_value = ([], None)
        bot.transcribe(np.zeros(48000, dtype=np.float32), model, vad_filter=False)
        self.assertFalse(model.transcribe.call_args.kwargs['vad_filter'])

    def test_capture_level_distinguishes_silence_from_voice(self):
        self.assertEqual(bot.capture_level(np.zeros(48000, dtype=np.float32)), (0.0, 0.0))
        rms, peak = bot.capture_level(np.array([0.0, 0.5, -0.5, 0.0], dtype=np.float32))
        self.assertAlmostEqual(rms, 0.353553, places=5)
        self.assertAlmostEqual(peak, 0.5)

    @patch('bot.ask_hermes')
    def test_diagnostic_mode_never_asks_or_speaks(self, ask):
        result = bot.should_answer('Hey Neuro, hvad hedder du?', diagnostic=True)
        self.assertEqual(result, '')
        ask.assert_not_called()

    def test_safe_wasapi_device_names(self):
        source = bot.find_device('Voicemeeter Out B1', 'input')
        sink = bot.find_device('CABLE Input', 'output')
        bot.validate_devices(source, sink)


if __name__ == '__main__':
    unittest.main()
