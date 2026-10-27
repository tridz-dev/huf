import logging

import pytest

from huf.ai.gateways.slack import api as sa
from huf.ai.gateways.slack.api import SlackApi, SlackApiError

TOKEN = "xoxb-SECRET-TOKEN-123"


class Resp:
	def __init__(self, body=None, status=200, headers=None):
		self.body = {"ok": True} if body is None else body
		self.status_code = status
		self.headers = headers or {}

	def json(self):
		if isinstance(self.body, Exception):
			raise self.body
		return self.body


class Http:
	def __init__(self, *resps, raises=None):
		self.resps, self.calls, self.raises = list(resps), [], raises

	def __call__(self, url, **kw):
		self.calls.append((url, kw))
		if self.raises:
			raise self.raises
		return self.resps.pop(0) if len(self.resps) > 1 else self.resps[0]


def api(*resps, **kw):
	h = Http(*resps, **kw)
	sleeps = []
	return SlackApi(TOKEN, http=h, sleep=sleeps.append), h, sleeps


def test_auth_test_ok_and_auth_header():
	a, h, _ = api(Resp({"ok": True, "user_id": "U1"}))
	assert a.auth_test()["user_id"] == "U1"
	url, kw = h.calls[0]
	assert url == "https://slack.com/api/auth.test"
	assert kw["headers"]["Authorization"] == f"Bearer {TOKEN}"


def test_ok_false_raises_with_code():
	a, _, _ = api(Resp({"ok": False, "error": "invalid_auth"}))
	with pytest.raises(SlackApiError) as e:
		a.auth_test()
	assert e.value.error_code == "invalid_auth" and e.value.method == "auth.test"


def test_http_error_status():
	a, _, _ = api(Resp({}, status=500))
	with pytest.raises(SlackApiError) as e:
		a.auth_test()
	assert e.value.status == 500 and e.value.error_code == "http_500"


def test_invalid_json():
	a, _, _ = api(Resp(ValueError("x")))
	with pytest.raises(SlackApiError) as e:
		a.auth_test()
	assert e.value.error_code == "invalid_json"


def test_non_dict_json():
	a, _, _ = api(Resp([1]))
	with pytest.raises(SlackApiError):
		a.auth_test()


def test_transport_error_hides_original():
	a, _, _ = api(Resp(), raises=RuntimeError(f"boom {TOKEN}"))
	with pytest.raises(SlackApiError) as e:
		a.auth_test()
	assert TOKEN not in str(e.value) and TOKEN not in repr(e.value)
	assert e.value.__cause__ is None and e.value.__suppress_context__


def test_429_retries_once_then_succeeds():
	a, h, sleeps = api(Resp({}, 429, {"Retry-After": "3"}), Resp({"ok": True}))
	assert a.auth_test()["ok"]
	assert sleeps == [3.0] and len(h.calls) == 2


def test_429_twice_raises():
	a, h, sleeps = api(Resp({}, 429, {"Retry-After": "1"}))
	with pytest.raises(SlackApiError) as e:
		a.auth_test()
	assert e.value.error_code == "ratelimited" and e.value.status == 429
	assert len(h.calls) == 2 and len(sleeps) == 1


def test_ratelimited_error_code_retries_once():
	a, h, sleeps = api(Resp({"ok": False, "error": "ratelimited"}, 200, {"Retry-After": "2"}),
		Resp({"ok": True}))
	a.auth_test()
	assert sleeps == [2.0]


def test_ratelimited_error_code_twice_raises():
	a, _, _ = api(Resp({"ok": False, "error": "ratelimited"}))
	with pytest.raises(SlackApiError):
		a.auth_test()


def test_retry_after_capped_and_bad_value():
	a, _, sleeps = api(Resp({}, 429, {"Retry-After": "9999"}), Resp())
	a.auth_test()
	assert sleeps == [sa.MAX_RETRY_AFTER]
	a, _, sleeps = api(Resp({}, 429, {"Retry-After": "abc"}), Resp())
	a.auth_test()
	assert sleeps == [1.0]


def test_token_never_in_error_repr_or_str():
	a, _, _ = api(Resp({"ok": False, "error": "x"}))
	with pytest.raises(SlackApiError) as e:
		a.auth_test()
	for s in (str(e.value), repr(e.value), repr(a), str(a)):
		assert TOKEN not in s


def test_token_never_in_logs(caplog):
	caplog.set_level(logging.DEBUG)
	a, _, _ = api(Resp({"ok": False, "error": "x"}))
	with pytest.raises(SlackApiError):
		a.post_message("C1", "hi")
	assert TOKEN not in caplog.text


def test_users_info_normalized():
	a, h, _ = api(Resp({"ok": True, "user": {"id": "U1", "team_id": "T1", "is_bot": False,
		"is_restricted": True, "deleted": False, "real_name": "x", "profile": {"email": "a@b.c"}}}))
	u = a.users_info("U1")
	assert u == {"id": "U1", "team_id": "T1", "is_bot": False, "is_restricted": True,
		"is_ultra_restricted": False, "deleted": False, "profile": {"email": "a@b.c"}}
	assert h.calls[0][1]["data"] == {"user": "U1"}


def test_users_info_no_email():
	a, _, _ = api(Resp({"ok": True, "user": {"id": "U1", "profile": {}}}))
	assert "profile" not in a.users_info("U1")


def test_users_list_and_conversations_list_params():
	a, h, _ = api(Resp({"ok": True, "members": []}))
	a.users_list(cursor="c", limit=50)
	assert h.calls[0][1]["data"] == {"cursor": "c", "limit": 50}
	a.conversations_list(types="public_channel,private_channel")
	assert h.calls[1][1]["data"] == {"types": "public_channel,private_channel", "limit": 200}


def test_conversations_open_returns_id():
	a, h, _ = api(Resp({"ok": True, "channel": {"id": "D9"}}))
	assert a.conversations_open(["U1", "U2"]) == "D9"
	assert h.calls[0][1]["data"] == {"users": "U1,U2"}


def test_post_message_payload():
	a, h, _ = api(Resp({"ok": True, "ts": "1.2"}))
	a.post_message("C1", "hi", thread_ts="1.0")
	url, kw = h.calls[0]
	assert url.endswith("chat.postMessage")
	assert kw["json"] == {"channel": "C1", "text": "hi", "thread_ts": "1.0",
		"unfurl_links": False, "unfurl_media": False}


def test_post_message_unfurl_true():
	a, h, _ = api(Resp())
	a.post_message("C1", "hi", unfurl=True)
	assert h.calls[0][1]["json"]["unfurl_links"] is True


def test_blocks_passed_through_unchanged():
	blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": "*x*"}}, {"type": "divider"}]
	a, h, _ = api(Resp())
	a.post_message("C1", blocks=blocks)
	assert h.calls[0][1]["json"]["blocks"] is blocks
	a.post_ephemeral("C1", "U1", blocks=blocks)
	assert h.calls[1][1]["json"]["blocks"] is blocks
	a.update_message("C1", "1.2", blocks=blocks)
	assert h.calls[2][1]["json"]["blocks"] is blocks


def test_ephemeral_shape_has_user_and_no_unfurl():
	a, h, _ = api(Resp())
	a.post_ephemeral("C1", "U1", text="psst", thread_ts="1.0")
	url, kw = h.calls[0]
	assert url.endswith("chat.postEphemeral")
	assert kw["json"] == {"channel": "C1", "user": "U1", "text": "psst", "thread_ts": "1.0"}


def test_normal_message_has_no_user_field():
	a, h, _ = api(Resp())
	a.post_message("C1", "x")
	assert "user" not in h.calls[0][1]["json"]


def test_update_message_payload():
	a, h, _ = api(Resp())
	a.update_message("C1", "1.2", text="new")
	assert h.calls[0][1]["json"] == {"channel": "C1", "ts": "1.2", "text": "new"}


def test_reactions_and_permalink():
	a, h, _ = api(Resp(), Resp(), Resp({"ok": True, "permalink": "https://x/p"}))
	a.add_reaction("C1", "1.2", "eyes")
	a.remove_reaction("C1", "1.2", "eyes")
	assert h.calls[0][1]["data"] == {"channel": "C1", "timestamp": "1.2", "name": "eyes"}
	assert h.calls[1][0].endswith("reactions.remove")
	assert a.permalink("C1", "1.2") == "https://x/p"
	assert h.calls[2][1]["data"] == {"channel": "C1", "message_ts": "1.2"}


def _page(items, nxt=""):
	return Resp({"ok": True, "channels": items, "response_metadata": {"next_cursor": nxt}})


def test_paginate_follows_cursor():
	a, h, _ = api(_page([1], "n1"), _page([2], "n2"), _page([3]))
	assert list(a.paginate("conversations.list", "channels", limit=1)) == [1, 2, 3]
	assert h.calls[1][1]["data"]["cursor"] == "n1"


def test_paginate_hard_cap():
	a, h, _ = api(_page([1], "more"))
	assert list(a.paginate("conversations.list", "channels", max_pages=3)) == [1, 1, 1]
	assert len(h.calls) == 3


def test_paginate_default_cap_bounded():
	a, h, _ = api(_page([1], "more"))
	list(a.paginate("conversations.list", "channels"))
	assert len(h.calls) == sa.MAX_PAGES


def test_inspect_token_bot():
	hdr = {"X-OAuth-Scopes": "chat:write, users:read,im:write"}
	a, _, _ = api(Resp({"ok": True, "user_id": "UB", "team_id": "T1", "team": "Acme",
		"url": "https://acme.slack.com/"}, headers=hdr))
	info = sa.inspect_token(a)
	assert info["token_kind"] == "bot" and info["bot_user_id"] == "UB"
	assert info["team_id"] == "T1" and info["team"] == "Acme" and info["url"].startswith("https")
	assert info["granted_scopes"] == ["chat:write", "users:read", "im:write"]
	assert "users:read.email" in info["missing_scopes"] and "chat:write" not in info["missing_scopes"]


def test_inspect_token_kinds():
	assert sa.token_kind("xoxp-1") == "user"
	assert sa.token_kind("xoxb-1") == "bot"
	assert sa.token_kind("abc") == "unknown" and sa.token_kind("") == "unknown"


def test_inspect_token_no_header():
	a, _, _ = api(Resp())
	info = sa.inspect_token(a)
	assert info["granted_scopes"] == []
	assert info["missing_scopes"] == sa.REQUIRED_BOT_SCOPES


def test_missing_scopes_custom_and_all_granted():
	assert sa.missing_scopes(["a"], ["a", "b"]) == ["b"]
	assert sa.missing_scopes(sa.REQUIRED_BOT_SCOPES) == []


def test_required_scopes_contents():
	assert len(sa.REQUIRED_BOT_SCOPES) == 16
	assert "users:read.email" in sa.REQUIRED_BOT_SCOPES


def test_inspect_error_propagates_without_token():
	a, _, _ = api(Resp({"ok": False, "error": "invalid_auth"}))
	with pytest.raises(SlackApiError) as e:
		sa.inspect_token(a)
	assert TOKEN not in str(e.value)
