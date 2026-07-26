import json

import frappe
import requests

from huf.ai.tools.credentials import get_credential, require_credential, update_last_error

logger = frappe.logger("huf")

BASE_URL = "https://places.googleapis.com/v1"
SERVICE_NAME = "google_maps"

# Truncate raw Google error payloads before surfacing them in tool output
_MAX_ERROR_LENGTH = 500

# Practical limit for autocomplete input — place names are never this long
_MAX_INPUT_LENGTH = 200

# Coordinate range constants
_LATITUDE_MIN, _LATITUDE_MAX = -90.0, 90.0
_LONGITUDE_MIN, _LONGITUDE_MAX = -180.0, 180.0
_RADIUS_MIN = 1.0  # metres

# Non-country place types covering cities, states, districts and neighborhoods.
# Google Places API (New) allows at most 5 types in includedPrimaryTypes.
_DEFAULT_INCLUDED_PRIMARY_TYPES_CSV = (
	"locality,sublocality,administrative_area_level_1,administrative_area_level_2,neighborhood"
)


def _cfg(key, default=None, cast=None):
	"""Read optional configuration from the google_maps Integration Service."""
	raw = get_credential(SERVICE_NAME, key, None)
	if raw is None or raw == "":
		return default
	if cast is bool:
		return _as_bool(raw)
	if cast is int:
		try:
			return int(float(raw))
		except (TypeError, ValueError):
			return default
	if cast is float:
		try:
			return float(raw)
		except (TypeError, ValueError):
			return default
	return raw


def _cache_ttl():
	return _cfg("places_cache_ttl", 86400, int)


def _cache_enabled():
	return _cfg("places_cache_enabled", True, bool)

SEARCH_FIELD_MASK = (
	"places.id,places.displayName,places.formattedAddress,places.primaryType,"
	"places.types,places.rating,places.userRatingCount,places.priceLevel,"
	"places.location,places.googleMapsUri,places.businessStatus,"
	"places.currentOpeningHours.openNow,nextPageToken"
)

DETAILS_FIELD_MASK = (
	"id,displayName,primaryType,types,rating,userRatingCount,priceLevel,"
	"location,googleMapsUri,businessStatus,formattedAddress,"
	"internationalPhoneNumber,websiteUri,regularOpeningHours,photos,reviews,"
	"reviewSummary,editorialSummary,accessibilityOptions,paymentOptions,"
	"parkingOptions"
)


def _key():
	return require_credential(SERVICE_NAME, "api_key")


def _request_timeout(autocomplete=False):
	key = "autocomplete_request_timeout" if autocomplete else "places_request_timeout"
	default = 5 if autocomplete else 15
	return _cfg(key, default, int)


def _as_bool(value):
	"""Coerce common truthy/falsy representations to bool."""
	if isinstance(value, bool):
		return value
	if isinstance(value, int | float):
		return bool(value)
	if isinstance(value, str):
		return value.strip().lower() in ("1", "true", "yes", "on")
	return bool(value)


def _as_float(value):
	try:
		return float(value)
	except (TypeError, ValueError):
		return None


def _as_int(value):
	try:
		return int(float(value))
	except (TypeError, ValueError):
		return None


def _as_csv(value):
	"""Accept a comma-separated string or a list and return a clean list of strings."""
	if value is None:
		return []
	if isinstance(value, str):
		return [part.strip() for part in value.split(",") if part.strip()]
	if isinstance(value, list | tuple):
		return [str(part).strip() for part in value if str(part).strip()]
	return [str(value)]


def _request_error(resp):
	"""Build a truncated error message from a non-OK Google API response."""
	try:
		message = resp.json().get("error", {}).get("message") or resp.text
	except Exception:
		message = resp.text
	return f"Google Places API Error ({resp.status_code}): {str(message)[:_MAX_ERROR_LENGTH]}"


def _post(endpoint, body, field_mask=None, timeout=None):
	"""POST to the Places API (New). Returns (data, error_message)."""
	if timeout is None:
		timeout = _request_timeout()
	headers = {
		"Content-Type": "application/json",
		"X-Goog-Api-Key": _key(),
	}
	if field_mask:
		headers["X-Goog-FieldMask"] = field_mask
	resp = requests.post(f"{BASE_URL}/{endpoint}", headers=headers, json=body, timeout=timeout)
	if not resp.ok:
		return None, _request_error(resp)
	return resp.json(), None


def _default_radius():
	return _cfg("places_default_radius", 50000.0, float)


def _build_circle(latitude, longitude, radius):
	"""Validate coordinates and build a circle dict. Returns (circle, error_message)."""
	lat = _as_float(latitude)
	lng = _as_float(longitude)
	rad = _as_float(radius if radius is not None else _default_radius())
	if lat is None or lng is None:
		return None, "latitude and longitude must be numeric"
	if rad is None:
		return None, "radius must be numeric"
	if not (_LATITUDE_MIN <= lat <= _LATITUDE_MAX):
		return None, f"latitude must be between {_LATITUDE_MIN} and {_LATITUDE_MAX}"
	if not (_LONGITUDE_MIN <= lng <= _LONGITUDE_MAX):
		return None, f"longitude must be between {_LONGITUDE_MIN} and {_LONGITUDE_MAX}"
	if rad < _RADIUS_MIN:
		return None, f"radius must be at least {_RADIUS_MIN} metre"
	return {"center": {"latitude": lat, "longitude": lng}, "radius": rad}, None


def _normalize_place(place):
	location = place.get("location") or {}
	opening_hours = place.get("currentOpeningHours") or {}
	return {
		"place_id": place.get("id", ""),
		"name": (place.get("displayName") or {}).get("text", ""),
		"address": place.get("formattedAddress", ""),
		"primary_type": place.get("primaryType"),
		"types": place.get("types", []),
		"rating": place.get("rating"),
		"user_rating_count": place.get("userRatingCount"),
		"price_level": place.get("priceLevel"),
		"latitude": location.get("latitude"),
		"longitude": location.get("longitude"),
		"google_maps_uri": place.get("googleMapsUri"),
		"business_status": place.get("businessStatus"),
		"open_now": opening_hours.get("openNow"),
	}


def _is_country_prediction(place_prediction):
	"""True if an autocomplete placePrediction is a country-level place."""
	types = place_prediction.get("types")
	return place_prediction.get("primaryType") == "country" or (
		isinstance(types, list) and "country" in types
	)


def _cache_get(cache_key):
	if not _cache_enabled():
		return None
	try:
		return frappe.cache().get_value(cache_key)
	except Exception:
		# Cache read failure is non-fatal; proceed to live API call
		return None


def _cache_set(cache_key, value):
	if not _cache_enabled():
		return
	ttl = _cache_ttl()
	if ttl <= 0:
		return
	try:
		frappe.cache().set_value(cache_key, value, expires_in_sec=ttl)
	except Exception:
		# Cache write failure is non-fatal
		pass


def handle_gplaces_text_search(**kwargs):
	"""Search for places with a free-text query using the Google Places API (New)."""
	try:
		query = (kwargs.get("query") or "").strip()
		if not query:
			return json.dumps({"success": False, "error": "query is required"})

		body = {"textQuery": query}

		if kwargs.get("language_code"):
			body["languageCode"] = kwargs["language_code"]
		if kwargs.get("region_code"):
			body["regionCode"] = kwargs["region_code"]
		if kwargs.get("included_type"):
			body["includedType"] = kwargs["included_type"]

		if kwargs.get("min_rating") is not None:
			min_rating = _as_float(kwargs["min_rating"])
			if min_rating is None or not (0.0 <= min_rating <= 5.0):
				return json.dumps({"success": False, "error": "min_rating must be a number between 0 and 5"})
			body["minRating"] = min_rating

		price_levels = _as_csv(kwargs.get("price_levels"))
		if price_levels:
			body["priceLevels"] = price_levels

		if kwargs.get("open_now") is not None:
			body["openNow"] = _as_bool(kwargs["open_now"])

		if kwargs.get("rank_preference"):
			rank = str(kwargs["rank_preference"]).upper()
			if rank not in ("RELEVANCE", "DISTANCE"):
				return json.dumps(
					{"success": False, "error": "rank_preference must be RELEVANCE or DISTANCE"}
				)
			body["rankPreference"] = rank

		page_size = kwargs.get("page_size")
		if page_size is None:
			body["pageSize"] = 10
		else:
			page_size = _as_int(page_size)
			if page_size is None or not (1 <= page_size <= 20):
				return json.dumps(
					{"success": False, "error": "page_size must be an integer between 1 and 20"}
				)
			body["pageSize"] = page_size

		if kwargs.get("page_token"):
			body["pageToken"] = kwargs["page_token"]

		if kwargs.get("latitude") is not None or kwargs.get("longitude") is not None:
			circle, error = _build_circle(
				kwargs.get("latitude"), kwargs.get("longitude"), kwargs.get("radius")
			)
			if error:
				return json.dumps({"success": False, "error": error})
			key = "locationRestriction" if _as_bool(kwargs.get("strict_location")) else "locationBias"
			body[key] = {"circle": circle}

		data, error = _post("places:searchText", body, SEARCH_FIELD_MASK)
		if error:
			update_last_error(SERVICE_NAME, error)
			return json.dumps({"success": False, "error": error})

		places = [_normalize_place(p) for p in data.get("places", [])]
		return json.dumps({"success": True, "places": places, "next_page_token": data.get("nextPageToken")})
	except Exception as e:
		logger.warning(f"Google Places Error (Text Search): {e}")
		update_last_error(SERVICE_NAME, str(e))
		return json.dumps({"success": False, "error": str(e)})


def handle_gplaces_place_details(**kwargs):
	"""Fetch full details for a single place by place_id."""
	try:
		place_id = (kwargs.get("place_id") or "").strip()
		if not place_id:
			return json.dumps({"success": False, "error": "place_id is required"})

		params = {}
		if kwargs.get("language_code"):
			params["languageCode"] = kwargs["language_code"]
		if kwargs.get("region_code"):
			params["regionCode"] = kwargs["region_code"]

		resp = requests.get(
			f"{BASE_URL}/places/{place_id}",
			headers={"X-Goog-Api-Key": _key(), "X-Goog-FieldMask": DETAILS_FIELD_MASK},
			params=params or None,
			timeout=_request_timeout(),
		)
		if not resp.ok:
			error = _request_error(resp)
			update_last_error(SERVICE_NAME, error)
			return json.dumps({"success": False, "error": error})

		p = resp.json()
		location = p.get("location") or {}
		opening_hours = p.get("regularOpeningHours") or {}
		photos = [
			{
				"name": photo.get("name"),
				"width_px": photo.get("widthPx"),
				"height_px": photo.get("heightPx"),
				"author": ((photo.get("authorAttributions") or [{}])[0]).get("displayName"),
			}
			for photo in p.get("photos", [])
		]
		reviews = []
		for review in p.get("reviews", [])[:5]:
			text = review.get("text") or {}
			reviews.append(
				{
					"review_id": review.get("name"),
					"author": (review.get("authorAttribution") or {}).get("displayName"),
					"rating": review.get("rating"),
					"text": text.get("text"),
					"language": text.get("languageCode"),
					"publish_time": review.get("publishTime"),
					"relative_time": review.get("relativePublishTimeDescription"),
					"google_maps_uri": review.get("googleMapsUri"),
				}
			)
		review_summary = (p.get("reviewSummary") or {}).get("text") or {}
		editorial_summary = (p.get("editorialSummary") or {}).get("text") or {}

		return json.dumps(
			{
				"success": True,
				"place": {
					"place_id": p.get("id", ""),
					"name": (p.get("displayName") or {}).get("text", ""),
					"address": p.get("formattedAddress", ""),
					"primary_type": p.get("primaryType"),
					"types": p.get("types", []),
					"rating": p.get("rating"),
					"user_rating_count": p.get("userRatingCount"),
					"price_level": p.get("priceLevel"),
					"latitude": location.get("latitude"),
					"longitude": location.get("longitude"),
					"google_maps_uri": p.get("googleMapsUri"),
					"business_status": p.get("businessStatus"),
					"phone": p.get("internationalPhoneNumber"),
					"website": p.get("websiteUri"),
					"opening_hours": opening_hours.get("weekdayDescriptions", []),
					"photos": photos,
					"reviews": reviews,
					"review_summary": review_summary.get("text"),
					"editorial_summary": editorial_summary.get("text"),
					"accessibility_options": p.get("accessibilityOptions"),
					"payment_options": p.get("paymentOptions"),
					"parking_options": p.get("parkingOptions"),
				},
			}
		)
	except Exception as e:
		logger.warning(f"Google Places Error (Place Details): {e}")
		update_last_error(SERVICE_NAME, str(e))
		return json.dumps({"success": False, "error": str(e)})


def handle_gplaces_place_photo(**kwargs):
	"""Resolve a Places photo resource name to a usable photo URL."""
	try:
		photo_name = (kwargs.get("photo_name") or "").strip()
		if not photo_name:
			return json.dumps({"success": False, "error": "photo_name is required"})

		max_height = _as_int(kwargs.get("max_height_px")) or _cfg("places_photo_max_px", 800, int)
		max_width = _as_int(kwargs.get("max_width_px")) or _cfg("places_photo_max_px", 800, int)
		skip_redirect = kwargs.get("skip_http_redirect")
		skip_redirect = True if skip_redirect is None else _as_bool(skip_redirect)

		url = f"{BASE_URL}/{photo_name}/media"
		headers = {"X-Goog-Api-Key": _key()}
		params = {"maxHeightPx": max_height, "maxWidthPx": max_width}
		timeout = _request_timeout()

		if skip_redirect:
			# skipHttpRedirect returns a JSON body with a pre-signed photoUri
			params["skipHttpRedirect"] = "true"
			resp = requests.get(url, headers=headers, params=params, timeout=timeout)
			if not resp.ok:
				error = _request_error(resp)
				update_last_error(SERVICE_NAME, error)
				return json.dumps({"success": False, "error": error})
			photo_url = resp.json().get("photoUri")
		else:
			# Manually capture the redirect to the actual image CDN URL
			resp = requests.get(url, headers=headers, params=params, timeout=timeout, allow_redirects=False)
			if resp.status_code in (301, 302, 303, 307, 308):
				photo_url = resp.headers.get("Location")
			elif resp.ok:
				photo_url = resp.url
			else:
				error = _request_error(resp)
				update_last_error(SERVICE_NAME, error)
				return json.dumps({"success": False, "error": error})

		if not photo_url:
			error = "Google Places API did not return a photo URL"
			update_last_error(SERVICE_NAME, error)
			return json.dumps({"success": False, "error": error})

		return json.dumps({"success": True, "photo_url": photo_url})
	except Exception as e:
		logger.warning(f"Google Places Error (Place Photo): {e}")
		update_last_error(SERVICE_NAME, str(e))
		return json.dumps({"success": False, "error": str(e)})


def handle_gplaces_autocomplete(**kwargs):
	"""Fetch place autocomplete suggestions, cached in Redis for 24 hours."""
	try:
		input_text = kwargs.get("input")
		if not input_text or not isinstance(input_text, str):
			return json.dumps({"success": False, "error": "input is required"})
		input_text = input_text.strip()
		if not input_text:
			return json.dumps({"success": False, "error": "input is required"})
		if len(input_text) > _MAX_INPUT_LENGTH:
			return json.dumps(
				{
					"success": False,
					"error": f"input exceeds the maximum length of {_MAX_INPUT_LENGTH} characters",
				}
			)

		primary_types = (
			_as_csv(kwargs.get("included_primary_types"))
			or _as_csv(_cfg("places_autocomplete_primary_types", None))
			or _as_csv(_DEFAULT_INCLUDED_PRIMARY_TYPES_CSV)
		)
		language_code = kwargs.get("language_code")
		region_code = kwargs.get("region_code")

		circle = None
		if kwargs.get("latitude") is not None or kwargs.get("longitude") is not None:
			circle, error = _build_circle(
				kwargs.get("latitude"), kwargs.get("longitude"), kwargs.get("radius")
			)
			if error:
				return json.dumps({"success": False, "error": error})

		origin = None
		if kwargs.get("origin_latitude") is not None or kwargs.get("origin_longitude") is not None:
			origin_lat = _as_float(kwargs.get("origin_latitude"))
			origin_lng = _as_float(kwargs.get("origin_longitude"))
			if origin_lat is None or origin_lng is None:
				return json.dumps(
					{"success": False, "error": "origin_latitude and origin_longitude must be numeric"}
				)
			if not (_LATITUDE_MIN <= origin_lat <= _LATITUDE_MAX):
				return json.dumps(
					{
						"success": False,
						"error": f"origin_latitude must be between {_LATITUDE_MIN} and {_LATITUDE_MAX}",
					}
				)
			if not (_LONGITUDE_MIN <= origin_lng <= _LONGITUDE_MAX):
				return json.dumps(
					{
						"success": False,
						"error": f"origin_longitude must be between {_LONGITUDE_MIN} and {_LONGITUDE_MAX}",
					}
				)
			origin = {"latitude": origin_lat, "longitude": origin_lng}

		# Cache key covers every input that changes the result set
		key_parts = [input_text.lower(), ",".join(primary_types)]
		if language_code:
			key_parts.append(str(language_code))
		if region_code:
			key_parts.append(str(region_code))
		if circle:
			key_parts.extend(
				[str(circle["center"]["latitude"]), str(circle["center"]["longitude"]), str(circle["radius"])]
			)
		cache_key = "place_suggestions::" + "::".join(key_parts)

		cached = _cache_get(cache_key)
		if cached is not None:
			# Re-apply the country filter in case the cache predates it
			if isinstance(cached, dict) and isinstance(cached.get("suggestions"), list):
				cached = {**cached, "cached": True}
				return json.dumps(cached)
			return json.dumps({"success": True, "suggestions": [], "cached": True})

		body = {"input": input_text, "includedPrimaryTypes": primary_types}
		if language_code:
			body["languageCode"] = language_code
		if region_code:
			body["regionCode"] = region_code
		if kwargs.get("session_token"):
			body["sessionToken"] = kwargs["session_token"]
		if kwargs.get("include_query_predictions") is not None:
			body["includeQueryPredictions"] = _as_bool(kwargs["include_query_predictions"])
		if circle:
			key = "locationRestriction" if _as_bool(kwargs.get("strict_location")) else "locationBias"
			body[key] = {"circle": circle}
		if origin:
			body["origin"] = origin

		data, error = _post("places:autocomplete", body, timeout=_request_timeout(autocomplete=True))
		if error:
			update_last_error(SERVICE_NAME, error)
			return json.dumps({"success": False, "error": error})

		# Defensive post-filter: drop country-level results the API may return
		# despite includedPrimaryTypes (e.g., due to API changes).
		suggestions = []
		for suggestion in data.get("suggestions", []):
			prediction = suggestion.get("placePrediction") if isinstance(suggestion, dict) else None
			if not isinstance(prediction, dict) or _is_country_prediction(prediction):
				continue
			item = {
				"place_id": prediction.get("placeId"),
				"text": (prediction.get("text") or {}).get("text", ""),
				"primary_type": prediction.get("primaryType"),
				"types": prediction.get("types", []),
			}
			if prediction.get("distanceMeters") is not None:
				item["distance_meters"] = prediction.get("distanceMeters")
			suggestions.append(item)

		result = {"success": True, "suggestions": suggestions, "cached": False}
		_cache_set(cache_key, result)
		return json.dumps(result)
	except Exception as e:
		logger.warning(f"Google Places Error (Autocomplete): {e}")
		update_last_error(SERVICE_NAME, str(e))
		return json.dumps({"success": False, "error": str(e)})


def handle_gplaces_nearby_search(**kwargs):
	"""Search for places near a location using the Google Places API (New)."""
	try:
		if kwargs.get("latitude") is None or kwargs.get("longitude") is None:
			return json.dumps({"success": False, "error": "latitude and longitude are required"})

		circle, error = _build_circle(kwargs.get("latitude"), kwargs.get("longitude"), kwargs.get("radius"))
		if error:
			return json.dumps({"success": False, "error": error})

		body = {"locationRestriction": {"circle": circle}}

		for kwarg, field in (
			("included_types", "includedTypes"),
			("excluded_types", "excludedTypes"),
			("included_primary_types", "includedPrimaryTypes"),
			("excluded_primary_types", "excludedPrimaryTypes"),
		):
			values = _as_csv(kwargs.get(kwarg))
			if values:
				body[field] = values

		max_results = kwargs.get("max_result_count")
		if max_results is None:
			body["maxResultCount"] = 10
		else:
			max_results = _as_int(max_results)
			if max_results is None or not (1 <= max_results <= 20):
				return json.dumps(
					{"success": False, "error": "max_result_count must be an integer between 1 and 20"}
				)
			body["maxResultCount"] = max_results

		if kwargs.get("language_code"):
			body["languageCode"] = kwargs["language_code"]
		if kwargs.get("region_code"):
			body["regionCode"] = kwargs["region_code"]

		if kwargs.get("rank_preference"):
			rank = str(kwargs["rank_preference"]).upper()
			if rank not in ("POPULARITY", "DISTANCE"):
				return json.dumps(
					{"success": False, "error": "rank_preference must be POPULARITY or DISTANCE"}
				)
			body["rankPreference"] = rank

		data, error = _post("places:searchNearby", body, SEARCH_FIELD_MASK)
		if error:
			update_last_error(SERVICE_NAME, error)
			return json.dumps({"success": False, "error": error})

		places = [_normalize_place(p) for p in data.get("places", [])]
		return json.dumps({"success": True, "places": places})
	except Exception as e:
		logger.warning(f"Google Places Error (Nearby Search): {e}")
		update_last_error(SERVICE_NAME, str(e))
		return json.dumps({"success": False, "error": str(e)})
