# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt
"""
skill_importer.py
-----------------
Fetch and parse Skills from GitHub repositories that follow the
agentskills.io open standard (compatible with Claude Code, OpenCode,
GitHub Copilot, Cursor, and 30+ other agent products).

Standard skill layout inside a repo:
  <any-prefix>/
    <skill-name>/
      SKILL.md          ← required (YAML frontmatter + Markdown body)
      scripts/          ← optional executables
      references/       ← optional sub-documents

Common repo paths scanned (in priority order):
  skills/              ← anthropics/skills, vercel-labs/skills style
  .claude/skills/
  .agents/skills/
  .opencode/skills/
  (root)               ← single-skill repos
"""

import base64
import json
import re
from typing import Any

import frappe
import requests


# ──────────────────────────────────────────────────────────────────────────────
# GitHub API helpers
# ──────────────────────────────────────────────────────────────────────────────

GITHUB_API = "https://api.github.com"
# Candidate prefix directories to scan inside the repo tree.
SKILL_PREFIXES = ["skills", ".claude/skills", ".agents/skills", ".opencode/skills", ""]

# Requests session (shared across calls within one request lifecycle)
_session: requests.Session | None = None


def _get_session(github_token: str | None = None) -> requests.Session:
	global _session
	if _session is None:
		_session = requests.Session()
		_session.headers.update(
			{
				"Accept": "application/vnd.github+json",
				"X-GitHub-Api-Version": "2022-11-28",
			}
		)
	if github_token:
		_session.headers["Authorization"] = f"Bearer {github_token}"
	elif "Authorization" in _session.headers:
		del _session.headers["Authorization"]
	return _session


def _github_get(path: str, github_token: str | None = None) -> Any:
	"""GET a GitHub API path; raise on non-200."""
	session = _get_session(github_token)
	url = f"{GITHUB_API}/{path.lstrip('/')}"
	resp = session.get(url, timeout=15)
	if resp.status_code == 404:
		frappe.throw(f"GitHub resource not found: {url}", title="Not Found")
	if resp.status_code == 403:
		frappe.throw(
			"GitHub rate limit exceeded. Provide a Personal Access Token to increase limits.",
			title="Rate Limited",
		)
	resp.raise_for_status()
	return resp.json()


def _fetch_repo_tree(owner: str, repo: str, github_token: str | None = None) -> list[dict]:
	"""Return the full flat file tree of the repo's default branch."""
	# First get default branch
	repo_info = _github_get(f"repos/{owner}/{repo}", github_token)
	default_branch = repo_info.get("default_branch", "HEAD")
	tree_data = _github_get(
		f"repos/{owner}/{repo}/git/trees/{default_branch}?recursive=1",
		github_token,
	)
	return tree_data.get("tree", [])


def _fetch_file_content(owner: str, repo: str, path: str, github_token: str | None = None) -> str:
	"""Fetch and decode a single file's content from GitHub."""
	data = _github_get(f"repos/{owner}/{repo}/contents/{path}", github_token)
	if isinstance(data, list):
		frappe.throw(f"Expected a file at '{path}', got a directory.")
	encoded = data.get("content", "")
	return base64.b64decode(encoded).decode("utf-8", errors="replace")


# ──────────────────────────────────────────────────────────────────────────────
# SKILL.md parser
# ──────────────────────────────────────────────────────────────────────────────

def _parse_skill_md(raw: str) -> dict | None:
	"""
	Parse a SKILL.md file into a dict with keys:
	  skill_name, display_name, description, content,
	  version, author, author_url, source_url (empty, filled by caller),
	  license, compatibility

	Returns None if the file is missing required frontmatter fields.
	"""
	# Split on YAML frontmatter delimiters
	match = re.match(r"^\s*---\s*\n(.*?)\n---\s*\n?(.*)", raw, re.DOTALL)
	if not match:
		return None

	fm_raw, body = match.group(1), match.group(2).strip()

	# Parse YAML frontmatter (using simple key:value, avoid yaml dependency assumption)
	try:
		import yaml

		fm = yaml.safe_load(fm_raw) or {}
	except Exception:
		# Fallback: simple line-by-line parse for basic scalar fields
		fm = {}
		for line in fm_raw.splitlines():
			if ":" in line:
				k, _, v = line.partition(":")
				fm[k.strip()] = v.strip().strip('"').strip("'")

	name = str(fm.get("name", "")).strip()
	description = str(fm.get("description", "")).strip()

	# Validate required fields per agentskills.io spec
	if not name or not description:
		return None

	# Validate slug format
	if not re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", name):
		# Attempt to normalise: lower, replace spaces/underscores with hyphens
		name = re.sub(r"[\s_]+", "-", name.lower())
		name = re.sub(r"[^a-z0-9-]", "", name)
		name = re.sub(r"-{2,}", "-", name).strip("-")
		if not name:
			return None

	# Derive display_name from first H1 heading in body, or from name
	h1_match = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
	display_name = h1_match.group(1).strip() if h1_match else name.replace("-", " ").title()

	metadata = fm.get("metadata", {}) or {}

	return {
		"skill_name": name,
		"display_name": display_name,
		"description": description[:1024],
		"content": body,
		"version": str(fm.get("version", metadata.get("version", "")) or "").strip() or None,
		"author": str(fm.get("author", metadata.get("author", "")) or "").strip() or None,
		"license": str(fm.get("license", "") or "").strip() or None,
		"compatibility": str(fm.get("compatibility", "") or "").strip() or None,
		"source_url": "",  # filled by caller
	}


# ──────────────────────────────────────────────────────────────────────────────
# Discovery
# ──────────────────────────────────────────────────────────────────────────────

def discover_skills_in_tree(
	owner: str,
	repo: str,
	tree: list[dict],
	github_token: str | None = None,
) -> list[dict]:
	"""
	Walk the flat repo tree, find all SKILL.md files, fetch and parse each.
	Returns a list of parsed skill dicts (with source_url populated).

	Respects SKILL_PREFIXES priority: stops after the first prefix that yields
	at least one skill (prevents double-counting re-exports).
	"""
	blob_paths = {item["path"] for item in tree if item.get("type") == "blob"}

	repo_url = f"https://github.com/{owner}/{repo}"

	for prefix in SKILL_PREFIXES:
		found: list[dict] = []

		for path in sorted(blob_paths):
			# Normalise prefix comparison
			if prefix:
				if not (path.startswith(f"{prefix}/") and path.endswith("/SKILL.md")):
					continue
				# Must be exactly <prefix>/<skill-dir>/SKILL.md (one extra level)
				relative = path[len(prefix) + 1 :]
			else:
				if not path.endswith("/SKILL.md"):
					continue
				relative = path

			parts = relative.split("/")
			# Exactly <skill-name>/SKILL.md
			if len(parts) != 2:
				continue

			skill_dir = parts[0]
			try:
				raw = _fetch_file_content(owner, repo, path, github_token)
				parsed = _parse_skill_md(raw)
				if parsed:
					parsed["source_url"] = f"{repo_url}/tree/HEAD/{path[: path.rfind('/')]}"
					# Prefer directory name as skill_name if it's a valid slug
					if re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", skill_dir):
						parsed["skill_name"] = skill_dir
					found.append(parsed)
			except Exception as e:
				frappe.log_error(f"Could not parse {path}: {e}", "Skill Importer")

		if found:
			return found

	# Fallback: single-skill repo — SKILL.md at root
	if "SKILL.md" in blob_paths:
		try:
			raw = _fetch_file_content(owner, repo, "SKILL.md", github_token)
			parsed = _parse_skill_md(raw)
			if parsed:
				parsed["source_url"] = repo_url
				return [parsed]
		except Exception as e:
			frappe.log_error(f"Could not parse root SKILL.md: {e}", "Skill Importer")

	return []


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def preview_from_github(repo_slug: str, github_token: str | None = None) -> list[dict]:
	"""
	Fetch and parse all skills from a GitHub repo slug (owner/repo).
	Returns a list of parsed skill dicts — does NOT write to the database.
	"""
	parts = repo_slug.strip().split("/")
	if len(parts) != 2 or not all(parts):
		frappe.throw("Repo must be in 'owner/repo' format (e.g. anthropics/skills).")

	owner, repo = parts
	tree = _fetch_repo_tree(owner, repo, github_token)
	return discover_skills_in_tree(owner, repo, tree, github_token)


def import_skills(skills: list[dict]) -> dict:
	"""
	Create or update Skill documents from a list of parsed skill dicts.

	Returns:
	  { "created": [...names], "updated": [...names], "skipped": [...names] }
	"""
	created, updated, skipped = [], [], []

	for skill_data in skills:
		skill_name = skill_data.get("skill_name", "").strip()
		if not skill_name:
			skipped.append(skill_name or "(unknown)")
			continue

		try:
			existing = frappe.db.exists("Skill", skill_name)
			if existing:
				doc = frappe.get_doc("Skill", skill_name)
				doc.display_name = skill_data.get("display_name") or doc.display_name
				doc.description = skill_data.get("description") or doc.description
				doc.content = skill_data.get("content") or doc.content
				doc.version = skill_data.get("version") or doc.version
				doc.author = skill_data.get("author") or doc.author
				doc.source_url = skill_data.get("source_url") or doc.source_url
				doc.save(ignore_permissions=True)
				updated.append(skill_name)
			else:
				doc = frappe.new_doc("Skill")
				doc.skill_name = skill_name
				doc.display_name = skill_data.get("display_name") or skill_name.replace("-", " ").title()
				doc.description = skill_data.get("description", "")
				doc.content = skill_data.get("content", "")
				doc.version = skill_data.get("version") or ""
				doc.author = skill_data.get("author") or ""
				doc.source_url = skill_data.get("source_url") or ""
				doc.is_active = 1
				doc.scope = "Global"
				doc.insert(ignore_permissions=True)
				created.append(skill_name)
		except Exception as e:
			frappe.log_error(f"Failed to import skill '{skill_name}': {e}", "Skill Importer")
			skipped.append(skill_name)

	frappe.db.commit()
	return {"created": created, "updated": updated, "skipped": skipped}
