import json

from huf.ai.tools.credentials import require_credential
import requests

BASE = "https://maps.googleapis.com/maps/api"


def _key():
	return require_credential("google", "api_key")


def handle_search_places(**kwargs):
	"""Search for places using Google Maps."""
	try:
		resp = requests.get(
			f"{BASE}/place/textsearch/json",
			params={"query": kwargs["query"], "key": _key()},
			timeout=15,
		)
		resp.raise_for_status()
		results = [
			{
				"name": p.get("name", ""),
				"address": p.get("formatted_address", ""),
				"rating": p.get("rating"),
				"place_id": p.get("place_id", ""),
			}
			for p in resp.json().get("results", [])[:10]
		]
		return json.dumps({"count": len(results), "places": results})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_get_directions(**kwargs):
	"""Get driving directions between two locations."""
	try:
		params = {
			"origin": kwargs["origin"],
			"destination": kwargs["destination"],
			"mode": kwargs.get("mode", "driving"),
			"key": _key(),
		}
		resp = requests.get(f"{BASE}/directions/json", params=params, timeout=15)
		resp.raise_for_status()
		data = resp.json()
		routes = data.get("routes", [])
		if not routes:
			return json.dumps({"error": "No routes found"})

		leg = routes[0].get("legs", [{}])[0]
		return json.dumps({
			"distance": leg.get("distance", {}).get("text", ""),
			"duration": leg.get("duration", {}).get("text", ""),
			"start_address": leg.get("start_address", ""),
			"end_address": leg.get("end_address", ""),
		})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_geocode(**kwargs):
	"""Convert an address to coordinates."""
	try:
		resp = requests.get(
			f"{BASE}/geocode/json",
			params={"address": kwargs["address"], "key": _key()},
			timeout=15,
		)
		resp.raise_for_status()
		results = resp.json().get("results", [])
		if not results:
			return json.dumps({"error": "Address not found"})

		loc = results[0].get("geometry", {}).get("location", {})
		return json.dumps({
			"address": results[0].get("formatted_address", ""),
			"lat": loc.get("lat"),
			"lng": loc.get("lng"),
		})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_reverse_geocode(**kwargs):
	"""Convert coordinates to an address."""
	try:
		resp = requests.get(
			f"{BASE}/geocode/json",
			params={"latlng": f"{kwargs['lat']},{kwargs['lng']}", "key": _key()},
			timeout=15,
		)
		resp.raise_for_status()
		results = resp.json().get("results", [])
		if not results:
			return json.dumps({"error": "No address found for coordinates"})

		return json.dumps({"address": results[0].get("formatted_address", ""), "place_id": results[0].get("place_id", "")})
	except Exception as e:
		return json.dumps({"error": str(e)})
