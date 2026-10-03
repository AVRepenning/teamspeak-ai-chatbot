import importlib.util
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from skynet import Settings, hermes_answer, drain_notifications, session_id, reset_session


class Response:
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def read(self):
        return json.dumps({'choices': [{'message': {'content': 'Ja, menneske.'}}]}).encode()


class FakeQuery:
    def __init__(self):
        self.sent = []
        self.config = type('Config', (), {'channel_id': 42})()
    def send_channel_message(self, text): self.sent.append(text)


class BridgeTests(TestCase):
    def test_session_survives_restart_and_rotates(self):
        with TemporaryDirectory() as root:
            first = session_id(root)
            self.assertEqual(first, session_id(root))
            reset_session(root)
            self.assertNotEqual(first, session_id(root))

    def test_hermes_uses_authenticated_session_and_low_luna(self):
        with TemporaryDirectory() as root:
            config = Settings('teamspeak6', 10022, 'skynet', 'test', 'SHA256:' + 'A'*43,
                              1, 42, 'test', state_dir=root, hermes_key='local-test-key')
            with patch('skynet.request.urlopen', return_value=Response()) as urlopen:
                answer = hermes_answer(config, 'Afsender: Tom\nSpørgsmål: Hej', [])
            self.assertEqual(answer, 'Ja, menneske.')
            req = urlopen.call_args.args[0]
            self.assertEqual(req.full_url, 'http://10.253.252.1:8650/v1/chat/completions')
            self.assertEqual(req.get_header('X-hermes-session-id'), session_id(root))
            payload = json.loads(req.data)
            self.assertEqual(payload['model'], 'gpt-6-luna')
            self.assertEqual(payload['model_options']['reasoning_effort'], 'low')
            self.assertEqual(len(payload['messages']), 1)

    def test_notifications_retain_failed_delivery(self):
        with TemporaryDirectory() as root:
            event = Path(root) / 'notify-1.json'
            event.write_text(json.dumps({'kind': 'memory', 'action': 'add'}))
            query = FakeQuery()
            drain_notifications(query, root)
            self.assertEqual(query.sent, ['Skynet: Hukommelsen er opdateret.'])
            self.assertFalse(event.exists())
            event.write_text(json.dumps({'kind': 'skill', 'action': 'create', 'name': 'gruppe-jokes'}))
            with patch.object(query, 'send_channel_message', side_effect=RuntimeError('offline')):
                with self.assertRaises(RuntimeError): drain_notifications(query, root)
            self.assertTrue(event.exists())

    def test_hook_only_queues_successful_committed_writes(self):
        path = Path(__file__).resolve().parents[1] / 'hermes_plugin' / '__init__.py'
        spec = importlib.util.spec_from_file_location('skynet_hook', path)
        plugin = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(plugin)
        with TemporaryDirectory() as root, patch.object(plugin, 'STATE_DIR', Path(root)):
            plugin.notify('memory', {'action': 'add'}, '{"success": false}')
            plugin.notify('memory', {'action': 'add'}, '{"success": true, "staged": true}')
            plugin.notify('skill_manage', {'operations': [{'name': 'jokes', 'action': 'create'}]}, '{"success": true, "operations_applied": 1}')
            plugin.notify('memory', {'action': 'add'}, '{"success": true}')
            entries = [json.loads(p.read_text()) for p in Path(root).glob('notify-*.json')]
            self.assertEqual(sorted(e['kind'] for e in entries), ['memory', 'skill'])

    def test_web_notices_only_show_successful_searches_and_visited_hosts(self):
        path = Path(__file__).resolve().parents[1] / 'hermes_plugin' / '__init__.py'
        spec = importlib.util.spec_from_file_location('skynet_hook_web', path)
        plugin = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(plugin)
        with TemporaryDirectory() as root, patch.object(plugin, 'STATE_DIR', Path(root)):
            plugin.notify('web_search', {'query': 'Apollo weather'}, {'data': {'web': [{'url': 'https://example.com'}]}})
            plugin.notify('web_search', {'query': 'broken'}, {'error': 'rate limited'})
            plugin.notify('web_extract', {'urls': ['https://example.com/?token=secret', 'https://another.org/path']},
                          {'results': [{'url': 'https://example.com/?token=secret', 'content': 'hello'},
                                       {'url': 'https://another.org/path', 'error': 'blocked'}]})
            plugin.notify('read_file', {'path': '/secret'}, {'content': 'hello'})
            entries = [json.loads(p.read_text()) for p in Path(root).glob('notify-*.json')]
            self.assertEqual(sorted(e['kind'] for e in entries), ['web_extract', 'web_search'])
            q = FakeQuery()
            drain_notifications(q, root)
            self.assertEqual(q.sent, ['Skynet: Søgte på nettet: Apollo weather',
                                      'Skynet: Besøgte website: example.com'])
            self.assertFalse(list(Path(root).glob('notify-*.json')))

    def test_danish_weather_search_is_forced_to_dmi(self):
        path = Path(__file__).resolve().parents[1] / 'hermes_plugin' / '__init__.py'
        spec = importlib.util.spec_from_file_location('skynet_weather_guard', path)
        plugin = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(plugin)
        result = plugin.guard_weather_sources(
            'web_search',
            {'query': 'site:accuweather.com weather København today temperature'},
            turn_id='weather-turn-1',
        )
        self.assertEqual(result['action'], 'modify')
        self.assertIn('site:dmi.dk', result['args']['query'])
        self.assertNotIn('site:accuweather.com', result['args']['query'])

    def test_danish_weather_extraction_blocks_nonofficial_pages(self):
        path = Path(__file__).resolve().parents[1] / 'hermes_plugin' / '__init__.py'
        spec = importlib.util.spec_from_file_location('skynet_weather_extract_guard', path)
        plugin = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(plugin)
        plugin.guard_weather_sources(
            'web_search', {'query': 'weather København today'}, turn_id='weather-turn-2'
        )
        blocked = plugin.guard_weather_sources(
            'web_extract',
            {'urls': ['https://www.accuweather.com/en/dk/copenhagen/']},
            turn_id='weather-turn-2',
        )
        self.assertEqual(blocked['action'], 'block')
        allowed = plugin.guard_weather_sources(
            'web_extract',
            {'urls': ['https://www.dmi.dk/danmark/']},
            turn_id='weather-turn-2',
        )
        self.assertIsNone(allowed)

    def test_other_weather_locations_are_not_rewritten(self):
        path = Path(__file__).resolve().parents[1] / 'hermes_plugin' / '__init__.py'
        spec = importlib.util.spec_from_file_location('skynet_weather_other', path)
        plugin = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(plugin)
        result = plugin.guard_weather_sources(
            'web_search', {'query': 'weather in New York today'}, turn_id='weather-turn-3'
        )
        self.assertIsNone(result)

    def test_official_fallback_is_constrained_after_dmi_search(self):
        path = Path(__file__).resolve().parents[1] / 'hermes_plugin' / '__init__.py'
        spec = importlib.util.spec_from_file_location('skynet_weather_fallback', path)
        plugin = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(plugin)
        first = plugin.guard_weather_sources(
            'web_search', {'query': 'weather Copenhagen today'}, turn_id='weather-turn-fallback'
        )
        self.assertIn('site:dmi.dk', first['args']['query'])
        fallback = plugin.guard_weather_sources(
            'web_search', {'query': 'MET Norway weather forecast Copenhagen'},
            turn_id='weather-turn-fallback',
        )
        self.assertEqual(fallback['action'], 'modify')
        self.assertIn('site:met.no', fallback['args']['query'])
        self.assertNotIn('site:dmi.dk', fallback['args']['query'])
