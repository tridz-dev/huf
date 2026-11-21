# Copyright (c) 2026, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.automation import event_alias as ea

APP = "ea_test"


def _make_alias(key, sources, **kw):
	doc = frappe.get_doc(
		{
			"doctype": "Event Alias",
			"app": APP,
			"key": key,
			"label": key,
			"sources": sources,
			**kw,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


def _src(event="on_update", **kw):
	return {"reference_doctype": "ToDo", "doc_event": event, "enabled": 1, **kw}


def _todo():
	return frappe.get_doc({"doctype": "ToDo", "description": "event alias test"}).insert(
		ignore_permissions=True
	)


class TestEventAlias(IntegrationTestCase):
	def setUp(self):
		frappe.db.delete("Event Alias Source", {"parent": ["like", f"{APP}.%"]})
		frappe.db.delete("Event Alias", {"app": APP})
		ea.clear_alias_cache()

	def tearDown(self):
		frappe.db.rollback()
		frappe.db.delete("Event Alias Source", {"parent": ["like", f"{APP}.%"]})
		frappe.db.delete("Event Alias", {"app": APP})
		frappe.db.delete("ToDo", {"description": "event alias test"})
		frappe.db.commit()
		ea.clear_alias_cache()

	def _fires(self, mock_enqueue):
		return [c.kwargs["alias_name"] for c in mock_enqueue.call_args_list]

	# 1. fires once after commit; rollback fires nothing; repeated saves dedupe
	def test_fires_once_after_commit(self):
		_make_alias("once", [_src("on_update")])
		frappe.db.commit()
		with patch("frappe.enqueue") as enq:
			todo = _todo()
			todo.description = "event alias test"
			todo.priority = "High"
			todo.save()
			todo.priority = "Low"
			todo.save()
			self.assertEqual(self._fires(enq), [], "nothing may fire before commit")
			frappe.db.commit()
			self.assertEqual(self._fires(enq), [f"{APP}.once"])
			self.assertEqual(enq.call_args.kwargs["payload"], {"doctype": "ToDo", "name": todo.name})

	def test_rollback_fires_nothing(self):
		_make_alias("rb", [_src("after_insert")])
		frappe.db.commit()
		with patch("frappe.enqueue") as enq:
			_todo()
			frappe.db.rollback()
			frappe.db.commit()
			self.assertEqual(self._fires(enq), [])

	def test_condition_and_mapping(self):
		_make_alias(
			"cm",
			[
				_src(
					"after_insert",
					condition="doc.priority == 'High'",
					payload_mapping='{"who": "doc.owner", "p": "doc.priority"}',
					dedupe_key="doc.name",
				)
			],
		)
		frappe.db.commit()
		with patch("frappe.enqueue") as enq:
			frappe.get_doc({"doctype": "ToDo", "description": "event alias test", "priority": "Low"}).insert()
			frappe.db.commit()
			self.assertEqual(self._fires(enq), [])
			frappe.get_doc({"doctype": "ToDo", "description": "event alias test", "priority": "High"}).insert()
			frappe.db.commit()
			self.assertEqual(self._fires(enq), [f"{APP}.cm"])
			self.assertEqual(enq.call_args.kwargs["payload"]["p"], "High")

	# 2. never fails a save
	def test_alias_error_never_fails_save(self):
		_make_alias("bad", [_src("after_insert", condition="doc.nothing_here.x > 1")])
		frappe.db.commit()
		before = ea.get_error_count(f"{APP}.bad")  # the counter lives in cache and survives reruns
		with patch("frappe.enqueue") as enq:
			todo = _todo()  # must not raise
			self.assertTrue(frappe.db.exists("ToDo", todo.name))
			frappe.db.commit()
			self.assertEqual(self._fires(enq), [])
		self.assertEqual(ea.get_error_count(f"{APP}.bad"), before + 1)
		self.assertTrue(frappe.db.exists("Error Log", {"method": ["like", f"Event Alias error: {APP}.bad%"]}))

	# 3. zero cost on doctypes without aliases
	def test_unaliased_doctype_zero_queries(self):
		_make_alias("some", [_src("on_update")])
		ea.get_alias_map()  # warm
		doc = frappe._dict(doctype="Note", name="n1")
		calls = []
		real = frappe.db.sql

		def counting(*a, **kw):
			calls.append(a)
			return real(*a, **kw)

		with patch.object(frappe.db, "sql", counting):
			ea.dispatch_doc_event(doc, "on_update")
		self.assertEqual(calls, [])

	def test_cache_cleared_on_alias_save(self):
		self.assertEqual(ea.get_sources("ToDo", "on_update"), [])
		_make_alias("late", [_src("on_update")])
		self.assertEqual(len(ea.get_sources("ToDo", "on_update")), 1)

	# 4. versioning and deprecation
	def test_versioning_and_deprecation(self):
		alias = _make_alias("ver", [_src("on_update"), _src("after_insert")])
		self.assertEqual(alias.version, 1)
		alias.description = "more words"
		alias.append("sources", _src("on_submit"))
		alias.save()
		self.assertEqual(alias.version, 1, "additive change keeps version")
		alias.remove(alias.sources[0])
		alias.save()
		self.assertEqual(alias.version, 2, "removing a source bumps version")

		_make_alias("ver2", [_src("on_update")])
		dep = ea.deprecate_alias(f"{APP}.ver", replaced_by=f"{APP}.ver2")
		self.assertEqual((dep.status, dep.replaced_by, dep.version), ("Deprecated", f"{APP}.ver2", 3))

		with patch("huf.ai.automation.event_alias.fan_out_app_event", return_value={"triggered": 1}) as fan:
			res = ea.fire_alias(f"{APP}.ver", {"a": 1}, run_as="Administrator")
		self.assertEqual(res, {"triggered": 1})
		fan.assert_called_once_with(APP, "ver", {"a": 1}, "Administrator")

	# 6. legacy runtime no-ops
	def test_legacy_runtime_noop(self):
		_make_alias("leg", [_src("after_insert")])
		frappe.db.commit()
		with patch("frappe.enqueue") as enq, patch.object(ea, "automation_runtime_is_new", return_value=False):
			_todo()
			frappe.db.commit()
			self.assertEqual(self._fires(enq), [])
			self.assertEqual(ea.fire_alias(f"{APP}.leg")["skipped"], "legacy_runtime")
