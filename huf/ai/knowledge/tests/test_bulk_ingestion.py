
import frappe
from frappe.tests import IntegrationTestCase
from unittest.mock import patch, MagicMock


class TestBulkIngestionChecksumSkip(IntegrationTestCase):
	"""huf.ai.knowledge.bulk.orchestrator.process_batch — checksum-based skip logic."""

	def setUp(self):
		self.source_name = "Test Bulk Source Checksum"
		if not frappe.db.exists("Knowledge Source", self.source_name):
			frappe.get_doc({
				"doctype": "Knowledge Source",
				"source_name": self.source_name,
				"scope": "Global",
				"storage_mode": "Frappe File",
				"knowledge_type": "sqlite_fts",
				"status": "Ready",
				"chunk_size": 512,
				"chunk_overlap": 50,
			}).insert(ignore_permissions=True)

		self.existing_checksum = "checksum-abc-123"

		# An existing Knowledge Input already ingested under this checksum.
		self.existing_input = frappe.get_doc({
			"doctype": "Knowledge Input",
			"knowledge_source": self.source_name,
			"input_type": "Text",
			"text": "already ingested content",
			"external_checksum": self.existing_checksum,
			"status": "Indexed",
		}).insert(ignore_permissions=True)

		# An Ingestion Job with one Pending item whose checksum matches the
		# already-ingested Knowledge Input above.
		self.job = frappe.get_doc({
			"doctype": "Ingestion Job",
			"knowledge_source": self.source_name,
			"source_kind": "Directory",
			"status": "Processing",
			"directory_path": "/tmp/bulk-test",
			"items": [
				{
					"external_path": "/tmp/bulk-test/dup.txt",
					"external_checksum": self.existing_checksum,
					"size_bytes": 42,
					"status": "Pending",
				}
			],
		}).insert(ignore_permissions=True)
		self.item_name = self.job.items[0].name

	def tearDown(self):
		frappe.delete_doc("Ingestion Job", self.job.name, force=True, ignore_permissions=True)
		frappe.delete_doc("Knowledge Input", self.existing_input.name, force=True, ignore_permissions=True)
		frappe.delete_doc("Knowledge Source", self.source_name, force=True, ignore_permissions=True)

	def test_checksum_skip_logic(self):
		with patch("huf.ai.knowledge.indexer.process_knowledge_input") as mock_process:
			from huf.ai.knowledge.bulk import orchestrator

			orchestrator.process_batch(self.job.name, [self.item_name])

			# The real indexing/vector-backend pipeline must never be touched
			# for a checksum that already exists in this source.
			mock_process.assert_not_called()

		self.job.reload()
		item = self.job.items[0]
		self.assertEqual(item.status, "Skipped")

		# No second Knowledge Input should have been created for this checksum.
		count = frappe.db.count("Knowledge Input", {
			"knowledge_source": self.source_name,
			"external_checksum": self.existing_checksum,
		})
		self.assertEqual(count, 1)


class TestScanS3PaginationAndCursor(IntegrationTestCase):
	"""huf.ai.knowledge.bulk.scanners.scan_s3 — pagination + sync_cursor handling."""

	def setUp(self):
		self.source_name = "Test Bulk Source S3"
		if not frappe.db.exists("Knowledge Source", self.source_name):
			frappe.get_doc({
				"doctype": "Knowledge Source",
				"source_name": self.source_name,
				"scope": "Global",
				"storage_mode": "Frappe File",
				"knowledge_type": "sqlite_fts",
				"status": "Ready",
				"chunk_size": 512,
				"chunk_overlap": 50,
			}).insert(ignore_permissions=True)

		self.job = frappe.get_doc({
			"doctype": "Ingestion Job",
			"knowledge_source": self.source_name,
			"source_kind": "S3",
			"status": "Queued",
			"s3_bucket": "test-bucket",
			"s3_prefix": "docs/",
		}).insert(ignore_permissions=True)

	def tearDown(self):
		frappe.delete_doc("Ingestion Job", self.job.name, force=True, ignore_permissions=True)
		frappe.delete_doc("Knowledge Source", self.source_name, force=True, ignore_permissions=True)

	def test_scan_s3_pagination_and_cursor(self):
		page_1 = {
			"objects": [
				{"key": "docs/a.txt", "size": 10, "last_modified": "2024-01-01T00:00:00", "etag": "etag-a"},
				{"key": "docs/b.txt", "size": 20, "last_modified": "2024-01-02T00:00:00", "etag": "etag-b"},
			],
			"next_token": "page2",
		}
		page_2 = {
			"objects": [
				{"key": "docs/c.txt", "size": 30, "last_modified": "2024-01-03T00:00:00", "etag": "etag-c"},
			],
			"next_token": None,
		}

		def fake_list_objects_page(client, bucket, prefix="", continuation_token=None, page_size=100):
			if continuation_token is None:
				return page_1
			self.assertEqual(continuation_token, "page2")
			return page_2

		with patch("huf.ai.knowledge.bulk.scanners.list_objects_page", side_effect=fake_list_objects_page), \
				patch("huf.ai.knowledge.bulk.scanners.require_credential", return_value="dummy"), \
				patch("huf.ai.knowledge.bulk.scanners.boto3") as mock_boto3, \
				patch("huf.ai.knowledge.bulk.scanners.frappe.enqueue"):
			mock_boto3.client.return_value = MagicMock()

			from huf.ai.knowledge.bulk import scanners
			scanners.scan_s3(self.job.name)
			# Note: list_objects_page, require_credential, and boto3 are imported at
			# module level in huf.ai.knowledge.bulk.scanners specifically so they can
			# be patched here -- scan_s3() does not re-import them locally.

		self.job.reload()

		# Items from BOTH pages must have been written.
		created_paths = {row.external_path for row in self.job.items}
		self.assertEqual(
			created_paths,
			{"docs/a.txt", "docs/b.txt", "docs/c.txt"},
		)
		self.assertEqual(len(self.job.items), 3)

		# sync_cursor must be cleared once the scan is fully complete.
		self.assertIn(self.job.sync_cursor, (None, "", "null"))


class TestScanSftpPaginationAndCursor(IntegrationTestCase):
	"""huf.ai.knowledge.bulk.scanners.scan_sftp — pagination + sync_cursor handling."""

	def setUp(self):
		self.source_name = "Test Bulk Source SFTP"
		if not frappe.db.exists("Knowledge Source", self.source_name):
			frappe.get_doc({
				"doctype": "Knowledge Source",
				"source_name": self.source_name,
				"scope": "Global",
				"storage_mode": "Frappe File",
				"knowledge_type": "sqlite_fts",
				"status": "Ready",
				"chunk_size": 512,
				"chunk_overlap": 50,
			}).insert(ignore_permissions=True)

		self.job = frappe.get_doc({
			"doctype": "Ingestion Job",
			"knowledge_source": self.source_name,
			"source_kind": "SFTP",
			"status": "Queued",
			"sftp_root_path": "/remote/root",
		}).insert(ignore_permissions=True)

	def tearDown(self):
		frappe.delete_doc("Ingestion Job", self.job.name, force=True, ignore_permissions=True)
		frappe.delete_doc("Knowledge Source", self.source_name, force=True, ignore_permissions=True)

	def test_scan_sftp_pagination_and_cursor(self):
		files_page_1 = [
			{"path": "/remote/root/a.txt", "size": 10, "mtime": 1700000000},
			{"path": "/remote/root/b.txt", "size": 20, "mtime": 1700000001},
		]
		files_page_2 = [
			{"path": "/remote/root/sub/c.txt", "size": 30, "mtime": 1700000002},
		]

		call_log = []

		def fake_list_dir_recursive(sftp, dir_queue):
			call_log.append(list(dir_queue))
			if len(call_log) == 1:
				self.assertEqual(dir_queue, ["/remote/root"])
				return files_page_1, ["/remote/root/sub"]
			self.assertEqual(dir_queue, ["/remote/root/sub"])
			return files_page_2, []

		fake_ssh_client = MagicMock()
		fake_sftp_session = MagicMock()

		with patch("huf.ai.knowledge.bulk.scanners._connect", return_value=(fake_ssh_client, fake_sftp_session)), \
				patch("huf.ai.knowledge.bulk.scanners.list_dir_recursive", side_effect=fake_list_dir_recursive), \
				patch("huf.ai.knowledge.bulk.scanners.frappe.enqueue"):
			# _connect and list_dir_recursive are imported by name at module level
			# in huf.ai.knowledge.bulk.scanners specifically so they can be patched
			# here -- scan_sftp() does not re-import them locally. _connect's real
			# return order is (ssh_client, sftp_client).

			from huf.ai.knowledge.bulk import scanners
			scanners.scan_sftp(self.job.name)

		self.assertEqual(len(call_log), 2)

		self.job.reload()

		created_paths = {row.external_path for row in self.job.items}
		self.assertEqual(
			created_paths,
			{"/remote/root/a.txt", "/remote/root/b.txt", "/remote/root/sub/c.txt"},
		)
		self.assertEqual(len(self.job.items), 3)

		# sync_cursor must be cleared once the directory queue is exhausted.
		self.assertIn(self.job.sync_cursor, (None, "", "null"))
