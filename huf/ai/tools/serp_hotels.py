"""SerpApi Google Hotels tools: search, details, and batch details."""

import concurrent.futures
import json

import frappe

from huf.ai.tools import serp_common
from huf.ai.tools.credentials import update_last_error
from huf.ai.tools.serp_common import SerpValidationError, _as_bool, _as_csv, _as_int, _safe_float

logger = frappe.logger("huf")

SERVICE_NAME = serp_common.SERVICE_NAME

# SerpApi Google Hotels filter value reference:
# rating:      7 (3.5+), 8 (4.0+), 9 (4.5+)
# sort_by:     3 (lowest price), 8 (highest rating), 13 (most reviewed); else relevance
# hotel_class: 2, 3, 4, 5 (star ratings; comma-separated)
VALID_RATINGS = (7, 8, 9)
VALID_SORT_BY = (3, 8, 13)
VALID_HOTEL_CLASS = (2, 3, 4, 5)


def _extract_lowest_price(prop: dict) -> float:
	for path_fn in (
		lambda p: p.get("rate_per_night", {}).get("extracted_lowest"),
		lambda p: p.get("rate_per_night", {}).get("lowest"),
		lambda p: p.get("total_rate", {}).get("extracted_lowest"),
		lambda p: p.get("total_rate", {}).get("lowest"),
	):
		raw = None
		try:
			raw = path_fn(prop)
		except (TypeError, AttributeError):
			continue
		if raw is None:
			continue
		val = _safe_float(raw)
		if val:
			return val
		cleaned = str(raw).replace(",", "").strip()
		numeric = ""
		for char in cleaned:
			if char.isdigit() or char == ".":
				numeric += char
			elif numeric:
				break
		if numeric:
			try:
				return float(numeric)
			except ValueError:
				continue
	return 0.0


def _normalize_property(prop: dict) -> dict:
	gps = prop.get("gps_coordinates") or {}

	images = []
	for img in prop.get("images") or []:
		if isinstance(img, dict):
			images.append(
				{
					"thumbnail": str(img.get("thumbnail", "")),
					"original_image": str(img.get("original_image", "")),
				}
			)
		elif isinstance(img, str):
			images.append({"thumbnail": img, "original_image": img})

	nearby = []
	for place in prop.get("nearby_places") or []:
		if isinstance(place, dict):
			nearby.append({"name": str(place.get("name", ""))})
		elif isinstance(place, str):
			nearby.append({"name": place})

	amenities = [a for a in (prop.get("amenities") or []) if isinstance(a, str)]

	return {
		"type": str(prop.get("type", "")),
		"name": str(prop.get("name", "")),
		"description": str(prop.get("description", "")),
		"property_token": str(prop.get("property_token", "")),
		"hotel_class": str(prop.get("extracted_hotel_class") or prop.get("hotel_class") or ""),
		"overall_rating": _safe_float(prop.get("overall_rating")),
		"reviews": _safe_float(prop.get("reviews")),
		"lowest_price": _extract_lowest_price(prop),
		"free_cancellation": bool(prop.get("free_cancellation")),
		"gps_coordinates": {
			"latitude": _safe_float(gps.get("latitude")),
			"longitude": _safe_float(gps.get("longitude")),
		},
		"images": images,
		"nearby_places": nearby,
		"amenities": amenities,
	}


def _search_hotels(
	q: str,
	check_in_date: str,
	check_out_date: str,
	adults=2,
	children=None,
	children_ages=None,
	currency: str = "INR",
	gl: str = "in",
	hl: str = "en",
	sort_by=None,
	min_price=None,
	max_price=None,
	rating=None,
	hotel_class=None,
	property_types=None,
	amenities=None,
	brands=None,
	free_cancellation=False,
	special_offers=False,
	eco_certified=False,
	vacation_rentals=False,
	bedrooms=None,
	bathrooms=None,
	next_page_token=None,
) -> dict:
	"""Search hotels on the SerpApi Google Hotels engine with the full filter set."""
	if not q or not str(q).strip():
		raise SerpValidationError("q is required.")
	if not check_in_date or not check_out_date:
		raise SerpValidationError("Both check_in_date and check_out_date are required.")

	# numeric guests / budget
	adults_int = _as_int(adults, "adults")
	if adults_int is None:
		adults_int = 2
	if adults_int < 1:
		raise SerpValidationError("At least 1 adult is required.")
	children_int = _as_int(children, "children")
	min_price_int = _as_int(min_price, "min_price")
	max_price_int = _as_int(max_price, "max_price")
	bedrooms_int = _as_int(bedrooms, "bedrooms")
	bathrooms_int = _as_int(bathrooms, "bathrooms")

	if min_price_int is not None and min_price_int < 0:
		raise SerpValidationError("min_price cannot be negative.")
	if max_price_int is not None and max_price_int < 0:
		raise SerpValidationError("max_price cannot be negative.")
	if min_price_int is not None and max_price_int is not None and min_price_int > max_price_int:
		raise SerpValidationError("min_price cannot be greater than max_price.")

	# rating
	rating_int = _as_int(rating, "rating")
	if rating_int is not None and rating_int not in VALID_RATINGS:
		raise SerpValidationError(f"Invalid rating '{rating_int}'. Must be 7 (3.5+), 8 (4.0+), or 9 (4.5+).")

	# sort_by
	sort_by_int = _as_int(sort_by, "sort_by")
	if sort_by_int is not None and sort_by_int not in VALID_SORT_BY:
		raise SerpValidationError(
			f"Invalid sort_by '{sort_by_int}'. Must be 3 (lowest price), "
			"8 (highest rating), or 13 (most reviewed)."
		)

	# hotel_class — validate each value
	hotel_class_csv = _as_csv(hotel_class)
	if hotel_class_csv:
		for part in hotel_class_csv.split(","):
			try:
				hotel_class_int = int(part)
			except (TypeError, ValueError):
				raise SerpValidationError(f"Invalid hotel_class '{part}'. Allowed: 2, 3, 4, 5.")
			if hotel_class_int not in VALID_HOTEL_CLASS:
				raise SerpValidationError(f"Invalid hotel_class '{part}'. Allowed: 2, 3, 4, 5.")

	children_ages_csv = _as_csv(children_ages)
	property_types_csv = _as_csv(property_types)
	amenities_csv = _as_csv(amenities)
	brands_csv = _as_csv(brands)

	is_vacation = _as_bool(vacation_rentals)

	params = {
		"engine": "google_hotels",
		"q": str(q).strip(),
		"gl": gl,
		"hl": hl,
		"check_in_date": check_in_date,
		"check_out_date": check_out_date,
		"currency": currency,
		"adults": adults_int,
	}

	# optional numeric / list filters — only sent when provided
	if children_int is not None:
		params["children"] = children_int
	if children_ages_csv:
		params["children_ages"] = children_ages_csv
	if sort_by_int is not None:
		params["sort_by"] = sort_by_int
	if min_price_int is not None:
		params["min_price"] = min_price_int
	if max_price_int is not None:
		params["max_price"] = max_price_int
	if rating_int is not None:
		params["rating"] = rating_int
	if hotel_class_csv:
		params["hotel_class"] = hotel_class_csv
	if property_types_csv:
		params["property_types"] = property_types_csv
	if amenities_csv:
		params["amenities"] = amenities_csv

	# boolean toggles — SerpApi expects the param present and "true"
	if _as_bool(free_cancellation):
		params["free_cancellation"] = "true"
	if _as_bool(special_offers):
		params["special_offers"] = "true"
	if _as_bool(eco_certified):
		params["eco_certified"] = "true"

	if is_vacation:
		params["vacation_rentals"] = "true"
		if bedrooms_int is not None:
			params["bedrooms"] = bedrooms_int
		if bathrooms_int is not None:
			params["bathrooms"] = bathrooms_int
	elif brands_csv:
		# brands are not supported for vacation rentals
		params["brands"] = brands_csv

	if next_page_token:
		params["next_page_token"] = next_page_token

	results = serp_common._search(params)

	properties = [_normalize_property(p) for p in results.get("properties", [])]
	# A specific-hotel query (e.g. an exact hotel name) makes Google Hotels resolve
	# directly to one property at the top level instead of a `properties` array.
	if not properties and results.get("property_token"):
		properties = [_normalize_property(results)]
	next_token = results.get("serpapi_pagination", {}).get("next_page_token") or None

	applied = {k: v for k, v in params.items() if k != "engine"}
	return {
		"properties": properties,
		"next_page_token": next_token,
		"search_query": params["q"],
		"applied_filters": applied,
	}


def handle_serp_hotel_search(**kwargs) -> str:
	"""Search hotels with the full Google Hotels filter set."""
	try:
		result = _search_hotels(
			q=kwargs.get("q"),
			check_in_date=kwargs.get("check_in_date"),
			check_out_date=kwargs.get("check_out_date"),
			adults=kwargs.get("adults", 2),
			children=kwargs.get("children"),
			children_ages=kwargs.get("children_ages"),
			currency=kwargs.get("currency", "INR"),
			gl=kwargs.get("gl", "in"),
			hl=kwargs.get("hl", "en"),
			sort_by=kwargs.get("sort_by"),
			min_price=kwargs.get("min_price"),
			max_price=kwargs.get("max_price"),
			rating=kwargs.get("rating"),
			hotel_class=kwargs.get("hotel_class"),
			property_types=kwargs.get("property_types"),
			amenities=kwargs.get("amenities"),
			brands=kwargs.get("brands"),
			free_cancellation=kwargs.get("free_cancellation", False),
			special_offers=kwargs.get("special_offers", False),
			eco_certified=kwargs.get("eco_certified", False),
			vacation_rentals=kwargs.get("vacation_rentals", False),
			bedrooms=kwargs.get("bedrooms"),
			bathrooms=kwargs.get("bathrooms"),
			next_page_token=kwargs.get("next_page_token"),
		)
		return json.dumps({"success": True, **result})
	except SerpValidationError as e:
		return json.dumps({"success": False, "error": str(e)})
	except Exception as e:
		logger.warning(f"SerpApi Error (Hotel Search): {e!s}")
		update_last_error(SERVICE_NAME, str(e))
		return json.dumps({"success": False, "error": str(e)})


def _normalize_featured_prices(result: dict) -> list:
	"""Per-OTA rates (Booking.com, Agoda, etc.) for the requested stay."""
	prices = []
	for src in result.get("prices") or []:
		if not isinstance(src, dict):
			continue
		prices.append(
			{
				"source": str(src.get("source", "")),
				"logo": str(src.get("logo", "")),
				"link": str(src.get("link", "")),
				"rate_per_night": _safe_float((src.get("rate_per_night") or {}).get("extracted_lowest")),
				"total_rate": _safe_float((src.get("total_rate") or {}).get("extracted_lowest")),
			}
		)
	return prices


def _normalize_images(result: dict) -> list:
	images = []
	for img in result.get("images") or []:
		if isinstance(img, dict):
			images.append(
				{
					"thumbnail": str(img.get("thumbnail", "")),
					"original_image": str(img.get("original_image", "")),
				}
			)
		elif isinstance(img, str):
			images.append({"thumbnail": img, "original_image": img})
	return images


def _normalize_reviews_breakdown(result: dict) -> list:
	breakdown = []
	for row in result.get("reviews_breakdown") or []:
		if isinstance(row, dict):
			breakdown.append(
				{
					"name": str(row.get("name", "")),
					"description": str(row.get("description", "")),
					"total_mentioned": _safe_float(row.get("total_mentioned")),
					"positive": _safe_float(row.get("positive")),
					"negative": _safe_float(row.get("negative")),
					"neutral": _safe_float(row.get("neutral")),
				}
			)
	return breakdown


def _coerce_adults(adults) -> int:
	adults_int = _as_int(adults, "adults")
	if adults_int is None:
		adults_int = 2
	if adults_int < 1:
		raise SerpValidationError("At least 1 adult is required.")
	return adults_int


def _hotel_details(
	property_token: str,
	check_in_date: str,
	check_out_date: str,
	q: str | None = None,
	adults=2,
	currency: str = "INR",
	gl: str = "in",
	hl: str = "en",
	api_key: str | None = None,
) -> dict:
	"""Fetch full details for a single hotel from the SerpApi Google Hotels engine."""
	if not property_token or not str(property_token).strip():
		raise SerpValidationError("property_token is required.")
	if not check_in_date or not check_out_date:
		raise SerpValidationError("Both check_in_date and check_out_date are required.")

	result = serp_common._search(
		{
			"engine": "google_hotels",
			"q": str(q).strip() if q and str(q).strip() else "Hotels",
			"hl": hl,
			"gl": gl,
			"property_token": str(property_token).strip(),
			"check_in_date": check_in_date,
			"check_out_date": check_out_date,
			"adults": _coerce_adults(adults),
			"currency": currency,
		},
		api_key=api_key,
	)

	prices = _normalize_featured_prices(result)
	rate_candidates = [p["rate_per_night"] for p in prices if p["rate_per_night"] > 0]
	lowest_rate = (
		min(rate_candidates)
		if rate_candidates
		else _safe_float((result.get("rate_per_night") or {}).get("extracted_lowest"))
	)

	gps = result.get("gps_coordinates") or {}
	address = result.get("address")
	if isinstance(address, list):
		address = ", ".join(str(part) for part in address if part)

	amenities = [str(a) for a in (result.get("amenities") or []) if isinstance(a, str)]

	nearby = []
	for place in result.get("nearby_places") or []:
		if isinstance(place, dict):
			nearby.append({"name": str(place.get("name", ""))})
		elif isinstance(place, str):
			nearby.append({"name": place})

	return {
		"name": str(result.get("name", "")),
		"type": str(result.get("type", "")),
		"description": str(result.get("description", "")),
		"property_token": str(property_token).strip(),
		"hotel_class": str(result.get("extracted_hotel_class") or result.get("hotel_class") or ""),
		"overall_rating": _safe_float(result.get("overall_rating")),
		"reviews": _safe_float(result.get("reviews")),
		"link": str(result.get("link", "")),
		"check_in_time": str(result.get("check_in_time", "")),
		"check_out_time": str(result.get("check_out_time", "")),
		"gps_coordinates": {
			"latitude": _safe_float(gps.get("latitude")),
			"longitude": _safe_float(gps.get("longitude")),
		},
		"address": str(address or ""),
		"phone": str(result.get("phone", "")),
		"lowest_rate_per_night": lowest_rate,
		"prices": prices,
		"amenities": amenities,
		"images": _normalize_images(result),
		"nearby_places": nearby,
		"reviews_breakdown": _normalize_reviews_breakdown(result),
	}


def handle_serp_hotel_details(**kwargs) -> str:
	"""Fetch full details for one hotel by property_token."""
	try:
		result = _hotel_details(
			property_token=kwargs.get("property_token"),
			check_in_date=kwargs.get("check_in_date"),
			check_out_date=kwargs.get("check_out_date"),
			q=kwargs.get("q"),
			adults=kwargs.get("adults", 2),
			currency=kwargs.get("currency", "INR"),
			gl=kwargs.get("gl", "in"),
			hl=kwargs.get("hl", "en"),
		)
		return json.dumps({"success": True, **result})
	except SerpValidationError as e:
		return json.dumps({"success": False, "error": str(e)})
	except Exception as e:
		logger.warning(f"SerpApi Error (Hotel Details): {e!s}")
		update_last_error(SERVICE_NAME, str(e))
		return json.dumps({"success": False, "error": str(e)})


def _coerce_tokens(property_tokens) -> list:
	"""Accept a list, a JSON array string, or a comma string -> list of tokens."""
	if property_tokens in (None, ""):
		return []
	if isinstance(property_tokens, str):
		raw = property_tokens.strip()
		if raw.startswith("["):
			try:
				property_tokens = json.loads(raw)
			except Exception:
				property_tokens = raw.split(",")
		else:
			property_tokens = raw.split(",")
	if not isinstance(property_tokens, list | tuple):
		property_tokens = [property_tokens]

	seen, tokens = set(), []
	for tok in property_tokens:
		tok = str(tok).strip()
		if tok and tok not in seen:
			seen.add(tok)
			tokens.append(tok)
	return tokens


def handle_serp_hotel_details_batch(**kwargs) -> str:
	"""Fetch details for several hotels in one call, concurrently.

	The SerpApi key is resolved once on the calling thread and reused, since
	worker threads have no Frappe DB context.
	"""
	try:
		tokens = _coerce_tokens(kwargs.get("property_tokens"))
		if not tokens:
			raise SerpValidationError("At least one property_token is required.")
		check_in_date = kwargs.get("check_in_date")
		check_out_date = kwargs.get("check_out_date")
		if not check_in_date or not check_out_date:
			raise SerpValidationError("Both check_in_date and check_out_date are required.")

		max_workers = _as_int(kwargs.get("max_workers"), "max_workers")
		if max_workers is None or max_workers < 1:
			max_workers = 8

		api_key = serp_common.require_credential(SERVICE_NAME, "api_key")

		def _fetch(token):
			return _hotel_details(
				property_token=token,
				check_in_date=check_in_date,
				check_out_date=check_out_date,
				q=kwargs.get("q"),
				adults=kwargs.get("adults", 2),
				currency=kwargs.get("currency", "INR"),
				gl=kwargs.get("gl", "in"),
				hl=kwargs.get("hl", "en"),
				api_key=api_key,
			)

		hotels, errors = [], []
		with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
			future_map = {executor.submit(_fetch, t): t for t in tokens}
			for future in concurrent.futures.as_completed(future_map):
				token = future_map[future]
				try:
					hotels.append(future.result())
				except Exception as exc:
					errors.append({"property_token": token, "error": str(exc)})

		for err in errors:
			logger.warning(f"SerpApi Hotel Details Error ({err['property_token']}): {err['error']}")

		return json.dumps(
			{
				"success": True,
				"hotels": hotels,
				"errors": errors,
				"requested": len(tokens),
				"succeeded": len(hotels),
			}
		)
	except SerpValidationError as e:
		return json.dumps({"success": False, "error": str(e)})
	except Exception as e:
		logger.warning(f"SerpApi Error (Hotel Details Batch): {e!s}")
		update_last_error(SERVICE_NAME, str(e))
		return json.dumps({"success": False, "error": str(e)})
