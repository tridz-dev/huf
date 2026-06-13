# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Skill exporter for Huf.

Packages a ``Skill`` document and its linked resources into a portable ``.huf``
zip archive. The archive contains only ``SKILL.md`` — the canonical format for
Huf skills. No separate ``manifest.json`` is generated.
"""

from __future__ import annotations

import io
import zipfile
from typing import Any

import frappe
import yaml
from frappe import _

SKILL_DOCTYPE = "Skill"
TOOL_DOCTYPE = "Agent Tool Function"
KNOWLEDGE_DOCTYPE = "Knowledge Source"
PROMPT_DOCTYPE = "Agent Prompt"
MCP_DOCTYPE = "MCP Server"


class SkillExportError(frappe.ValidationError):
	"""Raised when a skill export fails."""


def _get_tool_name(tool_row) -> str | None:
	"""Return the tool_name of the linked Agent Tool Function."""
	try:
		tool_doc = frappe.get_doc(TOOL_DOCTYPE, tool_row.tool)
		return tool_doc.tool_name or tool_row.tool
	except Exception:
		return None


def _get_source_name(ks_row) -> str | None:
	"""Return the source_name of the linked Knowledge Source."""
	try:
		source_doc = frappe.get_doc(KNOWLEDGE_DOCTYPE, ks_row.knowledge_source)
		return source_doc.source_name or ks_row.knowledge_source
	except Exception:
		return None


def _get_prompt_slug(prompt_row) -> str | None:
	"""Return the slug/title of the linked Agent Prompt."""
	try:
		prompt_doc = frappe.get_doc(PROMPT_DOCTYPE, prompt_row.prompt)
		return prompt_doc.slug or prompt_doc.title or prompt_row.prompt
	except Exception:
		return None


def _get_server_name(mcp_row) -> str | None:
	"""Return the server_name of the linked MCP Server."""
	try:
		server_doc = frappe.get_doc(MCP_DOCTYPE, mcp_row.mcp_server)
		return server_doc.server_name or mcp_row.mcp_server
	except Exception:
		return None


def _build_huf_block(skill_doc) -> dict[str, Any]:
	"""Build the ``huf:`` extension block from the Skill document."""
	tools = []
	for row in skill_doc.get("skill_tools", []):
		tool_name = _get_tool_name(row)
		if not tool_name:
			continue
		entry: dict[str, Any] = {"tool_name": tool_name}
		if row.description:
			entry["description"] = row.description
		if row.required:
			entry["required"] = 1
		tools.append(entry)

	knowledge = []
	for row in skill_doc.get("skill_knowledge", []):
		source_name = _get_source_name(row)
		if not source_name:
			continue
		knowledge.append({
			"source_name": source_name,
			"mode": row.mode or "Mandatory",
			"max_chunks": row.max_chunks or 5,
			"token_budget": row.token_budget or 2000,
		})

	prompts = []
	for row in skill_doc.get("skill_prompts", []):
		prompt_slug = _get_prompt_slug(row)
		if not prompt_slug:
			continue
		prompts.append({
			"slug": prompt_slug,
			"usage": row.usage or "System",
		})

	mcp_servers = []
	for row in skill_doc.get("skill_mcp_servers", []):
		server_name = _get_server_name(row)
		if not server_name:
			continue
		mcp_servers.append({
			"server_name": server_name,
			"enabled": 1 if row.enabled else 0,
		})

	return {
		"version": skill_doc.version or "1.0.0",
		"author": skill_doc.author or "",
		"category": skill_doc.skill_category or "",
		"tools": tools,
		"knowledge": knowledge,
		"prompts": prompts,
		"mcp_servers": mcp_servers,
	}


def build_skill_md(skill_doc) -> str:
	"""Build the canonical ``SKILL.md`` content for a Skill document."""
	frontmatter: dict[str, Any] = {
		"name": skill_doc.skill_name,
		"description": skill_doc.description or "",
		"compatibility": {"requires": []},
	}
	frontmatter["huf"] = _build_huf_block(skill_doc)

	yaml_block = yaml.dump(
		frontmatter,
		default_flow_style=False,
		sort_keys=False,
		allow_unicode=True,
		width=120,
	)

	instructions = (skill_doc.instructions or "").strip()
	parts = ["---", yaml_block.rstrip(), "---"]
	if instructions:
		parts.extend(["", instructions])
	return "\n".join(parts) + "\n"


def build_huf_archive(skill_name: str) -> bytes:
	"""Build a ``.huf`` zip archive in memory and return the raw bytes."""
	if not frappe.db.exists(SKILL_DOCTYPE, {"skill_name": skill_name}):
		frappe.throw(_("Skill '{0}' does not exist.").format(skill_name), SkillExportError)

	skill_doc = frappe.get_doc(SKILL_DOCTYPE, {"skill_name": skill_name})
	skill_md = build_skill_md(skill_doc)

	buffer = io.BytesIO()
	with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
		zf.writestr("SKILL.md", skill_md.encode("utf-8"))

	buffer.seek(0)
	return buffer.read()


@frappe.whitelist()
def download_skill_huf(skill_name: str):
	"""Download a Skill as a ``.huf`` archive.

	Sets ``frappe.response`` so Frappe serves the file as a download.
	"""
	archive_bytes = build_huf_archive(skill_name)
	frappe.response["filename"] = f"{skill_name}.huf"
	frappe.response["filecontent"] = archive_bytes
	frappe.response["type"] = "download"
