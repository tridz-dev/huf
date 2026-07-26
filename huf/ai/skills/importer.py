# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Skill importer for Huf.

Supports importing skills from Git repositories, configurable common destinations,
local filesystem paths, and ``.huf`` zip archives. ``SKILL.md`` with standard
Anthropic/Claude frontmatter plus a ``huf:`` extension block is the canonical
format. ``skill.json`` is supported only as a legacy fallback.
"""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import frappe
import requests
import yaml
from frappe import _

SKILL_DOCTYPE = "Skill"
CATEGORY_DOCTYPE = "Skill Category"
IMPORT_LOG_DOCTYPE = "Skill Import Log"
TOOL_DOCTYPE = "Agent Tool Function"
KNOWLEDGE_DOCTYPE = "Knowledge Source"
PROMPT_DOCTYPE = "Agent Prompt"
MCP_DOCTYPE = "MCP Server"

DEFAULT_DESTINATIONS = {
	"huf-skills": {
		"repo_url": "https://github.com/tridz-dev/huf-skills",
		"path": "skills",
		"ref": "main",
	},
}

ALLOWED_GIT_DOMAINS = {
	"github.com",
	"gitlab.com",
	"bitbucket.org",
	"raw.githubusercontent.com",
}


class SkillImportError(frappe.ValidationError):
	"""Raised when a skill import fails."""


def _get_allowed_domains() -> set[str]:
	"""Return the set of allowed Git domains (common destinations only)."""
	return ALLOWED_GIT_DOMAINS.copy()


def _validate_git_url(repo_url: str, require_allowlist: bool = True) -> None:
	"""Validate that ``repo_url`` is a safe HTTPS Git URL."""
	parsed = urlparse(repo_url)

	if parsed.scheme != "https":
		frappe.throw(
			_("Only HTTPS Git URLs are supported (got {0}).").format(parsed.scheme or "empty"),
			SkillImportError,
		)

	if not parsed.netloc:
		frappe.throw(_("Invalid Git URL: missing host."), SkillImportError)

	if require_allowlist and parsed.netloc.lower() not in _get_allowed_domains():
		frappe.throw(
			_("Git host '{0}' is not in the allowed domain list.").format(parsed.netloc),
			SkillImportError,
		)


def _run_git_clone(repo_url: str, target_dir: str, ref: str = "main") -> None:
	"""Clone a Git repository shallowly into ``target_dir`` with a subprocess timeout."""
	cmd = [
		"git",
		"clone",
		"--depth",
		"1",
		"--branch",
		ref,
		"--single-branch",
		repo_url,
		target_dir,
	]

	try:
		subprocess.run(
			cmd,
			check=True,
			stdout=subprocess.PIPE,
			stderr=subprocess.PIPE,
			text=True,
			timeout=120,
		)
	except subprocess.TimeoutExpired as e:
		raise SkillImportError(
			_("Git clone timed out after {0} seconds.").format(e.timeout)
		) from e
	except subprocess.CalledProcessError as e:
		stderr = e.stderr or ""
		raise SkillImportError(
			_("Git clone failed (exit {0}): {1}").format(e.returncode, stderr[:500])
		) from e


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str] | None:
	"""Parse YAML frontmatter and return (frontmatter_dict, body)."""
	if not text.startswith("---"):
		return None

	parts = text.split("---", 2)
	if len(parts) < 3:
		return None

	frontmatter_text = parts[1].strip()
	body = parts[2].strip()
	if not frontmatter_text:
		return None

	try:
		data = yaml.safe_load(frontmatter_text)
	except yaml.YAMLError as e:
		raise SkillImportError(
			_("Invalid YAML frontmatter in SKILL.md: {0}").format(str(e))
		) from e

	if not isinstance(data, dict):
		raise SkillImportError(_("SKILL.md frontmatter must be a YAML mapping."))

	return data, body


def _merge_huf_block(manifest: dict[str, Any]) -> dict[str, Any]:
	"""Merge the ``huf:`` extension block into the manifest root."""
	huf_block = manifest.pop("huf", {}) or {}
	if not isinstance(huf_block, dict):
		return manifest

	# huf block fields take precedence for wiring metadata.
	for key, value in huf_block.items():
		if value is None:
			continue
		if key in manifest and key in ("name", "description"):
			continue
		manifest[key] = value

	return manifest


def _parse_skill_manifest(path: str) -> dict[str, Any]:
	"""Parse a skill manifest from ``SKILL.md`` (canonical) or ``skill.json`` (legacy)."""
	skill_path = Path(path)

	md_file = skill_path / "SKILL.md"
	if md_file.exists():
		try:
			text = md_file.read_text(encoding="utf-8")
		except UnicodeDecodeError as e:
			raise SkillImportError(
				_("Could not read SKILL.md: {0}").format(str(e))
			) from e

		parsed = _parse_frontmatter(text)
		if parsed is None:
			raise SkillImportError(
				_("SKILL.md does not contain a valid frontmatter block.")
			)

		manifest, body = parsed
		manifest["instructions"] = body
		return _merge_huf_block(manifest)

	# Legacy fallback: skill.json
	json_file = skill_path / "skill.json"
	if json_file.exists():
		try:
			with open(json_file, encoding="utf-8") as f:
				return json.load(f)
		except json.JSONDecodeError as e:
			raise SkillImportError(
				_("Invalid JSON in skill.json: {0}").format(str(e))
			) from e

	raise SkillImportError(
		_("No SKILL.md or skill.json found at {0}").format(path)
	)


def _resolve_link(
	doctype: str,
	fieldname: str,
	value: str | dict[str, Any] | None,
	warnings: list[str],
) -> str | None:
	"""Resolve a manifest reference to an existing DocType record name."""
	if not value:
		return None

	if isinstance(value, dict):
		lookup = value.get(fieldname) or value.get("name")
	else:
		lookup = str(value)

	if not lookup:
		return None

	if frappe.db.exists(doctype, {fieldname: lookup}):
		return lookup

	# Fallback: try by name (for doctypes where name == field value)
	if frappe.db.exists(doctype, lookup):
		return lookup

	warnings.append(
		_("Referenced {0} '{1}' does not exist; skipping.").format(doctype, lookup)
	)
	return None


def _ensure_category(category_name: str | None) -> str | None:
	"""Ensure the Skill Category exists, creating it if necessary."""
	if not category_name:
		return None

	category_name = str(category_name).strip()
	if frappe.db.exists(CATEGORY_DOCTYPE, category_name):
		return category_name

	try:
		doc = frappe.get_doc(
			{
				"doctype": CATEGORY_DOCTYPE,
				"category_name": category_name,
			}
		)
		doc.insert(ignore_permissions=True)
		frappe.db.commit()
	except Exception as e:
		frappe.log_error(
			_("Failed to create Skill Category '{0}': {1}").format(category_name, str(e)),
			"Skill Import",
		)
		return None

	return category_name


def _create_or_update_skill(
	manifest: dict[str, Any],
	source_meta: dict[str, Any],
) -> tuple[str, list[str]]:
	"""Create or update a Skill document from a parsed manifest.

	Returns a tuple of (skill_name, warnings).
	"""
	warnings: list[str] = []

	skill_name = manifest.get("name") or manifest.get("skill_name")
	if not skill_name:
		raise SkillImportError(_("Skill manifest is missing 'name' or 'skill_name'."))

	title = manifest.get("title") or skill_name.replace("-", " ").replace("_", " ").title()
	description = manifest.get("description", "")
	category = _ensure_category(manifest.get("category"))
	version = manifest.get("version", "1.0.0")
	author = manifest.get("author", "")
	instructions = manifest.get("instructions", "")
	icon = manifest.get("icon") or manifest.get("skill_icon", "")

	# Build child table rows with validation
	skill_tools = []
	for item in manifest.get("tools", []):
		tool_name = _resolve_link(TOOL_DOCTYPE, "tool_name", item, warnings)
		if tool_name:
			row = {"tool": tool_name}
			if isinstance(item, dict):
				row["description"] = item.get("description", "")
				row["required"] = int(item.get("required", 0))
			skill_tools.append(row)

	skill_knowledge = []
	for item in manifest.get("knowledge", []):
		if isinstance(item, dict) and "source" in item and "source_name" not in item:
			item = {**item, "source_name": item.pop("source")}
		source_name = _resolve_link(KNOWLEDGE_DOCTYPE, "source_name", item, warnings)
		if source_name:
			row = {"knowledge_source": source_name}
			if isinstance(item, dict):
				row["mode"] = item.get("mode", "Mandatory")
				row["max_chunks"] = item.get("max_chunks", 5)
				row["token_budget"] = item.get("token_budget", 2000)
			else:
				row["mode"] = "Mandatory"
				row["max_chunks"] = 5
				row["token_budget"] = 2000
			skill_knowledge.append(row)

	skill_prompts = []
	for item in manifest.get("prompts", []):
		prompt_slug = _resolve_link(PROMPT_DOCTYPE, "slug", item, warnings)
		if not prompt_slug and isinstance(item, dict):
			# Allow "prompt": "Title" shorthand used in some SKILL.md specs.
			prompt_slug = _resolve_link(
				PROMPT_DOCTYPE, "title", item.get("prompt") or item, warnings
			)
		if not prompt_slug:
			prompt_slug = _resolve_link(PROMPT_DOCTYPE, "title", item, warnings)
		if prompt_slug:
			row = {"prompt": prompt_slug}
			if isinstance(item, dict):
				row["usage"] = item.get("usage", "System")
			else:
				row["usage"] = "System"
			skill_prompts.append(row)

	skill_mcp_servers = []
	for item in manifest.get("mcp_servers", []):
		if isinstance(item, dict) and "server" in item and "server_name" not in item:
			item = {**item, "server_name": item.pop("server")}
		server_name = _resolve_link(MCP_DOCTYPE, "server_name", item, warnings)
		if server_name:
			row = {"mcp_server": server_name}
			if isinstance(item, dict):
				row["enabled"] = int(item.get("enabled", 1))
			else:
				row["enabled"] = 1
			skill_mcp_servers.append(row)

	existing_name = frappe.db.get_value(SKILL_DOCTYPE, {"skill_name": skill_name}, "name")

	if existing_name:
		doc = frappe.get_doc(SKILL_DOCTYPE, existing_name)
		doc.title = title
		doc.description = description
		if category:
			doc.skill_category = category
		doc.version = version
		doc.author = author
		doc.instructions = instructions
		doc.skill_icon = icon
		doc.source_type = source_meta.get("source_type", "Git")
		doc.source_url = source_meta.get("source_url", "")
		doc.source_path = source_meta.get("source_path", "")
		doc.source_ref = source_meta.get("source_ref", "")
		doc.provider_app = source_meta.get("provider_app", "")
		doc.status = "Active"
		doc.set("skill_tools", skill_tools)
		doc.set("skill_knowledge", skill_knowledge)
		doc.set("skill_prompts", skill_prompts)
		doc.set("skill_mcp_servers", skill_mcp_servers)
		doc.save(ignore_permissions=True)
	else:
		doc = frappe.get_doc(
			{
				"doctype": SKILL_DOCTYPE,
				"skill_name": skill_name,
				"title": title,
				"description": description,
				"skill_category": category,
				"version": version,
				"author": author,
				"instructions": instructions,
				"skill_icon": icon,
				"source_type": source_meta.get("source_type", "Git"),
				"source_url": source_meta.get("source_url", ""),
				"source_path": source_meta.get("source_path", ""),
				"source_ref": source_meta.get("source_ref", ""),
				"provider_app": source_meta.get("provider_app", ""),
				"status": "Active",
				"skill_tools": skill_tools,
				"skill_knowledge": skill_knowledge,
				"skill_prompts": skill_prompts,
				"skill_mcp_servers": skill_mcp_servers,
			}
		)
		doc.insert(ignore_permissions=True)

	frappe.db.commit()
	return skill_name, warnings


def _write_import_log(
	skill_name: str | None,
	source_url: str,
	source_ref: str,
	status: str,
	error_message: str | None = None,
	warnings: list[str] | None = None,
) -> None:
	"""Write a Skill Import Log entry for audit purposes."""
	try:
		if not frappe.db.exists("DocType", IMPORT_LOG_DOCTYPE):
			return

		doc = frappe.get_doc(
			{
				"doctype": IMPORT_LOG_DOCTYPE,
				"skill": skill_name,
				"source_url": source_url,
				"source_ref": source_ref,
				"status": status,
				"error_message": error_message or "",
			}
		)
		doc.insert(ignore_permissions=True)
		frappe.db.commit()

		if warnings:
			for warning in warnings[:20]:
				frappe.log_error(warning, "Skill Import Warning")
	except Exception:
		# Import logging is best-effort
		frappe.log_error(
			_("Failed to write skill import log for {0}").format(source_url), "Skill Import"
		)


def import_skill_from_path(
	path: str,
	source_type: str = "Local",
	source_url: str | None = None,
	source_ref: str | None = None,
	provider_app: str | None = None,
) -> dict[str, Any]:
	"""Import a single skill from a local directory or SKILL.md file path.

	Args:
		path: Path to a skill directory or a SKILL.md file.
		source_type: Value for the Skill ``source_type`` field.
		source_url: Optional source URL (e.g., Git repo URL).
		source_ref: Optional source ref (e.g., branch name).
		provider_app: Optional app name for app-provided skills.

	Returns:
		dict: {"skill": skill_name, "warnings": [...]}
	"""
	path_obj = Path(path)
	if path_obj.is_file() and path_obj.name.lower() == "skill.md":
		path_obj = path_obj.parent

	manifest = _parse_skill_manifest(str(path_obj))

	source_meta = {
		"source_type": source_type,
		"source_url": source_url or "",
		"source_path": str(path_obj),
		"source_ref": source_ref or "",
		"provider_app": provider_app or "",
	}

	skill_name, warnings = _create_or_update_skill(manifest, source_meta)
	return {"skill": skill_name, "warnings": warnings}


def _extract_huf_archive(file_path: str, target_dir: str) -> Path:
	"""Extract a ``.huf`` zip archive and return the skill root directory."""
	try:
		with zipfile.ZipFile(file_path, "r") as zf:
			zf.extractall(target_dir)
	except zipfile.BadZipFile as e:
		raise SkillImportError(_("The uploaded file is not a valid .huf archive.")) from e

	root = Path(target_dir)
	if (root / "SKILL.md").exists():
		return root

	for entry in root.iterdir():
		if entry.is_dir() and (entry / "SKILL.md").exists():
			return entry

	raise SkillImportError(_("The .huf archive does not contain a SKILL.md file."))


@frappe.whitelist()
def import_skill_from_huf(file_url: str) -> dict[str, Any]:
	"""Import a skill from an uploaded ``.huf`` archive.

	Args:
		file_url: The Frappe ``file_url`` of the uploaded ``.huf`` file.

	Returns:
		dict: {"skill": skill_name, "warnings": [...]}
	"""
	file_name = frappe.db.get_value("File", {"file_url": file_url}, "name")
	if not file_name:
		frappe.throw(_("Uploaded file not found."), SkillImportError)

	file_doc = frappe.get_doc("File", file_name)
	file_path = file_doc.get_full_path()

	if not os.path.exists(file_path):
		frappe.throw(_("Uploaded file path does not exist."), SkillImportError)

	temp_dir = tempfile.mkdtemp(prefix="huf_skill_huf_")
	try:
		skill_dir = _extract_huf_archive(file_path, temp_dir)
		return import_skill_from_path(
			str(skill_dir),
			source_type="Local",
			source_url=file_url,
		)
	finally:
		shutil.rmtree(temp_dir, ignore_errors=True)


def _get_common_destinations() -> dict[str, dict[str, str]]:
	"""Return common skill destinations merged from defaults and Agent Settings."""
	destinations = DEFAULT_DESTINATIONS.copy()

	try:
		if frappe.db.exists("DocType", "Agent Settings"):
			settings = frappe.get_single("Agent Settings")
			if hasattr(settings, "skill_destinations") and settings.skill_destinations:
				try:
					user_destinations = json.loads(settings.skill_destinations)
					if isinstance(user_destinations, dict):
						destinations.update(user_destinations)
					elif isinstance(user_destinations, list):
						for entry in user_destinations:
							if isinstance(entry, dict) and entry.get("name"):
								destinations[entry["name"]] = entry
				except json.JSONDecodeError:
					frappe.log_error(
						_("Agent Settings.skill_destinations is not valid JSON."),
						"Skill Import",
					)
	except Exception:
		pass

	return destinations


@frappe.whitelist()
def import_skill_from_git(
	repo_url: str,
	path: str = "skills",
	ref: str = "main",
) -> dict[str, Any]:
	"""Clone a Git repository and import skills under ``path``.

	The repository URL must use HTTPS and the host must be in the allowlist
	(GitHub, GitLab, Bitbucket by default). A shallow clone with a subprocess
	timeout is used to limit resource consumption.

	Args:
		repo_url: HTTPS URL of the Git repository.
		path: Sub-path inside the repository that contains skill directories.
		ref: Git ref to clone (branch, tag, or commit; default ``main``).

	Returns:
		dict: Summary of imported skills and any warnings/errors.
	"""
	_validate_git_url(repo_url, require_allowlist=True)

	temp_dir = tempfile.mkdtemp(prefix="huf_skill_import_")
	cloned = False

	try:
		_run_git_clone(repo_url, temp_dir, ref=ref)
		cloned = True

		skills_root = Path(temp_dir) / path.strip("/")
		if not skills_root.exists() or not skills_root.is_dir():
			raise SkillImportError(
				_("Skills path '{0}' not found in repository.").format(path)
			)

		imported: list[dict[str, Any]] = []
		errors: list[str] = []

		# Single-skill directory (contains SKILL.md directly)
		if (skills_root / "SKILL.md").exists():
			try:
				result = import_skill_from_path(
					str(skills_root),
					source_type="Git",
					source_url=repo_url,
					source_ref=ref,
				)
				imported.append(result)
				_write_import_log(
					skill_name=result["skill"],
					source_url=repo_url,
					source_ref=ref,
					status="Success",
					warnings=result.get("warnings"),
				)
			except Exception as e:
				error_msg = str(e)
				errors.append(f"{path}: {error_msg}")
				_write_import_log(
					skill_name=None,
					source_url=repo_url,
					source_ref=ref,
					status="Error",
					error_message=error_msg,
				)
				frappe.log_error(
					f"Failed to import skill from {skills_root}: {error_msg}", "Skill Import"
				)

			return {
				"imported": imported,
				"count": len(imported),
				"errors": errors,
				"repo_url": repo_url,
				"path": path,
				"ref": ref,
			}

		for entry in sorted(skills_root.iterdir()):
			if not entry.is_dir():
				continue

			try:
				result = import_skill_from_path(
					str(entry),
					source_type="Git",
					source_url=repo_url,
					source_ref=ref,
				)
				imported.append(result)

				_write_import_log(
					skill_name=result["skill"],
					source_url=repo_url,
					source_ref=ref,
					status="Success",
					warnings=result.get("warnings"),
				)
			except Exception as e:
				error_msg = str(e)
				errors.append(f"{entry.name}: {error_msg}")
				_write_import_log(
					skill_name=None,
					source_url=repo_url,
					source_ref=ref,
					status="Error",
					error_message=error_msg,
				)
				frappe.log_error(
					f"Failed to import skill from {entry}: {error_msg}", "Skill Import"
				)

		return {
			"imported": imported,
			"count": len(imported),
			"errors": errors,
			"repo_url": repo_url,
			"path": path,
			"ref": ref,
		}
	finally:
		if cloned or os.path.exists(temp_dir):
			try:
				shutil.rmtree(temp_dir)
			except Exception:
				pass


@frappe.whitelist()
def import_skill_from_common_destination(destination_name: str) -> dict[str, Any]:
	"""Import skills from a configured common destination.

	Common destinations are configured in ``Agent Settings.skill_destinations``.
	The default destination points to the curated ``tridz-dev/huf-skills`` repo.

	Args:
		destination_name: Key identifying the common destination.

	Returns:
		dict: Result from ``import_skill_from_git`` or an error summary.
	"""
	destinations = _get_common_destinations()

	if destination_name not in destinations:
		frappe.throw(
			_("Unknown common destination '{0}'.").format(destination_name),
			SkillImportError,
		)

	config = destinations[destination_name]
	repo_url = config.get("repo_url") or config.get("url")
	path = config.get("path", "skills")
	ref = config.get("ref", "main")

	if not repo_url:
		frappe.throw(
			_("Destination '{0}' is missing a repository URL.").format(destination_name),
			SkillImportError,
		)

	return import_skill_from_git(repo_url=repo_url, path=path, ref=ref)


def _parse_repo_url(repo_url: str) -> tuple[str, str]:
	"""Extract owner and repo name from a GitHub/GitLab/Bitbucket HTTPS URL."""
	parsed = urlparse(repo_url)
	path = parsed.path.strip("/").removesuffix(".git")
	parts = path.split("/")
	if len(parts) < 2:
		frappe.throw(_("Could not parse repository URL."), SkillImportError)
	return parts[-2], parts[-1]


def fetch_skill_registry(
	repo_url: str,
	ref: str = "main",
	path: str = "_index.json",
) -> dict[str, Any]:
	"""Fetch and parse a skill registry ``_index.json`` file from a Git repo."""
	_validate_git_url(repo_url, require_allowlist=True)
	owner, repo = _parse_repo_url(repo_url)
	raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path.lstrip('/')}"

	try:
		resp = requests.get(raw_url, timeout=30)
		resp.raise_for_status()
	except requests.RequestException as e:
		raise SkillImportError(
			_("Could not fetch skill registry: {0}").format(str(e))
		) from e

	try:
		return resp.json()
	except json.JSONDecodeError as e:
		raise SkillImportError(_("Invalid registry JSON: {0}").format(str(e))) from e


@frappe.whitelist()
def import_skill_from_registry(
	repo_url: str,
	skill_name: str | None = None,
	path: str = "skills",
	ref: str = "main",
) -> dict[str, Any]:
	"""Import skill(s) from a registry ``_index.json``.

	If ``skill_name`` is provided, only that skill is imported using the path
	declared in the registry. Otherwise all skills under ``path`` are imported.
	"""
	if not skill_name:
		return import_skill_from_git(repo_url=repo_url, path=path, ref=ref)

	registry = fetch_skill_registry(repo_url, ref=ref)
	skills = registry.get("skills", [])
	match = next((s for s in skills if s.get("name") == skill_name), None)
	if not match:
		frappe.throw(
			_("Skill '{0}' not found in registry.").format(skill_name),
			SkillImportError,
		)

	skill_path = match.get("path") or f"{path}/{skill_name}"
	return import_skill_from_git(repo_url=repo_url, path=skill_path, ref=ref)
