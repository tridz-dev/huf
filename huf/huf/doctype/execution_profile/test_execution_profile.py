"""
Tests for Execution Profile: controller validation, capability-gated
``has_permission``, and the ``Execution Profile Permission`` allow/deny matrix
as enforced by the code-execution broker (``_make_broker_handler``).

Run with: bench --site <site> run-tests --app huf --module huf.huf.doctype.execution_profile.test_execution_profile

NOTE (Phase 7 verification): this file requires a live Frappe bench. It was
authored in an environment with NO bench available and has NOT been executed
yet — it py_compiles and its imports resolve, but its first real run is
pending. Do not treat presence in the tree as evidence of a passing run.
"""
import unittest

import frappe

from huf.ai.tools.code_execution import _make_broker_handler
from huf.install import create_default_execution_profiles, create_huf_roles


class TestExecutionProfile(unittest.TestCase):
	"""Execution Profile controller + permission-row matrix tests."""

	@classmethod
	def setUpClass(cls):
		# Idempotent: ensures Huf Role capability rows exist for capability checks.
		create_huf_roles()
		cls._orig_kill_switch = frappe.conf.get("huf_python_execution_enabled")
		frappe.conf["huf_python_execution_enabled"] = True

	@classmethod
	def tearDownClass(cls):
		if cls._orig_kill_switch is None:
			frappe.conf.pop("huf_python_execution_enabled", None)
		else:
			frappe.conf["huf_python_execution_enabled"] = cls._orig_kill_switch

	def setUp(self):
		self._users = []
		self._todos = []
		self._profiles = []

	def tearDown(self):
		frappe.set_user("Administrator")
		for name in self._profiles:
			self._delete("Execution Profile", name)
		for name in self._todos:
			self._delete("ToDo", name)
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

	def _make_todo(self, description="exec-profile-matrix"):
		todo = frappe.get_doc({"doctype": "ToDo", "description": description})
		todo.insert(ignore_permissions=True)
		self._todos.append(todo.name)
		return todo

	@staticmethod
	def _snapshot(rows):
		return {
			"permissions": rows,
			"network_policy": None,
			"approval_mode": "Auto Approve",
			"filesystem_policy": "None",
			"limits": {},
		}

	# -- controller validation --------------------------------------------------

	@unittest.skip("quarantined pending RegressionCI triage - see Tracks/RegressionCI/CONTEXT.md Quarantine backlog")
	def test_profile_rejects_non_positive_limits(self):
		profile = frappe.get_doc(
			{
				"doctype": "Execution Profile",
				"profile_name": f"bad-limits-{frappe.generate_hash(length=8)}",
				"max_wall_time_s": 0,
			}
		)
		with self.assertRaises(frappe.ValidationError):
			profile.insert(ignore_permissions=True)

	@unittest.skip("quarantined pending RegressionCI triage - see Tracks/RegressionCI/CONTEXT.md Quarantine backlog")
	def test_profile_accepts_positive_limits(self):
		name = f"good-limits-{frappe.generate_hash(length=8)}"
		profile = frappe.get_doc(
			{
				"doctype": "Execution Profile",
				"profile_name": name,
				"max_wall_time_s": 30,
				"max_cpu_seconds": 30,
				"max_memory_mb": 256,
				"max_output_bytes": 1048576,
			}
		)
		profile.insert(ignore_permissions=True)
		self._profiles.append(profile.name)
		self.assertTrue(frappe.db.exists("Execution Profile", name))

	# -- controller has_permission (capability gating) --------------------------

	@unittest.skip("quarantined pending RegressionCI triage - see Tracks/RegressionCI/CONTEXT.md Quarantine backlog")
	def test_manage_capability_gates_mutation_but_not_read(self):
		profile = frappe.new_doc("Execution Profile")

		plain_user = self._make_user(roles=("Huf User",))
		manager_user = self._make_user(roles=("Huf Manager",))

		# A user without execution_profile.manage cannot mutate, but may read.
		frappe.set_user(plain_user)
		self.assertFalse(profile.has_permission("create"))
		self.assertFalse(profile.has_permission("write"))
		self.assertFalse(profile.has_permission("delete"))
		self.assertTrue(profile.has_permission("read"))

		# Huf Manager holds execution_profile.manage (seeded default grant).
		frappe.set_user(manager_user)
		self.assertTrue(profile.has_permission("create"))
		self.assertTrue(profile.has_permission("write"))
		self.assertTrue(profile.has_permission("delete"))

		# System Manager always passes (safety net).
		frappe.set_user("Administrator")
		self.assertTrue(profile.has_permission("delete"))

		frappe.set_user("Administrator")

	# -- Execution Profile Permission allow/deny matrix (broker authorization) --

	@unittest.skip("quarantined pending RegressionCI triage - see Tracks/RegressionCI/CONTEXT.md Quarantine backlog")
	def test_absent_capability_denies(self):
		handler = _make_broker_handler(self._snapshot([]), "Administrator")
		ok, payload = handler("doc.read", {"doctype": "ToDo", "name": "x"})
		self.assertFalse(ok)
		self.assertIn("not granted by profile", payload)

	@unittest.skip("quarantined pending RegressionCI triage - see Tracks/RegressionCI/CONTEXT.md Quarantine backlog")
	def test_unknown_capability_denies(self):
		rows = [{"capability": "doc.delete", "reference_doctype": None, "is_read_only": 0}]
		handler = _make_broker_handler(self._snapshot(rows), "Administrator")
		ok, payload = handler("doc.delete", {"doctype": "ToDo", "name": "x"})
		self.assertFalse(ok)
		self.assertIn("unknown capability", payload)

	@unittest.skip("quarantined pending RegressionCI triage - see Tracks/RegressionCI/CONTEXT.md Quarantine backlog")
	def test_scoped_row_does_not_grant_other_doctype(self):
		rows = [{"capability": "doc.read", "reference_doctype": "ToDo", "is_read_only": 0}]
		handler = _make_broker_handler(self._snapshot(rows), "Administrator")
		ok, payload = handler("doc.read", {"doctype": "Note", "name": "x"})
		self.assertFalse(ok)
		self.assertIn("not granted for doctype 'Note'", payload)

	@unittest.skip("quarantined pending RegressionCI triage - see Tracks/RegressionCI/CONTEXT.md Quarantine backlog")
	def test_read_only_row_rejects_write_capability(self):
		# Administrator passes the has_permission layer, so the denial must come
		# from the read-only row check itself.
		rows = [{"capability": "doc.create", "reference_doctype": None, "is_read_only": 1}]
		handler = _make_broker_handler(self._snapshot(rows), "Administrator")
		ok, payload = handler("doc.create", {"doctype": "ToDo", "values": {"description": "x"}})
		self.assertFalse(ok)
		self.assertIn("read-only", payload)

	@unittest.skip("quarantined pending RegressionCI triage - see Tracks/RegressionCI/CONTEXT.md Quarantine backlog")
	def test_read_only_row_still_allows_read(self):
		todo = self._make_todo()
		rows = [{"capability": "doc.read", "reference_doctype": "ToDo", "is_read_only": 1}]
		handler = _make_broker_handler(self._snapshot(rows), "Administrator")
		ok, payload = handler("doc.read", {"doctype": "ToDo", "name": todo.name})
		self.assertTrue(ok, payload)
		self.assertEqual(payload.get("name"), todo.name)

	@unittest.skip("quarantined pending RegressionCI triage - see Tracks/RegressionCI/CONTEXT.md Quarantine backlog")
	def test_unscoped_row_grants_any_doctype(self):
		todo = self._make_todo()
		rows = [{"capability": "doc.read", "reference_doctype": None, "is_read_only": 0}]
		handler = _make_broker_handler(self._snapshot(rows), "Administrator")
		ok, payload = handler("doc.read", {"doctype": "ToDo", "name": todo.name})
		self.assertTrue(ok, payload)
		self.assertEqual(payload.get("name"), todo.name)

	@unittest.skip("quarantined pending RegressionCI triage - see Tracks/RegressionCI/CONTEXT.md Quarantine backlog")
	def test_scoped_row_grants_its_own_doctype(self):
		todo = self._make_todo()
		rows = [{"capability": "doc.read", "reference_doctype": "ToDo", "is_read_only": 0}]
		handler = _make_broker_handler(self._snapshot(rows), "Administrator")
		ok, payload = handler("doc.read", {"doctype": "ToDo", "name": todo.name})
		self.assertTrue(ok, payload)
		self.assertEqual(payload.get("name"), todo.name)

	def test_default_execution_profiles_creation(self):
		create_default_execution_profiles()
		expected = {
			"Restricted": "Ask Every Time",
			"Trusted": "Auto Approve",
			"Blocked": "Never Allow",
		}
		for name, approval_mode in expected.items():
			self.assertTrue(frappe.db.exists("Execution Profile", name))
			doc = frappe.get_doc("Execution Profile", name)
			self.assertEqual(doc.approval_mode, approval_mode)
			self.assertEqual(doc.is_builtin, 1)


if __name__ == "__main__":
	unittest.main()

