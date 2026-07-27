import json
import pytest
from unittest.mock import patch, MagicMock
from huf.ai.tools.frappe_cloud import (
    handle_fc_archive_bench,
    handle_fc_create_bench,
    handle_fc_list_benches,
    handle_fc_list_sites,
    handle_fc_create_site
)

@patch("huf.ai.tools.frappe_cloud.get_credential")
@patch("huf.ai.tools.frappe_cloud.httpx.request")
def test_handle_fc_list_benches(mock_request, mock_get_credential):
    mock_get_credential.side_effect = lambda service, key: "test_key" if key == "api_key" else "test_secret" if key == "api_secret" else "https://frappecloud.com"
    mock_response = MagicMock()
    mock_response.text = '{"message": [{"name": "bench-1"}]}'
    mock_response.json.return_value = {"message": [{"name": "bench-1"}]}
    mock_response.raise_for_status.return_value = None
    mock_request.return_value = mock_response

    result = handle_fc_list_benches()
    data = json.loads(result)
    assert data["success"] is True
    assert data["results"] == [{"name": "bench-1"}]
    mock_request.assert_called_once()
    assert mock_request.call_args.args[:2] == ("POST", "https://frappecloud.com/api/method/press.api.bench.all")

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
