import unittest
from unittest.mock import patch
import json

from skynet import Query, ReconnectBackoff, Settings, chunks, fields, handle_event, openai_answer, probe, question_from_message, ts_escape


def settings() -> Settings:
    return Settings(
        host="teamspeak6", port=10022, username="skynet", password="test",
        host_key_sha256="SHA256:" + "A" * 43, server_id=1, channel_id=42,
        openai_key="test",
    )


class FakeQuery:
    self_id = 9

    def __init__(self):
        self.sent = []

    def send_channel_message(self, text):
        self.sent.append(text)


class FakeChannel:
    closed = False

    def __init__(self, incoming):
        self.incoming = [incoming.encode("utf-8")]
        self.sent = []

    def exit_status_ready(self):
        return False

    def recv(self, _size):
        return self.incoming.pop(0)

    def sendall(self, data):
        self.sent.append(data)

    def settimeout(self, _timeout):
        pass


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, *_args):
        return json.dumps({
            "status": "completed",
            "output": [
                {"type": "reasoning"},
                {"type": "message", "role": "assistant", "content": [
                    {"type": "output_text", "text": "Hej fra Skynet"}
                ]},
            ],
        }).encode("utf-8")


class SkynetTests(unittest.TestCase):
    def test_query_escaping_and_notification_decoding(self):
        original = "hej /skynet | test\\linje\nny"
        encoded = ts_escape(original)
        self.assertEqual(fields("notifytextmessage msg=" + encoded)["msg"], original)

    def test_command_prefix_and_length(self):
        self.assertEqual(question_from_message("!Skynet hvad er 2+2?", 50), "hvad er 2+2?")
        self.assertEqual(question_from_message("/skynet test", 50), "test")
        self.assertIsNone(question_from_message("Hej skynet test", 50))
        with self.assertRaises(ValueError):
            question_from_message("!skynet " + "x" * 51, 50)

    def test_star_prefix_accepts_optional_space(self):
        self.assertEqual(question_from_message("* hej skynet", 50), "hej skynet")
        self.assertEqual(question_from_message("*hej skynet", 50), "hej skynet")
        self.assertEqual(question_from_message("  *   hej  ", 50), "hej")
        self.assertEqual(question_from_message("*", 50), "")
        self.assertIsNone(question_from_message("hej *skynet", 50))

    def test_star_prefix_routes_channel_question_to_answer(self):
        query = FakeQuery()
        event = "notifytextmessage targetmode=2 invokerid=7 invokername=Tom msg=" + ts_escape("*hej skynet")
        observed = []
        handle_event(event, query, settings(), lambda _config, question, _history: observed.append(question) or "Svar")
        self.assertEqual(len(observed), 1)
        self.assertTrue(observed[0].endswith("Spørgsmål: hej skynet"))
        self.assertEqual(query.sent, ["@Tom: Svar"])

    def test_new_command_clears_shared_history(self):
        query = FakeQuery()
        history = [
            {"role": "user", "content": "Gamle spørgsmål"},
            {"role": "assistant", "content": "Gamle svar"},
        ]
        event = "notifytextmessage targetmode=2 invokerid=7 msg=/new"
        handle_event(
            event, query, settings(),
            lambda *_args: self.fail("/new must not call the answer function"),
            history=history,
        )
        self.assertEqual(history, [])
        self.assertEqual(query.sent, ["Ny fælles session startet."])

    def test_shared_session_tracks_speaker_and_exchange(self):
        query = FakeQuery()
        history = [{"role": "user", "content": "Ældre spørgsmål"}]
        observed = []

        def answer(_config, question, previous):
            observed.append((question, list(previous)))
            return "Fortsættelsen"

        event = (
            "notifytextmessage targetmode=2 invokerid=7 invokeruid=userA "
            "invokername=Hummingbird87 msg=" + ts_escape("!skynet Fortsæt")
        )
        handle_event(event, query, settings(), answer, history=history)
        self.assertEqual(len(observed), 1)
        question, previous = observed[0]
        self.assertRegex(
            question,
            r"^Aktuelt tidspunkt fra serverens ur \(Europe/Copenhagen\): "
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}\n"
            r"Afsender: Hummingbird87\nSpørgsmål: Fortsæt$",
        )
        self.assertEqual(previous, [{"role": "user", "content": "Ældre spørgsmål"}])
        self.assertEqual(history, [
            {"role": "user", "content": "Ældre spørgsmål"},
            {"role": "user", "content": question},
            {"role": "assistant", "content": "Fortsættelsen"},
        ])
        self.assertEqual(query.sent, ["@Hummingbird87: Fortsættelsen"])

    def test_shared_session_keeps_ten_recent_turns(self):
        query = FakeQuery()
        history = [
            message
            for turn in range(10)
            for message in (
                {"role": "user", "content": f"Spørgsmål {turn}"},
                {"role": "assistant", "content": f"Svar {turn}"},
            )
        ]
        event = (
            "notifytextmessage targetmode=2 invokerid=7 invokername=Tom msg="
            + ts_escape("!skynet næste")
        )
        handle_event(event, query, settings(), lambda *_args: "Sidste svar", history=history)
        self.assertEqual(len(history), 20)
        self.assertEqual(history[0], {"role": "user", "content": "Spørgsmål 1"})
        latest = history[-2]["content"]
        self.assertIn("Aktuelt tidspunkt fra serverens ur (Europe/Copenhagen):", latest)
        self.assertTrue(latest.endswith("Afsender: Tom\nSpørgsmål: næste"))

    def test_rapid_questions_from_same_user_are_both_answered_and_self_is_ignored(self):
        query = FakeQuery()
        prefix = "notifytextmessage targetmode=2 invokerid=7 invokeruid=userA invokername=Tom msg="
        event = prefix + ts_escape("!skynet hej")
        second_event = prefix + ts_escape("!skynet igen")
        self_event = prefix.replace("invokerid=7", "invokerid=9") + ts_escape("!skynet hej")
        answer = lambda _config, _question, _history: "Svar"
        handle_event(event, query, settings(), answer)
        handle_event(second_event, query, settings(), answer)
        handle_event(self_event, query, settings(), answer)
        self.assertEqual(query.sent, ["@Tom: Svar", "@Tom: Svar"])

    def test_only_channel_messages_are_processed(self):
        query = FakeQuery()
        handle_event(
            "notifytextmessage targetmode=1 invokerid=7 msg=!skynet\\shej",
            query, settings(), lambda *_: "Svar",
        )
        self.assertEqual(query.sent, [])

    def test_query_keeps_event_while_reading_command_response(self):
        query = Query(settings())
        channel = FakeChannel(
            "notifytextmessage targetmode=2 invokerid=7 msg=!skynet\\shej\n"
            "client_id=9 client_channel_id=42\nerror id=0 msg=ok\n"
        )
        query.channel = channel
        self.assertEqual(query.command("whoami"), ["client_id=9 client_channel_id=42"])
        self.assertEqual(channel.sent, [b"whoami\n"])
        self.assertTrue(query.next_event().startswith("notifytextmessage "))

    def test_query_does_not_move_when_already_in_target_channel(self):
        channel = FakeChannel(
            "error id=0 msg=ok\n"
            "client_id=9 client_channel_id=42\nerror id=0 msg=ok\n"
            "error id=0 msg=ok\n"
            "error id=0 msg=ok\n"
        )
        with patch("skynet.paramiko.SSHClient") as ssh_client:
            ssh_client.return_value.invoke_shell.return_value = channel
            query = Query(settings())
            query.connect()
            query.close()
        self.assertEqual(channel.sent, [
            b"use sid=1\n",
            b"whoami\n",
            b"servernotifyregister event=textchannel id=42\n",
        ])

    def test_probe_moves_only_its_query_client_when_needed(self):
        channel = FakeChannel(
            "error id=0 msg=ok\n"
            "client_id=9 client_channel_id=1\nerror id=0 msg=ok\n"
            "error id=0 msg=ok\n"
            "error id=0 msg=ok\n"
            "notifytextmessage targetmode=2 invokerid=7 msg=ping\n"
        )
        with patch("skynet.paramiko.SSHClient") as ssh_client:
            ssh_client.return_value.invoke_shell.return_value = channel
            self.assertEqual(probe(settings()), 0)
        self.assertEqual(channel.sent, [
            b"use sid=1\n",
            b"whoami\n",
            b"clientmove clid=9 cid=42\n",
            b"servernotifyregister event=textchannel id=42\n",
        ])

    def test_reconnect_backoff_grows_caps_and_resets(self):
        backoff = ReconnectBackoff()
        self.assertEqual(
            [backoff.after_failure() for _ in range(6)],
            [30, 60, 120, 240, 300, 300],
        )
        backoff.reset()
        self.assertEqual(backoff.after_failure(), 30)

    def test_long_answer_is_bounded(self):
        result = chunks("ord " * 600, limit=50, count=3)
        self.assertEqual(len(result), 3)
        self.assertTrue(all(len(part) <= 50 for part in result))
        self.assertTrue(result[-1].endswith("…"))

    def test_openai_payload_and_text_extraction(self):
        with patch("skynet.request.urlopen", return_value=FakeResponse()) as urlopen:
            answer = openai_answer(settings(), "Hvad er 2+2?")
        self.assertEqual(answer, "Hej fra Skynet")
        payload = json.loads(urlopen.call_args.args[0].data)
        self.assertEqual(payload["model"], "gpt-6-luna")
        self.assertEqual(payload["reasoning"], {"effort": "low"})
        self.assertEqual(payload["input"], "Hvad er 2+2?")
        self.assertFalse(payload["store"])
        self.assertIsInstance(payload["instructions"], str)
        self.assertTrue(payload["instructions"].strip())

    def test_openai_payload_contains_shared_session_history(self):
        history = [
            {"role": "user", "content": "Første spørgsmål"},
            {"role": "assistant", "content": "Første svar"},
        ]
        with patch("skynet.request.urlopen", return_value=FakeResponse()) as urlopen:
            openai_answer(settings(), "Fortsæt", history)
        payload = json.loads(urlopen.call_args.args[0].data)
        self.assertEqual(payload["input"], history + [{"role": "user", "content": "Fortsæt"}])
        self.assertFalse(payload["store"])


if __name__ == "__main__":
    unittest.main()
