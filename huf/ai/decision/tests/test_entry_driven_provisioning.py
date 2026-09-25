# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Layer A (mocked-frappe, no bench) tests for entry-driven decision provisioning.

`setup_deployment` used to call the install-time Jev seeders, whose every key is
a module constant, so a non-Jev catalog entry either mutated the existing
OpenCode Zen deployment or created a mislabelled one whose endpoint_path was
`/v1/systemone`. `provision_catalog_entry` derives every row from the entry.

These tests assert the ROWS THAT WOULD BE CREATED -- the consumer -- not the
catalog dict. The earlier Laya catalog tests passed unchanged while the defect
was live precisely because they only re-read the data they asserted on.

Run standalone (no bench) from the repo root:
    PYTHONPATH=. python3 huf/ai/decision/tests/test_entry_driven_provisioning.py -v
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
from huf.patches.v1 import seed_decision_system_one as seed  # noqa: E402


class _Captured:
	"""Records what provision_catalog_entry would insert, keyed by doctype."""

	def __init__(self):
		self.rows = {}

	def get_or_create(self, doctype, key_field, key_value, values, **kwargs):
		self.rows.setdefault(doctype, []).append({key_field: key_value, **values})
		return f"{doctype}:{key_value}"


class ProvisioningTestCase(unittest.TestCase):
	def _provision(self, brand, model_name, provider_name):
		entry = catalog.get_entry(brand, model_name)
		self.assertIsNotNone(entry, f"no catalog entry for {brand}/{model_name}")
		cap = _Captured()
		with patch.object(seed, "_get_or_create", side_effect=cap.get_or_create):
			deployment = seed.provision_catalog_entry(entry, provider_name)
		return entry, cap, deployment

	def _only(self, cap, doctype, **match):
		rows = [r for r in cap.rows.get(doctype, []) if all(r.get(k) == v for k, v in match.items())]
		self.assertEqual(len(rows), 1, f"expected exactly one {doctype} matching {match}, got {rows}")
		return rows[0]


class TestLayaProvisioning(ProvisioningTestCase):
	"""The case that was silently broken."""

	def test_laya_deployment_uses_predict_not_systemone(self):
		"""This is the assertion the catalog-only tests could never make."""
		entry, cap, _ = self._provision("laya", "laya-english", "MyLaya")
		dep = self._only(cap, "Decision Deployment", provider_model_id="laya-english")
		self.assertEqual(dep["endpoint_path"], "/predict")
		self.assertEqual(dep["endpoint_path"], entry.endpoint_path)
		self.assertEqual(dep["wire_protocol"], "systemone")
		self.assertEqual(dep["provider"], "MyLaya")

	def test_laya_does_not_touch_the_jev_deployment(self):
		"""The old path reused deployment_key 'jev-1-13-opencode-zen'."""
		_, cap, deployment = self._provision("laya", "laya-english", "MyLaya")
		keys = [r["deployment_key"] for r in cap.rows["Decision Deployment"]]
		self.assertNotIn(seed.DEPLOYMENT_KEY, keys)
		self.assertNotIn("jev", deployment.lower())

	def test_laya_binds_to_the_laya_family(self):
		"""Family comes from entry.model_family, not a hardcoded 'jev' lookup."""
		_, cap, _ = self._provision("laya", "laya-english", "MyLaya")
		model = self._only(cap, "Decision Model", model_name="Laya English")
		self.assertIn("laya", model["family"].lower())
		family = self._only(cap, "Decision Model Family", family_key="laya")
		# Same wire as Jev, so deliberately the same registered adapter.
		self.assertEqual(family["adapter_id"], "jev_system_one")

	def test_each_checkpoint_gets_its_own_rows(self):
		"""Three checkpoints must not collapse onto one deployment."""
		seen = set()
		for model_name in ("laya-english", "laya-multilingual", "laya-typed"):
			_, cap, _ = self._provision("laya", model_name, "MyLaya")
			dep = self._only(cap, "Decision Deployment", provider_model_id=model_name)
			seen.add(dep["deployment_key"])
			self.assertEqual(dep["endpoint_path"], "/predict")
		self.assertEqual(len(seen), 3, f"deployment keys collided: {seen}")


class TestJevStillProvisions(ProvisioningTestCase):
	"""Laya must not be bought at Jev's expense."""

	def test_jev_keeps_its_endpoint_and_model_id(self):
		entry, cap, _ = self._provision("opencode-zen", "jev-1.13-free", "OpenCodeZen")
		dep = self._only(cap, "Decision Deployment", provider_model_id="jev-1.13-free")
		self.assertEqual(dep["endpoint_path"], "/v1/systemone")
		self.assertEqual(dep["endpoint_path"], entry.endpoint_path)
		self.assertEqual(dep["wire_protocol"], "systemone")

	def test_jev_binds_to_the_jev_family(self):
		_, cap, _ = self._provision("opencode-zen", "jev-1.13-free", "OpenCodeZen")
		family = self._only(cap, "Decision Model Family", family_key="jev")
		self.assertEqual(family["adapter_id"], "jev_system_one")

	def test_jev_and_laya_do_not_share_a_deployment_key(self):
		_, jev_cap, _ = self._provision("opencode-zen", "jev-1.13-free", "OpenCodeZen")
		_, laya_cap, _ = self._provision("laya", "laya-english", "MyLaya")
		jev_key = self._only(jev_cap, "Decision Deployment", provider_model_id="jev-1.13-free")[
			"deployment_key"
		]
		laya_key = self._only(laya_cap, "Decision Deployment", provider_model_id="laya-english")[
			"deployment_key"
		]
		self.assertNotEqual(jev_key, laya_key)


class TestUnknownFamilyIsRejected(ProvisioningTestCase):
	def test_entry_naming_an_unregistered_family_throws(self):
		"""Better to fail than provision against the wrong adapter."""
		bogus = catalog.CatalogEntry(
			provider_brand="acme",
			model_name="acme-1",
			canonical_model="Acme 1",
			model_family="Acme",
			model_class="System One",
			wire_protocol="systemone",
			endpoint_path="/predict",
		)
		cap = _Captured()
		with patch.object(seed, "_get_or_create", side_effect=cap.get_or_create):
			with patch.object(seed.frappe, "throw", side_effect=RuntimeError) as thrown:
				with self.assertRaises(RuntimeError):
					seed.provision_catalog_entry(bogus, "Acme")
				self.assertTrue(thrown.called)


if __name__ == "__main__":
	unittest.main(verbosity=2)
