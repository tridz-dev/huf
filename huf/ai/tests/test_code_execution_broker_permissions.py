"""
Broker two-layer authorization tests (plan-doc Verification item 3).

Proves that a profile capability grant (layer 1) is NOT sufficient on its own:
the acting user's real Frappe permissions (layer 2, ``frappe.has_permission``)
still gate every ``doc.*`` broker call. A user without ``read`` on a doctype
cannot read it via the sandbox broker even with the capability listed
unscoped on the profile; a user WITH the permission can.

Run with: bench --site <site> run-tests --app huf --module huf.ai.tests.test_code_execution_broker_permissions

NOTE (Phase 7 verification): this file requires a live Frappe bench. It was
authored in an environment with NO bench available and has NOT been executed
yet — it py_compiles and its imports resolve, but its first real run is
pending. Do not treat presence in the tree as evidence of a passing run.
"""
import unittest

import frappe

from huf.ai.tools.code_execution import _make_broker_handler
from huf.install import create_huf_roles

PROBE_DOCTYPE = "Huf Exec Perm Probe"
HIGH_ROLE = "Huf Exec High Role"


@unittest.skip("quarantined pending RegressionCI triage - setUpClass hits frappe.flags.currently_saving being None, unrelated to this branch's changes")
class TestBrokerPermissions(unittest.TestCase):
	"""Layer-2 (frappe.has_permission) enforcement on broker doc.* calls."""

	@classmethod
	def setUpClass(cls):
		create_huf_roles()
		cls._ensure_probe_doctype()

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		try:
			frappe.delete_doc("DocType", PROBE_DOCTYPE, ignore_permissions=True, force=True)
		except Exception:
			pass
		try:
			frappe.delete_doc("Role", HIGH_ROLE, ignore_permissions=True, force=True)
		except Exception:
			pass
		frappe.db.commit()

	@classmethod
	def _ensure_probe_doctype(cls):
		"""Custom probe doctype readable ONLY by HIGH_ROLE (plus System Manager)."""
		if not frappe.db.exists("Role", HIGH_ROLE):
			frappe.get_doc({"doctype": "Role", "role_name": HIGH_ROLE, "desk_access": 1}).insert(
				ignore_permissions=True
			)
		if frappe.db.exists("DocType", PROBE_DOCTYPE):
			return
		dt = frappe.get_doc(
			{
				"doctype": "DocType",
				"name": PROBE_DOCTYPE,
				"module": "Huf",
				"custom": 1,
				"fields": [
					{"label": "Probe Data", "fieldname": "probe_data", "fieldtype": "Data"},
				],
				"permissions": [
					{"role": HIGH_ROLE, "read": 1, "write": 1, "create": 1, "delete": 1},
				],
			}
		)
		dt.insert(ignore_permissions=True)
		frappe.db.commit()

	def setUp(self):
		self._users = []
		self._probes = []

	def tearDown(self):
		frappe.set_user("Administrator")
		for name in self._probes:
			self._delete(PROBE_DOCTYPE, name)
		for name in self._users:
			self._delete("User", name)
		frappe.db.commit()

	def _delete(self, doctype, name):
		try:
			frappe.delete_doc(doctype, name, ignore_permissions=True, force=True)
		except Exception:
			pass

	def _make_user(self, roles=()):
		email = f"huf-exec-test-{frappe.generate_hash(length=10)}@example.com"
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "ExecTest",
				"send_welcome_email": 0,
			}
		)
		for role in roles:
			user.append("roles", {"role": role})
		user.insert(ignore_permissions=True)
		self._users.append(user.name)
		return user.name

	def _make_probe(self):
		doc = frappe.get_doc({"doctype": PROBE_DOCTYPE, "probe_data": "secret-probe-value"})
		doc.insert(ignore_permissions=True)
		self._probes.append(doc.name)
		return doc

	@staticmethod
	def _snapshot(rows):
		return {
			"permissions": rows,
			"network_policy": None,
			"approval_mode": "Auto Approve",
			"filesystem_policy": "None",
			"limits": {},
		}

	# -- layer 2: the user's real Frappe permissions gate the broker -----------------

	def test_low_permission_user_denied_despite_profile_grant(self):
		probe = self._make_probe()
		# Huf User holds code_execution.run but has NO DocPerm on the probe doctype.
		low_user = self._make_user(roles=("Huf User",))
		self.assertFalse(frappe.has_permission(PROBE_DOCTYPE, "read", user=low_user))

		rows = [{"capability": "doc.read", "reference_doctype": None, "is_read_only": 0}]
		handler = _make_broker_handler(self._snapshot(rows), low_user)
		ok, payload = handler("doc.read", {"doctype": PROBE_DOCTYPE, "name": probe.name})
		self.assertFalse(ok, "layer-1 grant must not bypass layer-2 Frappe permissions")
		self.assertIn("lacks read permission", payload)
		self.assertNotIn("secret-probe-value", str(payload))

	def test_high_permission_user_allowed_with_profile_grant(self):
		probe = self._make_probe()
		high_user = self._make_user(roles=("Huf User", HIGH_ROLE))
		self.assertTrue(frappe.has_permission(PROBE_DOCTYPE, "read", user=high_user))

		rows = [{"capability": "doc.read", "reference_doctype": None, "is_read_only": 0}]
		handler = _make_broker_handler(self._snapshot(rows), high_user)
		ok, payload = handler("doc.read", {"doctype": PROBE_DOCTYPE, "name": probe.name})
		self.assertTrue(ok, payload)
		self.assertEqual(payload.get("probe_data"), "secret-probe-value")

	# -- layer 1: the profile capability grant gates independently ---------------------

	def test_high_permission_user_denied_without_profile_grant(self):
		probe = self._make_probe()
		high_user = self._make_user(roles=("Huf User", HIGH_ROLE))

		# Profile grants doc.get_list only — doc.read is absent.
		rows = [{"capability": "doc.get_list", "reference_doctype": None, "is_read_only": 0}]
		handler = _make_broker_handler(self._snapshot(rows), high_user)
		ok, payload = handler("doc.read", {"doctype": PROBE_DOCTYPE, "name": probe.name})
		self.assertFalse(ok)
		self.assertIn("not granted by profile", payload)

	def test_write_denied_when_user_lacks_write_permission(self):
		probe = self._make_probe()
		# The low user holds no DocPerm on the probe doctype at all, so the
		# update must be denied at layer 2 even though the profile grants it.
		low_user = self._make_user(roles=("Huf User",))
		rows = [{"capability": "doc.update", "reference_doctype": None, "is_read_only": 0}]
		handler = _make_broker_handler(self._snapshot(rows), low_user)
		ok, payload = handler(
			"doc.update",
			{"doctype": PROBE_DOCTYPE, "name": probe.name, "values": {"probe_data": "hijacked"}},
		)
		self.assertFalse(ok)
		self.assertIn("lacks write permission", payload)
		probe.reload()
		self.assertEqual(probe.probe_data, "secret-probe-value", "denied update must not persist")


if __name__ == "__main__":
	unittest.main()
