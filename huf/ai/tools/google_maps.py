import json
import frappe
from huf.ai.tools.credentials import require_credential, update_last_error
import requests

BASE = "https://maps.googleapis.com/maps/api"


def _key():
	return require_credential("google_maps", "api_key")


def handle_search_places(**kwargs):
	"""Search for places using Google Maps."""
	service_name = "google_maps"
	try:
		query = kwargs.get("query")
		if not query:
			return json.dumps({"success": False, "error": "query is required"})

		headers = {
			"X-Goog-Api-Key": _key(),
			"X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.rating,places.id",
			"Content-Type": "application/json"
		}
		resp = requests.post(
			"https://places.googleapis.com/v1/places:searchText",
			headers=headers,
			json={"textQuery": query},
			timeout=15,
		)
		
		# Handle API errors safely
		if not resp.ok:
			try:
				error_data = resp.json()
				error_msg = error_data.get("error", {}).get("message", resp.text)
			except Exception:
				error_msg = resp.text
			return json.dumps({"success": False, "error": f"Google API Error: {error_msg}"})

		data = resp.json()
		results = [
			{
				"name": p.get("displayName", {}).get("text", ""),
				"address": p.get("formattedAddress", ""),
				"rating": p.get("rating"),
				"place_id": p.get("id", ""),
			}
			for p in data.get("places", [])[:10]
		]
		return json.dumps({
			"success": True, 
			"count": len(results), 
			"results": results
		})
	except Exception as e:
		frappe.log_error(f"Google Maps Error (Search): {str(e)}", "Google Maps Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})


def handle_get_directions(**kwargs):
	"""Get driving directions between two locations."""
	service_name = "google_maps"
	try:
		origin = kwargs.get("origin")
		destination = kwargs.get("destination")
		if not all([origin, destination]):
			return json.dumps({"success": False, "error": "origin and destination are required"})

		params = {
			"origin": origin,
			"destination": destination,
			"mode": kwargs.get("mode", "driving"),
			"key": _key(),
		}
		resp = requests.get(f"{BASE}/directions/json", params=params, timeout=15)
		resp.raise_for_status()
		data = resp.json()

		if data.get("status") not in ("OK", "ZERO_RESULTS"):
			error_msg = data.get("error_message", f"Google API Error: {data.get('status')}")
			return json.dumps({"success": False, "error": error_msg})

		routes = data.get("routes", [])
		if not routes:
			return json.dumps({"success": False, "error": "No routes found"})

		leg = routes[0].get("legs", [{}])[0]
		return json.dumps({
			"success": True,
			"results": {
				"distance": leg.get("distance", {}).get("text", ""),
				"duration": leg.get("duration", {}).get("text", ""),
				"start_address": leg.get("start_address", ""),
				"end_address": leg.get("end_address", ""),
			}
		})
	except Exception as e:
		frappe.log_error(f"Google Maps Error (Directions): {str(e)}", "Google Maps Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})


def handle_geocode(**kwargs):
	"""Convert an address to coordinates."""
	service_name = "google_maps"
	try:
		address = kwargs.get("address")
		if not address:
			return json.dumps({"success": False, "error": "address is required"})

		resp = requests.get(
			f"{BASE}/geocode/json",
			params={"address": address, "key": _key()},
			timeout=15,
		)
		resp.raise_for_status()
		data = resp.json()

		if data.get("status") not in ("OK", "ZERO_RESULTS"):
			error_msg = data.get("error_message", f"Google API Error: {data.get('status')}")
			return json.dumps({"success": False, "error": error_msg})

		results = data.get("results", [])
		if not results:
			return json.dumps({"success": False, "error": "Address not found"})

		loc = results[0].get("geometry", {}).get("location", {})
		return json.dumps({
			"success": True,
			"results": {
				"address": results[0].get("formatted_address", ""),
				"lat": loc.get("lat"),
				"lng": loc.get("lng"),
			}
		})
	except Exception as e:
		frappe.log_error(f"Google Maps Error (Geocode): {str(e)}", "Google Maps Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})


def handle_reverse_geocode(**kwargs):
	"""Convert coordinates to an address."""
	service_name = "google_maps"
	try:
		lat = kwargs.get("lat")
		lng = kwargs.get("lng")
		if lat is None or lng is None:
			return json.dumps({"success": False, "error": "lat and lng are required"})

		resp = requests.get(
			f"{BASE}/geocode/json",
			params={"latlng": f"{lat},{lng}", "key": _key()},
			timeout=15,
		)
		resp.raise_for_status()
		data = resp.json()

		if data.get("status") not in ("OK", "ZERO_RESULTS"):
			error_msg = data.get("error_message", f"Google API Error: {data.get('status')}")
			return json.dumps({"success": False, "error": error_msg})

		results = data.get("results", [])
		if not results:
			return json.dumps({"success": False, "error": "No address found for coordinates"})

		return json.dumps({
			"success": True,
			"results": {
				"address": results[0].get("formatted_address", ""), 
				"place_id": results[0].get("place_id", "")
			}
		})
	except Exception as e:
		frappe.log_error(f"Google Maps Error (Reverse Geocode): {str(e)}", "Google Maps Tool")
		update_last_error(service_name, str(e))
		return json.dumps({"success": False, "error": str(e)})
