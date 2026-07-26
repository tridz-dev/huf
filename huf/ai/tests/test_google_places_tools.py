# Copyright (c) 2025, Tridz Technologies Pvt Ltd and Contributors
# See license.txt

"""Tests for the Google Places (New) integration tools.

All HTTP calls and Frappe cache access are mocked — no live API key or
Redis instance is required.
"""

import json
import unittest
from unittest.mock import MagicMock, patch

from huf.ai.tools import google_places
from huf.ai.tools._registry import GOOGLE_PLACES_TOOLS

MODULE = "huf.ai.tools.google_places"

SAMPLE_PLACE = {
	"id": "ChIJN1t_tDeuEmsRUsoyG83frY4",
	"displayName": {"text": "Sample Cafe", "languageCode": "en"},
	"formattedAddress": "1 Test St, Sydney",
	"primaryType": "cafe",
	"types": ["cafe", "food"],
	"rating": 4.5,
	"userRatingCount": 123,
	"priceLevel": "PRICE_LEVEL_MODERATE",
	"location": {"latitude": -33.86, "longitude": 151.20},
	"googleMapsUri": "https://maps.google.com/?cid=1",
	"businessStatus": "OPERATIONAL",
	"currentOpeningHours": {"openNow": True},
}


def _mock_response(payload=None, status_code=200, url="https://places.googleapis.com/v1/x"):
	resp = MagicMock()
	resp.status_code = status_code
	resp.ok = 200 <= status_code < 400
	resp.json.return_value = payload if payload is not None else {}
	resp.text = json.dumps(payload or {})
	resp.url = url
	resp.headers = {}
	return resp


def _result(raw):
	return json.loads(raw)


class TestTextSearch(unittest.TestCase):
	@patch(f"{MODULE}.update_last_error")
	@patch(f"{MODULE}.require_credential", return_value="test-key")
	@patch(f"{MODULE}.requests.post")
	def test_builds_full_request_body(self, mock_post, _cred, _err):
		mock_post.return_value = _mock_response({"places": [SAMPLE_PLACE], "nextPageToken": "tok-2"})

		out = _result(
			google_places.handle_gplaces_text_search(
				query="vegan restaurants",
				language_code="en",
				region_code="us",
				included_type="restaurant",
				min_rating="4.0",
				price_levels="PRICE_LEVEL_INEXPENSIVE, PRICE_LEVEL_MODERATE",
				open_now="true",
				rank_preference="relevance",
				latitude=-33.86,
				longitude=151.20,
				radius="5000",
				page_size="15",
				page_token="tok-1",
			)
		)

		self.assertTrue(out["success"])
		self.assertEqual(out["next_page_token"], "tok-2")
		self.assertEqual(len(out["places"]), 1)
		place = out["places"][0]
		self.assertEqual(place["place_id"], SAMPLE_PLACE["id"])
		self.assertEqual(place["name"], "Sample Cafe")
		self.assertEqual(place["latitude"], -33.86)
		self.assertTrue(place["open_now"])

		_, kwargs = mock_post.call_args
		self.assertEqual(kwargs["json"]["textQuery"], "vegan restaurants")
		body = kwargs["json"]
		self.assertEqual(body["languageCode"], "en")
		self.assertEqual(body["regionCode"], "us")
		self.assertEqual(body["includedType"], "restaurant")
		self.assertEqual(body["minRating"], 4.0)
		self.assertEqual(body["priceLevels"], ["PRICE_LEVEL_INEXPENSIVE", "PRICE_LEVEL_MODERATE"])
		self.assertTrue(body["openNow"])
		self.assertEqual(body["rankPreference"], "RELEVANCE")
		self.assertEqual(body["pageSize"], 15)
		self.assertEqual(body["pageToken"], "tok-1")
		self.assertEqual(
			body["locationBias"]["circle"],
			{"center": {"latitude": -33.86, "longitude": 151.2}, "radius": 5000.0},
		)
		self.assertIn("places.id", kwargs["headers"]["X-Goog-FieldMask"])
		self.assertEqual(kwargs["headers"]["X-Goog-Api-Key"], "test-key")

	@patch(f"{MODULE}.update_last_error")
	@patch(f"{MODULE}.require_credential", return_value="test-key")
	@patch(f"{MODULE}.requests.post")
	def test_strict_location_uses_restriction(self, mock_post, _cred, _err):
		mock_post.return_value = _mock_response({"places": []})

		out = _result(
			google_places.handle_gplaces_text_search(
				query="coffee", latitude=10, longitude=20, strict_location=True
			)
		)

		self.assertTrue(out["success"])
		body = mock_post.call_args.kwargs["json"]
		self.assertIn("locationRestriction", body)
		self.assertNotIn("locationBias", body)
		# default radius applies
		self.assertEqual(body["locationRestriction"]["circle"]["radius"], 50000.0)

	@patch(f"{MODULE}.update_last_error")
	@patch(f"{MODULE}.require_credential", return_value="test-key")
	@patch(f"{MODULE}.requests.post")
	def test_validation_errors(self, mock_post, _cred, _err):
		bad_calls = [
			{},  # missing query
			{"query": "  "},  # blank query
			{"query": "x", "latitude": 91, "longitude": 0},  # latitude out of range
			{"query": "x", "latitude": 0, "longitude": 181},  # longitude out of range
			{"query": "x", "latitude": 0, "longitude": 0, "radius": 0},  # radius below min
			{"query": "x", "latitude": "abc", "longitude": 0},  # non-numeric latitude
			{"query": "x", "rank_preference": "CLOSEST"},  # invalid enum
			{"query": "x", "page_size": 0},  # page_size out of range
			{"query": "x", "page_size": 21},
			{"query": "x", "min_rating": 5.5},  # rating out of range
		]
		for kwargs in bad_calls:
			out = _result(google_places.handle_gplaces_text_search(**kwargs))
			self.assertFalse(out["success"], f"expected failure for {kwargs}")
			self.assertIn("error", out)
		mock_post.assert_not_called()


class TestPlaceDetails(unittest.TestCase):
	@patch(f"{MODULE}.update_last_error")
	@patch(f"{MODULE}.require_credential", return_value="test-key")
	@patch(f"{MODULE}.requests.get")
	def test_normalizes_details(self, mock_get, _cred, _err):
		payload = dict(SAMPLE_PLACE)
		payload["internationalPhoneNumber"] = "+61 2 0000 0000"
		payload["websiteUri"] = "https://sample.cafe"
		payload["regularOpeningHours"] = {"weekdayDescriptions": ["Monday: 9-5"]}
		payload["photos"] = [
			{
				"name": "places/abc/photos/p1",
				"widthPx": 1200,
				"heightPx": 800,
				"authorAttributions": [{"displayName": "Jane"}],
			}
		]
		payload["reviews"] = [
			{
				"name": f"places/abc/reviews/r{i}",
				"authorAttribution": {"displayName": f"Reviewer {i}"},
				"rating": 5,
				"text": {"text": "Great", "languageCode": "en"},
				"publishTime": "2024-01-01T00:00:00Z",
				"relativePublishTimeDescription": "a month ago",
				"googleMapsUri": "https://maps.google.com/review",
			}
			for i in range(7)
		]
		payload["reviewSummary"] = {"text": {"text": "Loved it", "languageCode": "en"}}
		payload["editorialSummary"] = {"text": {"text": "A cozy cafe", "languageCode": "en"}}
		mock_get.return_value = _mock_response(payload)

		out = _result(
			google_places.handle_gplaces_place_details(
				place_id="ChIJN1t_tDeuEmsRUsoyG83frY4", language_code="en", region_code="au"
			)
		)

		self.assertTrue(out["success"])
		place = out["place"]
		self.assertEqual(place["phone"], "+61 2 0000 0000")
		self.assertEqual(place["website"], "https://sample.cafe")
		self.assertEqual(place["opening_hours"], ["Monday: 9-5"])
		self.assertEqual(
			place["photos"],
			[{"name": "places/abc/photos/p1", "width_px": 1200, "height_px": 800, "author": "Jane"}],
		)
		# capped at 5 most relevant reviews
		self.assertEqual(len(place["reviews"]), 5)
		self.assertEqual(place["reviews"][0]["author"], "Reviewer 0")
		self.assertEqual(place["reviews"][0]["relative_time"], "a month ago")
		self.assertEqual(place["review_summary"], "Loved it")
		self.assertEqual(place["editorial_summary"], "A cozy cafe")

		args, kwargs = mock_get.call_args
		self.assertIn("/v1/places/ChIJN1t_tDeuEmsRUsoyG83frY4", args[0])
		self.assertIn("reviews", kwargs["headers"]["X-Goog-FieldMask"])
		self.assertEqual(kwargs["params"], {"languageCode": "en", "regionCode": "au"})

	@patch(f"{MODULE}.requests.get")
	def test_requires_place_id(self, mock_get):
		out = _result(google_places.handle_gplaces_place_details())
		self.assertFalse(out["success"])
		self.assertIn("place_id", out["error"])
		mock_get.assert_not_called()


class TestPlacePhoto(unittest.TestCase):
	@patch(f"{MODULE}.update_last_error")
	@patch(f"{MODULE}.require_credential", return_value="test-key")
	@patch(f"{MODULE}.requests.get")
	def test_skip_http_redirect_returns_photo_uri(self, mock_get, _cred, _err):
		mock_get.return_value = _mock_response(
			{"name": "places/abc/photos/p1", "photoUri": "https://cdn.example.com/photo.jpg"}
		)

		out = _result(google_places.handle_gplaces_place_photo(photo_name="places/abc/photos/p1"))

		self.assertTrue(out["success"])
		self.assertEqual(out["photo_url"], "https://cdn.example.com/photo.jpg")
		_, kwargs = mock_get.call_args
		self.assertEqual(kwargs["params"]["skipHttpRedirect"], "true")
		self.assertEqual(kwargs["params"]["maxHeightPx"], 800)
		self.assertEqual(kwargs["params"]["maxWidthPx"], 800)

	@patch(f"{MODULE}.update_last_error")
	@patch(f"{MODULE}.require_credential", return_value="test-key")
	@patch(f"{MODULE}.requests.get")
	def test_redirect_captures_location_header(self, mock_get, _cred, _err):
		resp = _mock_response(status_code=302)
		resp.headers = {"Location": "https://cdn.example.com/redirected.jpg"}
		mock_get.return_value = resp

		out = _result(
			google_places.handle_gplaces_place_photo(
				photo_name="places/abc/photos/p1",
				max_height_px=400,
				max_width_px=400,
				skip_http_redirect=False,
			)
		)

		self.assertTrue(out["success"])
		self.assertEqual(out["photo_url"], "https://cdn.example.com/redirected.jpg")
		_, kwargs = mock_get.call_args
		self.assertFalse(kwargs["allow_redirects"])
		self.assertNotIn("skipHttpRedirect", kwargs["params"])
		self.assertEqual(kwargs["params"]["maxHeightPx"], 400)

	@patch(f"{MODULE}.requests.get")
	def test_requires_photo_name(self, mock_get):
		out = _result(google_places.handle_gplaces_place_photo())
		self.assertFalse(out["success"])
		self.assertIn("photo_name", out["error"])
		mock_get.assert_not_called()


class TestAutocomplete(unittest.TestCase):
	def _cache(self, get_value=None):
		cache = MagicMock()
		cache.get_value.return_value = get_value
		return cache

	@patch(f"{MODULE}.frappe")
	@patch(f"{MODULE}.update_last_error")
	@patch(f"{MODULE}.require_credential", return_value="test-key")
	@patch(f"{MODULE}.requests.post")
	def test_builds_body_and_filters_countries(self, mock_post, _cred, _err, mock_frappe):
		cache = self._cache()
		mock_frappe.cache.return_value = cache
		mock_post.return_value = _mock_response(
			{
				"suggestions": [
					{
						"placePrediction": {
							"placeId": "p1",
							"text": {"text": "Lisbon, Portugal"},
							"primaryType": "locality",
							"types": ["locality", "political"],
							"distanceMeters": 1200,
						}
					},
					{
						"placePrediction": {
							"placeId": "p2",
							"text": {"text": "Portugal"},
							"primaryType": "country",
							"types": ["country", "political"],
						}
					},
					{"queryPrediction": {"text": {"text": "lisbon airport"}}},
				]
			}
		)

		out = _result(
			google_places.handle_gplaces_autocomplete(
				input="Lisbon",
				latitude=38.72,
				longitude=-9.14,
				radius=10000,
				strict_location=True,
				origin_latitude=38.70,
				origin_longitude=-9.10,
				session_token="sess-1",
				include_query_predictions=True,
			)
		)

		self.assertTrue(out["success"])
		self.assertFalse(out["cached"])
		# country prediction and query prediction are dropped
		self.assertEqual(len(out["suggestions"]), 1)
		suggestion = out["suggestions"][0]
		self.assertEqual(suggestion["place_id"], "p1")
		self.assertEqual(suggestion["text"], "Lisbon, Portugal")
		self.assertEqual(suggestion["distance_meters"], 1200)

		body = mock_post.call_args.kwargs["json"]
		self.assertEqual(body["input"], "Lisbon")
		self.assertEqual(
			body["includedPrimaryTypes"],
			[
				"locality",
				"sublocality",
				"administrative_area_level_1",
				"administrative_area_level_2",
				"neighborhood",
			],
		)
		self.assertIn("locationRestriction", body)
		self.assertEqual(body["origin"], {"latitude": 38.7, "longitude": -9.1})
		self.assertEqual(body["sessionToken"], "sess-1")
		self.assertTrue(body["includeQueryPredictions"])

		# result cached under a place_suggestions:: key for 24h
		cache.set_value.assert_called_once()
		cache_key = cache.set_value.call_args.args[0]
		self.assertTrue(cache_key.startswith("place_suggestions::lisbon"))
		self.assertIn("38.72", cache_key)
		self.assertEqual(cache.set_value.call_args.kwargs["expires_in_sec"], 86400)

	@patch(f"{MODULE}.frappe")
	@patch(f"{MODULE}.update_last_error")
	@patch(f"{MODULE}.require_credential", return_value="test-key")
	@patch(f"{MODULE}.requests.post")
	def test_cache_hit_skips_api_call(self, mock_post, _cred, _err, mock_frappe):
		cached_payload = {
			"success": True,
			"suggestions": [{"place_id": "p1", "text": "Lisbon", "primary_type": "locality", "types": []}],
			"cached": False,
		}
		mock_frappe.cache.return_value = self._cache(get_value=cached_payload)

		out = _result(google_places.handle_gplaces_autocomplete(input="lisbon"))

		self.assertTrue(out["success"])
		self.assertTrue(out["cached"])
		self.assertEqual(out["suggestions"][0]["place_id"], "p1")
		mock_post.assert_not_called()

	@patch(f"{MODULE}.frappe")
	@patch(f"{MODULE}.requests.post")
	def test_validation_errors(self, mock_post, mock_frappe):
		mock_frappe.cache.return_value = self._cache()

		for kwargs in [
			{},  # missing input
			{"input": "   "},  # blank input
			{"input": "x" * 201},  # over 200 chars
			{"input": "x", "latitude": -91, "longitude": 0},  # bad latitude
			{"input": "x", "latitude": 0, "longitude": 0, "radius": -5},  # bad radius
			{"input": "x", "origin_latitude": "north", "origin_longitude": 0},  # bad origin
		]:
			out = _result(google_places.handle_gplaces_autocomplete(**kwargs))
			self.assertFalse(out["success"], f"expected failure for {list(kwargs)}")
			self.assertIn("error", out)
		mock_post.assert_not_called()


class TestNearbySearch(unittest.TestCase):
	@patch(f"{MODULE}.update_last_error")
	@patch(f"{MODULE}.require_credential", return_value="test-key")
	@patch(f"{MODULE}.requests.post")
	def test_builds_full_request_body(self, mock_post, _cred, _err):
		mock_post.return_value = _mock_response({"places": [SAMPLE_PLACE]})

		out = _result(
			google_places.handle_gplaces_nearby_search(
				latitude="-33.86",
				longitude="151.20",
				radius=2000,
				included_types="restaurant, cafe",
				excluded_types=["bar"],
				included_primary_types="restaurant",
				max_result_count="20",
				language_code="en",
				region_code="au",
				rank_preference="distance",
			)
		)

		self.assertTrue(out["success"])
		self.assertEqual(out["places"][0]["place_id"], SAMPLE_PLACE["id"])

		body = mock_post.call_args.kwargs["json"]
		self.assertEqual(
			body["locationRestriction"]["circle"],
			{"center": {"latitude": -33.86, "longitude": 151.2}, "radius": 2000.0},
		)
		self.assertEqual(body["includedTypes"], ["restaurant", "cafe"])
		self.assertEqual(body["excludedTypes"], ["bar"])
		self.assertEqual(body["includedPrimaryTypes"], ["restaurant"])
		self.assertEqual(body["maxResultCount"], 20)
		self.assertEqual(body["rankPreference"], "DISTANCE")
		self.assertEqual(body["languageCode"], "en")

	@patch(f"{MODULE}.requests.post")
	def test_validation_errors(self, mock_post):
		for kwargs in [
			{},  # missing coordinates
			{"latitude": 10},  # missing longitude
			{"latitude": 10, "longitude": 200},  # longitude out of range
			{"latitude": 10, "longitude": 20, "radius": 0},  # radius below min
			{"latitude": 10, "longitude": 20, "rank_preference": "BEST"},  # invalid enum
			{"latitude": 10, "longitude": 20, "max_result_count": 25},  # out of range
		]:
			out = _result(google_places.handle_gplaces_nearby_search(**kwargs))
			self.assertFalse(out["success"], f"expected failure for {kwargs}")
			self.assertIn("error", out)
		mock_post.assert_not_called()


class TestErrorEnvelope(unittest.TestCase):
	@patch(f"{MODULE}.update_last_error")
	@patch(f"{MODULE}.require_credential", return_value="test-key")
	@patch(f"{MODULE}.requests.post")
	def test_api_error_includes_status_and_truncated_message(self, mock_post, _cred, mock_err):
		mock_post.return_value = _mock_response(
			{"error": {"message": "API key not valid. " + "x" * 1000}}, status_code=403
		)

		out = _result(google_places.handle_gplaces_text_search(query="coffee"))

		self.assertFalse(out["success"])
		self.assertIn("403", out["error"])
		self.assertIn("API key not valid", out["error"])
		self.assertLess(len(out["error"]), 600)
		mock_err.assert_called_once()
		self.assertEqual(mock_err.call_args.args[0], "google_maps")

	@patch(f"{MODULE}.update_last_error")
	@patch(f"{MODULE}.require_credential", return_value="test-key")
	@patch(f"{MODULE}.requests.post")
	def test_network_exception_returns_error_envelope(self, mock_post, _cred, mock_err):
		mock_post.side_effect = ConnectionError("dns failure")

		out = _result(google_places.handle_gplaces_text_search(query="coffee"))

		self.assertFalse(out["success"])
		self.assertIn("dns failure", out["error"])
		mock_err.assert_called_once()


class TestRegistry(unittest.TestCase):
	def test_all_five_tools_registered(self):
		expected = {
			"gplaces_text_search": "handle_gplaces_text_search",
			"gplaces_place_details": "handle_gplaces_place_details",
			"gplaces_place_photo": "handle_gplaces_place_photo",
			"gplaces_autocomplete": "handle_gplaces_autocomplete",
			"gplaces_nearby_search": "handle_gplaces_nearby_search",
		}
		by_name = {t["tool_name"]: t for t in GOOGLE_PLACES_TOOLS}
		self.assertEqual(set(by_name), set(expected))
		for tool_name, handler in expected.items():
			tool = by_name[tool_name]
			self.assertEqual(tool["category"], "Google Places")
			self.assertEqual(tool["function_path"], f"huf.ai.tools.google_places.{handler}")
			# handler actually exists and is importable
			self.assertTrue(callable(getattr(google_places, handler)))

	def test_registered_in_all_integration_tools(self):
		from huf.ai.tools._registry import ALL_INTEGRATION_TOOLS

		names = {t["tool_name"] for t in ALL_INTEGRATION_TOOLS}
		for tool in GOOGLE_PLACES_TOOLS:
			self.assertIn(tool["tool_name"], names)


if __name__ == "__main__":
	unittest.main()
