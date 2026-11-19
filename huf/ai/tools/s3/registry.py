"""Agent tool catalog and Integration Service seed for S3 (kept out of _registry.py / install.py)."""

S3_SERVICE = {
	"service_name": "S3",
	"category": "Storage",
	"surface": "Integration",
	"description": "S3 and S3-compatible object storage (AWS S3, Cloudflare R2, MinIO)",
	"required_credentials": [
		{"key": "access_key_id", "label": "Access Key ID", "required": True},
		{"key": "secret_access_key", "label": "Secret Access Key", "required": True},
		{
			"key": "endpoint_url",
			"label": "Endpoint URL",
			"required": False,
			"secret": False,
			"description": "Leave empty for AWS S3. For Cloudflare R2 or MinIO use the S3 API endpoint.",
		},
		{
			"key": "region",
			"label": "Region",
			"required": False,
			"secret": False,
			"description": "Defaults to 'auto' when an endpoint URL is set, otherwise us-east-1.",
		},
	],
}


def _p(name, type="string", required=False, description=""):
	return {
		"label": name.replace("_", " ").title(),
		"fieldname": name,
		"type": type,
		"required": int(required),
		"description": description,
	}


S3_TOOLS = [
	{
		"tool_name": "s3_list_objects",
		"description": "List objects in an S3-compatible bucket (one page). Requires S3 credentials.",
		"function_path": "huf.ai.tools.s3.handle_list_objects",
		"category": "Storage",
		"parameters": [
			_p("bucket", required=True, description="Bucket name"),
			_p("prefix", description="Only keys starting with this prefix"),
			_p("limit", type="integer", description="Max objects, 1-1000 (default 100)"),
			_p("continuation_token", description="next_token from a previous call"),
		],
	},
	{
		"tool_name": "s3_search_objects",
		"description": "Find objects whose key contains a text (case-insensitive). Requires S3 credentials.",
		"function_path": "huf.ai.tools.s3.handle_search_objects",
		"category": "Storage",
		"parameters": [
			_p("bucket", required=True, description="Bucket name"),
			_p("query", required=True, description="Text to find in object keys"),
			_p("prefix", description="Only search keys starting with this prefix"),
			_p("limit", type="integer", description="Max matches (default 20)"),
		],
	},
	{
		"tool_name": "s3_get_object_text",
		"description": "Read a text object (up to 5 MB) and return its text, truncated. Requires S3 credentials.",
		"function_path": "huf.ai.tools.s3.handle_get_object_text",
		"category": "Storage",
		"parameters": [
			_p("bucket", required=True, description="Bucket name"),
			_p("key", required=True, description="Object key"),
			_p("max_chars", type="integer", description="Max characters returned (default 20000)"),
		],
	},
]
