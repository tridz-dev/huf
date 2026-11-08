# ruff: noqa: S101
from __future__ import annotations

import json

import pytest

from huf.ai.external.jsonrpc import (
	HUF_APPROVAL_REQUIRED,
	HUF_DENIED,
	INTERNAL_ERROR,
	INVALID_PARAMS,
	INVALID_REQUEST,
	METHOD_NOT_FOUND,
	PARSE_ERROR,
	JsonRpcError,
	is_notification,
	make_error,
	make_result,
	parse_request,
)


def test_error_code_constants():
	assert PARSE_ERROR == -32700
	assert INVALID_REQUEST == -32600
	assert METHOD_NOT_FOUND == -32601
	assert INVALID_PARAMS == -32602
	assert INTERNAL_ERROR == -32603
	assert HUF_DENIED == -32001
	assert HUF_APPROVAL_REQUIRED == -32002


def test_valid_request_dict_keeps_id_and_params():
	req = parse_request({"jsonrpc": "2.0", "method": "huf.ping", "params": {"a": 1}, "id": 7})
	assert req == {"jsonrpc": "2.0", "method": "huf.ping", "params": {"a": 1}, "id": 7}


def test_str_and_bytes_input_parse_identically():
	text = '{"jsonrpc": "2.0", "method": "m", "params": {"x": "y"}, "id": "abc"}'
	from_str = parse_request(text)
	from_bytes = parse_request(text.encode("utf-8"))
	assert from_str == from_bytes
	assert from_str["id"] == "abc"
	assert from_str["params"] == {"x": "y"}


def test_bad_json_raises_parse_error():
	with pytest.raises(JsonRpcError) as exc_info:
		parse_request("{not json")
	assert exc_info.value.code == PARSE_ERROR
	assert exc_info.value.message == "Parse error"


def test_invalid_utf8_bytes_raise_parse_error():
	with pytest.raises(JsonRpcError) as exc_info:
		parse_request(b"\xff\xfe\x00")
	assert exc_info.value.code == PARSE_ERROR


def test_non_object_json_is_invalid_request():
	with pytest.raises(JsonRpcError) as exc_info:
		parse_request(json.dumps([{"jsonrpc": "2.0", "method": "m"}]))
	assert exc_info.value.code == INVALID_REQUEST


@pytest.mark.parametrize(
	"body",
	[
		{"method": "m"},
		{"jsonrpc": "1.0", "method": "m"},
		{"jsonrpc": 2, "method": "m"},
	],
)
def test_wrong_or_missing_version_is_invalid_request(body):
	with pytest.raises(JsonRpcError) as exc_info:
		parse_request(body)
	assert exc_info.value.code == INVALID_REQUEST


@pytest.mark.parametrize(
	"method",
	[None, "", 5, ["m"]],
)
def test_missing_or_bad_method_is_invalid_request(method):
	body = {"jsonrpc": "2.0", "id": 1}
	if method is not None:
		body["method"] = method
	with pytest.raises(JsonRpcError) as exc_info:
		parse_request(body)
	assert exc_info.value.code == INVALID_REQUEST


def test_absent_or_null_params_default_to_empty_dict():
	absent = parse_request({"jsonrpc": "2.0", "method": "m"})
	null = parse_request({"jsonrpc": "2.0", "method": "m", "params": None})
	assert absent["params"] == {}
	assert null["params"] == {}


@pytest.mark.parametrize("params", [[1, 2], "text", 3])
def test_non_object_params_are_invalid_params(params):
	with pytest.raises(JsonRpcError) as exc_info:
		parse_request({"jsonrpc": "2.0", "method": "m", "params": params})
	assert exc_info.value.code == INVALID_PARAMS


def test_list_params_from_json_text_are_invalid_params():
	with pytest.raises(JsonRpcError) as exc_info:
		parse_request('{"jsonrpc": "2.0", "method": "m", "params": [1, 2]}')
	assert exc_info.value.code == INVALID_PARAMS


def test_id_is_omitted_when_absent_and_kept_when_null_or_string():
	no_id = parse_request({"jsonrpc": "2.0", "method": "m"})
	assert "id" not in no_id
	null_id = parse_request({"jsonrpc": "2.0", "method": "m", "id": None})
	assert null_id["id"] is None
	str_id = parse_request({"jsonrpc": "2.0", "method": "m", "id": "x-1"})
	assert str_id["id"] == "x-1"


def test_notification_detection():
	notification = parse_request({"jsonrpc": "2.0", "method": "m"})
	request = parse_request({"jsonrpc": "2.0", "method": "m", "id": 0})
	assert is_notification(notification) is True
	assert is_notification(request) is False
	# An explicit null id is still a request, not a notification.
	assert is_notification({"jsonrpc": "2.0", "method": "m", "id": None}) is False


def test_make_result_shape():
	assert make_result(3, {"ok": True}) == {"jsonrpc": "2.0", "id": 3, "result": {"ok": True}}


def test_make_error_omits_data_when_none():
	response = make_error(1, METHOD_NOT_FOUND, "Method not found")
	assert response == {
		"jsonrpc": "2.0",
		"id": 1,
		"error": {"code": METHOD_NOT_FOUND, "message": "Method not found"},
	}


def test_make_error_includes_data_when_given():
	response = make_error("a", HUF_DENIED, "Denied", data={"reason": "scope"})
	assert response["error"]["data"] == {"reason": "scope"}


def test_error_to_response_shape_without_data():
	err = JsonRpcError(INTERNAL_ERROR, "boom")
	assert err.code == INTERNAL_ERROR
	assert err.message == "boom"
	assert err.data is None
	assert err.to_response(9) == {
		"jsonrpc": "2.0",
		"id": 9,
		"error": {"code": INTERNAL_ERROR, "message": "boom"},
	}


def test_error_to_response_shape_with_data_and_method():
	err = JsonRpcError(HUF_APPROVAL_REQUIRED, "Approval required", data={"run": "R-1"}, method="huf.run")
	assert err.method == "huf.run"
	assert err.to_response(None) == {
		"jsonrpc": "2.0",
		"id": None,
		"error": {"code": HUF_APPROVAL_REQUIRED, "message": "Approval required", "data": {"run": "R-1"}},
	}


def test_parse_error_converts_to_response():
	try:
		parse_request("nope")
	except JsonRpcError as exc:
		response = exc.to_response(None)
	assert response["error"]["code"] == PARSE_ERROR
	assert response["id"] is None
