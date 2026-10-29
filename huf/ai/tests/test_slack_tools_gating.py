import json
from unittest.mock import MagicMock

from huf.ai.tests.unit_support import SupportCase  # noqa: E402

from huf.ai.tools import slack

BOT = "xoxb-SECRET-BOT-TOKEN"
USER = "xoxp-SECRET-USER-TOKEN"


def creds(monkeypatch, token=BOT, **flags):
	data = {"token": token, **flags}
	monkeypatch.setattr(slack, "get_credential", lambda svc, key, default=None: data.get(key, default))
	monkeypatch.setattr(slack, "update_last_error", lambda *a, **k: None)


def http(monkeypatch, body):
	resp = MagicMock()
	resp.json.return_value = body
	resp.raise_for_status.return_value = None
	m = MagicMock(return_value=resp)
	monkeypatch.setattr(slack.httpx, "get", m)
	monkeypatch.setattr(slack.httpx, "post", m)
	return m


READ = [
	("handle_list_channels", {}, {"ok": True, "channels": [{"id": "C1", "name": "g"}]}),
	("handle_get_channel_history", {"channel": "C1"}, {"ok": True, "messages": [{"ts": "1", "text": "hi"}]}),
	("handle_list_users", {}, {"ok": True, "members": [{"id": "U1", "name": "a"}]}),
]


class TestModule(SupportCase):
	def test_read_tools_off_by_default(self):
		monkeypatch = self.monkeypatch
		for fn, args, body in READ:
			with self.subTest(fn=fn, args=args, body=body):
				creds(monkeypatch)
				m = http(monkeypatch, body)
				out = json.loads(getattr(slack, fn)(**args))
				assert out["success"] is False and "disabled by the administrator" in out["error"]
				m.assert_not_called()
				assert BOT not in json.dumps(out)

	def test_read_tools_on_when_enabled(self):
		monkeypatch = self.monkeypatch
		for fn, args, body in READ:
			with self.subTest(fn=fn, args=args, body=body):
				creds(monkeypatch, allow_workspace_read="1")
				http(monkeypatch, body)
				out = json.loads(getattr(slack, fn)(**args))
				assert out["success"] is True and "Untrusted" in out["notice"]
				assert BOT not in json.dumps(out)

	def test_search_off_by_default(self):
		monkeypatch = self.monkeypatch
		creds(monkeypatch, token=USER)
		m = http(monkeypatch, {"ok": True})
		out = json.loads(slack.handle_search_messages(query="x"))
		assert "disabled by the administrator" in out["error"]
		m.assert_not_called()

	def test_search_refused_for_bot_token(self):
		monkeypatch = self.monkeypatch
		creds(monkeypatch, allow_workspace_read="1")
		m = http(monkeypatch, {"ok": True})
		s = slack.handle_search_messages(query="x")
		assert "user token" in json.loads(s)["error"]
		assert BOT not in s
		m.assert_not_called()

	def test_search_with_user_token_needs_allow_user_token(self):
		monkeypatch = self.monkeypatch
		creds(monkeypatch, token=USER, allow_workspace_read="1")
		m = http(monkeypatch, {"ok": True})
		s = slack.handle_search_messages(query="x")
		assert "allow_user_token" in json.loads(s)["error"]
		assert USER not in s
		m.assert_not_called()

	def test_search_works_with_user_token_and_both_flags(self):
		monkeypatch = self.monkeypatch
		creds(monkeypatch, token=USER, allow_workspace_read="1", allow_user_token="1")
		http(monkeypatch, {"ok": True, "messages": {"matches": [{"text": "t", "channel": {"name": "c"}}]}})
		s = slack.handle_search_messages(query="x")
		out = json.loads(s)
		assert out["success"] is True and out["count"] == 1
		assert USER not in s

	def test_send_refuses_user_token(self):
		monkeypatch = self.monkeypatch
		for fn, args in [
	("handle_send_message", {"channel": "C", "text": "t"}),
	("handle_send_message_thread", {"channel": "C", "text": "t", "thread_ts": "1"}),
]:
			with self.subTest(fn=fn, args=args):
				creds(monkeypatch, token=USER)
				m = http(monkeypatch, {"ok": True})
				s = getattr(slack, fn)(**args)
				assert "allow_user_token" in json.loads(s)["error"] and USER not in s
				m.assert_not_called()

	def test_send_bot_token_works_without_read_flag(self):
		monkeypatch = self.monkeypatch
		for fn, args in [
	("handle_send_message", {"channel": "C", "text": "t"}),
	("handle_send_message_thread", {"channel": "C", "text": "t", "thread_ts": "1"}),
]:
			with self.subTest(fn=fn, args=args):
				creds(monkeypatch)
				m = http(monkeypatch, {"ok": True})
				assert json.loads(getattr(slack, fn)(**args))["success"] is True
				m.assert_called_once()

	def test_send_user_token_allowed_with_flag(self):
		monkeypatch = self.monkeypatch
		creds(monkeypatch, token=USER, allow_user_token="1")
		http(monkeypatch, {"ok": True})
		assert json.loads(slack.handle_send_message(channel="C", text="t"))["success"] is True

	def test_error_path_does_not_leak_token(self):
		monkeypatch = self.monkeypatch
		creds(monkeypatch, allow_workspace_read="1")
		http(monkeypatch, {"ok": False, "error": "channel_not_found"})
		s = slack.handle_get_channel_history(channel="C1")
		assert "channel_not_found" in s and BOT not in s
