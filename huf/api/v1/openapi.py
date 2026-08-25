"""Minimal OpenAPI 3.0 scaffold for the Huf public developer API (v1).

This is intentionally not a full spec generator - just enough structure
so paths can be added per-endpoint as later phases add real endpoints.
"""


def get_openapi_spec() -> dict:
	"""Return the (currently minimal) OpenAPI 3.0 spec for the v1 API."""
	return {
		"openapi": "3.0.0",
		"info": {
			"title": "Huf Developer API",
			"version": "v1",
		},
		"paths": {
			"/huf/api/v1/ping": {
				"get": {
					"summary": "Health check",
					"operationId": "ping",
					"security": [],
					"responses": {
						"200": {
							"description": "Service is healthy.",
							"content": {
								"application/json": {
									"schema": {
										"type": "object",
										"properties": {
											"data": {
												"type": "object",
												"properties": {
													"status": {"type": "string"},
													"version": {"type": "string"},
												},
											},
											"request_id": {"type": "string"},
											"meta": {"type": "object"},
										},
									}
								}
							},
						}
					},
				}
			},
			"/huf/api/v1/me": {
				"get": {
					"summary": "Resolved principal for the current request",
					"operationId": "me",
					"security": [{"session": []}],
					"responses": {
						"200": {
							"description": "The authenticated principal.",
							"content": {
								"application/json": {
									"schema": {
										"type": "object",
										"properties": {
											"data": {
												"type": "object",
												"properties": {
													"user": {"type": "string"},
													"request_id": {"type": "string"},
												},
											},
											"request_id": {"type": "string"},
											"meta": {"type": "object"},
										},
									}
								}
							},
						},
						"401": {"description": "Authentication required."},
					},
				}
			},
		},
	}
