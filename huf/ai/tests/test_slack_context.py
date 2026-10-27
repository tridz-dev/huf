import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, "huf/testing")
import _stub_env  # noqa: E402

_stub_env.install()

import frappe  # noqa: E402
import pytest  # noqa: E402

from huf.ai.gateways import slack_context  # noqa: E402


class Row:
	def __init__(self, key, value):
		self.key = key
		self._v = value

	def get_password(self, _f):
		return self._v


def _gw(name="IS-1"):
	return SimpleNamespace(integration_settings=name)


def test_reads_credential(monkeypatch):
	monkeypatch.setattr(frappe, "get_doc", MagicMock(return_value=SimpleNamespace(credentials=[Row("token", "xoxb-1"), Row("signing_secret", "s")])))
	assert slack_context.get_gateway_credential(_gw(), "signing_secret") == "s"
	assert slack_context.get_gateway_credential(_gw(), "nope") == ""


def test_no_settings_link():
	assert slack_context.get_gateway_credential(_gw(None), "token") == ""


def test_get_slack_api_requires_token(monkeypatch):
	monkeypatch.setattr(frappe, "get_doc", MagicMock(return_value=SimpleNamespace(credentials=[])))
	with pytest.raises(ValueError) as e:
		slack_context.get_slack_api(_gw())
	assert "xoxb" not in str(e.value)


def test_get_slack_api_builds_client(monkeypatch):
	monkeypatch.setattr(frappe, "get_doc", MagicMock(return_value=SimpleNamespace(credentials=[Row("token", "xoxb-secret")])))
	api = slack_context.get_slack_api(_gw())
	assert "xoxb-secret" not in repr(api)
