"""
Tests for HUF App manifest sync and the launcher API.
Run with:
    bench --site hufai.localhost run-tests --app huf --module huf.ai.app_seeding.tests.test_apps_sync
"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import frappe

from huf.ai.app_seeding import apps_loader
from huf.ai.app_seeding.apps_loader import sync_huf_apps, upsert_huf_app, validate_manifest
from huf.ai.app_seeding.seeder import seed_app
from huf.ai.apps_api import get_huf_app, get_huf_apps


def allow_all(user=None, app=None):
	"""permission_method test double: always allow."""
	return True


def deny_all(user=None, app=None):
	"""permission_method test double: always deny."""
	return False


ALLOW_ALL_PATH = "huf.ai.app_seeding.tests.test_apps_sync.allow_all"
DENY_ALL_PATH = "huf.ai.app_seeding.tests.test_apps_sync.deny_all"


class TestAppsSync(unittest.TestCase):
	"""Acceptance tests for the HUF Apps registry sync."""

	def setUp(self):
		self.test_app = "test_apps_sync_app"
		self.test_app_b = "test_apps_sync_app_b"
		self.huf_dir = Path(tempfile.mkdtemp()) / "huf"
		self.huf_dir.mkdir()
		self.huf_dir_b = Path(tempfile.mkdtemp()) / "huf"
		self.huf_dir_b.mkdir()

		# Unique, app_id-safe suffix to avoid collisions across test runs
		self.suffix = frappe.generate_hash(length=8).lower()
		self._created_app_ids = []

	def tearDown(self):
		shutil.rmtree(self.huf_dir.parent, ignore_errors=True)
		shutil.rmtree(self.huf_dir_b.parent, ignore_errors=True)

		for app_id in self._created_app_ids:
			try:
				frappe.db.sql("DELETE FROM `tabHUF App` WHERE name = %s", app_id)
			except Exception:
				pass

		frappe.set_user("Administrator")
		frappe.db.commit()

	def _write_manifest(self, folder_path, filename, payload):
		target_dir = folder_path / "apps"
		target_dir.mkdir(exist_ok=True)
		target_path = target_dir / filename
		with open(target_path, "w", encoding="utf-8") as f:
			json.dump(payload, f)
		return target_path

	def _app_id(self, label):
		app_id = f"tapps_{label}_{self.suffix}"
		self._created_app_ids.append(app_id)
		return app_id

	def _valid_manifest(self, app_id, **overrides):
		manifest = {
			"manifest_version": 1,
			"app_id": app_id,
			"title": "Test App",
			"description": "A test HUF App.",
			"version": "0.1.0",
			"route": f"/{app_id}",
			"icon": "/assets/test_apps_sync_app/icon.svg",
			"category": "Create",
			"launch_mode": "route",
			"sort_order": 10,
			"enabled": True,
		}
		manifest.update(overrides)
		return manifest

	# ------------------------------------------------------------------
	# Valid manifests
	# ------------------------------------------------------------------

	def test_valid_manifest_syncs_to_registry(self):
		"""A valid manifest is discovered by seed_app and synced to the
		registry with provenance and sync state recorded by HUF."""
		app_id = self._app_id("valid")
		self._write_manifest(self.huf_dir, "valid.app.json", self._valid_manifest(app_id))

		result = seed_app(self.test_app, self.huf_dir)

		self.assertEqual(result.skipped, 0, f"Valid manifest should not be skipped: {result.errors}")
		self.assertTrue(frappe.db.exists("HUF App", app_id))

		doc = frappe.get_doc("HUF App", app_id)
		self.assertEqual(doc.title, "Test App")
		self.assertEqual(doc.route, f"/{app_id}")
		self.assertEqual(doc.category, "Create")
		self.assertEqual(doc.launch_mode, "Route")
		self.assertEqual(doc.sort_order, 10)
		self.assertEqual(doc.enabled, 1)
		self.assertEqual(doc.sync_status, "Active")
		self.assertEqual(doc.source_app, self.test_app)
		self.assertEqual(doc.source_file, "huf/apps/valid.app.json")
		self.assertTrue(doc.manifest_hash)
		self.assertTrue(doc.last_synced_at)

	def test_provenance_fields_in_manifest_are_rejected(self):
		"""source_app/source_file/manifest_hash must never be trusted from
		the manifest JSON; they are unknown top-level fields."""
		app_id = self._app_id("provenance")
		manifest = self._valid_manifest(app_id, source_app="malicious_app")

		normalized, error = validate_manifest(manifest)

		self.assertIsNone(normalized)
		self.assertIn("unknown top-level field", error)

	def test_unchanged_manifest_skips_write(self):
		"""A second sync with an identical manifest does not rewrite the
		registry record (hash comparison)."""
		app_id = self._app_id("hashskip")
		manifest = self._valid_manifest(app_id)

		ok, error = upsert_huf_app(manifest, self.test_app, "huf/apps/hashskip.app.json")
		self.assertTrue(ok, error)
		modified_after_insert = frappe.db.get_value("HUF App", app_id, "modified")

		ok, error = upsert_huf_app(manifest, self.test_app, "huf/apps/hashskip.app.json")
		self.assertTrue(ok, error)
		modified_after_resync = frappe.db.get_value("HUF App", app_id, "modified")

		self.assertEqual(modified_after_insert, modified_after_resync)

	# ------------------------------------------------------------------
	# Invalid manifests
	# ------------------------------------------------------------------

	def test_invalid_manifests_do_not_break_valid_ones(self):
		"""Bad route, unknown field, bad app_id and external URL manifests
		are isolated; the valid manifest in the same folder still syncs."""
		valid_id = self._app_id("mixedvalid")
		bad_route_id = self._app_id("badroute")
		unknown_field_id = self._app_id("unknownfield")
		external_url_id = self._app_id("externalurl")

		self._write_manifest(self.huf_dir, "valid.app.json", self._valid_manifest(valid_id))
		self._write_manifest(
			self.huf_dir,
			"bad_route.app.json",
			self._valid_manifest(bad_route_id, route="//evil.com/app"),
		)
		self._write_manifest(
			self.huf_dir,
			"unknown_field.app.json",
			self._valid_manifest(unknown_field_id, bundle_url="https://evil.com/x.js"),
		)
		self._write_manifest(
			self.huf_dir,
			"external_url.app.json",
			self._valid_manifest(external_url_id, route="https://evil.com/app"),
		)
		self._write_manifest(
			self.huf_dir,
			"bad_app_id.app.json",
			self._valid_manifest("Bad App ID!"),
		)

		result = seed_app(self.test_app, self.huf_dir)

		# Valid manifest still loads
		self.assertTrue(frappe.db.exists("HUF App", valid_id))
		self.assertEqual(
			frappe.db.get_value("HUF App", valid_id, "sync_status"), "Active"
		)

		# Manifests with a usable app_id are recorded as Invalid, not Active
		for app_id in (bad_route_id, unknown_field_id, external_url_id):
			self.assertTrue(frappe.db.exists("HUF App", app_id), f"{app_id} should be recorded")
			doc = frappe.get_doc("HUF App", app_id)
			self.assertEqual(doc.sync_status, "Invalid")
			self.assertTrue(doc.sync_error)
			self.assertEqual(doc.enabled, 0)

		# A manifest without a usable app_id cannot be recorded, but must not crash
		self.assertFalse(frappe.db.exists("HUF App", "Bad App ID!"))
		self.assertEqual(result.skipped, 4)

	def test_invalid_permission_method_recorded_invalid(self):
		"""A permission_method that does not resolve to a callable marks the
		record Invalid without crashing the sync."""
		app_id = self._app_id("badperm")
		self._write_manifest(
			self.huf_dir,
			"bad_perm.app.json",
			self._valid_manifest(app_id, permission_method="huf.does.not.exist"),
		)

		result = seed_app(self.test_app, self.huf_dir)

		self.assertEqual(result.skipped, 1)
		doc = frappe.get_doc("HUF App", app_id)
		self.assertEqual(doc.sync_status, "Invalid")
		self.assertIn("permission_method", doc.sync_error)

	# ------------------------------------------------------------------
	# Duplicate app_id
	# ------------------------------------------------------------------

	def test_duplicate_app_id_does_not_silently_overwrite(self):
		"""Two provider apps declaring the same app_id: the existing valid
		registration is kept, the collision is logged and surfaced."""
		app_id = self._app_id("duplicate")
		self._write_manifest(
			self.huf_dir, "dup.app.json", self._valid_manifest(app_id, title="First App")
		)
		self._write_manifest(
			self.huf_dir_b, "dup.app.json", self._valid_manifest(app_id, title="Second App")
		)

		result_a = seed_app(self.test_app, self.huf_dir)
		self.assertEqual(result_a.skipped, 0)

		result_b = seed_app(self.test_app_b, self.huf_dir_b)
		self.assertEqual(result_b.skipped, 1, "Colliding manifest should be rejected")

		doc = frappe.get_doc("HUF App", app_id)
		self.assertEqual(doc.title, "First App", "Existing registration must be kept")
		self.assertEqual(doc.source_app, self.test_app)
		self.assertEqual(doc.sync_status, "Active")
		self.assertIn("Duplicate app_id", doc.sync_error)

	# ------------------------------------------------------------------
	# Orphan cleanup
	# ------------------------------------------------------------------

	def test_removed_manifest_deletes_registry_record(self):
		"""A registry record whose source file no longer exists is deleted on
		the next full sync."""
		app_id = self._app_id("orphan")
		manifest_path = self._write_manifest(
			self.huf_dir, "orphan.app.json", self._valid_manifest(app_id)
		)

		original_find_seed_dirs = apps_loader.find_seed_dirs
		original_get_installed_apps = frappe.get_installed_apps
		apps_loader.find_seed_dirs = lambda: {self.test_app: self.huf_dir}
		frappe.get_installed_apps = lambda: original_get_installed_apps() + [self.test_app]
		try:
			summary = sync_huf_apps()
			self.assertEqual(summary["invalid"], 0, f"Unexpected errors: {summary['errors']}")
			self.assertTrue(frappe.db.exists("HUF App", app_id))

			manifest_path.unlink()
			summary = sync_huf_apps()
		finally:
			apps_loader.find_seed_dirs = original_find_seed_dirs
			frappe.get_installed_apps = original_get_installed_apps

		self.assertFalse(
			frappe.db.exists("HUF App", app_id),
			"Orphaned registry record should be deleted",
		)
		self.assertIn(app_id, summary["deleted_apps"])

	def test_uninstalled_provider_app_removes_registry_entries(self):
		"""The after_app_uninstall hook deletes all entries of the provider."""
		app_id = self._app_id("uninstall")
		self._write_manifest(self.huf_dir, "uninstall.app.json", self._valid_manifest(app_id))
		seed_app(self.test_app, self.huf_dir)
		self.assertTrue(frappe.db.exists("HUF App", app_id))

		apps_loader.on_app_uninstalled(self.test_app)

		self.assertFalse(frappe.db.exists("HUF App", app_id))


class TestAppsApiPermissions(unittest.TestCase):
	"""Permission filtering in the launcher API."""

	def setUp(self):
		self.suffix = frappe.generate_hash(length=8).lower()
		self.test_app = "test_apps_sync_app"
		self._created_app_ids = []

		self.enabled_id = self._app_id("enabled")
		self.disabled_id = self._app_id("disabled")
		self.allow_id = self._app_id("allow")
		self.deny_id = self._app_id("deny")

		self._make_registry_app(self.enabled_id, enabled=1)
		self._make_registry_app(self.disabled_id, enabled=0)
		self._make_registry_app(self.allow_id, enabled=1, permission_method=ALLOW_ALL_PATH)
		self._make_registry_app(self.deny_id, enabled=1, permission_method=DENY_ALL_PATH)

		# A normal user with the Huf User role (grants agent.use)
		self.normal_user = f"test-apps-sync-{self.suffix}@example.com"
		self._ensure_huf_user_capability()
		if not frappe.db.exists("User", self.normal_user):
			user = frappe.get_doc(
				{
					"doctype": "User",
					"email": self.normal_user,
					"first_name": "Test Apps Sync",
					"send_welcome_email": 0,
				}
			)
			user.insert(ignore_permissions=True)
		if not frappe.db.exists("Huf User Role", {"user": self.normal_user}):
			frappe.get_doc(
				{
					"doctype": "Huf User Role",
					"user": self.normal_user,
					"huf_role": "Huf User",
					"enabled": 1,
				}
			).insert(ignore_permissions=True)

	def tearDown(self):
		frappe.set_user("Administrator")
		for app_id in self._created_app_ids:
			try:
				frappe.db.sql("DELETE FROM `tabHUF App` WHERE name = %s", app_id)
			except Exception:
				pass
		try:
			frappe.db.sql("DELETE FROM `tabHuf User Role` WHERE user = %s", self.normal_user)
			frappe.db.sql("DELETE FROM `tabUser` WHERE name = %s", self.normal_user)
		except Exception:
			pass
		frappe.db.commit()

	def _app_id(self, label):
		app_id = f"tapps_api_{label}_{self.suffix}"
		self._created_app_ids.append(app_id)
		return app_id

	def _make_registry_app(self, app_id, enabled=1, permission_method=None):
		frappe.get_doc(
			{
				"doctype": "HUF App",
				"app_id": app_id,
				"title": app_id,
				"description": "API permission test app",
				"route": f"/{app_id}",
				"category": "Other",
				"version": "0.1.0",
				"launch_mode": "Route",
				"sort_order": 100,
				"enabled": enabled,
				"permission_method": permission_method or "",
				"sync_status": "Active",
				"source_app": self.test_app,
				"source_file": "huf/apps/test.app.json",
			}
		).insert(ignore_permissions=True)

	def _ensure_huf_user_capability(self):
		"""Make sure the 'Huf User' Huf Role exists and grants agent.use."""
		if not frappe.db.exists("Huf Role", "Huf User"):
			doc = frappe.get_doc(
				{
					"doctype": "Huf Role",
					"role_name": "Huf User",
					"description": "End user.",
					"is_system_role": 1,
					"frappe_role": "Huf User",
				}
			)
			doc.append("permissions", {"capability": "agent.use"})
			doc.insert(ignore_permissions=True)
		elif not frappe.db.exists(
			"Huf Role Permission", {"parent": "Huf User", "capability": "agent.use"}
		):
			doc = frappe.get_doc("Huf Role", "Huf User")
			doc.append("permissions", {"capability": "agent.use"})
			doc.save(ignore_permissions=True)

	def _listed_ids(self, user):
		frappe.set_user(user)
		try:
			return {app["app_id"] for app in get_huf_apps()["apps"]}
		finally:
			frappe.set_user("Administrator")

	def test_administrator_sees_all_valid_registrations(self):
		ids = self._listed_ids("Administrator")
		self.assertIn(self.enabled_id, ids)
		self.assertIn(self.disabled_id, ids, "System Manager sees disabled apps too")
		self.assertIn(self.allow_id, ids)
		self.assertIn(self.deny_id, ids)

	def test_normal_user_filtering(self):
		ids = self._listed_ids(self.normal_user)
		self.assertIn(self.enabled_id, ids, "Enabled app without permission_method needs base access")
		self.assertNotIn(self.disabled_id, ids, "Disabled apps are hidden from normal users")
		self.assertIn(self.allow_id, ids, "permission_method allowing the user is honored")
		self.assertNotIn(self.deny_id, ids, "permission_method denying the user is honored")

	def test_guest_sees_nothing(self):
		ids = self._listed_ids("Guest")
		self.assertEqual(ids, set())

	def test_only_safe_fields_are_returned(self):
		frappe.set_user(self.normal_user)
		try:
			apps = get_huf_apps()["apps"]
		finally:
			frappe.set_user("Administrator")

		self.assertTrue(apps)
		for app in apps:
			self.assertEqual(
				set(app),
				{"app_id", "title", "description", "route", "icon", "category", "version"},
				"Only safe launcher fields may be exposed",
			)

	def test_get_huf_app_detail_and_denied(self):
		frappe.set_user(self.normal_user)
		try:
			app = get_huf_app(self.enabled_id)
			self.assertEqual(app["app_id"], self.enabled_id)
			self.assertNotIn("permission_method", app)

			with self.assertRaises(frappe.DoesNotExistError):
				get_huf_app(self.deny_id)

			with self.assertRaises(frappe.DoesNotExistError):
				get_huf_app(f"tapps_api_missing_{self.suffix}")
		finally:
			frappe.set_user("Administrator")

	def test_sync_endpoint_requires_system_manager(self):
		frappe.set_user(self.normal_user)
		try:
			with self.assertRaises(frappe.PermissionError):
				from huf.ai.apps_api import sync_huf_apps as sync_endpoint

				sync_endpoint()
		finally:
			frappe.set_user("Administrator")


if __name__ == "__main__":
	unittest.main()
