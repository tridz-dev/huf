"""SerpApi review tools: Google Maps, Google Hotels, TripAdvisor, and Yelp."""

import json

import frappe

from huf.ai.tools import serp_common, serp_hotels
from huf.ai.tools.credentials import update_last_error
from huf.ai.tools.serp_common import SerpValidationError, _as_bool, _as_int, _cfg, _safe_float

logger = frappe.logger("huf")

SERVICE_NAME = serp_common.SERVICE_NAME


def _default_currency():
	return _cfg("default_currency", "INR")


def _default_gl():
	return _cfg("default_gl", "in")


def _default_hl():
	return _cfg("default_hl", "en")

# SerpApi Google Maps Reviews sort options
MAPS_REVIEW_SORT_BY = ("qualityScore", "newestFirst", "ratingHigh", "ratingLow")

# SerpApi TripAdvisor Reviews sort options
TRIPADVISOR_SORT_BY = ("most_recent", "detailed_review")

# TripAdvisor Search category filter (ssrc):
# a = All, r = Restaurants, A = ThingsToDo, h = Hotels, g = Destinations, v = Rentals, f = Forums
TRIPADVISOR_SSRC = ("a", "r", "A", "h", "g", "v", "f")

# SerpApi Yelp Reviews sort options
YELP_SORT_BY = (
	"relevance_desc",
	"date_desc",
	"date_asc",
	"rating_desc",
	"rating_asc",
	"elites_desc",
)


# ---------------------------------------------------------------------------
# Google Maps reviews
# ---------------------------------------------------------------------------


def _normalize_maps_review(review: dict) -> dict:
	user = review.get("user") or {}
	return {
		"review_id": str(review.get("review_id", "")),
		"author": str(user.get("name", "")),
		"author_link": str(user.get("link", "")),
		"author_thumbnail": str(user.get("thumbnail", "")),
		"author_reviews_count": _safe_float(user.get("reviews")),
		"rating": _safe_float(review.get("rating")),
		"date": str(review.get("date", "")),
		"iso_date": str(review.get("iso_date", "")),
		"snippet": str(review.get("snippet", "")),
		"likes": _safe_float(review.get("likes")),
		"images": [str(i) for i in (review.get("images") or []) if isinstance(i, str)],
		"response": str((review.get("response") or {}).get("snippet", "")),
	}


def _search_google_maps(q: str, hl: str | None = None, gl: str | None = None) -> dict:
	"""Search Google Maps for a place to obtain its data_id (needed for reviews)."""
	if not q or not str(q).strip():
		raise SerpValidationError("q is required.")

	hl = hl or _default_hl()
	gl = gl or _default_gl()
	results = serp_common._search(
		{"engine": "google_maps", "q": str(q).strip(), "hl": hl, "gl": gl, "type": "search"}
	)

	raw = results.get("local_results") or []
	if not raw and results.get("place_results"):
		raw = [results["place_results"]]

	places = []
	for p in raw:
		if not isinstance(p, dict):
			continue
		gps = p.get("gps_coordinates") or {}
		places.append(
			{
				"data_id": str(p.get("data_id", "")),
				"place_id": str(p.get("place_id", "")),
				"title": str(p.get("title", "")),
				"address": str(p.get("address", "")),
				"rating": _safe_float(p.get("rating")),
				"reviews_count": _safe_float(p.get("reviews")),
				"gps_coordinates": {
					"latitude": _safe_float(gps.get("latitude")),
					"longitude": _safe_float(gps.get("longitude")),
				},
			}
		)
	return {"results": places}


def _google_maps_reviews(
	data_id: str | None = None,
	place_id: str | None = None,
	sort_by: str | None = None,
	hl: str | None = None,
	gl: str | None = None,
	next_page_token: str | None = None,
) -> dict:
	"""Fetch reviews for a place from the SerpApi Google Maps Reviews engine."""
	if not (data_id and str(data_id).strip()) and not (place_id and str(place_id).strip()):
		raise SerpValidationError("Either data_id or place_id is required.")

	hl = hl or _default_hl()
	gl = gl or _default_gl()

	if sort_by and sort_by not in MAPS_REVIEW_SORT_BY:
		raise SerpValidationError(f"Invalid sort_by '{sort_by}'. Allowed: {', '.join(MAPS_REVIEW_SORT_BY)}.")

	params = {"engine": "google_maps_reviews", "hl": hl, "gl": gl}
	if data_id:
		params["data_id"] = str(data_id).strip()
	if place_id:
		params["place_id"] = str(place_id).strip()
	if sort_by:
		params["sort_by"] = sort_by
	if next_page_token:
		params["next_page_token"] = next_page_token

	results = serp_common._search(params)

	place = results.get("place_info") or {}
	reviews = [_normalize_maps_review(r) for r in (results.get("reviews") or [])]
	next_token = results.get("serpapi_pagination", {}).get("next_page_token") or None

	return {
		"place": {
			"title": str(place.get("title", "")),
			"rating": _safe_float(place.get("rating")),
			"reviews_count": _safe_float(place.get("reviews")),
		},
		"reviews": reviews,
		"next_page_token": next_token,
	}


def handle_serp_google_maps_reviews(**kwargs) -> str:
	"""Reviews for a place on Google Maps — single self-contained tool.

	Pass a human-friendly `place_query` (e.g. "Leopold Cafe Mumbai"); the data_id
	is resolved internally via a Google Maps search, then its reviews are fetched.
	If you already have a `data_id`/`place_id`, pass it to skip the search.
	"""
	try:
		place_query = kwargs.get("place_query")
		data_id = kwargs.get("data_id")
		place_id = kwargs.get("place_id")
		hl = kwargs.get("hl") or _default_hl()
		gl = kwargs.get("gl") or _default_gl()

		matched = ""
		has_id = (data_id and str(data_id).strip()) or (place_id and str(place_id).strip())
		if not has_id:
			if not place_query or not str(place_query).strip():
				raise SerpValidationError("Provide place_query (or a data_id/place_id).")
			found = _search_google_maps(q=place_query, hl=hl, gl=gl)
			match = next((r for r in found["results"] if r.get("data_id")), None)
			if not match:
				raise SerpValidationError(f"No Google Maps place found for '{place_query}'.")
			data_id = match["data_id"]
			matched = match["title"]

		result = _google_maps_reviews(
			data_id=data_id,
			place_id=place_id,
			sort_by=kwargs.get("sort_by"),
			hl=hl,
			gl=gl,
			next_page_token=kwargs.get("next_page_token"),
		)
		result["data_id"] = data_id
		result["matched_place"] = matched
		return json.dumps({"success": True, **result})
	except SerpValidationError as e:
		return json.dumps({"success": False, "error": str(e)})
	except Exception as e:
		logger.warning(f"SerpApi Error (Google Maps Reviews): {e!s}")
		update_last_error(SERVICE_NAME, str(e))
		return json.dumps({"success": False, "error": str(e)})


# ---------------------------------------------------------------------------
# Google Hotel reviews
# ---------------------------------------------------------------------------


def _normalize_ratings(result: dict) -> list:
	"""Star distribution, e.g. [{"stars": 5, "count": 800}, ...]."""
	ratings = []
	for row in result.get("ratings") or []:
		if isinstance(row, dict):
			ratings.append(
				{
					"stars": int(_safe_float(row.get("stars"))),
					"count": _safe_float(row.get("count")),
				}
			)
	return ratings


def _google_hotel_reviews(
	property_token: str,
	check_in_date: str,
	check_out_date: str,
	q: str | None = None,
	adults=2,
	currency: str | None = None,
) -> dict:
	"""Fetch the review data for a single hotel from SerpApi Google Hotels."""
	if not property_token or not str(property_token).strip():
		raise SerpValidationError("property_token is required.")
	if not check_in_date or not check_out_date:
		raise SerpValidationError("Both check_in_date and check_out_date are required.")

	currency = currency or _default_currency()

	result = serp_common._search(
		{
			"engine": "google_hotels",
			"q": str(q).strip() if q and str(q).strip() else "Hotels",
			"hl": _default_hl(),
			"gl": _default_gl(),
			"property_token": str(property_token).strip(),
			"check_in_date": check_in_date,
			"check_out_date": check_out_date,
			"adults": serp_hotels._coerce_adults(adults),
			"currency": currency,
		}
	)

	return {
		"name": str(result.get("name", "")),
		"overall_rating": _safe_float(result.get("overall_rating")),
		"reviews_count": _safe_float(result.get("reviews")),
		"ratings": _normalize_ratings(result),
		"reviews_breakdown": serp_hotels._normalize_reviews_breakdown(result),
	}


def handle_serp_google_hotel_reviews(**kwargs) -> str:
	"""Review data for a hotel — single self-contained tool.

	Pass a human-friendly `hotel_query` plus the stay dates; the property_token is
	resolved internally via a Google Hotels search. If you already have a
	`property_token`, pass it to skip the search.
	"""
	try:
		hotel_query = kwargs.get("hotel_query")
		property_token = kwargs.get("property_token")
		check_in_date = kwargs.get("check_in_date")
		check_out_date = kwargs.get("check_out_date")
		adults = kwargs.get("adults", 2)
		currency = kwargs.get("currency") or _default_currency()

		if not check_in_date or not check_out_date:
			raise SerpValidationError("Both check_in_date and check_out_date are required.")

		matched = ""
		if not property_token or not str(property_token).strip():
			if not hotel_query or not str(hotel_query).strip():
				raise SerpValidationError("Provide hotel_query (or a property_token).")
			found = serp_hotels._search_hotels(
				q=hotel_query,
				check_in_date=check_in_date,
				check_out_date=check_out_date,
				adults=adults,
				currency=currency,
			)
			props = [p for p in found.get("properties", []) if p.get("property_token")]
			if not props:
				raise SerpValidationError(f"No hotel found for '{hotel_query}'.")
			property_token = props[0]["property_token"]
			matched = props[0]["name"]

		result = _google_hotel_reviews(
			property_token=property_token,
			check_in_date=check_in_date,
			check_out_date=check_out_date,
			q=hotel_query,
			adults=adults,
			currency=currency,
		)
		result["property_token"] = property_token
		result["matched_hotel"] = matched
		return json.dumps({"success": True, **result})
	except SerpValidationError as e:
		return json.dumps({"success": False, "error": str(e)})
	except Exception as e:
		logger.warning(f"SerpApi Error (Google Hotel Reviews): {e!s}")
		update_last_error(SERVICE_NAME, str(e))
		return json.dumps({"success": False, "error": str(e)})


# ---------------------------------------------------------------------------
# TripAdvisor
# ---------------------------------------------------------------------------


def _normalize_tripadvisor_place(place: dict) -> dict:
	return {
		"place_id": str(place.get("place_id") or place.get("location_id") or ""),
		"title": str(place.get("title", "")),
		"place_type": str(place.get("place_type", "")),
		"link": str(place.get("link", "")),
		"rating": _safe_float(place.get("rating")),
		"reviews_count": _safe_float(place.get("reviews")),
		"location": str(place.get("location", "")),
		"thumbnail": str(place.get("thumbnail", "")),
	}


def _normalize_tripadvisor_review(review: dict) -> dict:
	author = review.get("author") or {}
	trip = review.get("trip_info") or {}
	response = review.get("response") or {}

	additional = []
	for row in review.get("additional_ratings") or []:
		if isinstance(row, dict):
			additional.append(
				{
					"label": str(row.get("label", "")),
					"rating": _safe_float(row.get("rating")),
				}
			)

	return {
		"review_id": str(review.get("review_id", "")),
		"title": str(review.get("title", "")),
		"snippet": str(review.get("snippet", "")),
		"rating": _safe_float(review.get("rating")),
		"date": str(review.get("date", "")),
		"link": str(review.get("link", "")),
		"language": str(review.get("language", "")),
		"trip_type": str(trip.get("type", "")),
		"trip_date": str(trip.get("date", "")),
		"votes": _safe_float(review.get("votes")),
		"images": [str(i) for i in (review.get("images") or []) if isinstance(i, str)],
		"additional_ratings": additional,
		"author": str(author.get("display_name") or author.get("username") or ""),
		"author_contributions": _safe_float(author.get("contributions")),
		"author_hometown": str(author.get("hometown", "")),
		"response": str(response.get("snippet", "")),
	}


def _search_tripadvisor(
	q: str,
	ssrc: str | None = None,
	tripadvisor_domain: str | None = None,
	offset=None,
	limit=None,
) -> dict:
	"""Search TripAdvisor to find a place and its place_id."""
	if not q or not str(q).strip():
		raise SerpValidationError("q is required.")
	if ssrc and ssrc not in TRIPADVISOR_SSRC:
		raise SerpValidationError(f"Invalid ssrc '{ssrc}'. Allowed: {', '.join(TRIPADVISOR_SSRC)}.")

	params = {"engine": "tripadvisor", "q": str(q).strip()}
	if ssrc:
		params["ssrc"] = ssrc
	if tripadvisor_domain:
		params["tripadvisor_domain"] = tripadvisor_domain
	off = _as_int(offset, "offset")
	lim = _as_int(limit, "limit")
	if off is not None:
		params["offset"] = off
	if lim is not None:
		params["limit"] = lim

	results = serp_common._search(params)
	raw = results.get("places") or results.get("locations") or []
	return {"places": [_normalize_tripadvisor_place(p) for p in raw]}


def handle_serp_tripadvisor_search(**kwargs) -> str:
	"""Find a TripAdvisor place (and its place_id)."""
	try:
		result = _search_tripadvisor(
			q=kwargs.get("q"),
			ssrc=kwargs.get("ssrc"),
			tripadvisor_domain=kwargs.get("tripadvisor_domain"),
			offset=kwargs.get("offset"),
			limit=kwargs.get("limit"),
		)
		return json.dumps({"success": True, **result})
	except SerpValidationError as e:
		return json.dumps({"success": False, "error": str(e)})
	except Exception as e:
		logger.warning(f"SerpApi Error (TripAdvisor Search): {e!s}")
		update_last_error(SERVICE_NAME, str(e))
		return json.dumps({"success": False, "error": str(e)})


def _tripadvisor_reviews(
	place_id: str,
	sort_by: str | None = None,
	rating: str | None = None,
	language: str | None = None,
	tripadvisor_domain: str | None = None,
	translate=False,
	offset=None,
	limit=None,
) -> dict:
	"""Fetch reviews for a TripAdvisor place via the tripadvisor_reviews engine."""
	if not place_id or not str(place_id).strip():
		raise SerpValidationError("place_id is required.")
	if sort_by and sort_by not in TRIPADVISOR_SORT_BY:
		raise SerpValidationError(f"Invalid sort_by '{sort_by}'. Allowed: {', '.join(TRIPADVISOR_SORT_BY)}.")

	off = _as_int(offset, "offset") or 0
	lim = _as_int(limit, "limit")
	if lim is not None and (lim < 1 or lim > 20):
		raise SerpValidationError("limit must be between 1 and 20.")

	params = {
		"engine": "tripadvisor_reviews",
		"place_id": str(place_id).strip(),
		"offset": off,
	}
	if sort_by:
		params["sort_by"] = sort_by
	if rating:
		params["rating"] = str(rating).strip()
	if language:
		params["language"] = language
	if tripadvisor_domain:
		params["tripadvisor_domain"] = tripadvisor_domain
	if _as_bool(translate):
		params["translate"] = "true"
	if lim is not None:
		params["limit"] = lim

	results = serp_common._search(params)
	reviews = [_normalize_tripadvisor_review(r) for r in (results.get("reviews") or [])]

	# tripadvisor_reviews paginates by offset; compute the next offset if a
	# "next" page exists.
	next_offset = None
	if results.get("serpapi_pagination", {}).get("next"):
		next_offset = off + (lim or len(reviews) or 10)

	return {"reviews": reviews, "next_offset": next_offset}


def handle_serp_tripadvisor_reviews(**kwargs) -> str:
	"""Reviews for a TripAdvisor place — single self-contained tool.

	Pass a human-friendly `place_query`; the TripAdvisor place_id is resolved
	internally via search, then its reviews are fetched. If you already have a
	`place_id`, pass it to skip the search.
	"""
	try:
		place_query = kwargs.get("place_query")
		place_id = kwargs.get("place_id")

		matched = ""
		if not place_id or not str(place_id).strip():
			if not place_query or not str(place_query).strip():
				raise SerpValidationError("Provide place_query (or a place_id).")
			found = _search_tripadvisor(q=place_query)
			if not found["places"]:
				raise SerpValidationError(f"No TripAdvisor place found for '{place_query}'.")
			top = found["places"][0]
			place_id = top["place_id"]
			matched = top["title"]

		result = _tripadvisor_reviews(
			place_id=place_id,
			sort_by=kwargs.get("sort_by"),
			rating=kwargs.get("rating"),
			language=kwargs.get("language"),
			tripadvisor_domain=kwargs.get("tripadvisor_domain"),
			translate=kwargs.get("translate", False),
			offset=kwargs.get("offset"),
			limit=kwargs.get("limit"),
		)
		result["place_id"] = place_id
		result["matched_place"] = matched
		return json.dumps({"success": True, **result})
	except SerpValidationError as e:
		return json.dumps({"success": False, "error": str(e)})
	except Exception as e:
		logger.warning(f"SerpApi Error (TripAdvisor Reviews): {e!s}")
		update_last_error(SERVICE_NAME, str(e))
		return json.dumps({"success": False, "error": str(e)})


# ---------------------------------------------------------------------------
# Yelp
# ---------------------------------------------------------------------------


def _normalize_yelp_business(biz: dict) -> dict:
	# categories arrive as dicts ({"title": "Pizza", "link": ...}) or plain strings
	categories = []
	for c in biz.get("categories") or []:
		if isinstance(c, dict):
			categories.append(str(c.get("title", "")))
		elif isinstance(c, str):
			categories.append(c)

	return {
		"place_id": str(biz.get("place_ids", [""])[0] if biz.get("place_ids") else biz.get("place_id", "")),
		"title": str(biz.get("title", "")),
		"link": str(biz.get("link", "")),
		"rating": _safe_float(biz.get("rating")),
		"reviews_count": _safe_float(biz.get("reviews")),
		"price": str(biz.get("price", "")),
		"categories": [c for c in categories if c],
		"snippet": str(biz.get("snippet", "")),
		"phone": str(biz.get("phone", "")),
		"address": str(biz.get("neighborhoods", "") or biz.get("address", "")),
		"thumbnail": str(biz.get("thumbnail", "")),
		"reviews_link": str(biz.get("reviews_link", "")),
	}


def _normalize_yelp_review(review: dict) -> dict:
	user = review.get("user") or {}
	comment = review.get("comment") or {}
	return {
		"author": str(user.get("name", "")),
		"author_link": str(user.get("link", "")),
		"author_thumbnail": str(user.get("thumbnail", "")),
		"author_reviews_count": _safe_float(user.get("reviews")),
		"rating": _safe_float(review.get("rating")),
		"date": str(review.get("date", "")),
		"text": str(comment.get("text", "") or review.get("snippet", "")),
		"tags": [str(t) for t in (review.get("tags") or []) if isinstance(t, str)],
	}


def _search_yelp(find_desc: str, find_loc: str, hl: str | None = None, start=None) -> dict:
	"""Find Yelp businesses (to obtain a place_id for reviews)."""
	if not find_desc or not str(find_desc).strip():
		raise SerpValidationError("find_desc is required.")
	if not find_loc or not str(find_loc).strip():
		raise SerpValidationError("find_loc is required.")

	params = {
		"engine": "yelp",
		"find_desc": str(find_desc).strip(),
		"find_loc": str(find_loc).strip(),
		"hl": hl or _default_hl(),
	}
	start_int = _as_int(start, "start")
	if start_int is not None:
		params["start"] = start_int

	results = serp_common._search(params)
	businesses = [_normalize_yelp_business(b) for b in (results.get("organic_results") or [])]
	return {"businesses": businesses}


def handle_serp_yelp_search(**kwargs) -> str:
	"""Find Yelp businesses (and their place_id)."""
	try:
		result = _search_yelp(
			find_desc=kwargs.get("find_desc"),
			find_loc=kwargs.get("find_loc"),
			hl=kwargs.get("hl") or _default_hl(),
			start=kwargs.get("start"),
		)
		return json.dumps({"success": True, **result})
	except SerpValidationError as e:
		return json.dumps({"success": False, "error": str(e)})
	except Exception as e:
		logger.warning(f"SerpApi Error (Yelp Search): {e!s}")
		update_last_error(SERVICE_NAME, str(e))
		return json.dumps({"success": False, "error": str(e)})


def _yelp_reviews(
	place_id: str,
	sort_by: str | None = None,
	start=None,
	num=None,
	hl: str | None = None,
) -> dict:
	"""Fetch reviews for a Yelp business via the SerpApi Yelp Reviews engine."""
	if not place_id or not str(place_id).strip():
		raise SerpValidationError("place_id is required.")
	if sort_by and sort_by not in YELP_SORT_BY:
		raise SerpValidationError(f"Invalid sort_by '{sort_by}'. Allowed: {', '.join(YELP_SORT_BY)}.")

	params = {"engine": "yelp_reviews", "place_id": str(place_id).strip(), "hl": hl or _default_hl()}
	if sort_by:
		# SerpApi quirk: the Yelp Reviews engine takes the sort param as `sortby`
		params["sortby"] = sort_by
	start_int = _as_int(start, "start")
	if start_int is not None:
		params["start"] = start_int
	num_int = _as_int(num, "num")
	if num_int is not None:
		params["num"] = num_int

	results = serp_common._search(params)
	reviews = [_normalize_yelp_review(r) for r in (results.get("reviews") or [])]
	total = _safe_float((results.get("search_information") or {}).get("total_results"))

	return {"reviews": reviews, "total_reviews": total}


def handle_serp_yelp_reviews(**kwargs) -> str:
	"""Reviews for a Yelp business — single self-contained tool.

	Pass a human-friendly `business_name` + `location`; the Yelp place_id is
	resolved internally via search, then its reviews are fetched. If you already
	have a `place_id`, pass it to skip the search.
	"""
	try:
		business_name = kwargs.get("business_name")
		location = kwargs.get("location")
		place_id = kwargs.get("place_id")
		hl = kwargs.get("hl") or _default_hl()

		matched = ""
		if not place_id or not str(place_id).strip():
			if not (business_name and str(business_name).strip() and location and str(location).strip()):
				raise SerpValidationError("Provide business_name and location (or a place_id).")
			found = _search_yelp(find_desc=business_name, find_loc=location, hl=hl)
			if not found["businesses"]:
				raise SerpValidationError(f"No Yelp business found for '{business_name}' in '{location}'.")
			top = found["businesses"][0]
			place_id = top["place_id"]
			matched = top["title"]

		result = _yelp_reviews(
			place_id=place_id,
			sort_by=kwargs.get("sort_by"),
			start=kwargs.get("start"),
			num=kwargs.get("num"),
			hl=hl,
		)
		result["place_id"] = place_id
		result["matched_business"] = matched
		return json.dumps({"success": True, **result})
	except SerpValidationError as e:
		return json.dumps({"success": False, "error": str(e)})
	except Exception as e:
		logger.warning(f"SerpApi Error (Yelp Reviews): {e!s}")
		update_last_error(SERVICE_NAME, str(e))
		return json.dumps({"success": False, "error": str(e)})
