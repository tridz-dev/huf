import json
import frappe
from huf.ai.tools.credentials import require_credential, update_last_error


def handle_send_email(**kwargs):
	"""Send an email using Amazon SES."""
	service_name = "aws"
	try:
		import boto3
	except ImportError:
		return json.dumps({"success": False, "error": "boto3 is required. Install with: pip install boto3"})

	try:
		region = require_credential(service_name, "region")
		access_key = require_credential(service_name, "access_key")
		secret_key = require_credential(service_name, "secret_key")
		
		client = boto3.client(
			"ses", 
			region_name=region,
			aws_access_key_id=access_key,
			aws_secret_access_key=secret_key
		)

		resp = client.send_email(
			Source=kwargs.get("sender") or kwargs.get("from_email"),
			Destination={"ToAddresses": [kwargs["receiver_email"]]},
			Message={
				"Subject": {"Data": kwargs["subject"]},
				"Body": {"Html": {"Data": kwargs["body"]}},
			},
		)
		return json.dumps({"success": True, "message_id": resp.get("MessageId", "")})
	except Exception as e:
		frappe.log_error(f"AWS SES Error: {str(e)}", "AWS SES Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})
