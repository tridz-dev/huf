import json
import pytest
from unittest.mock import patch, MagicMock
from huf.ai.tools.frappe_cloud import (
    handle_fc_add_webhook,
    handle_fc_archive_bench,
    handle_fc_create_bench,
    handle_fc_delete_webhook,
    handle_fc_list_benches,
    handle_fc_create_site,
    handle_fc_site_options,
)

@patch("huf.ai.tools.frappe_cloud.get_credential")
@patch("huf.ai.tools.frappe_cloud.httpx.request")
def test_handle_fc_list_benches(mock_request, mock_get_credential):
    mock_get_credential.side_effect = lambda service, key: "test_key" if key == "api_key" else "test_secret" if key == "api_secret" else "https://frappecloud.com"
    mock_response = MagicMock()
    mock_response.text = '{"message": [{"name": "bench-1", "title": "Bench 1", "extra": "raw"}]}'
    mock_response.json.return_value = {"message": [{"name": "bench-1", "title": "Bench 1", "extra": "raw"}]}
    mock_response.raise_for_status.return_value = None
    mock_request.return_value = mock_response

    result = handle_fc_list_benches()
    data = json.loads(result)
    assert data["success"] is True
    assert data["results"] == [{"name": "bench-1", "title": "Bench 1"}]
    mock_request.assert_called_once()
    assert mock_request.call_args.args[:2] == ("POST", "https://frappecloud.com/api/method/press.api.bench.all")

    result = handle_fc_list_benches(full=True)
    data = json.loads(result)
    assert data["results"][0]["extra"] == "raw"

@patch("huf.ai.tools.frappe_cloud.get_credential")
@patch("huf.ai.tools.frappe_cloud.httpx.request")
def test_handle_fc_create_site(mock_request, mock_get_credential):
    mock_get_credential.side_effect = lambda service, key: "test_key" if key == "api_key" else "test_secret" if key == "api_secret" else "https://frappecloud.com"
    mock_response = MagicMock()
    mock_response.text = '{"message": {"name": "site-1"}}'
    mock_response.json.return_value = {"message": {"name": "site-1"}}
    mock_response.raise_for_status.return_value = None
    mock_request.return_value = mock_response

    result = handle_fc_create_site(bench="bench-1", site_name="site-1")
    data = json.loads(result)
    assert data["success"] is True
    assert data["results"]["name"] == "site-1"
    payload = mock_request.call_args.kwargs["json"]
    assert payload["site"]["name"] == "site-1"
    assert payload["site"]["group"] == "bench-1"
    assert payload["site"]["plan"] == "USD 5"

@patch("huf.ai.tools.frappe_cloud.get_credential")
@patch("huf.ai.tools.frappe_cloud.httpx.request")
def test_handle_fc_create_bench(mock_request, mock_get_credential):
    mock_get_credential.side_effect = lambda service, key: "test_key" if key == "api_key" else "test_secret" if key == "api_secret" else "https://frappecloud.com"
    mock_response = MagicMock()
    mock_response.text = '{"message": "bench-1"}'
    mock_response.json.return_value = {"message": "bench-1"}
    mock_response.raise_for_status.return_value = None
    mock_request.return_value = mock_response

    result = handle_fc_create_bench(title="test-bench")
    data = json.loads(result)
    assert data["success"] is True
    assert data["results"] == "bench-1"
    payload = mock_request.call_args.kwargs["json"]
    assert payload["bench"]["title"] == "test-bench"
    assert payload["bench"]["apps"][0]["name"] == "frappe"

@patch("huf.ai.tools.frappe_cloud.get_credential")
@patch("huf.ai.tools.frappe_cloud.httpx.request")
def test_handle_fc_archive_bench(mock_request, mock_get_credential):
    mock_get_credential.side_effect = lambda service, key: "test_key" if key == "api_key" else "test_secret" if key == "api_secret" else "https://frappecloud.com"
    mock_response = MagicMock()
    mock_response.text = "{}"
    mock_response.json.return_value = {}
    mock_response.raise_for_status.return_value = None
    mock_request.return_value = mock_response

    result = handle_fc_archive_bench(bench="bench-1")
    data = json.loads(result)
    assert data["success"] is True
    assert mock_request.call_args.args[:2] == ("POST", "https://frappecloud.com/api/method/press.api.bench.archive")

@patch("huf.ai.tools.frappe_cloud.get_credential")
@patch("huf.ai.tools.frappe_cloud.httpx.request")
def test_handle_fc_site_options_uses_current_endpoint(mock_request, mock_get_credential):
    mock_get_credential.side_effect = lambda service, key: "test_key" if key == "api_key" else "test_secret" if key == "api_secret" else "https://frappecloud.com"
    mock_response = MagicMock()
    mock_response.text = '{"message": {"versions": [], "domain": "frappe.cloud"}}'
    mock_response.json.return_value = {"message": {"versions": [], "domain": "frappe.cloud"}}
    mock_response.raise_for_status.return_value = None
    mock_request.return_value = mock_response

    result = handle_fc_site_options(bench="bench-1")
    data = json.loads(result)
    assert data["success"] is True
    assert data["results"]["domain"] == "frappe.cloud"
    assert mock_request.call_args.args[:2] == ("POST", "https://frappecloud.com/api/method/press.api.site.options_for_new")
    assert mock_request.call_args.kwargs["json"] == {"for_bench": "bench-1"}

@patch("huf.ai.tools.frappe_cloud.get_credential")
@patch("huf.ai.tools.frappe_cloud.httpx.request")
def test_handle_fc_add_webhook(mock_request, mock_get_credential):
    mock_get_credential.side_effect = lambda service, key: "test_key" if key == "api_key" else "test_secret" if key == "api_secret" else "https://frappecloud.com"
    mock_response = MagicMock()
    mock_response.text = "{}"
    mock_response.json.return_value = {}
    mock_response.raise_for_status.return_value = None
    mock_request.return_value = mock_response

    result = handle_fc_add_webhook(endpoint="https://example.com/webhook", secret="secret", events=["Site Status Update"])
    data = json.loads(result)
    assert data["success"] is True
    assert mock_request.call_args.args[:2] == ("POST", "https://frappecloud.com/api/method/press.api.webhook.add")
    assert mock_request.call_args.kwargs["json"]["events"] == ["Site Status Update"]

@patch("huf.ai.tools.frappe_cloud.get_credential")
@patch("huf.ai.tools.frappe_cloud.httpx.request")
def test_handle_fc_delete_webhook(mock_request, mock_get_credential):
    mock_get_credential.side_effect = lambda service, key: "test_key" if key == "api_key" else "test_secret" if key == "api_secret" else "https://frappecloud.com"
    mock_response = MagicMock()
    mock_response.text = "{}"
    mock_response.json.return_value = {}
    mock_response.raise_for_status.return_value = None
    mock_request.return_value = mock_response

    result = handle_fc_delete_webhook(name="webhook-1")
    data = json.loads(result)
    assert data["success"] is True
    assert mock_request.call_args.args[:2] == ("POST", "https://frappecloud.com/api/method/press.api.client.delete")
    assert mock_request.call_args.kwargs["json"] == {"doctype": "Press Webhook", "name": "webhook-1"}
