"""Tests for the SerpApi ("SERP") integration tools.

All SerpApi calls are mocked at `huf.ai.tools.serp_common._client`; no live keys
or DB access are required.
"""

import json
import sys
import types
import unittest
from typing import ClassVar
from unittest.mock import MagicMock, patch

from huf.ai.tools import _registry, serp_common, serp_hotels, serp_reviews, serp_youtube
from huf.ai.tools.credentials import _get_alt_env_names
from huf.ai.tools.serp_common import SerpValidationError


class SerpToolTestCase(unittest.TestCase):
	"""Base class wiring a mocked SerpApi client that records search params."""

	def setUp(self):
		self.responses = {}
		self.captured = []
		self.client = MagicMock()
		self.client.search.side_effect = self._record
		patcher = patch("huf.ai.tools.serp_common._client", return_value=self.client)
		self.mock_client_fn = patcher.start()
		self.addCleanup(patcher.stop)

		# _cfg reads optional service defaults; tests use the built-in defaults.
		cfg_patcher = patch(
			"huf.ai.tools.serp_common.get_credential",
			side_effect=lambda service, key, default=None: default,
		)
		cfg_patcher.start()
		self.addCleanup(cfg_patcher.stop)

		# The batch handler resolves the API key once on the calling thread.
		key_patcher = patch(
			"huf.ai.tools.serp_common.require_credential", return_value="test-key"
		)
		key_patcher.start()
		self.addCleanup(key_patcher.stop)

	def _record(self, params):
		params = dict(params)
		self.captured.append(params)
		resp = self.responses[params["engine"]]
		if callable(resp):
			return resp(params)
		if isinstance(resp, Exception):
			raise resp
		return resp


class TestSerpCommonHelpers(unittest.TestCase):
	def test_safe_float(self):
		self.assertEqual(serp_common._safe_float(None), 0.0)
		self.assertEqual(serp_common._safe_float("bad"), 0.0)
		self.assertEqual(serp_common._safe_float("4.5"), 4.5)
		self.assertEqual(serp_common._safe_float(3), 3.0)

	def test_as_int(self):
		self.assertIsNone(serp_common._as_int(None, "x"))
		self.assertIsNone(serp_common._as_int("", "x"))
		self.assertEqual(serp_common._as_int("7", "x"), 7)
		with self.assertRaises(SerpValidationError):
			serp_common._as_int("abc", "x")

	def test_as_bool(self):
		self.assertTrue(serp_common._as_bool(True))
		self.assertFalse(serp_common._as_bool(False))
		for truthy in ("1", "true", "True", "yes", "on", 1):
			self.assertTrue(serp_common._as_bool(truthy))
		for falsy in ("0", "false", "no", "", None, 0):
			self.assertFalse(serp_common._as_bool(falsy))

	def test_as_csv(self):
		self.assertIsNone(serp_common._as_csv(None))
		self.assertIsNone(serp_common._as_csv(""))
		self.assertEqual(serp_common._as_csv("4, 5"), "4,5")
		self.assertEqual(serp_common._as_csv(["4", " 5 ", ""]), "4,5")
		self.assertEqual(serp_common._as_csv(("a", "b")), "a,b")

	def test_client_lazy_import_uses_credential(self):
		fake_serpapi = types.ModuleType("serpapi")
		fake_serpapi.Client = MagicMock()
		with (
			patch("huf.ai.tools.serp_common.require_credential", return_value="KEY-1") as mock_cred,
			patch.dict(sys.modules, {"serpapi": fake_serpapi}),
		):
			serp_common._client()
			fake_serpapi.Client.assert_called_once_with(api_key="KEY-1")
			mock_cred.assert_called_once_with("serpapi", "api_key")

			mock_cred.reset_mock()
			serp_common._client(api_key="EXPLICIT")
			mock_cred.assert_not_called()


class TestHotelSearch(SerpToolTestCase):
	BASE: ClassVar = {
		"q": "Hotels in Bandra Mumbai",
		"check_in_date": "2026-01-10",
		"check_out_date": "2026-01-12",
	}

	def test_full_param_building(self):
		self.responses = {"google_hotels": {"properties": [], "serpapi_pagination": {}}}
		out = json.loads(
			serp_hotels.handle_serp_hotel_search(
				**self.BASE,
				adults=2,
				children=2,
				children_ages="5, 8",
				currency="USD",
				gl="us",
				hl="en",
				sort_by=3,
				min_price=100,
				max_price=500,
				rating=8,
				hotel_class="4,5",
				property_types="12,17",
				amenities="1,2",
				brands="33,44",
				free_cancellation=True,
				special_offers="yes",
				eco_certified=1,
				next_page_token="TOK0",
			)
		)
		self.assertTrue(out["success"])
		expected = {
			"engine": "google_hotels",
			"q": "Hotels in Bandra Mumbai",
			"gl": "us",
			"hl": "en",
			"check_in_date": "2026-01-10",
			"check_out_date": "2026-01-12",
			"currency": "USD",
			"adults": 2,
			"children": 2,
			"children_ages": "5,8",
			"sort_by": 3,
			"min_price": 100,
			"max_price": 500,
			"rating": 8,
			"hotel_class": "4,5",
			"property_types": "12,17",
			"amenities": "1,2",
			"brands": "33,44",
			"free_cancellation": "true",
			"special_offers": "true",
			"eco_certified": "true",
			"next_page_token": "TOK0",
		}
		self.assertEqual(self.captured, [expected])
		self.assertEqual(out["applied_filters"], {k: v for k, v in expected.items() if k != "engine"})
		self.assertEqual(out["search_query"], "Hotels in Bandra Mumbai")

	def test_defaults_only_send_required_params(self):
		self.responses = {"google_hotels": {}}
		json.loads(serp_hotels.handle_serp_hotel_search(**self.BASE))
		params = self.captured[0]
		self.assertEqual(
			params,
			{
				"engine": "google_hotels",
				"q": "Hotels in Bandra Mumbai",
				"gl": "in",
				"hl": "en",
				"check_in_date": "2026-01-10",
				"check_out_date": "2026-01-12",
				"currency": "INR",
				"adults": 2,
			},
		)

	def test_vacation_rentals_gates_brands_bedrooms(self):
		self.responses = {"google_hotels": {}}
		json.loads(
			serp_hotels.handle_serp_hotel_search(
				**self.BASE, vacation_rentals=True, bedrooms=2, bathrooms="1", brands="33"
			)
		)
		params = self.captured[0]
		self.assertEqual(params["vacation_rentals"], "true")
		self.assertEqual(params["bedrooms"], 2)
		self.assertEqual(params["bathrooms"], 1)
		self.assertNotIn("brands", params)

		json.loads(serp_hotels.handle_serp_hotel_search(**self.BASE, bedrooms=2, brands="33"))
		params = self.captured[1]
		self.assertNotIn("vacation_rentals", params)
		self.assertNotIn("bedrooms", params)
		self.assertNotIn("bathrooms", params)
		self.assertEqual(params["brands"], "33")

	def test_validation_errors_do_not_call_api(self):
		cases = [
			({}, "q is required"),
			({"q": "x"}, "check_in_date"),
			({**self.BASE, "adults": 0}, "At least 1 adult"),
			({**self.BASE, "sort_by": 5}, "Invalid sort_by"),
			({**self.BASE, "rating": 6}, "Invalid rating"),
			({**self.BASE, "hotel_class": "4,6"}, "Invalid hotel_class"),
			({**self.BASE, "min_price": 500, "max_price": 100}, "cannot be greater"),
			({**self.BASE, "min_price": -5}, "cannot be negative"),
			({**self.BASE, "adults": "two"}, "valid integer"),
		]
		for kwargs, fragment in cases:
			out = json.loads(serp_hotels.handle_serp_hotel_search(**kwargs))
			self.assertFalse(out["success"], kwargs)
			self.assertIn(fragment, out["error"], kwargs)
		self.assertEqual(self.captured, [])

	def test_normalization_and_pagination(self):
		self.responses = {
			"google_hotels": {
				"properties": [
					{
						"type": "hotel",
						"name": "Hotel A",
						"property_token": "tokA",
						"extracted_hotel_class": 5,
						"overall_rating": 4.6,
						"reviews": 1234,
						"rate_per_night": {"lowest": "$1,234"},
						"gps_coordinates": {"latitude": 19.0, "longitude": 72.8},
						"images": [{"thumbnail": "t.jpg", "original_image": "o.jpg"}, "plain.jpg"],
						"nearby_places": [{"name": "Beach"}, "Market"],
						"amenities": ["Wi-Fi", 42],
						"free_cancellation": True,
					},
					{
						"name": "Hotel B",
						"property_token": "tokB",
						"total_rate": {"extracted_lowest": 900},
					},
				],
				"serpapi_pagination": {"next_page_token": "NEXT"},
			}
		}
		out = json.loads(serp_hotels.handle_serp_hotel_search(**self.BASE))
		self.assertTrue(out["success"])
		self.assertEqual(out["next_page_token"], "NEXT")
		a, b = out["properties"]
		self.assertEqual(a["lowest_price"], 1234.0)
		self.assertEqual(a["hotel_class"], "5")
		self.assertEqual(a["reviews"], 1234.0)
		self.assertTrue(a["free_cancellation"])
		self.assertEqual(a["images"][1], {"thumbnail": "plain.jpg", "original_image": "plain.jpg"})
		self.assertEqual(a["nearby_places"][1], {"name": "Market"})
		self.assertEqual(a["amenities"], ["Wi-Fi"])
		self.assertEqual(b["lowest_price"], 900.0)

	def test_lowest_price_fallback_chain(self):
		prop = {"total_rate": {"lowest": "₹2,500.50"}}
		self.assertEqual(serp_hotels._extract_lowest_price(prop), 2500.5)
		self.assertEqual(serp_hotels._extract_lowest_price({}), 0.0)
		self.assertEqual(
			serp_hotels._extract_lowest_price({"rate_per_night": {"extracted_lowest": None, "lowest": 75}}),
			75.0,
		)
		# source quirk: a numeric zero short-circuits via the string-parsing path
		self.assertEqual(
			serp_hotels._extract_lowest_price({"rate_per_night": {"extracted_lowest": 0, "lowest": 75}}),
			0.0,
		)

	def test_single_property_top_level_fallback(self):
		self.responses = {
			"google_hotels": {
				"name": "Exact Hotel",
				"property_token": "tokExact",
				"rate_per_night": {"extracted_lowest": 300},
			}
		}
		out = json.loads(serp_hotels.handle_serp_hotel_search(**self.BASE))
		self.assertEqual(len(out["properties"]), 1)
		self.assertEqual(out["properties"][0]["property_token"], "tokExact")
		self.assertIsNone(out["next_page_token"])

	@patch("huf.ai.tools.serp_hotels.update_last_error")
	def test_error_envelope_updates_last_error(self, mock_update):
		self.responses = {"google_hotels": RuntimeError("api down")}
		out = json.loads(serp_hotels.handle_serp_hotel_search(**self.BASE))
		self.assertFalse(out["success"])
		self.assertEqual(out["error"], "api down")
		mock_update.assert_called_once_with("serpapi", "api down")


class TestHotelDetails(SerpToolTestCase):
	def test_params_and_normalization(self):
		self.responses = {
			"google_hotels": {
				"name": "Hotel A",
				"type": "hotel",
				"extracted_hotel_class": 4,
				"overall_rating": 4.2,
				"reviews": 500,
				"link": "https://example.com",
				"address": ["12 MG Road", "Mumbai"],
				"phone": "+91 22 1234",
				"gps_coordinates": {"latitude": 19.1, "longitude": 72.9},
				"check_in_time": "2 PM",
				"check_out_time": "11 AM",
				"prices": [
					{"source": "Booking.com", "rate_per_night": {"extracted_lowest": 120}},
					{"source": "Agoda", "rate_per_night": {"extracted_lowest": 95}},
					{"source": "NoRate"},
				],
				"amenities": ["Pool"],
				"images": ["img.jpg"],
				"nearby_places": ["Airport"],
				"reviews_breakdown": [
					{
						"name": "Cleanliness",
						"positive": 10,
						"negative": 2,
						"neutral": 1,
						"total_mentioned": 13,
					}
				],
			}
		}
		out = json.loads(
			serp_hotels.handle_serp_hotel_details(
				property_token="tok1", check_in_date="2026-01-10", check_out_date="2026-01-12"
			)
		)
		self.assertTrue(out["success"])
		params = self.captured[0]
		self.assertEqual(params["engine"], "google_hotels")
		self.assertEqual(params["property_token"], "tok1")
		self.assertEqual(params["q"], "Hotels")
		self.assertEqual(params["hl"], "en")
		self.assertEqual(params["gl"], "in")
		self.assertEqual(params["adults"], 2)
		self.assertEqual(params["currency"], "INR")
		self.assertEqual(out["lowest_rate_per_night"], 95.0)
		self.assertEqual(out["address"], "12 MG Road, Mumbai")
		self.assertEqual(out["hotel_class"], "4")
		self.assertEqual(len(out["prices"]), 3)
		self.assertEqual(out["prices"][2]["rate_per_night"], 0.0)
		self.assertEqual(out["images"], [{"thumbnail": "img.jpg", "original_image": "img.jpg"}])
		self.assertEqual(out["reviews_breakdown"][0]["name"], "Cleanliness")

	def test_q_and_locale_overrides(self):
		self.responses = {"google_hotels": {}}
		json.loads(
			serp_hotels.handle_serp_hotel_details(
				property_token="tok1",
				check_in_date="2026-01-10",
				check_out_date="2026-01-12",
				q="Hotels in Goa",
				gl="us",
				hl="fr",
				currency="USD",
				adults="3",
			)
		)
		params = self.captured[0]
		self.assertEqual(params["q"], "Hotels in Goa")
		self.assertEqual(params["gl"], "us")
		self.assertEqual(params["hl"], "fr")
		self.assertEqual(params["adults"], 3)
		self.assertEqual(params["currency"], "USD")

	def test_validation(self):
		out = json.loads(
			serp_hotels.handle_serp_hotel_details(check_in_date="2026-01-10", check_out_date="2026-01-12")
		)
		self.assertFalse(out["success"])
		self.assertIn("property_token", out["error"])
		out = json.loads(serp_hotels.handle_serp_hotel_details(property_token="tok1"))
		self.assertFalse(out["success"])
		self.assertIn("check_in_date", out["error"])
		self.assertEqual(self.captured, [])


class TestHotelDetailsBatch(SerpToolTestCase):
	def _details_router(self, params):
		if params["property_token"] == "bad":
			raise RuntimeError("fetch failed")
		return {
			"name": f"Hotel {params['property_token']}",
			"property_token": params["property_token"],
			"prices": [],
		}

	@patch("huf.ai.tools.serp_common.require_credential", return_value="KEY-BATCH")
	def test_batch_success_dedupe_and_key_resolution(self, mock_cred):
		self.responses = {"google_hotels": self._details_router}
		out = json.loads(
			serp_hotels.handle_serp_hotel_details_batch(
				property_tokens="t1,t2,t1, ,t3",
				check_in_date="2026-01-10",
				check_out_date="2026-01-12",
			)
		)
		self.assertTrue(out["success"])
		self.assertEqual(out["requested"], 3)
		self.assertEqual(out["succeeded"], 3)
		self.assertEqual(out["errors"], [])
		self.assertEqual({h["property_token"] for h in out["hotels"]}, {"t1", "t2", "t3"})
		mock_cred.assert_called_once_with("serpapi", "api_key")
		# key resolved once on the calling thread, passed down to workers
		for call in self.mock_client_fn.call_args_list:
			self.assertEqual(call.kwargs["api_key"], "KEY-BATCH")

	@patch("huf.ai.tools.serp_common.require_credential", return_value="KEY-BATCH")
	def test_batch_json_tokens_and_errors(self, mock_cred):
		self.responses = {"google_hotels": self._details_router}
		out = json.loads(
			serp_hotels.handle_serp_hotel_details_batch(
				property_tokens='["t1", "bad"]',
				check_in_date="2026-01-10",
				check_out_date="2026-01-12",
				max_workers=2,
			)
		)
		self.assertTrue(out["success"])
		self.assertEqual(out["requested"], 2)
		self.assertEqual(out["succeeded"], 1)
		self.assertEqual(out["errors"], [{"property_token": "bad", "error": "fetch failed"}])

	def test_batch_validation(self):
		out = json.loads(serp_hotels.handle_serp_hotel_details_batch(property_tokens=""))
		self.assertFalse(out["success"])
		self.assertIn("property_token", out["error"])
		out = json.loads(serp_hotels.handle_serp_hotel_details_batch(property_tokens="t1"))
		self.assertFalse(out["success"])
		self.assertIn("check_in_date", out["error"])


class TestGoogleMapsReviews(SerpToolTestCase):
	MAP_SEARCH: ClassVar = {
		"local_results": [
			{"place_id": "p0", "title": "No Data Id"},
			{
				"data_id": "0x1:0x2",
				"place_id": "p1",
				"title": "Leopold Cafe",
				"address": "Colaba",
				"rating": 4.2,
				"reviews": 8000,
				"gps_coordinates": {"latitude": 18.9, "longitude": 72.8},
			},
		]
	}
	REVIEWS: ClassVar = {
		"place_info": {"title": "Leopold Cafe", "rating": 4.2, "reviews": 8000},
		"reviews": [
			{
				"review_id": "r1",
				"user": {"name": "Jane", "link": "l", "thumbnail": "t", "reviews": 10},
				"rating": 5,
				"date": "a week ago",
				"iso_date": "2026-01-01",
				"snippet": "Great",
				"likes": 3,
				"images": ["i.jpg"],
				"response": {"snippet": "Thanks!"},
			}
		],
		"serpapi_pagination": {"next_page_token": "MT"},
	}

	def test_two_step_resolution_and_matched_place(self):
		self.responses = {"google_maps": self.MAP_SEARCH, "google_maps_reviews": self.REVIEWS}
		out = json.loads(serp_reviews.handle_serp_google_maps_reviews(place_query="Leopold Cafe Mumbai"))
		self.assertTrue(out["success"])
		self.assertEqual(len(self.captured), 2)
		search_params, review_params = self.captured
		self.assertEqual(
			search_params,
			{"engine": "google_maps", "q": "Leopold Cafe Mumbai", "hl": "en", "gl": "in", "type": "search"},
		)
		self.assertEqual(review_params["engine"], "google_maps_reviews")
		self.assertEqual(review_params["data_id"], "0x1:0x2")
		self.assertNotIn("place_id", review_params)
		self.assertEqual(out["data_id"], "0x1:0x2")
		self.assertEqual(out["matched_place"], "Leopold Cafe")
		self.assertEqual(out["next_page_token"], "MT")
		self.assertEqual(out["place"]["title"], "Leopold Cafe")
		review = out["reviews"][0]
		self.assertEqual(review["author"], "Jane")
		self.assertEqual(review["response"], "Thanks!")
		self.assertEqual(review["likes"], 3.0)

	def test_direct_id_skips_search(self):
		self.responses = {"google_maps_reviews": self.REVIEWS}
		out = json.loads(
			serp_reviews.handle_serp_google_maps_reviews(
				data_id="0x9:0x9", sort_by="newestFirst", next_page_token="PREV", hl="en", gl="us"
			)
		)
		self.assertTrue(out["success"])
		self.assertEqual(len(self.captured), 1)
		params = self.captured[0]
		self.assertEqual(
			params,
			{
				"engine": "google_maps_reviews",
				"hl": "en",
				"gl": "us",
				"data_id": "0x9:0x9",
				"sort_by": "newestFirst",
				"next_page_token": "PREV",
			},
		)
		self.assertEqual(out["matched_place"], "")
		self.assertEqual(out["data_id"], "0x9:0x9")

	def test_validation(self):
		out = json.loads(serp_reviews.handle_serp_google_maps_reviews())
		self.assertFalse(out["success"])
		self.assertIn("place_query", out["error"])
		out = json.loads(serp_reviews.handle_serp_google_maps_reviews(data_id="x", sort_by="bogus"))
		self.assertFalse(out["success"])
		self.assertIn("Invalid sort_by", out["error"])
		self.assertEqual(self.captured, [])

	def test_no_match(self):
		self.responses = {"google_maps": {"local_results": []}}
		out = json.loads(serp_reviews.handle_serp_google_maps_reviews(place_query="Nowhere"))
		self.assertFalse(out["success"])
		self.assertIn("No Google Maps place found", out["error"])

	@patch("huf.ai.tools.serp_reviews.update_last_error")
	def test_error_envelope_updates_last_error(self, mock_update):
		self.responses = {"google_maps_reviews": RuntimeError("quota exceeded")}
		out = json.loads(serp_reviews.handle_serp_google_maps_reviews(data_id="0x1:0x2"))
		self.assertFalse(out["success"])
		self.assertEqual(out["error"], "quota exceeded")
		mock_update.assert_called_once_with("serpapi", "quota exceeded")


class TestGoogleHotelReviews(SerpToolTestCase):
	def _router(self, params):
		if "property_token" in params:
			return {
				"name": "Taj Mahal Palace",
				"overall_rating": 4.7,
				"reviews": 9000,
				"ratings": [{"stars": 5, "count": 7000}, {"stars": 4.0, "count": 1500}],
				"reviews_breakdown": [
					{"name": "Location", "positive": 50, "negative": 3, "neutral": 2, "total_mentioned": 55}
				],
			}
		return {"properties": [{"name": "Taj Mahal Palace", "property_token": "tokTaj"}]}

	def test_two_step_resolution(self):
		self.responses = {"google_hotels": self._router}
		out = json.loads(
			serp_reviews.handle_serp_google_hotel_reviews(
				hotel_query="Taj Mahal Palace Mumbai",
				check_in_date="2026-01-10",
				check_out_date="2026-01-12",
			)
		)
		self.assertTrue(out["success"])
		self.assertEqual(len(self.captured), 2)
		self.assertNotIn("property_token", self.captured[0])
		self.assertEqual(self.captured[1]["property_token"], "tokTaj")
		self.assertEqual(out["matched_hotel"], "Taj Mahal Palace")
		self.assertEqual(out["property_token"], "tokTaj")
		self.assertEqual(out["ratings"], [{"stars": 5, "count": 7000.0}, {"stars": 4, "count": 1500.0}])
		self.assertEqual(out["reviews_count"], 9000.0)
		self.assertEqual(out["reviews_breakdown"][0]["name"], "Location")

	def test_direct_token(self):
		self.responses = {"google_hotels": self._router}
		out = json.loads(
			serp_reviews.handle_serp_google_hotel_reviews(
				property_token="tokTaj", check_in_date="2026-01-10", check_out_date="2026-01-12"
			)
		)
		self.assertTrue(out["success"])
		self.assertEqual(len(self.captured), 1)
		self.assertEqual(out["matched_hotel"], "")

	def test_validation(self):
		out = json.loads(serp_reviews.handle_serp_google_hotel_reviews(hotel_query="x"))
		self.assertFalse(out["success"])
		self.assertIn("check_in_date", out["error"])
		out = json.loads(
			serp_reviews.handle_serp_google_hotel_reviews(
				check_in_date="2026-01-10", check_out_date="2026-01-12"
			)
		)
		self.assertFalse(out["success"])
		self.assertIn("hotel_query", out["error"])
		self.assertEqual(self.captured, [])


class TestTripadvisor(SerpToolTestCase):
	SEARCH: ClassVar = {
		"places": [
			{
				"location_id": "loc1",
				"title": "Taj Mahal Palace",
				"place_type": "hotel",
				"link": "https://tripadvisor.com/x",
				"rating": 4.5,
				"reviews": 5000,
				"location": "Mumbai",
				"thumbnail": "t.jpg",
			}
		]
	}

	def test_search_params(self):
		self.responses = {"tripadvisor": self.SEARCH}
		out = json.loads(
			serp_reviews.handle_serp_tripadvisor_search(
				q="Taj Mumbai", ssrc="h", tripadvisor_domain="www.tripadvisor.in", offset=30, limit=10
			)
		)
		self.assertTrue(out["success"])
		self.assertEqual(
			self.captured[0],
			{
				"engine": "tripadvisor",
				"q": "Taj Mumbai",
				"ssrc": "h",
				"tripadvisor_domain": "www.tripadvisor.in",
				"offset": 30,
				"limit": 10,
			},
		)
		place = out["places"][0]
		self.assertEqual(place["place_id"], "loc1")  # falls back to location_id
		self.assertEqual(place["reviews_count"], 5000.0)

	def test_search_validation(self):
		out = json.loads(serp_reviews.handle_serp_tripadvisor_search(q=""))
		self.assertFalse(out["success"])
		out = json.loads(serp_reviews.handle_serp_tripadvisor_search(q="x", ssrc="z"))
		self.assertFalse(out["success"])
		self.assertIn("Invalid ssrc", out["error"])
		self.assertEqual(self.captured, [])

	def test_reviews_params_and_next_offset(self):
		self.responses = {
			"tripadvisor_reviews": {
				"reviews": [
					{
						"review_id": "r1",
						"title": "Amazing",
						"snippet": "Loved it",
						"rating": 5,
						"author": {"display_name": "Bob", "contributions": 12, "hometown": "NYC"},
						"trip_info": {"type": "Couples", "date": "Dec 2025"},
						"additional_ratings": [{"label": "Service", "rating": 5}],
						"response": {"snippet": "Come again"},
					}
				],
				"serpapi_pagination": {"next": "https://serpapi.com/next"},
			}
		}
		out = json.loads(
			serp_reviews.handle_serp_tripadvisor_reviews(
				place_id="loc1",
				sort_by="most_recent",
				rating="5,4",
				language="en",
				translate="true",
				offset=30,
				limit=20,
			)
		)
		self.assertTrue(out["success"])
		self.assertEqual(
			self.captured[0],
			{
				"engine": "tripadvisor_reviews",
				"place_id": "loc1",
				"offset": 30,
				"sort_by": "most_recent",
				"rating": "5,4",
				"language": "en",
				"translate": "true",
				"limit": 20,
			},
		)
		self.assertEqual(out["next_offset"], 50)
		review = out["reviews"][0]
		self.assertEqual(review["author"], "Bob")
		self.assertEqual(review["trip_type"], "Couples")
		self.assertEqual(review["additional_ratings"], [{"label": "Service", "rating": 5.0}])
		self.assertEqual(review["response"], "Come again")

	def test_reviews_no_next_page(self):
		self.responses = {"tripadvisor_reviews": {"reviews": [], "serpapi_pagination": {}}}
		out = json.loads(serp_reviews.handle_serp_tripadvisor_reviews(place_id="loc1"))
		self.assertIsNone(out["next_offset"])
		self.assertEqual(self.captured[0]["offset"], 0)

	def test_reviews_limit_validation(self):
		out = json.loads(serp_reviews.handle_serp_tripadvisor_reviews(place_id="loc1", limit=21))
		self.assertFalse(out["success"])
		self.assertIn("between 1 and 20", out["error"])
		out = json.loads(serp_reviews.handle_serp_tripadvisor_reviews(place_id="loc1", sort_by="bogus"))
		self.assertFalse(out["success"])
		self.assertIn("Invalid sort_by", out["error"])
		self.assertEqual(self.captured, [])

	def test_two_step_resolution(self):
		self.responses = {
			"tripadvisor": self.SEARCH,
			"tripadvisor_reviews": {"reviews": [], "serpapi_pagination": {}},
		}
		out = json.loads(serp_reviews.handle_serp_tripadvisor_reviews(place_query="Taj Mumbai"))
		self.assertTrue(out["success"])
		self.assertEqual(self.captured[0]["engine"], "tripadvisor")
		self.assertEqual(self.captured[1]["place_id"], "loc1")
		self.assertEqual(out["place_id"], "loc1")
		self.assertEqual(out["matched_place"], "Taj Mahal Palace")


class TestYelp(SerpToolTestCase):
	SEARCH: ClassVar = {
		"organic_results": [
			{
				"place_ids": ["yelp-1"],
				"title": "Joe's Pizza",
				"rating": 4.4,
				"reviews": 300,
				"price": "$$",
				"categories": [{"title": "Pizza"}, "Italian"],
				"neighborhoods": "Greenwich Village",
				"phone": "212-555-1234",
				"reviews_link": "https://yelp.com/r",
			}
		]
	}

	def test_search_params(self):
		self.responses = {"yelp": self.SEARCH}
		out = json.loads(
			serp_reviews.handle_serp_yelp_search(find_desc="pizza", find_loc="New York, NY", start=10)
		)
		self.assertTrue(out["success"])
		self.assertEqual(
			self.captured[0],
			{"engine": "yelp", "find_desc": "pizza", "find_loc": "New York, NY", "hl": "en", "start": 10},
		)
		biz = out["businesses"][0]
		self.assertEqual(biz["place_id"], "yelp-1")
		self.assertEqual(biz["categories"], ["Pizza", "Italian"])
		self.assertEqual(biz["address"], "Greenwich Village")

	def test_search_validation(self):
		out = json.loads(serp_reviews.handle_serp_yelp_search(find_desc="", find_loc="x"))
		self.assertFalse(out["success"])
		out = json.loads(serp_reviews.handle_serp_yelp_search(find_desc="x", find_loc=""))
		self.assertFalse(out["success"])
		self.assertEqual(self.captured, [])

	def test_reviews_sortby_quirk_and_total(self):
		self.responses = {
			"yelp_reviews": {
				"reviews": [
					{
						"user": {"name": "Amy", "reviews": 7},
						"rating": 4,
						"date": "Jan 2026",
						"comment": {"text": "Solid slice"},
						"tags": ["elite"],
					}
				],
				"search_information": {"total_results": 300},
			}
		}
		out = json.loads(
			serp_reviews.handle_serp_yelp_reviews(place_id="yelp-1", sort_by="date_desc", start=20, num=10)
		)
		self.assertTrue(out["success"])
		params = self.captured[0]
		# SerpApi Yelp Reviews engine takes the sort param as `sortby`, not `sort_by`
		self.assertEqual(params["sortby"], "date_desc")
		self.assertNotIn("sort_by", params)
		self.assertEqual(params["start"], 20)
		self.assertEqual(params["num"], 10)
		self.assertEqual(out["total_reviews"], 300.0)
		review = out["reviews"][0]
		self.assertEqual(review["text"], "Solid slice")
		self.assertEqual(review["tags"], ["elite"])

	def test_reviews_validation(self):
		out = json.loads(serp_reviews.handle_serp_yelp_reviews(place_id="y1", sort_by="bogus"))
		self.assertFalse(out["success"])
		self.assertIn("Invalid sort_by", out["error"])
		out = json.loads(serp_reviews.handle_serp_yelp_reviews())
		self.assertFalse(out["success"])
		self.assertIn("business_name", out["error"])
		self.assertEqual(self.captured, [])

	def test_two_step_resolution(self):
		self.responses = {
			"yelp": self.SEARCH,
			"yelp_reviews": {"reviews": [], "search_information": {"total_results": 300}},
		}
		out = json.loads(
			serp_reviews.handle_serp_yelp_reviews(business_name="Joe's Pizza", location="New York, NY")
		)
		self.assertTrue(out["success"])
		self.assertEqual(self.captured[0]["engine"], "yelp")
		self.assertEqual(self.captured[1]["place_id"], "yelp-1")
		self.assertEqual(out["place_id"], "yelp-1")
		self.assertEqual(out["matched_business"], "Joe's Pizza")


class TestYouTubeSearch(SerpToolTestCase):
	def test_params_and_video_id_parsing(self):
		self.responses = {
			"youtube": {
				"video_results": [
					{
						"title": "V1",
						"link": "https://www.youtube.com/watch?v=abc123&t=10",
						"channel": {"name": "Chan", "link": "cl"},
						"published_date": "2 days ago",
						"views": 1000,
						"length": "10:01",
						"description": "d",
						"thumbnail": {"static": "th.jpg"},
					},
					{"title": "V2", "link": "https://youtu.be/def456?si=x"},
					{"title": "V3", "link": "https://www.youtube.com/shorts/ghi789"},
				]
			}
		}
		out = json.loads(
			serp_youtube.handle_serp_youtube_search(search_query="lofi", gl="us", hl="en", sp="CAI%3D")
		)
		self.assertTrue(out["success"])
		self.assertEqual(
			self.captured[0],
			{"engine": "youtube", "search_query": "lofi", "gl": "us", "hl": "en", "sp": "CAI%3D"},
		)
		self.assertEqual(out["search_query"], "lofi")
		v1, v2, v3 = out["videos"]
		self.assertEqual(v1["video_id"], "abc123")
		self.assertEqual(v1["channel"], "Chan")
		self.assertEqual(v1["views"], 1000.0)
		self.assertEqual(v1["thumbnail"], "th.jpg")
		self.assertEqual(v2["video_id"], "def456")
		self.assertEqual(v3["video_id"], "ghi789")

	def test_validation(self):
		out = json.loads(serp_youtube.handle_serp_youtube_search(search_query="  "))
		self.assertFalse(out["success"])
		self.assertIn("search_query", out["error"])
		self.assertEqual(self.captured, [])


class _FakeFetchedTranscript:
	language_code = "hi"

	def to_raw_data(self):
		return [
			{"text": "hello", "start": 0.0, "duration": 1.5},
			{"text": "world", "start": 1.5, "duration": 2.0},
		]


class _FakeYouTubeTranscriptApi:
	last_call = None

	def fetch(self, video_id, languages=None):
		type(self).last_call = (video_id, languages)
		return _FakeFetchedTranscript()


def _fake_transcript_module():
	mod = types.ModuleType("youtube_transcript_api")
	mod.YouTubeTranscriptApi = _FakeYouTubeTranscriptApi
	return mod


class TestYouTubeTranscript(unittest.TestCase):
	def setUp(self):
		_FakeYouTubeTranscriptApi.last_call = None

	def test_video_id_url_variants(self):
		extract = serp_youtube._extract_video_id
		self.assertEqual(extract("https://www.youtube.com/watch?v=abc123&t=5"), "abc123")
		self.assertEqual(extract("https://youtu.be/def456?si=x"), "def456")
		self.assertEqual(extract("https://www.youtube.com/shorts/ghi789"), "ghi789")
		self.assertEqual(extract("https://www.youtube.com/embed/jkl012?rel=0"), "jkl012")
		self.assertEqual(extract("  plainid  "), "plainid")
		self.assertEqual(extract(""), "")

	def test_transcript_success_and_language_coercion(self):
		with patch.dict(sys.modules, {"youtube_transcript_api": _fake_transcript_module()}):
			out = json.loads(
				serp_youtube.handle_youtube_transcript(
					video="https://youtu.be/abc123?t=9", languages="en, hi"
				)
			)
		self.assertTrue(out["success"])
		self.assertEqual(out["video_id"], "abc123")
		self.assertEqual(_FakeYouTubeTranscriptApi.last_call, ("abc123", ["en", "hi"]))
		self.assertEqual(out["language"], "hi")
		self.assertEqual(out["segment_count"], 2)
		self.assertEqual(out["full_text"], "hello world")
		self.assertEqual(out["segments"][1], {"text": "world", "start": 1.5, "duration": 2.0})

	def test_transcript_default_language(self):
		with patch.dict(sys.modules, {"youtube_transcript_api": _fake_transcript_module()}):
			out = json.loads(serp_youtube.handle_youtube_transcript(video="abc123"))
		self.assertTrue(out["success"])
		self.assertEqual(_FakeYouTubeTranscriptApi.last_call, ("abc123", ["en"]))

	def test_transcript_missing_video(self):
		with patch.dict(sys.modules, {"youtube_transcript_api": _fake_transcript_module()}):
			out = json.loads(serp_youtube.handle_youtube_transcript(video=""))
		self.assertFalse(out["success"])
		self.assertIn("video id or YouTube URL", out["error"])

	def test_transcript_package_missing(self):
		with patch.dict(sys.modules, {"youtube_transcript_api": None}):
			out = json.loads(serp_youtube.handle_youtube_transcript(video="abc123"))
		self.assertFalse(out["success"])
		self.assertIn("youtube-transcript-api is not installed", out["error"])

	def test_transcript_fetch_failure(self):
		class _FailingApi:
			def fetch(self, video_id, languages=None):
				raise RuntimeError("TranscriptsDisabled")

		mod = types.ModuleType("youtube_transcript_api")
		mod.YouTubeTranscriptApi = _FailingApi
		with patch.dict(sys.modules, {"youtube_transcript_api": mod}):
			out = json.loads(serp_youtube.handle_youtube_transcript(video="abc123"))
		self.assertFalse(out["success"])
		self.assertIn("Could not fetch transcript", out["error"])


class TestRegistryWiring(unittest.TestCase):
	EXPECTED: ClassVar = {
		"serp_hotel_search": "huf.ai.tools.serp_hotels.handle_serp_hotel_search",
		"serp_hotel_details": "huf.ai.tools.serp_hotels.handle_serp_hotel_details",
		"serp_hotel_details_batch": "huf.ai.tools.serp_hotels.handle_serp_hotel_details_batch",
		"serp_google_maps_reviews": "huf.ai.tools.serp_reviews.handle_serp_google_maps_reviews",
		"serp_google_hotel_reviews": "huf.ai.tools.serp_reviews.handle_serp_google_hotel_reviews",
		"serp_tripadvisor_search": "huf.ai.tools.serp_reviews.handle_serp_tripadvisor_search",
		"serp_tripadvisor_reviews": "huf.ai.tools.serp_reviews.handle_serp_tripadvisor_reviews",
		"serp_yelp_search": "huf.ai.tools.serp_reviews.handle_serp_yelp_search",
		"serp_yelp_reviews": "huf.ai.tools.serp_reviews.handle_serp_yelp_reviews",
		"serp_youtube_search": "huf.ai.tools.serp_youtube.handle_serp_youtube_search",
		"youtube_transcript": "huf.ai.tools.serp_youtube.handle_youtube_transcript",
	}

	def test_all_serp_tools_registered(self):
		registered = {t["tool_name"]: t for t in _registry.ALL_INTEGRATION_TOOLS}
		for tool_name, path in self.EXPECTED.items():
			self.assertIn(tool_name, registered)
			tool = registered[tool_name]
			self.assertEqual(tool["category"], "SERP", tool_name)
			self.assertEqual(tool["function_path"], path, tool_name)
			self.assertTrue(tool["description"], tool_name)
			# handlers actually exist at the registered paths
			module_path, func_name = path.rsplit(".", 1)
			module = __import__(module_path, fromlist=[func_name])
			self.assertTrue(callable(getattr(module, func_name)), tool_name)

	def test_registry_lists(self):
		self.assertEqual(len(_registry.SERP_HOTEL_TOOLS), 3)
		self.assertEqual(len(_registry.SERP_REVIEW_TOOLS), 6)
		self.assertEqual(len(_registry.SERP_YOUTUBE_TOOLS), 2)

	def test_required_params_flagged(self):
		registered = {t["tool_name"]: t for t in _registry.ALL_INTEGRATION_TOOLS}
		required = {p["fieldname"] for p in registered["serp_hotel_search"]["parameters"] if p["required"]}
		self.assertEqual(required, {"q", "check_in_date", "check_out_date"})
		required = {p["fieldname"] for p in registered["youtube_transcript"]["parameters"] if p["required"]}
		self.assertEqual(required, {"video"})

	def test_serpapi_env_fallback(self):
		self.assertIn("SERPAPI_API_KEY", _get_alt_env_names("serpapi", "api_key"))


class TestConfig(unittest.TestCase):
	"""Operational defaults are configurable via the serpapi Integration Service."""

	@patch("huf.ai.tools.serp_common.get_credential")
	@patch("huf.ai.tools.serp_common._client")
	def test_default_currency_gl_hl_override(self, mock_client, mock_cfg):
		mock_cfg.side_effect = lambda service, key, default=None: {
			"default_currency": "USD",
			"default_gl": "us",
			"default_hl": "es",
		}.get(key, default)
		captured = []
		client = MagicMock()
		client.search.side_effect = lambda params: (captured.append(dict(params)) or {"properties": []})
		mock_client.return_value = client

		out = json.loads(serp_hotels.handle_serp_hotel_search(q="x", check_in_date="2026-01-10", check_out_date="2026-01-12"))
		self.assertTrue(out["success"])
		params = captured[0]
		self.assertEqual(params["currency"], "USD")
		self.assertEqual(params["gl"], "us")
		self.assertEqual(params["hl"], "es")

	@patch("huf.ai.tools.serp_common.require_credential", return_value="test-key")
	@patch("huf.ai.tools.serp_common.get_credential")
	@patch("huf.ai.tools.serp_common._client")
	def test_batch_max_workers_override(self, mock_client, mock_cfg, _key):
		mock_cfg.side_effect = lambda service, key, default=None: (
			"2" if key == "batch_max_workers" else default
		)
		captured = []
		client = MagicMock()
		client.search.side_effect = lambda params: (captured.append(dict(params)) or {})
		mock_client.return_value = client

		out = json.loads(
			serp_hotels.handle_serp_hotel_details_batch(
				property_tokens="a,b,c",
				check_in_date="2026-01-10",
				check_out_date="2026-01-12",
			)
		)
		self.assertTrue(out["success"])
		self.assertEqual(out["requested"], 3)
		self.assertEqual(out["succeeded"], 3)

	@patch("huf.ai.tools.serp_common.get_credential")
	@patch("huf.ai.tools.serp_common._client")
	def test_youtube_default_gl_hl_override(self, mock_client, mock_cfg):
		mock_cfg.side_effect = lambda service, key, default=None: {
			"default_gl": "gb",
			"default_hl": "fr",
		}.get(key, default)
		captured = []
		client = MagicMock()
		client.search.side_effect = lambda params: (captured.append(dict(params)) or {"video_results": []})
		mock_client.return_value = client

		out = json.loads(serp_youtube.handle_serp_youtube_search(search_query="paris"))
		self.assertTrue(out["success"])
		params = captured[0]
		self.assertEqual(params["gl"], "gb")
		self.assertEqual(params["hl"], "fr")


if __name__ == "__main__":
	unittest.main()
