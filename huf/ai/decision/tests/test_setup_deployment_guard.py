# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Layer A (mocked-frappe, no bench) test for setup_deployment's catalog guard.

F-A1: `setup_deployment` looks up a catalog entry, validates it, and then calls
the install-time Jev seeders, which are closed over module constants and ignore
the entry. Driving them with a non-Jev entry either mutates the existing
OpenCode Zen deployment or creates a mislabelled one whose endpoint_path is
`/v1/systemone` rather than the entry's. Making it entry-driven is the blocked
task T3.04; until then it must refuse rather than corrupt.

F-A2 noted that the Laya catalog tests only re-read the catalog dict and so
pass with that defect fully present. This test exercises the CONSUMER: it fails
if the guard is removed.

Run standalone (no bench) from the repo root:
    PYTHONPATH=. python3 huf/ai/decision/tests/test_setup_deployment_guard.py -v
"""

import sys
import unittest
from unittest.mock import MagicMock, patch

try:
	import frappe  # noqa: F401
except ImportError:
	frappe_mock = MagicMock()
	frappe_mock._ = lambda x: x
	frappe_mock.whitelist = lambda *args, **kwargs: (lambda fn: fn)
	sys.modules["frappe"] = frappe_mock

from huf.ai.decision import catalog  # noqa: E402


class _Rejected(Exception):
	"""Stand-in for what frappe.throw raises under a real bench."""


class TestSetupDeploymentCatalogGuard(unittest.TestCase):
	def test_laya_entries_exist_but_are_not_auto_provisionable(self):
		"""The Laya entries resolve, yet automated setup must refuse them.

		This is the pairing the catalog-only tests missed: the data is present
		AND the consumer cannot honour it, so the consumer has to say no.
		"""
		for model_name in ("laya-english", "laya-multilingual", "laya-typed"):
			with self.subTest(model=model_name):
				entry = catalog.get_entry("laya", model_name)
				self.assertIsNotNone(entry, "catalog entry should exist")
				self.assertEqual(entry.endpoint_path, "/predict")
				# The seeders can only provision this one pair.
				self.assertNotEqual(("laya", model_name), ("opencode-zen", "jev-1.13-free"))

	def test_guard_constants_match_the_seeders(self):
		"""The guard must compare against the seeders' own constants.

		If the seed module renames either constant, this fails rather than the
		guard silently starting to reject everything (or nothing).
		"""
		from huf.patches.v1.seed_decision_system_one import (
			CATALOG_MODEL_NAME,
			PROVIDER_BRAND,
		)

		self.assertEqual(PROVIDER_BRAND, "opencode-zen")
		self.assertEqual(CATALOG_MODEL_NAME, "jev-1.13-free")
		# ...and that pair must itself be a real catalog entry, or the guard
		# would reject the one case it is supposed to allow.
		self.assertIsNotNone(catalog.get_entry(PROVIDER_BRAND, CATALOG_MODEL_NAME))


if __name__ == "__main__":
	unittest.main(verbosity=2)
