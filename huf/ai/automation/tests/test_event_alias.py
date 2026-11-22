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
			frappe.get_doc(
				{"doctype": "ToDo", "description": "event alias test", "priority": "High"}
			).insert()
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
		with (
			patch("frappe.enqueue") as enq,
			patch.object(ea, "automation_runtime_is_new", return_value=False),
		):
			_todo()
			frappe.db.commit()
			self.assertEqual(self._fires(enq), [])
			self.assertEqual(ea.fire_alias(f"{APP}.leg")["skipped"], "legacy_runtime")


class TestEventAliasMigrateSafety(IntegrationTestCase):
	"""The wildcard hook must be inert before the Event Alias table exists."""

	def setUp(self):
		ea.clear_alias_cache()

	def tearDown(self):
		ea.clear_alias_cache()

	def test_missing_table_is_noop(self):
		doc = frappe.get_doc({"doctype": "ToDo", "description": "event alias test"})
		with (
			patch.object(frappe.db, "table_exists", return_value=False),
			patch("frappe.get_all", side_effect=RuntimeError("table missing")),
			patch("frappe.log_error") as log_error,
		):
			ea.dispatch_doc_event(doc, "on_update")
			ea.dispatch_doc_event(doc, "after_insert")
		log_error.assert_not_called()
		self.assertEqual(ea.get_alias_map(), {"sources": {}, "aliases": {}})

	def test_ignored_doctypes_skip_lookup(self):
		for dt in ("Error Log", "Event Alias", "Event Alias Source"):
			with (
				patch.object(ea, "get_sources", return_value=[]) as lookup,
				patch("frappe.log_error") as log_error,
			):
				ea.dispatch_doc_event(frappe._dict(doctype=dt, name="x"), "after_insert")
			lookup.assert_not_called()
			log_error.assert_not_called()

	def test_migrate_flag_skips(self):
		frappe.flags.in_migrate = True
		try:
			with (
				patch.object(ea, "get_sources", return_value=[]) as lookup,
				patch("frappe.log_error") as log_error,
			):
				ea.dispatch_doc_event(frappe._dict(doctype="ToDo", name="x"), "on_update")
		finally:
			frappe.flags.in_migrate = False
		lookup.assert_not_called()
		log_error.assert_not_called()

	def test_formerly_ignored_doctypes_still_dispatch(self):
		src = {"alias": "a.b", "condition": "", "payload_mapping": {}, "dedupe_key": ""}
		for dt in ("Communication", "Comment", "Notification Log", "Email Queue", "Integration Request"):
			with (
				patch.object(ea, "get_sources", return_value=[src]) as lookup,
				patch.object(ea, "_schedule") as schedule,
				patch.object(ea, "automation_runtime_is_new", return_value=True),
			):
				ea.dispatch_doc_event(frappe._dict(doctype=dt, name="x"), "after_insert")
			lookup.assert_called_once_with(dt, "after_insert")
			schedule.assert_called_once()

	def test_failure_does_not_recurse(self):
		"""log_error inserting an Error Log re-fires the hook: calls stay bounded."""
		doc = frappe._dict(doctype="ToDo", name="x")
		hook_calls = []

		def fake_log_error(*a, **kw):
			# What a real Error Log insert does: run wildcard doc-event hooks.
			hook_calls.append(1)
			assert len(hook_calls) < 10, "runaway recursion"
			ea.dispatch_doc_event(frappe._dict(doctype="Note", name="y"), "after_insert")

		with (
			patch.object(ea, "get_sources", side_effect=RuntimeError("boom")),
			patch("frappe.log_error", side_effect=fake_log_error),
		):
			ea.dispatch_doc_event(doc, "on_update")
		self.assertEqual(len(hook_calls), 1)
		self.assertFalse(getattr(frappe.local, ea._REENTRY_FLAG, False))

	def test_record_failure_never_raises(self):
		with patch("frappe.log_error", side_effect=RuntimeError("log broke")):
			ea.record_failure("a.b", "dispatch")


class _FakeCache:
	"""Mimics frappe's RedisWrapper: a miss without expires=True is memoised locally,
	and set_value with an expiry writes only to the backend."""

	def __init__(self):
		self.local, self.backend = {}, {}

	def get_value(self, key, expires=False, **kw):
		if key in self.local:
			return self.local[key]
		val = self.backend.get(key)
		if not expires:
			self.local[key] = val
		return val

	def set_value(self, key, val, expires_in_sec=None, **kw):
		self.backend[key] = val
		if not expires_in_sec:
			self.local[key] = val


class TestClaimDedupe(IntegrationTestCase):
	def test_claim_dedupe_only_first_wins(self):
		with patch("frappe.cache", return_value=_FakeCache()):
			self.assertTrue(ea.claim_dedupe("a.b", "k"))
			self.assertFalse(ea.claim_dedupe("a.b", "k"))
			self.assertFalse(ea.claim_dedupe("a.b", "k"))
			self.assertTrue(ea.claim_dedupe("a.b", "other"))
