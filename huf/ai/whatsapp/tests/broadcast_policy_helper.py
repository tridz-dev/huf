# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Test helper: pin broadcast limits without touching the settings document."""

from contextlib import contextmanager
from unittest.mock import patch

from huf.ai.whatsapp.broadcast import policy


@contextmanager
def limit_override(**values):
	"""Within the block ``policy.get(key)`` returns ``values[key]`` (source ``settings``)."""
	real = policy.resolve

	def fake(key, broadcast=None):
		return (values[key], "settings") if key in values else real(key, broadcast)

	with patch.object(policy, "resolve", fake):
		yield
