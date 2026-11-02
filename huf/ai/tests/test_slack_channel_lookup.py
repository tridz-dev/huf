import json
from unittest.mock import MagicMock

from huf.ai.tests.unit_support import SupportCase
from huf.ai.tools import connection_test, slack

TOKEN = "xoxb-SECRET-LOOKUP-TOKEN"


def _fx_clean(case):
	monkeypatch = case.monkeypatch
	slack._CHANNEL_CACHE.clear()
	data = {"token": TOKEN}
	monkeypatch.setattr(slack, "get_credential", lambda svc, key, default=None: data.get(key, default))
	monkeypatch.setattr(slack, "update_last_error", lambda *a, **k: None)
	yield
	slack._CHANNEL_CACHE.clear()


_AUTOUSE = (_fx_clean,)


def _resp(body):
	r = MagicMock()
	r.json.return_value = body
	r.raise_for_status.return_value = None
	return r


def _wire(monkeypatch, pages, post_body=None):
	"""conversations.list returns `pages` in order; chat.postMessage returns post_body."""
	get = MagicMock(side_effect=[_resp(p) for p in pages])
	post = MagicMock(return_value=_resp(post_body or {"ok": True, "ts": "1.0", "channel": "C1"}))
	monkeypatch.setattr(slack.httpx, "get", get)
	monkeypatch.setattr(slack.httpx, "post", post)
	return get, post


PAGE1 = {"ok": True, "channels": [{"id": "C111111111", "name": "general"}], "response_metadata": {"next_cursor": "abc"}}
PAGE2 = {"ok": True, "channels": [{"id": "C222222222", "name": "huf-live-test", "is_private": True}], "response_metadata": {"next_cursor": ""}}


class TestSlackChannelLookup(SupportCase):
	def test_name_with_and_without_hash_resolves_across_pages(self):
		monkeypatch = self.monkeypatch
		get, post = _wire(monkeypatch, [PAGE1, PAGE2])
		out = json.loads(slack.handle_send_message(channel="#Huf-Live-Test", text="hi"))
		assert out["success"] is True
		assert post.call_args.kwargs["json"]["channel"] == "C222222222"
		assert get.call_args_list[1].kwargs["params"]["cursor"] == "abc"
		# second call: served from the 5 minute cache, no more list calls
		slack.handle_send_message(channel="huf-live-test", text="hi")
		assert get.call_count == 2
		assert post.call_args.kwargs["json"]["channel"] == "C222222222"

	def test_id_is_not_looked_up(self):
		monkeypatch = self.monkeypatch
		get, post = _wire(monkeypatch, [])
		slack.handle_send_message(channel="C0123456789", text="hi")
		get.assert_not_called()
		assert post.call_args.kwargs["json"]["channel"] == "C0123456789"

	def test_not_found_is_clear_and_nothing_is_posted(self):
		monkeypatch = self.monkeypatch
		get, post = _wire(monkeypatch, [PAGE2])
		out = json.loads(slack.handle_send_message(channel="nope-channel", text="hi"))
		assert out["success"] is False and "#nope-channel" in out["error"]
		post.assert_not_called()
		assert TOKEN not in json.dumps(out)

	def test_ambiguous_name(self):
		monkeypatch = self.monkeypatch
		page = {"ok": True, "channels": [{"id": "C111111111", "name": "dup"}, {"id": "C222222222", "name": "dup"}]}
		_, post = _wire(monkeypatch, [page])
		out = json.loads(slack.handle_send_message(channel="dup", text="hi"))
		assert "More than one channel" in out["error"]
		post.assert_not_called()

	def test_missing_scope_message(self):
		monkeypatch = self.monkeypatch
		_, post = _wire(monkeypatch, [{"ok": False, "error": "missing_scope", "needed": "channels:read"}])
		out = json.loads(slack.handle_send_message(channel="general", text="hi"))
		assert out["success"] is False and "channels:read" in out["error"]
		post.assert_not_called()

	def test_thread_reply_resolves_name(self):
		monkeypatch = self.monkeypatch
		_, post = _wire(monkeypatch, [PAGE2])
		slack.handle_send_message_thread(channel="#huf-live-test", text="hi", thread_ts="1.0")
		assert post.call_args.kwargs["json"]["channel"] == "C222222222"

	def test_list_slack_channels_api(self):
		monkeypatch = self.monkeypatch
		_wire(monkeypatch, [PAGE1, PAGE2])
		monkeypatch.setattr(connection_test, "_resolve_credentials", lambda s, setting, p: {"token": TOKEN})
		out = connection_test.slack_channels_for_setting("s")
		assert out["status"] == "Connected"
		assert [c["name"] for c in out["channels"]] == ["general", "huf-live-test"]
		assert TOKEN not in json.dumps(out)

	def test_list_slack_channels_rejected(self):
		monkeypatch = self.monkeypatch
		_wire(monkeypatch, [{"ok": False, "error": "missing_scope", "needed": "groups:read"}])
		monkeypatch.setattr(connection_test, "_resolve_credentials", lambda s, setting, p: {"token": TOKEN})
		out = connection_test.slack_channels_for_setting("s")
		assert out["status"] == "Rejected" and "groups:read" in out["message"] and out["channels"] == []

	def test_reply_carries_readable_channel_name(self):
		monkeypatch = self.monkeypatch
		_, post = _wire(monkeypatch, [PAGE2], post_body={"ok": True, "ts": "1.0", "channel": "C222222222"})
		out = json.loads(slack.handle_send_message(channel="#huf-live-test", text="hi"))
		assert out["results"]["channel_name"] == "huf-live-test"
		# by id: the name comes from the channel cache that the lookup above filled
		out = json.loads(slack.handle_send_message(channel="C222222222", text="hi"))
		assert out["results"]["channel_name"] == "huf-live-test"

	def test_list_without_setting_uses_the_default_integration_token(self):
		monkeypatch = self.monkeypatch
		_wire(monkeypatch, [PAGE2])
		import huf.ai.tools.credentials as creds_mod

		monkeypatch.setattr(creds_mod, "get_credential", lambda svc, key, default=None: TOKEN if (svc, key) == ("slack", "token") else default)
		out = connection_test.slack_channels_for_setting(None)
		assert out["status"] == "Connected" and out["channels"][0]["id"] == "C222222222"
