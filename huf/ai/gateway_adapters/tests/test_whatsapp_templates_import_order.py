# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Smoke: the template modules import cleanly in any order (guards the late ``noqa`` import in whatsapp_templates)."""

import importlib
import itertools
import sys
import unittest

PKG = "huf.ai.gateway_adapters"
NAMES = (f"{PKG}.whatsapp_templates", f"{PKG}.whatsapp_bridge", f"{PKG}.whatsapp_template_parts")


def _purge():
	for name in list(sys.modules):
		if name in NAMES or name.startswith(f"{PKG}.whatsapp_template_parts."):
			del sys.modules[name]


class TestImportOrder(unittest.TestCase):
	def setUp(self):
		self._saved = {n: m for n, m in sys.modules.items() if n in NAMES or n.startswith(f"{PKG}.whatsapp_template_parts.")}
		self.addCleanup(self._restore)

	def _restore(self):
		_purge()
		sys.modules.update(self._saved)

	def test_every_import_order_works(self):
		for order in itertools.permutations(NAMES):
			_purge()
			with self.subTest(order=[n.rsplit(".", 1)[-1] for n in order]):
				for name in order:
					importlib.import_module(name)
				self.assertTrue(hasattr(sys.modules[NAMES[0]], "carousel_parts"))
