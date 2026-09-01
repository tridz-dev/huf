"""
Regression test for the transcribe-audio file-permission bypass.

``huf.ai.audio_service._resolve_file_doc`` (used by both
``transcribe_audio_file`` and the whitelisted ``huf.ai.audio_api.transcribe``
entrypoint) used to resolve any ``file_id``/``file_url`` straight to a
``File`` document with no permission check. Any authenticated user could
pass another user's private File id and get its contents transcribed back
to them.

Proves:
- A user without read permission on another user's private File is denied
  (``frappe.PermissionError``) when resolving/transcribing that file.
- The file's owner (who does have read permission) is NOT denied by the
  permission check itself.

Run with:
    bench --site <site> run-tests --app huf --module huf.ai.tests.test_transcribe_file_permission
"""
import frappe
from frappe.utils.file_manager import save_file

from frappe.tests import IntegrationTestCase

from huf.ai import audio_service


class TestTranscribeFilePermission(IntegrationTestCase):
	def setUp(self):
		self._users = []
		self._files = []
		self._agents = []

	def tearDown(self):
		frappe.set_user("Administrator")
		for name in self._files:
			try:
				frappe.delete_doc("File", name, ignore_permissions=True, force=True)
			except Exception:
				pass
		for name in self._agents:
			try:
				frappe.delete_doc("Agent", name, ignore_permissions=True, force=True)
			except Exception:
				pass
		for name in self._users:
			try:
				frappe.delete_doc("User", name, ignore_permissions=True, force=True)
			except Exception:
				pass
		frappe.db.commit()

	def _make_agent(self):
		frappe.set_user("Administrator")
		agent = frappe.get_doc(
			{
				"doctype": "Agent",
				"agent_name": f"huf-transcribe-perm-test-agent-{frappe.generate_hash(length=8)}",
				"agent_modality": "Text",
				"instructions": "You are a test agent used only for permission regression tests.",
			}
		)
		agent.insert(ignore_permissions=True)
		self._agents.append(agent.name)
		return agent.name

	def _make_user(self):
		email = f"huf-transcribe-perm-test-{frappe.generate_hash(length=10)}@example.com"
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "TranscribePermTest",
				"send_welcome_email": 0,
			}
		)
		user.insert(ignore_permissions=True)
		self._users.append(user.name)
		return user.name

	def _make_private_file_as(self, user):
		frappe.set_user(user)
		file_doc = save_file(
			"secret-audio-owner-only.txt",
			b"private transcript-worthy content",
			None,
			None,
			is_private=1,
		)
		self._files.append(file_doc.name)
		frappe.set_user("Administrator")
		return file_doc.name

	def test_other_user_cannot_resolve_private_file_owned_by_someone_else(self):
		user_a = self._make_user()
		user_b = self._make_user()
		file_id = self._make_private_file_as(user_a)

		frappe.set_user(user_b)
		self.assertFalse(frappe.has_permission("File", "read", doc=file_id))

		with self.assertRaises(frappe.PermissionError):
			audio_service._resolve_file_doc(file_id=file_id)

	def test_owner_can_resolve_own_private_file(self):
		user_a = self._make_user()
		file_id = self._make_private_file_as(user_a)

		frappe.set_user(user_a)
		self.assertTrue(frappe.has_permission("File", "read", doc=file_id))

		resolved = audio_service._resolve_file_doc(file_id=file_id)
		self.assertEqual(resolved.name, file_id)

	def test_transcribe_audio_file_denies_other_user_for_private_file(self):
		user_a = self._make_user()
		user_b = self._make_user()
		file_id = self._make_private_file_as(user_a)
		agent_name = self._make_agent()

		frappe.set_user(user_b)
		with self.assertRaises(frappe.PermissionError):
			audio_service.transcribe_audio_file(file_id=file_id, agent_name=agent_name)
