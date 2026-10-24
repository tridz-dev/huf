"""Mock-level proof that sync_discovered_tools upserts the telegram registry blocks."""

import unittest
from unittest.mock import MagicMock, patch

import frappe

from huf.ai.tools import registry as tool_registry
from huf.ai.tools._registry import ALL_INTEGRATION_TOOLS


def _run_sync(existing):
	"""Run the sync with registry tools; return (created payloads, updated docs)."""
	tools = [t for t in ALL_INTEGRATION_TOOLS if t["tool_name"] in ("telegram", "telegram_admin")]
	created, updated = [], []

	def get_doc(arg, name=None):
		# get_doc(dict) = create; get_doc(doctype, name) = load for update
		if isinstance(arg, dict):
			created.append(arg)
			return MagicMock()
		doc = MagicMock()
		updated.append((name, doc))
		return doc

	def get_all(doctype, filters=None, fields=None):
		if filters and "tool_name" in filters:
			return [frappe._dict(name=n, tool_name=n) for n in existing]
		return []

	frappe_mock = MagicMock()
	frappe_mock.get_doc.side_effect = get_doc
	frappe_mock.get_all.side_effect = get_all
	frappe_mock.db.exists.return_value = True
	frappe.local.flags = frappe._dict(in_test=False)
	with (
		patch.object(tool_registry, "frappe", frappe_mock),
		patch.object(tool_registry, "get_tools_by_app", return_value={"huf": tools}),
		patch.object(tool_registry, "commit_if_background"),
	):
		result = tool_registry.sync_discovered_tools(use_cache=False)
	return result, created, updated


class TestTelegramToolSync(unittest.TestCase):
	def test_registry_contains_admin_block_with_service(self):
		by_name = {t["tool_name"]: t for t in ALL_INTEGRATION_TOOLS}
		self.assertEqual(by_name["telegram_admin"]["service"], "telegram")
		self.assertEqual(by_name["telegram"]["service"], "telegram")

	def test_telegram_rows_are_the_argument_table(self):
		from huf.ai.tools import telegram_tool_spec as spec

		_, _, updated = _run_sync(existing=["telegram", "telegram_admin"])
		(doc,) = [d for n, d in updated if n == "telegram"]
		fields = [p["fieldname"] for p in doc.update.call_args[0][0]["parameters"]]
		declared = {n for a in spec.ACTION_ARGS.values() for n in a}
		self.assertEqual(set(fields), declared | {"action"})
		self.assertEqual(len(fields), len(set(fields)))
		self.assertFalse(set(spec.INTERNAL_ARGS) & set(fields))

	def test_new_admin_entry_is_created(self):
		result, created, updated = _run_sync(existing=["telegram"])
		self.assertEqual(result["error_count"], 0, result["errors"])
		self.assertEqual([c["tool_name"] for c in created], ["telegram_admin"])
		payload = created[0]
		self.assertEqual(payload["service"], "telegram")
		self.assertEqual(payload["types"], "App Provided")
		fields = {p["fieldname"] for p in payload["parameters"]}
		self.assertIn("action", fields)
		self.assertNotIn(
			"confirmation_token", fields
		)  # removed: approval is a human press, never an agent argument
		self.assertNotIn("confirm", fields)
		from huf.ai.tools import telegram_admin_spec as spec

		declared = {n for a in spec.ACTION_ARGS.values() for n in a}
		self.assertEqual(fields, declared | {"action"})  # the synced rows carry every action's arguments
		self.assertIn("short_description", fields)

	def test_existing_telegram_row_is_refreshed(self):
		_, _, updated = _run_sync(existing=["telegram", "telegram_admin"])
		self.assertEqual({n for n, _ in updated}, {"telegram", "telegram_admin"})
		reg = {t["tool_name"]: t for t in ALL_INTEGRATION_TOOLS}
		for name, doc in updated:
			payload = doc.update.call_args[0][0]
			self.assertEqual(payload["description"], reg[name]["description"])
			self.assertEqual(len(payload["parameters"]), len(reg[name]["parameters"]))
			doc.save.assert_called_once()
