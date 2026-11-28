"""Pure tests: capability, share, send-cap and approval-default records are write-denied for tools (M5)."""

import sys
import unittest
from unittest.mock import MagicMock

try:
	import frappe  # noqa: F401
except ImportError:
	sys.modules.setdefault("frappe", MagicMock())

from huf.ai.tools.doctype_guard import is_denylisted

NAMES = [
	"Huf Role Permission", "Huf Role", "DocShare", "Agent Role",
	"Execution Profile Permission", "Flow Send Counter", "Agent Settings",
]


class TestWriteDenylistM5(unittest.TestCase):
	def test_write_refused(self):
		for name in NAMES:
			self.assertTrue(is_denylisted(name), name)
			self.assertTrue(is_denylisted(f"  {name.upper()} "), name)

	def test_read_still_allowed(self):
		for name in NAMES:
			self.assertFalse(is_denylisted(name, read_only=True), name)


if __name__ == "__main__":
	unittest.main()
