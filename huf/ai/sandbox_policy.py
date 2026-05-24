# Copyright (c) 2025, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""
Sandbox network policy management.

Defines NetworkPolicy — a lightweight config object that controls outbound
network access for code interpreter sandboxes.  It is intentionally
deterministic (no LLM involvement) and is evaluated before the sandbox
starts so the LLM agent cannot influence the outcome.

Usage:
    policy = NetworkPolicy(mode="whitelist", presets=["pip", "npm"], domains=["api.example.com"])
    config = policy.to_sandbox_config()
    # {"network": "whitelist", "allowed_domains": [...]}
"""

from __future__ import annotations

import json


# ---------------------------------------------------------------------------
# Preset registry
# ---------------------------------------------------------------------------

PRESET_DOMAINS: dict[str, list[str]] = {
	"npm": [
		"registry.npmjs.org",
		"registry.yarnpkg.com",
		"npmjs.org",
	],
	"pip": [
		"pypi.org",
		"files.pythonhosted.org",
		"pypi.python.org",
	],
	"apt": [
		"archive.ubuntu.com",
		"security.ubuntu.com",
		"deb.debian.org",
		"ports.ubuntu.com",
		"ppa.launchpad.net",
	],
	"brew": [
		"formulae.brew.sh",
		"raw.githubusercontent.com",
		"objects.githubusercontent.com",
		"github.com",
		"api.github.com",
	],
	"docker": [
		"registry-1.docker.io",
		"auth.docker.io",
		"production.cloudflare.docker.com",
		"index.docker.io",
	],
	"cargo": [
		"crates.io",
		"static.crates.io",
		"index.crates.io",
	],
	"gem": [
		"rubygems.org",
		"api.rubygems.org",
		"gems.rubygems.org",
	],
	"go": [
		"proxy.golang.org",
		"sum.golang.org",
		"pkg.go.dev",
	],
	"maven": [
		"repo1.maven.org",
		"repo.maven.apache.org",
		"central.sonatype.com",
	],
	"nuget": [
		"api.nuget.org",
		"www.nuget.org",
	],
}

# Human-readable labels for presets (used in UI)
PRESET_LABELS: dict[str, str] = {
	"npm": "npm / yarn",
	"pip": "pip / PyPI",
	"apt": "apt / Ubuntu",
	"brew": "Homebrew",
	"docker": "Docker Hub",
	"cargo": "Cargo / crates.io",
	"gem": "RubyGems",
	"go": "Go modules",
	"maven": "Maven Central",
	"nuget": "NuGet",
}

VALID_MODES = ("disabled", "whitelist", "open")
VALID_PRESETS = set(PRESET_DOMAINS.keys())


class NetworkPolicy:
	"""
	Encapsulates the network access policy for a sandbox execution.

	Attributes:
	    mode:          "disabled" | "whitelist" | "open"
	    presets:       list of preset names ("npm", "pip", "apt", …)
	    extra_domains: additional whitelisted domains (raw strings)
	"""

	def __init__(
		self,
		mode: str = "disabled",
		presets: list[str] | None = None,
		domains: list[str] | None = None,
	) -> None:
		if mode not in VALID_MODES:
			raise ValueError(f"Invalid network mode '{mode}'. Must be one of: {', '.join(VALID_MODES)}")

		self.mode = mode
		self.presets: list[str] = [p for p in (presets or []) if p in VALID_PRESETS]
		self.extra_domains: list[str] = [d.strip() for d in (domains or []) if d.strip()]

	# ------------------------------------------------------------------
	# Class-level helpers
	# ------------------------------------------------------------------

	@classmethod
	def from_tool_doc(cls, tool_doc) -> "NetworkPolicy":
		"""
		Build a NetworkPolicy from an Agent Tool Function document.

		Reads network_mode, network_presets (JSON list), and allowed_domains
		(newline-separated string) from the document.
		"""
		mode = getattr(tool_doc, "network_mode", None) or "disabled"

		presets: list[str] = []
		raw_presets = getattr(tool_doc, "network_presets", None)
		if raw_presets:
			try:
				parsed = json.loads(raw_presets)
				if isinstance(parsed, list):
					presets = [str(p) for p in parsed]
			except (json.JSONDecodeError, TypeError):
				pass

		domains: list[str] = []
		raw_domains = getattr(tool_doc, "allowed_domains", None)
		if raw_domains:
			domains = [line.strip() for line in raw_domains.splitlines() if line.strip()]

		return cls(mode=mode, presets=presets, domains=domains)

	@classmethod
	def get_preset_info(cls) -> list[dict]:
		"""Return preset metadata for use in API responses / UI rendering."""
		return [
			{
				"id": preset_id,
				"label": PRESET_LABELS.get(preset_id, preset_id),
				"domains": PRESET_DOMAINS[preset_id],
			}
			for preset_id in PRESET_DOMAINS
		]

	# ------------------------------------------------------------------
	# Instance helpers
	# ------------------------------------------------------------------

	def resolved_domains(self) -> list[str]:
		"""Expand presets into a flat, deduplicated domain list."""
		if self.mode in ("open", "disabled"):
			return []

		domains: list[str] = []
		for preset in self.presets:
			domains.extend(PRESET_DOMAINS.get(preset, []))
		domains.extend(self.extra_domains)

		# Deduplicate while preserving order
		seen: set[str] = set()
		result: list[str] = []
		for d in domains:
			if d not in seen:
				seen.add(d)
				result.append(d)
		return result

	def to_sandbox_config(self) -> dict:
		"""
		Serialise to the dict passed to the sandbox runtime.

		Shape:
		    {"network": "allow_all"}
		    {"network": "block_all"}
		    {"network": "whitelist", "allowed_domains": [...]}
		"""
		if self.mode == "open":
			return {"network": "allow_all"}
		if self.mode == "disabled":
			return {"network": "block_all"}

		# whitelist
		return {
			"network": "whitelist",
			"allowed_domains": self.resolved_domains(),
		}

	def to_dict(self) -> dict:
		"""Serialise for storage / logging."""
		return {
			"mode": self.mode,
			"presets": self.presets,
			"extra_domains": self.extra_domains,
			"resolved_domains": self.resolved_domains(),
		}

	def __repr__(self) -> str:
		return f"NetworkPolicy(mode={self.mode!r}, presets={self.presets!r}, extra_domains={self.extra_domains!r})"
