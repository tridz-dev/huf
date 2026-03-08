import json

from huf.ai.tools.credentials import require_credential
import requests

BASE = "https://api.openweathermap.org"


def _key():
	return require_credential("openweather", "api_key")


def _geocode(location):
	resp = requests.get(
		f"{BASE}/geo/1.0/direct",
		params={"q": location, "limit": 1, "appid": _key()},
		timeout=15,
	)
	resp.raise_for_status()
	data = resp.json()
	if not data:
		return None, None
	return data[0]["lat"], data[0]["lon"]


def handle_get_current_weather(**kwargs):
	"""Get current weather for a location."""
	try:
		lat, lon = _geocode(kwargs["location"])
		if lat is None:
			return json.dumps({"error": f"Location not found: {kwargs['location']}"})

		resp = requests.get(
			f"{BASE}/data/2.5/weather",
			params={"lat": lat, "lon": lon, "appid": _key(), "units": "metric"},
			timeout=15,
		)
		resp.raise_for_status()
		d = resp.json()
		return json.dumps({
			"location": kwargs["location"],
			"temperature_c": d["main"]["temp"],
			"feels_like_c": d["main"]["feels_like"],
			"humidity": d["main"]["humidity"],
			"description": d["weather"][0]["description"] if d.get("weather") else "",
			"wind_speed_mps": d["wind"]["speed"],
		})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_get_forecast(**kwargs):
	"""Get 5-day weather forecast for a location."""
	try:
		lat, lon = _geocode(kwargs["location"])
		if lat is None:
			return json.dumps({"error": f"Location not found: {kwargs['location']}"})

		resp = requests.get(
			f"{BASE}/data/2.5/forecast",
			params={"lat": lat, "lon": lon, "appid": _key(), "units": "metric"},
			timeout=15,
		)
		resp.raise_for_status()
		d = resp.json()
		forecasts = [
			{
				"dt_txt": f["dt_txt"],
				"temp_c": f["main"]["temp"],
				"description": f["weather"][0]["description"] if f.get("weather") else "",
			}
			for f in d.get("list", [])[:10]
		]
		return json.dumps({"location": kwargs["location"], "forecasts": forecasts})
	except Exception as e:
		return json.dumps({"error": str(e)})


def handle_get_air_pollution(**kwargs):
	"""Get air pollution data for a location."""
	try:
		lat, lon = _geocode(kwargs["location"])
		if lat is None:
			return json.dumps({"error": f"Location not found: {kwargs['location']}"})

		resp = requests.get(
			f"{BASE}/data/2.5/air_pollution",
			params={"lat": lat, "lon": lon, "appid": _key()},
			timeout=15,
		)
		resp.raise_for_status()
		d = resp.json()
		item = d.get("list", [{}])[0] if d.get("list") else {}
		return json.dumps({
			"location": kwargs["location"],
			"aqi": item.get("main", {}).get("aqi"),
			"components": item.get("components", {}),
		})
	except Exception as e:
		return json.dumps({"error": str(e)})
