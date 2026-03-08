import json
import os


def handle_send_email(**kwargs):
	"""Send an email using Amazon SES."""
	try:
		import boto3
	except ImportError:
		return json.dumps({"error": "boto3 is required. Install with: pip install boto3"})

	try:
		region = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
		client = boto3.client("ses", region_name=region)

		resp = client.send_email(
			Source=kwargs.get("sender", os.getenv("AWS_SES_SENDER", "")),
			Destination={"ToAddresses": [kwargs["receiver_email"]]},
			Message={
				"Subject": {"Data": kwargs["subject"]},
				"Body": {"Html": {"Data": kwargs["body"]}},
			},
		)
		return json.dumps({"ok": True, "message_id": resp.get("MessageId", "")})
	except Exception as e:
		return json.dumps({"error": str(e)})
