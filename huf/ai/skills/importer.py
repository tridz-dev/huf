# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Skill importer for Huf.

Supports importing skills from Git repositories, configurable common destinations,
and local filesystem paths. Parses ``skill.json`` or ``SKILL.md`` frontmatter and
creates/updates ``Skill`` documents while validating linked tools, knowledge,
prompts, and MCP servers.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import frappe
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
    }
}

ALLOWED_GIT_DOMAINS = {
    "github.com",
    "gitlab.com",
    "bitbucket.org",
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


def _parse_frontmatter(text: str) -> dict[str, Any] | None:
    """Parse YAML-like frontmatter from a markdown file."""
    if not text.startswith("---"):
        return None

    parts = text.split("---", 2)
    if len(parts) < 3:
        return None

    frontmatter = parts[1].strip()
    if not frontmatter:
        return None

    manifest: dict[str, Any] = {}
    current_list_key: str | None = None
    current_list: list[Any] = []

    for raw_line in frontmatter.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue

        # Simple list item continuation (2 spaces indent + dash)
        if line.startswith("  -") and current_list_key:
            item_text = line[2:].lstrip("- ").strip()
            if item_text:
                current_list.append(item_text)
            continue

        current_list_key = None
        current_list = []

        if ":" not in line:
            continue

        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()

        if value.startswith("[") and value.endswith("]"):
            try:
                manifest[key] = json.loads(value.replace("'", '"'))
            except json.JSONDecodeError:
                manifest[key] = [v.strip() for v in value[1:-1].split(",") if v.strip()]
        elif value.startswith("'") and value.endswith("'"):
            manifest[key] = value[1:-1]
        elif value.startswith('"') and value.endswith('"'):
            manifest[key] = value[1:-1]
        elif value.lower() in ("true", "false"):
            manifest[key] = value.lower() == "true"
        elif re.match(r"^-?\d+$", value):
            manifest[key] = int(value)
        elif value:
            manifest[key] = value
        else:
            current_list_key = key
            manifest[key] = current_list

    return manifest or None


def _parse_skill_manifest(path: str) -> dict[str, Any]:
    """Parse a skill manifest from ``skill.json`` or ``SKILL.md`` frontmatter."""
    skill_path = Path(path)

    json_file = skill_path / "skill.json"
    if json_file.exists():
        try:
            with open(json_file, encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            raise SkillImportError(
                _("Invalid JSON in skill.json: {0}").format(str(e))
            ) from e

    md_file = skill_path / "SKILL.md"
    if md_file.exists():
        try:
            text = md_file.read_text(encoding="utf-8")
        except UnicodeDecodeError as e:
            raise SkillImportError(
                _("Could not read SKILL.md: {0}").format(str(e))
            ) from e

        manifest = _parse_frontmatter(text)
        if manifest is None:
            raise SkillImportError(
                _("SKILL.md does not contain a valid frontmatter block.")
            )
        return manifest

    raise SkillImportError(
        _("No skill.json or SKILL.md found at {0}").format(path)
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
        if not prompt_slug:
            # Fallback: try title
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
    """Clone a Git repository and import all skills under ``path``.

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
