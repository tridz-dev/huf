# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Unit tests for huf.ai.tools.s3 (no network, no DB): botocore Stubber and credential mocks."""

import datetime
import io
import json
import unittest
from unittest.mock import patch

from botocore.response import StreamingBody
from botocore.stub import Stubber

from huf.ai.tools import s3
from huf.ai.tools.integration.provider_errors import ProviderCredentialError

WHEN = datetime.datetime(2026, 1, 2, 3, 4, 5, tzinfo=datetime.timezone.utc)


def _creds(**overrides):
	values = {"access_key_id": "AKIATEST", "secret_access_key": "secret"}
	values.update(overrides)

	def fake(service, key):
		assert service == "S3"
		if key not in values:
			raise ValueError(f"Credential not found for service '{service}', key '{key}'.")
		return values[key]

	return patch("huf.ai.tools.s3.require_credential", side_effect=fake)


def _client(**overrides):
	with _creds(**overrides):
		return s3.get_s3_client()


def _obj(key, size=1):
	return {"Key": key, "Size": size, "LastModified": WHEN, "ETag": '"abc"'}


def _body(data: bytes):
	return StreamingBody(io.BytesIO(data), len(data))


class TestS3Client(unittest.TestCase):
	def test_endpoint_and_default_auto_region(self):
		client = _client(endpoint_url="https://acct.r2.cloudflarestorage.com")
		self.assertEqual(client.meta.endpoint_url, "https://acct.r2.cloudflarestorage.com")
		self.assertEqual(client.meta.region_name, "auto")
		self.assertEqual(client.meta.config.signature_version, "s3v4")

	def test_explicit_region_wins_with_endpoint(self):
		client = _client(endpoint_url="http://minio:9000", region="eu-west-1")
		self.assertEqual(client.meta.region_name, "eu-west-1")

	def test_no_endpoint_defaults_us_east_1(self):
		client = _client()
		self.assertEqual(client.meta.region_name, "us-east-1")
		self.assertEqual(client.meta.config.signature_version, "s3v4")

	def test_missing_access_key_raises_clear_error(self):
		with _creds() as mocked:
			mocked.side_effect = ValueError("Credential not found")
			with self.assertRaises(ProviderCredentialError) as ctx:
				s3.get_s3_client()
		self.assertIn("S3 is not connected", str(ctx.exception))
		self.assertIn("access key ID", str(ctx.exception))

	def test_missing_secret_raises_clear_error(self):
		def fake(service, key):
			if key == "access_key_id":
				return "AKIATEST"
			raise ValueError("missing")

		with patch("huf.ai.tools.s3.require_credential", side_effect=fake):
			with self.assertRaises(ProviderCredentialError) as ctx:
				s3.get_s3_client()
		self.assertIn("secret access key", str(ctx.exception))


class TestListObjectsPage(unittest.TestCase):
	def test_pagination_via_next_token_and_skips_directory_keys(self):
		client = _client()
		with Stubber(client) as stub:
			stub.add_response(
				"list_objects_v2",
				{"IsTruncated": True, "NextContinuationToken": "tok2", "Contents": [_obj("docs/"), _obj("docs/a.txt", 5)]},
				{"Bucket": "b", "Prefix": "docs/", "MaxKeys": 2},
			)
			stub.add_response(
				"list_objects_v2",
				{"IsTruncated": False, "Contents": [_obj("docs/b.txt", 7)]},
				{"Bucket": "b", "Prefix": "docs/", "MaxKeys": 2, "ContinuationToken": "tok2"},
			)
			first = s3.list_objects_page(client, "b", "docs/", page_size=2)
			self.assertEqual(first["next_token"], "tok2")
			self.assertEqual([o["key"] for o in first["objects"]], ["docs/a.txt"])
			self.assertEqual(first["objects"][0]["size"], 5)
			self.assertEqual(first["objects"][0]["etag"], "abc")
			self.assertEqual(first["objects"][0]["last_modified"], WHEN.isoformat())
			second = s3.list_objects_page(client, "b", "docs/", continuation_token="tok2", page_size=2)
			self.assertIsNone(second["next_token"])
			self.assertEqual([o["key"] for o in second["objects"]], ["docs/b.txt"])

	def test_empty_bucket(self):
		client = _client()
		with Stubber(client) as stub:
			stub.add_response("list_objects_v2", {"IsTruncated": False}, {"Bucket": "b", "Prefix": "", "MaxKeys": 1000})
			self.assertEqual(s3.list_objects_page(client, "b"), {"objects": [], "next_token": None})


class TestDownloadObject(unittest.TestCase):
	def test_returns_bytes_within_limit(self):
		client = _client()
		with Stubber(client) as stub:
			stub.add_response("get_object", {"Body": _body(b"hello"), "ContentLength": 5}, {"Bucket": "b", "Key": "k"})
			self.assertEqual(s3.download_object(client, "b", "k", 10), b"hello")

	def test_declared_size_over_limit_raises(self):
		client = _client()
		with Stubber(client) as stub:
			stub.add_response("get_object", {"Body": _body(b"x" * 20), "ContentLength": 20}, {"Bucket": "b", "Key": "k"})
			with self.assertRaises(ValueError):
				s3.download_object(client, "b", "k", 10)

	def test_actual_size_over_limit_raises_without_content_length(self):
		client = _client()
		with Stubber(client) as stub:
			stub.add_response("get_object", {"Body": _body(b"x" * 20)}, {"Bucket": "b", "Key": "k"})
			with self.assertRaises(ValueError):
				s3.download_object(client, "b", "k", 10)


class TestAgentTools(unittest.TestCase):
	def test_list_objects_requires_bucket(self):
		self.assertFalse(json.loads(s3.handle_list_objects())["success"])

	def test_search_scans_pages_and_matches_case_insensitively(self):
		client = _client()
		with Stubber(client) as stub:
			stub.add_response(
				"list_objects_v2",
				{"IsTruncated": True, "NextContinuationToken": "t", "Contents": [_obj("a/Report.txt"), _obj("a/x.txt")]},
				{"Bucket": "b", "Prefix": "", "MaxKeys": 1000},
			)
			stub.add_response(
				"list_objects_v2",
				{"IsTruncated": False, "Contents": [_obj("b/annual-report.pdf")]},
				{"Bucket": "b", "Prefix": "", "MaxKeys": 1000, "ContinuationToken": "t"},
			)
			with patch("huf.ai.tools.s3.get_s3_client", return_value=client):
				out = json.loads(s3.handle_search_objects(bucket="b", query="REPORT"))
		self.assertTrue(out["success"])
		self.assertEqual([o["key"] for o in out["results"]], ["a/Report.txt", "b/annual-report.pdf"])
		self.assertTrue(out["complete"])

	def test_get_object_text_truncates(self):
		client = _client()
		with Stubber(client) as stub:
			stub.add_response("get_object", {"Body": _body(b"abcdefghij"), "ContentLength": 10}, {"Bucket": "b", "Key": "k"})
			with patch("huf.ai.tools.s3.get_s3_client", return_value=client):
				out = json.loads(s3.handle_get_object_text(bucket="b", key="k", max_chars=4))
		self.assertEqual(out["text"], "abcd")
		self.assertTrue(out["truncated"])

	def test_missing_credential_returns_error_json(self):
		with patch("huf.ai.tools.s3.require_credential", side_effect=ValueError("missing")), patch(
			"huf.ai.tools.s3.update_last_error"
		):
			out = json.loads(s3.handle_list_objects(bucket="b"))
		self.assertFalse(out["success"])
		self.assertIn("S3 is not connected", out["error"])
