# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# See license.txt

"""Shared test infrastructure for huf's backend test suite.

Mirrors the ERPNextTestSuite / HRMSTestSuite pattern (unittest.TestCase
subclass with rollback teardown + a bootstrap-data helper for the master
records most huf doctypes link to), rather than the deprecated
frappe.tests.utils.FrappeTestCase used by the older doctype test stubs.
"""

import unittest
from contextlib import contextmanager

import frappe


class HufTestSuite(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		cls.bootstrap = BootStrapTestData()
		cls.bootstrap.setup()

	def tearDown(self):
		frappe.db.rollback()
		frappe.local.request_cache.clear()

	@contextmanager
	def set_user(self, user: str):
		old_user = frappe.session.user
		try:
			frappe.set_user(user)
			yield
		finally:
			frappe.set_user(old_user)

	@contextmanager
	def change_settings(self, doctype, settings_dict=None, /, **settings):
		"""Temporarily change fields on a settings doctype, restoring the
		original values on exit."""
		settings_dict = {**(settings_dict or {}), **settings}
		try:
			doc = frappe.get_single(doctype)
		except frappe.DoesNotExistError:
			doc = frappe.new_doc(doctype)

		original = {key: doc.get(key) for key in settings_dict}
		try:
			doc.update(settings_dict)
			doc.save(ignore_permissions=True)
			frappe.db.commit()
			yield doc
		finally:
			doc.update(original)
			doc.save(ignore_permissions=True)
			frappe.db.commit()


class BootStrapTestData:
	"""Creates minimal `_Test`-prefixed master data that huf doctypes commonly
	link to (an AI Provider + AI Model + Agent), so per-doctype tests don't
	each have to hand-roll the same fixture chain.

	Idempotent: safe to call multiple times (e.g. once per TestCase class via
	setUpClass) since it checks for existing records first.
	"""

	PROVIDER_NAME = "_Test Provider"
	MODEL_NAME = "_Test Model"
	AGENT_NAME = "_Test Agent"

	def setup(self):
		self.provider = self._get_or_create_provider()
		self.model = self._get_or_create_model()
		self.agent = self._get_or_create_agent()
		frappe.db.commit()  # visible across the test class's connections

	def _get_or_create_provider(self):
		if frappe.db.exists("AI Provider", self.PROVIDER_NAME):
			return frappe.get_doc("AI Provider", self.PROVIDER_NAME)

		return frappe.get_doc({
			"doctype": "AI Provider",
			"provider_name": self.PROVIDER_NAME,
			"provider_brand": "openai",
			"api_key": "test-key-not-real",
		}).insert(ignore_permissions=True)

	def _get_or_create_model(self):
		if frappe.db.exists("AI Model", self.MODEL_NAME):
			return frappe.get_doc("AI Model", self.MODEL_NAME)

		return frappe.get_doc({
			"doctype": "AI Model",
			"provider": self.provider.name,
			"model_name": self.MODEL_NAME,
		}).insert(ignore_permissions=True)

	def _get_or_create_agent(self):
		if frappe.db.exists("Agent", self.AGENT_NAME):
			return frappe.get_doc("Agent", self.AGENT_NAME)

		return frappe.get_doc({
			"doctype": "Agent",
			"agent_name": self.AGENT_NAME,
			"provider": self.provider.name,
			"model": self.model.name,
		}).insert(ignore_permissions=True)
