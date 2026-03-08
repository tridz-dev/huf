# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# App Agent Discovery - file scanning and JSON loading

from __future__ import annotations

import json
import os
from pathlib import Path

import frappe

KNOWN_TYPES = frozenset({
	"agents",
	"tools",
	"prompts",
	"providers",
	"models",
	"knowledge",
	"triggers",
})

FOLDER_TO_TYPE = {
	"agents": "agent",
	"tools": "tool",
	"prompts": "prompt",
	"providers": "provider",
	"models": "model",
	"knowledge": "knowledge",
	"triggers": "trigger",
}


def scan_app(app_name: str, huf_dir: str) -> dict[str, list[str]]:
	"""
	Scan an app's huf/ directory for definition files.

	Args:
		app_name: Name of the Frappe app
		huf_dir: Absolute path to the app's huf/ directory

	Returns:
		dict mapping definition type (folder name) to list of absolute file paths.
		e.g. {"agents": ["/path/to/lead_assistant.agent.json"], "tools": [...]}
	"""
	definitions: dict[str, list[str]] = {}

	for type_dir in sorted(KNOWN_TYPES):
		type_path = os.path.join(huf_dir, type_dir)
		if not os.path.isdir(type_path):
			continue

		files = []
		try:
			for fname in sorted(os.listdir(type_path)):
				if fname.endswith(".json") and not fname.startswith("."):
					files.append(os.path.join(type_path, fname))
		except OSError as e:
			frappe.log_error(
				f"Failed to list {type_path}: {e}",
				"HUF App Discovery",
			)
			continue

		if files:
			definitions[type_dir] = files

	return definitions


def load_definition(file_path: str, expected_type: str) -> dict | None:
	"""
	Load and parse a single definition file.

	Args:
		file_path: Absolute path to the JSON file
		expected_type: Folder-based type (e.g. "agents", "tools")

	Returns:
		Parsed definition dict, or None if the file is invalid.
	"""
	try:
		with open(file_path, encoding="utf-8") as f:
			data = json.load(f)
	except json.JSONDecodeError as e:
		frappe.log_error(
			f"Invalid JSON in {file_path}: {e}",
			"HUF App Discovery",
		)
		return None
	except OSError as e:
		frappe.log_error(
			f"Cannot read {file_path}: {e}",
			"HUF App Discovery",
		)
		return None

	if not isinstance(data, dict):
		frappe.log_error(
			f"Expected JSON object in {file_path}, got {type(data).__name__}",
			"HUF App Discovery",
		)
		return None

	file_type = data.get("type")
	expected_singular = FOLDER_TO_TYPE.get(expected_type)
	if file_type != expected_singular:
		frappe.log_error(
			f"Type mismatch in {file_path}: expected '{expected_singular}', got '{file_type}'",
			"HUF App Discovery",
		)
		return None

	return data


def get_huf_dir_for_app(app_name: str) -> str | None:
	"""
	Get the huf/ directory path for an installed app.

	Args:
		app_name: Name of the Frappe app

	Returns:
		Absolute path to huf/ directory, or None if not found.
	"""
	try:
		app_path = frappe.get_app_path(app_name)
		huf_dir = os.path.join(app_path, "huf")
		if os.path.isdir(huf_dir):
			return huf_dir
	except Exception:
		pass
	return None
