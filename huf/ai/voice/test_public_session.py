"""Bench-less regression test: start_public_session must reject a bad
publishable key with the intended PermissionError, not an UnboundLocalError
caused by the translation helper being shadowed inside the function."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import frappe
import pytest

if isinstance(frappe, MagicMock):  # bench-less stub: decorators must not swallow the handler
	frappe.whitelist = lambda *a, **k: (lambda fn: fn)

from huf.ai.voice import api


class Rejected(Exception):
	pass


def test_wrong_publishable_key_is_rejected_cleanly():
	agent_doc = SimpleNamespace(embed_enabled=1, publishable_key="pk_real", allowed_origins="")

	def fake_throw(message, exc=None):
		raise Rejected(message)

	with (
		patch.object(api.frappe, "get_doc", return_value=agent_doc),
		patch.object(api.frappe, "throw", side_effect=fake_throw),
	):
		with pytest.raises(Rejected):
			api.start_public_session("pk_wrong", "Some Agent")
