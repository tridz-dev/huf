import json

from huf.ai.tools.credentials import require_credential


def handle_send_email(**kwargs):
	"""Send an email using Amazon SES."""
	try:
		import boto3
	except ImportError:
		return json.dumps({"error": "boto3 is required. Install with: pip install boto3"})

	try:
		region = require_credential("aws", "default_region")
		access_key = require_credential("aws", "access_key_id")
		secret_key = require_credential("aws", "secret_access_key")
		
		client = boto3.client(
			"ses", 
			region_name=region,
			aws_access_key_id=access_key,
			aws_secret_access_key=secret_key
		)

		resp = client.send_email(
			Source=kwargs.get("sender", ""),
			Destination={"ToAddresses": [kwargs["receiver_email"]]},
			Message={
				"Subject": {"Data": kwargs["subject"]},
				"Body": {"Html": {"Data": kwargs["body"]}},
			},
		)
		return json.dumps({"ok": True, "message_id": resp.get("MessageId", "")})
	except Exception as e:
		return json.dumps({"error": str(e)})
