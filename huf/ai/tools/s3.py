import json
import frappe
logger = frappe.logger("huf")
from huf.ai.tools.credentials import require_credential, update_last_error
import boto3


def _get_client():
	service_name = "aws_s3"
	access_key_id = require_credential(service_name, "access_key_id")
	secret_access_key = require_credential(service_name, "secret_access_key")
	region = require_credential(service_name, "region")

	return boto3.client(
		"s3",
		aws_access_key_id=access_key_id,
		aws_secret_access_key=secret_access_key,
		region_name=region,
	)


def list_objects_page(client, bucket, prefix="", continuation_token=None, page_size=100):
	kwargs = {"Bucket": bucket, "Prefix": prefix, "MaxKeys": page_size}
	if continuation_token:
		kwargs["ContinuationToken"] = continuation_token

	resp = client.list_objects_v2(**kwargs)

	objects = []
	for obj in resp.get("Contents", []):
		objects.append({
			"key": obj.get("Key"),
			"size": obj.get("Size"),
			"last_modified": obj.get("LastModified").isoformat() if obj.get("LastModified") else None,
			"etag": obj.get("ETag"),
		})

	next_token = resp.get("NextContinuationToken") if resp.get("IsTruncated") else None

	return {"objects": objects, "next_token": next_token}


def handle_list_buckets(**kwargs):
	"""List S3 buckets."""
	service_name = "aws_s3"
	try:
		client = _get_client()
		resp = client.list_buckets()
		buckets = [
			{"name": b.get("Name"), "creation_date": b.get("CreationDate").isoformat() if b.get("CreationDate") else None}
			for b in resp.get("Buckets", [])
		]
		return json.dumps({
			"success": True,
			"count": len(buckets),
			"results": buckets
		})
	except Exception as e:
		logger.warning(f"S3 Error (List Buckets): {str(e)}")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})


def handle_list_objects(**kwargs):
	"""List objects in an S3 bucket."""
	service_name = "aws_s3"
	try:
		bucket = kwargs.get("bucket")
		if not bucket:
			return json.dumps({"success": False, "error": "bucket is required"})

		prefix = kwargs.get("prefix", "")
		limit = int(kwargs.get("limit", 50))

		client = _get_client()
		page = list_objects_page(client, bucket, prefix, page_size=limit)
		objects = page["objects"]

		return json.dumps({
			"success": True,
			"count": len(objects),
			"results": objects
		})
	except Exception as e:
		logger.warning(f"S3 Error (List Objects): {str(e)}")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})


def handle_get_object_metadata(**kwargs):
	"""Get metadata of an S3 object."""
	service_name = "aws_s3"
	try:
		bucket = kwargs.get("bucket")
		if not bucket:
			return json.dumps({"success": False, "error": "bucket is required"})

		key = kwargs.get("key")
		if not key:
			return json.dumps({"success": False, "error": "key is required"})

		client = _get_client()
		resp = client.head_object(Bucket=bucket, Key=key)

		data = {
			"content_length": resp.get("ContentLength"),
			"content_type": resp.get("ContentType"),
			"last_modified": resp.get("LastModified").isoformat() if resp.get("LastModified") else None,
			"etag": resp.get("ETag"),
		}

		return json.dumps({
			"success": True,
			"results": data
		})
	except Exception as e:
		logger.warning(f"S3 Error (Get Object Metadata): {str(e)}")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})


def handle_search_objects(**kwargs):
	"""Search for objects in an S3 bucket by key substring."""
	service_name = "aws_s3"
	try:
		bucket = kwargs.get("bucket")
		if not bucket:
			return json.dumps({"success": False, "error": "bucket is required"})

		query = kwargs.get("query")
		if not query:
			return json.dumps({"success": False, "error": "query is required"})

		client = _get_client()
		query_lower = query.lower()

		matches = []
		token = None
		for _ in range(5):
			page = list_objects_page(client, bucket, continuation_token=token)
			for obj in page["objects"]:
				if query_lower in obj["key"].lower():
					matches.append(obj)
					if len(matches) >= 200:
						break
			if len(matches) >= 200:
				break
			token = page["next_token"]
			if not token:
				break

		return json.dumps({
			"success": True,
			"count": len(matches),
			"results": matches
		})
	except Exception as e:
		logger.warning(f"S3 Error (Search Objects): {str(e)}")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})
