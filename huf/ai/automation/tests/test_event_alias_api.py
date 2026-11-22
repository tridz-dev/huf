# Copyright (c) 2026, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

"""emit / list / get, seeding folder and the huf_event_aliases hook.

    bench --site <site> run-tests --app huf --module huf.ai.automation.tests.test_event_alias_api
"""

import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from huf.ai.app_seeding.seeder import seed_app
from huf.ai.automation import event_alias as ea
from huf.api import events

_FIXTURE_ALIASES = (
	Path(__file__).resolve().parents[2] / "app_seeding" / "tests" / "fixture_app" / "huf" / "event_aliases"
)
APP = "ea_api_test"
SEED_APP = "ea_fixture_shop"


def _user(email, roles):
	if not frappe.db.exists("User", email):
		frappe.get_doc(
			{"doctype": "User", "email": email, "first_name": "EA", "send_welcome_email": 0}
		).insert(ignore_permissions=True)
	user = frappe.get_doc("User", email)
	user.roles = []
	for role in roles:
		user.append("roles", {"role": role})
	user.save(ignore_permissions=True)
	return email


def _hooks_returning(definitions):
	real = frappe.get_hooks

	def fake(hook=None, *args, **kwargs):
		if hook == "huf_event_aliases":
			return definitions
		return real(hook, *args, **kwargs)

	return patch("frappe.get_hooks", side_effect=fake)


def _alias(key="ping", **kw):
	name = f"{APP}.{key}"
	if not frappe.db.exists("Event Alias", name):
		frappe.get_doc(
			{"doctype": "Event Alias", "app": APP, "key": key, "label": key.title(), **kw}
		).insert(ignore_permissions=True)
	return name


class TestEventAliasApi(IntegrationTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		for app in (APP, SEED_APP):
			self._purge(app)
		frappe.db.commit()
		ea.clear_alias_cache()
		frappe.cache().delete_keys(ea.DEDUPE_PREFIX)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		for app in (APP, SEED_APP):
			self._purge(app)
		frappe.db.delete("ToDo", {"description": "event alias api test"})
		frappe.db.commit()
		ea.clear_alias_cache()

	@staticmethod
	def _purge(app):
		frappe.db.delete("Event Alias Source", {"parent": ["like", f"{app}.%"]})
		frappe.db.delete("Event Alias", {"app": app})

	def _fixture_dir(self):
		"""A huf/ folder holding only the fixture event_aliases (no agents or tools)."""
		root = Path(tempfile.mkdtemp())
		self.addCleanup(shutil.rmtree, root, ignore_errors=True)
		shutil.copytree(_FIXTURE_ALIASES, root / "event_aliases")
		return root

	def _fires(self, enq):
		return [c.kwargs["alias_name"] for c in enq.call_args_list]

	# emit: same after-commit, dedupe and error rules
	def test_emit_fires_after_commit_with_run_as(self):
		_alias()
		with patch("frappe.enqueue") as enq:
			out = events.emit(APP, "ping", {"a": 1}, run_as="Administrator")
			self.assertTrue(out["scheduled"])
			self.assertEqual(self._fires(enq), [], "nothing may fire before commit")
			frappe.db.commit()
			self.assertEqual(self._fires(enq), [f"{APP}.ping"])
			self.assertEqual(enq.call_args.kwargs["payload"], {"a": 1})
			self.assertEqual(enq.call_args.kwargs["run_as"], "Administrator")

	def test_emit_rollback_fires_nothing(self):
		_alias()
		frappe.db.commit()
		with patch("frappe.enqueue") as enq:
			events.emit(APP, "ping", {"a": 1})
			frappe.db.rollback()
			frappe.db.commit()
			self.assertEqual(self._fires(enq), [])

	def test_emit_dedupes_identical_payload_and_honours_dedupe_key(self):
		_alias()
		frappe.db.commit()
		with patch("frappe.enqueue") as enq:
			events.emit(APP, "ping", {"a": 1})
			events.emit(APP, "ping", {"a": 1})
			events.emit(APP, "ping", {"a": 2})
			frappe.db.commit()
			self.assertEqual(len(self._fires(enq)), 2)
		with patch("frappe.enqueue") as enq:
			events.emit(APP, "ping", {"n": 1}, dedupe_key="k1")
			events.emit(APP, "ping", {"n": 2}, dedupe_key="k1")
			frappe.db.commit()
			self.assertEqual(len(self._fires(enq)), 1)

	def test_emit_enqueue_failure_is_swallowed_and_counted(self):
		name = _alias()
		frappe.db.commit()
		before = ea.get_error_count(name)
		with patch("frappe.enqueue", side_effect=RuntimeError("boom")):
			events.emit(APP, "ping", {"x": 1})
			frappe.db.commit()
		self.assertEqual(ea.get_error_count(name), before + 1)

	def test_emit_validates_input(self):
		_alias()
		with self.assertRaises(frappe.DoesNotExistError):
			events.emit(APP, "nope", {})
		with self.assertRaises(frappe.ValidationError):
			events.emit(APP, "ping", [1, 2])
		self.assertEqual(events.emit(APP, "ping", "{}")["alias"], f"{APP}.ping")

	def test_run_as_other_user_needs_write_access(self):
		_alias()
		frappe.db.commit()
		plain = _user("ea_api_plain@example.com", ["Huf User"])
		frappe.set_user(plain)
		with self.assertRaises(frappe.PermissionError):
			events.emit(APP, "ping", {}, run_as="Administrator")
		with patch("frappe.enqueue") as enq:
			self.assertEqual(events.emit(APP, "ping", {"own": 1})["run_as"], plain)
			frappe.db.commit()
			self.assertEqual(enq.call_args.kwargs["run_as"], plain)

	def test_run_as_must_be_enabled_user(self):
		_alias()
		with self.assertRaises(frappe.ValidationError):
			events.emit(APP, "ping", {}, run_as="ghost-user@example.com")

	def test_emit_reaches_app_event_automations_as_service_user(self):
		name = _alias()
		frappe.db.commit()
		with patch("huf.ai.automation.event_alias.fan_out_app_event", return_value={"triggered": 1}) as fan:
			ea.fire_alias(name, {"a": 1}, "Administrator")
			fan.assert_called_once_with(APP, "ping", {"a": 1}, "Administrator")

	# list / get
	def test_list_and_get(self):
		_alias("one")
		_alias("two", description="second")
		frappe.db.commit()
		names = [a["name"] for a in events.list_aliases(APP)]
		self.assertEqual(sorted(names), [f"{APP}.one", f"{APP}.two"])
		self.assertEqual(events.list_aliases("no_such_app"), [])
		got = events.get_alias(f"{APP}.two")
		self.assertEqual(got["description"], "second")
		self.assertIn("error_count", got)

	def test_huf_user_can_read_but_anonymous_role_cannot(self):
		_alias()
		frappe.db.commit()
		frappe.set_user(_user("ea_api_reader@example.com", ["Huf User"]))
		self.assertEqual(len(events.list_aliases(APP)), 1)
		frappe.set_user(_user("ea_api_none@example.com", []))
		with self.assertRaises(frappe.PermissionError):
			events.list_aliases(APP)
		with self.assertRaises(frappe.PermissionError):
			events.get_alias(f"{APP}.ping")

	# seeding folder: round trip, admin edit survives, second consumer
	def test_seed_round_trip_and_admin_edit_survives(self):
		res = seed_app(SEED_APP, self._fixture_dir())
		self.assertEqual(res.errors, [])
		name = f"{SEED_APP}.customer_purchase"
		doc = frappe.get_doc("Event Alias", name)
		self.assertEqual(doc.label, "Customer purchase")
		self.assertEqual(doc.source_app, SEED_APP)
		self.assertEqual(len(doc.sources), 1)

		doc.label = "Shopper bought"
		doc.save(ignore_permissions=True)
		res = seed_app(SEED_APP, self._fixture_dir())
		doc.reload()
		self.assertEqual(doc.label, "Shopper bought", "admin edit must survive re-seed")
		self.assertEqual(doc.description, "A customer bought something.")
		self.assertEqual(doc.version, 1)
		self.assertEqual(frappe.db.count("Event Alias", {"app": SEED_APP}), 1)

	def test_seeded_alias_of_another_app_fires_via_dispatcher(self):
		seed_app(SEED_APP, self._fixture_dir())
		frappe.db.commit()
		ea.clear_alias_cache()
		with patch("frappe.enqueue") as enq:
			todo = frappe.get_doc({"doctype": "ToDo", "description": "event alias api test"}).insert(
				ignore_permissions=True
			)
			frappe.db.commit()
			self.assertEqual(self._fires(enq), [f"{SEED_APP}.customer_purchase"])
			self.assertEqual(enq.call_args.kwargs["payload"], {"invoice": todo.name})

	# huf_event_aliases hook
	def test_hook_defined_alias_synced_with_edit_survival(self):
		definition = {
			"app": APP,
			"key": "from_hook",
			"label": "From hook",
			"sources": [{"reference_doctype": "ToDo", "doc_event": "after_insert", "enabled": 1}],
		}
		with _hooks_returning([definition]):
			self.assertEqual(ea.sync_hook_aliases(), 1)
		name = f"{APP}.from_hook"
		doc = frappe.get_doc("Event Alias", name)
		self.assertEqual(doc.source_app, APP)
		doc.label = "Edited"
		doc.save(ignore_permissions=True)
		with _hooks_returning([json.loads(json.dumps(definition))]):
			ea.sync_hook_aliases()
		self.assertEqual(frappe.db.get_value("Event Alias", name, "label"), "Edited")
