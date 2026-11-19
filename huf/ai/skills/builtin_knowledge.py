# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
App-shipped manifest for the ``huf_knowledge_skill`` runtime skill.

Registered via the ``huf_skills`` hook in ``huf/hooks.py``:
``huf.ai.skills.hooks.sync_app_skills`` (wired into after_install /
after_migrate / after_app_install) resolves each hook entry, calls the
``function_path`` with no arguments, and upserts the returned manifest into
a ``Skill`` record with ``source_type="App Provided"``.

The manifest is parsed from the shipped ``SKILL.md`` using the same parser
manual imports use (``huf.ai.skills.importer._parse_skill_manifest``), so the
Skill record's ``instructions`` field is exactly the SKILL.md body and the
frontmatter supplies name/title/description/category/version.
"""

from __future__ import annotations

import os

from huf.ai.skills.importer import _parse_skill_manifest

SKILL_NAME = "huf_knowledge_skill"

_SKILL_DIR = os.path.join(
	os.path.dirname(__file__), "builtin", "huf_knowledge_skill"
)


def get_knowledge_skill_manifest() -> dict:
	"""Return the SKILL.md-parsed manifest for the bundled knowledge skill."""
	return _parse_skill_manifest(_SKILL_DIR)
