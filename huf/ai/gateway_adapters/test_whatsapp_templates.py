# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Unit tests for WhatsApp template methods without Frappe dependencies."""

import pytest
from unittest.mock import Mock
from huf.ai.gateway_adapters.whatsapp import WhatsAppGatewayAdapter
from huf.ai.gateway_adapters.types import GatewayTemplateSpec, GatewayTemplateStatus


class FakeResponse:
	"""Stub response object for testing."""

	def __init__(self, status_code: int, json_data: dict):
		self.status_code = status_code
		self._json_data = json_data

	def json(self):
		return self._json_data

	def raise_for_status(self):
		if self.status_code >= 400:
			raise Exception(f"HTTP {self.status_code}")


def test_push_template_create_path():
	"""Test creating a new template without external_id."""
	fake_post = Mock(
		return_value=FakeResponse(200, {
			"id": "123456789",
			"status": "APPROVED",
		})
	)
	adapter = WhatsAppGatewayAdapter(
		{
			"phone_number_id": "12345",
			"access_token": "token123",
			"webhook_verify_token": "verify123",
			"app_secret": "secret123",
			"business_id": "biz999",
		},
		http_post=fake_post,
	)

	template = GatewayTemplateSpec(
		name="greeting",
		language="en_US",
		category="MARKETING",
		components={"components": [{"type": "body", "text": "Hello"}]},
	)

	result = adapter.push_template(template)

	assert result.external_id == "123456789"
	assert result.status == "APPROVED"
	fake_post.assert_called_once()
	call_args = fake_post.call_args
	assert "message_templates" in call_args[0][0]
	assert call_args[1]["json"]["name"] == "greeting"
	assert call_args[1]["json"]["category"] == "MARKETING"


def test_push_template_update_path():
	"""Test updating an existing template with external_id."""
	fake_post = Mock(
		return_value=FakeResponse(200, {"success": True})
	)
	adapter = WhatsAppGatewayAdapter(
		{
			"phone_number_id": "12345",
			"access_token": "token123",
			"webhook_verify_token": "verify123",
			"app_secret": "secret123",
			"business_id": "biz999",
		},
		http_post=fake_post,
	)

	template = GatewayTemplateSpec(
		name="greeting",
		language="en_US",
		category="MARKETING",
		components={"components": [{"type": "body", "text": "Updated"}]},
		external_id="123456789",
	)

	result = adapter.push_template(template)

	assert result.external_id == "123456789"
	assert result.status == "PENDING"
	fake_post.assert_called_once()
	call_args = fake_post.call_args
	assert "123456789" in call_args[0][0]
	assert "message_templates" not in call_args[0][0]


def test_list_templates():
	"""Test fetching multiple templates from Meta."""
	fake_get = Mock(
		return_value=FakeResponse(200, {
			"data": [
				{
					"id": "111",
					"status": "APPROVED",
					"quality_score": {"score": "HIGH"},
				},
				{
					"id": "222",
					"status": "IN_REVIEW",
				},
				{
					"id": "333",
					"status": "REJECTED",
					"quality_score": {"score": "LOW"},
				},
			]
		})
	)
	adapter = WhatsAppGatewayAdapter(
		{
			"phone_number_id": "12345",
			"access_token": "token123",
			"webhook_verify_token": "verify123",
			"app_secret": "secret123",
			"business_id": "biz999",
		},
		http_get=fake_get,
	)

	results = adapter.list_templates()

	assert len(results) == 3
	assert results[0].external_id == "111"
	assert results[0].status == "APPROVED"
	assert results[0].quality_rating == "HIGH"
	assert results[1].external_id == "222"
	assert results[1].status == "IN_REVIEW"
	assert results[1].quality_rating is None
	assert results[2].external_id == "333"
	assert results[2].status == "REJECTED"
	assert results[2].quality_rating == "LOW"


def test_delete_template_not_found_swallowed():
	"""Test that delete gracefully handles 404 not-found errors."""
	fake_delete = Mock(
		return_value=FakeResponse(404, {
			"error": {
				"message": "Template not found",
				"code": 368,
			}
		})
	)
	adapter = WhatsAppGatewayAdapter(
		{
			"phone_number_id": "12345",
			"access_token": "token123",
			"webhook_verify_token": "verify123",
			"app_secret": "secret123",
			"business_id": "biz999",
		},
		http_delete=fake_delete,
	)

	adapter.delete_template("nonexistent_id")

	fake_delete.assert_called_once()
	call_args = fake_delete.call_args
	assert "hsm_id=nonexistent_id" in call_args[0][0]


def test_delete_template_other_error_raised():
	"""Test that delete re-raises non-404 errors."""
	fake_delete = Mock(
		return_value=FakeResponse(500, {
			"error": {
				"message": "Internal server error",
				"code": 1,
			}
		})
	)
	adapter = WhatsAppGatewayAdapter(
		{
			"phone_number_id": "12345",
			"access_token": "token123",
			"webhook_verify_token": "verify123",
			"app_secret": "secret123",
			"business_id": "biz999",
		},
		http_delete=fake_delete,
	)

	with pytest.raises(ValueError, match="delete API returned error"):
		adapter.delete_template("template_id")
