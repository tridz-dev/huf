import json
import os


def _get_client():
	try:
		from slack_sdk import WebClient
	except ImportError:
		raise ImportError("slack-sdk is required. Install with: pip install slack-sdk")

	token = os.getenv("SLACK_TOKEN")
	if not token:
		raise ValueError("SLACK_TOKEN environment variable is not set")
	return WebClient(token=token)


def handle_send_message(**kwargs):
	"""Send a message to a Slack channel."""
	try:
		client = _get_client()
		resp = client.chat_postMessage(channel=kwargs["channel"], text=kwargs["text"], mrkdwn=True)
		return json.dumps({"ok": True, "channel": kwargs["channel"], "ts": resp.get("ts", "")})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_send_message_thread(**kwargs):
	"""Reply to a thread in a Slack channel."""
	try:
		client = _get_client()
		resp = client.chat_postMessage(
			channel=kwargs["channel"],
			text=kwargs["text"],
			thread_ts=kwargs["thread_ts"],
			mrkdwn=True,
		)
		return json.dumps({"ok": True, "channel": kwargs["channel"], "ts": resp.get("ts", "")})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_list_channels(**kwargs):
	"""List all channels in the Slack workspace."""
	try:
		client = _get_client()
		resp = client.conversations_list()
		channels = [{"id": c["id"], "name": c["name"]} for c in resp.get("channels", [])]
		return json.dumps({"count": len(channels), "channels": channels})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_get_channel_history(**kwargs):
	"""Get message history of a Slack channel."""
	try:
		client = _get_client()
		limit = int(kwargs.get("limit", 100))
		resp = client.conversations_history(channel=kwargs["channel"], limit=limit)
		messages = [
			{
				"text": m.get("text", ""),
				"user": m.get("user", "unknown"),
				"ts": m.get("ts", ""),
			}
			for m in resp.get("messages", [])
		]
		return json.dumps({"count": len(messages), "messages": messages})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_search_messages(**kwargs):
	"""Search messages across the Slack workspace."""
	try:
		client = _get_client()
		limit = min(int(kwargs.get("limit", 20)), 100)
		resp = client.search_messages(query=kwargs["query"], count=limit)
		matches = resp.get("messages", {}).get("matches", [])
		messages = [
			{
				"text": m.get("text", ""),
				"user": m.get("user", "unknown"),
				"channel_name": m.get("channel", {}).get("name", ""),
				"ts": m.get("ts", ""),
				"permalink": m.get("permalink", ""),
			}
			for m in matches
		]
		return json.dumps({"count": len(messages), "messages": messages})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_list_users(**kwargs):
	"""List all users in the Slack workspace."""
	try:
		client = _get_client()
		limit = int(kwargs.get("limit", 100))
		resp = client.users_list(limit=limit)
		users = [
			{
				"id": m.get("id", ""),
				"name": m.get("name", ""),
				"real_name": m.get("profile", {}).get("real_name", ""),
				"is_bot": m.get("is_bot", False),
			}
			for m in resp.get("members", [])
			if not m.get("deleted", False)
		]
		return json.dumps({"count": len(users), "users": users})
	except Exception as e:
		return json.dumps({"error": str(e)})
