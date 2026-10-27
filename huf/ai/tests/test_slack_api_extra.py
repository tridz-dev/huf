import sys
from types import SimpleNamespace

sys.path.insert(0, "huf/ai/tests")
import _stub_env  # noqa: E402

_stub_env.install()

import pytest  # noqa: E402

from huf.ai.gateways.slack_api import SlackApi, SlackApiError  # noqa: E402


def _api(body):
	calls = []

	def http(url, **kw):
		calls.append((url, kw))
		return SimpleNamespace(status_code=200, headers={}, json=lambda: body)

	return SlackApi("xoxb-t", http=http), calls


def test_lookup_by_email_returns_id():
	api, calls = _api({"ok": True, "user": {"id": "U1"}})
	assert api.users_lookup_by_email("a@b.co") == "U1"
	assert calls[0][0].endswith("users.lookupByEmail")
	assert calls[0][1]["data"] == {"email": "a@b.co"}


def test_lookup_by_email_not_found_is_none():
	api, _ = _api({"ok": False, "error": "users_not_found"})
	assert api.users_lookup_by_email("a@b.co") is None


def test_lookup_by_email_other_error_raises():
	api, _ = _api({"ok": False, "error": "missing_scope"})
	with pytest.raises(SlackApiError):
		api.users_lookup_by_email("a@b.co")
