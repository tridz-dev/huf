import json
import os

import requests

BASE_URL = "https://discord.com/api/v10"


def _headers():
	token = os.getenv("DISCORD_BOT_TOKEN")
	if not token:
		raise ValueError("DISCORD_BOT_TOKEN environment variable is not set")
	return {"Authorization": f"Bot {token}", "Content-Type": "application/json"}


def handle_send_message(**kwargs):
	"""Send a message to a Discord channel."""
	try:
		resp = requests.post(
			f"{BASE_URL}/channels/{kwargs['channel_id']}/messages",
			headers=_headers(),
			json={"content": kwargs["message"]},
			timeout=30,
		)
		resp.raise_for_status()
		return json.dumps({"ok": True, "channel_id": kwargs["channel_id"]})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_get_channel_messages(**kwargs):
	"""Get message history of a Discord channel."""
	try:
		limit = int(kwargs.get("limit", 50))
		resp = requests.get(
			f"{BASE_URL}/channels/{kwargs['channel_id']}/messages",
			headers=_headers(),
			params={"limit": limit},
			timeout=30,
		)
		resp.raise_for_status()
		messages = resp.json()
		return json.dumps({"count": len(messages), "messages": messages})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_list_channels(**kwargs):
	"""List all channels in a Discord server (guild)."""
	try:
		resp = requests.get(
			f"{BASE_URL}/guilds/{kwargs['guild_id']}/channels",
			headers=_headers(),
			timeout=30,
		)
		resp.raise_for_status()
		channels = resp.json()
		return json.dumps({"count": len(channels), "channels": channels})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_delete_message(**kwargs):
	"""Delete a message from a Discord channel."""
	try:
		resp = requests.delete(
			f"{BASE_URL}/channels/{kwargs['channel_id']}/messages/{kwargs['message_id']}",
			headers=_headers(),
			timeout=30,
		)
		resp.raise_for_status()
		return json.dumps({"ok": True, "message_id": kwargs["message_id"]})
	except Exception as e:
		return json.dumps({"error": str(e)})
