"""S3 / S3-compatible (Cloudflare R2, MinIO) object storage: client, paging, download, agent tools."""

import json

import frappe

from huf.ai.tools.credentials import require_credential, update_last_error
from huf.ai.tools.integration.provider_errors import ProviderCredentialError, not_connected_message

logger = frappe.logger("huf")

SERVICE_LABEL = "S3"
DEFAULT_REGION = "us-east-1"
TEXT_MAX_BYTES = 5 * 1024 * 1024
DEFAULT_TEXT_CHARS = 20000
SEARCH_MAX_PAGES = 10


def _optional_credential(key: str) -> str | None:
	try:
		return require_credential(SERVICE_LABEL, key) or None
	except ValueError:
		return None


def _required_credential(key: str, label: str) -> str:
	try:
		value = require_credential(SERVICE_LABEL, key)
	except ValueError:
		value = None
	if not value:
		raise ProviderCredentialError(not_connected_message("S3", f"the {label}"), kind="missing")
	return value


def get_s3_client(credential: str | None = None):
	"""Build a boto3 S3 client from the saved "S3" credentials.

	`endpoint_url` (optional) points at R2/MinIO/any S3-compatible store; the region then
	defaults to "auto" (R2) and path-style addressing is used. Signature version is always v4.
	`credential` is an optional override for the access key id (its secret stays the saved one).
	"""
	import boto3
	from botocore.config import Config

	access_key = credential or _required_credential("access_key_id", "access key ID")
	secret_key = _required_credential("secret_access_key", "secret access key")
	endpoint_url = _optional_credential("endpoint_url")
	region = _optional_credential("region") or ("auto" if endpoint_url else DEFAULT_REGION)

	config_kwargs = {"signature_version": "s3v4", "retries": {"max_attempts": 3, "mode": "standard"}}
	if endpoint_url:
		config_kwargs["s3"] = {"addressing_style": "path"}
	return boto3.client(
		"s3",
		aws_access_key_id=access_key,
		aws_secret_access_key=secret_key,
		endpoint_url=endpoint_url,
		region_name=region,
		config=Config(**config_kwargs),
	)


def list_objects_page(client, bucket, prefix="", continuation_token=None, page_size=1000):
	"""One page of objects: {"objects": [{key,size,last_modified,etag}], "next_token": str|None}."""
	params = {"Bucket": bucket, "Prefix": prefix or "", "MaxKeys": int(page_size)}
	if continuation_token:
		params["ContinuationToken"] = continuation_token
	resp = client.list_objects_v2(**params)
	objects = []
	for item in resp.get("Contents") or []:
		key = item["Key"]
		if key.endswith("/"):
			continue
		modified = item.get("LastModified")
		objects.append({
			"key": key,
			"size": item.get("Size", 0),
			"last_modified": modified.isoformat() if hasattr(modified, "isoformat") else modified,
			"etag": (item.get("ETag") or "").strip('"'),
		})
	next_token = resp.get("NextContinuationToken") if resp.get("IsTruncated") else None
	return {"objects": objects, "next_token": next_token}


def download_object(client, bucket, key, max_bytes) -> bytes:
	"""Download an object; raise ValueError if it is larger than `max_bytes`."""
	resp = client.get_object(Bucket=bucket, Key=key)
	declared = resp.get("ContentLength")
	if declared is not None and declared > max_bytes:
		raise ValueError(f"Object '{key}' is {declared} bytes, over the {max_bytes} byte limit")
	data = resp["Body"].read(max_bytes + 1)
	if len(data) > max_bytes:
		raise ValueError(f"Object '{key}' is over the {max_bytes} byte limit")
	return data


def _fail(op: str, error: Exception) -> str:
	logger.warning(f"S3 Error ({op}): {error}")
	update_last_error(SERVICE_LABEL, str(error))
	return json.dumps({"success": False, "error": str(error)})


def handle_list_objects(**kwargs):
	"""List objects in a bucket (one page, optional prefix)."""
	try:
		bucket = kwargs.get("bucket")
		if not bucket:
			return json.dumps({"success": False, "error": "bucket is required"})
		limit = max(1, min(int(kwargs.get("limit") or 100), 1000))
		page = list_objects_page(
			get_s3_client(), bucket, kwargs.get("prefix") or "", kwargs.get("continuation_token"), limit
		)
		return json.dumps({
			"success": True,
			"count": len(page["objects"]),
			"results": page["objects"],
			"next_token": page["next_token"],
		})
	except Exception as e:
		return _fail("List", e)


def handle_search_objects(**kwargs):
	"""Find objects whose key contains `query` (case-insensitive), scanning a bounded number of pages."""
	try:
		bucket = kwargs.get("bucket")
		query = (kwargs.get("query") or "").strip().lower()
		if not bucket or not query:
			return json.dumps({"success": False, "error": "bucket and query are required"})
		limit = max(1, min(int(kwargs.get("limit") or 20), 200))
		client = get_s3_client()
		token, matches, scanned = None, [], 0
		for _ in range(SEARCH_MAX_PAGES):
			page = list_objects_page(client, bucket, kwargs.get("prefix") or "", token)
			scanned += len(page["objects"])
			matches.extend(o for o in page["objects"] if query in o["key"].lower())
			token = page["next_token"]
			if not token or len(matches) >= limit:
				break
		return json.dumps({
			"success": True,
			"count": len(matches[:limit]),
			"results": matches[:limit],
			"scanned": scanned,
			"complete": not token,
		})
	except Exception as e:
		return _fail("Search", e)


def handle_get_object_text(**kwargs):
	"""Read an object as UTF-8 text, truncated to `max_chars`."""
	try:
		bucket, key = kwargs.get("bucket"), kwargs.get("key")
		if not bucket or not key:
			return json.dumps({"success": False, "error": "bucket and key are required"})
		max_chars = max(1, int(kwargs.get("max_chars") or DEFAULT_TEXT_CHARS))
		data = download_object(get_s3_client(), bucket, key, TEXT_MAX_BYTES)
		text = data.decode("utf-8", errors="replace")
		return json.dumps({
			"success": True,
			"key": key,
			"truncated": len(text) > max_chars,
			"text": text[:max_chars],
		})
	except Exception as e:
		return _fail("Get Object", e)
