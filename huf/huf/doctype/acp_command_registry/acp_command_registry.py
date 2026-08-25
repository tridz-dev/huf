# Copyright (c) 2026, Tridz Technologies Pvt Ltd and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
import os
import re
import shutil
from typing import Any

import frappe
from frappe import _
from frappe.model.document import Document

_ENV_DENY_LIST = frozenset({
    "LD_PRELOAD",
    "LD_LIBRARY_PATH",
    "DYLD_INSERT_LIBRARIES",
    "DYLD_LIBRARY_PATH",
    "NODE_OPTIONS",
    "PYTHONPATH",
    "FRAPPE_BENCH_DIR",
    "FRAPPE_SITES_PATH",
    "DB_PASSWORD",
    "REDIS_CACHE_URL",
    "REDIS_QUEUE_URL",
    "REDIS_SOCKETIO_URL",
})

_ENV_DENY_FRAGMENTS = (
    "SECRET",
    "TOKEN",
    "PASSWORD",
    "PRIVATE_KEY",
    "API_KEY",
    "FRAPPE_",
    "DB_",
    "REDIS_",
)

_AUTH_ENV_KEY_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")

_DEFAULT_ENV_ROWS = [
    {"variable_name": "PATH", "fixed_value": "/usr/local/bin:/usr/bin:/bin"},
    {"variable_name": "HOME", "fixed_value": ""},
    {"variable_name": "TMPDIR", "fixed_value": ""},
]


class ACPCommandRegistry(Document):
    def before_insert(self):
        self._seed_default_env_vars()

    def validate(self):
        self._validate_binary_path()
        self._validate_argv_shape()
        self._validate_working_directory()
        self._validate_auth_env_key()
        self._validate_env_allow_list()
        self._ensure_allowed_roles()

    def get_launch_spec(self, auth_secret: str | None = None) -> dict[str, Any]:
        """Return a scrubbed launch context for this registry entry."""
        argv = self._parsed_argv()
        env = self._build_env()
        if self.auth_required and auth_secret and self.auth_env_key:
            env[self.auth_env_key] = auth_secret
        return {
            "cmd": [self.binary_path, *argv],
            "cwd": self.working_directory,
            "env": env,
            "auth_env_key": self.auth_env_key if self.auth_required else None,
            "auth_secret": auth_secret if self.auth_required else None,
            "max_wall_time_seconds": self.max_wall_time_seconds or 300,
        }

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    def _validate_binary_path(self):
        path = (self.binary_path or "").strip()
        if not path:
            frappe.throw(_("Binary Path is required."))
        if not os.path.isabs(path):
            frappe.throw(_("Binary Path must be absolute: {0}").format(path))
        if not os.path.isfile(path) and shutil.which(path) is None:
            frappe.throw(_("Binary Path is not executable or does not exist: {0}").format(path))
        if not os.access(path, os.X_OK):
            # shutil.which fallback: allow bare names only when they resolve to an executable.
            resolved = shutil.which(path)
            if resolved is None or not os.access(resolved, os.X_OK):
                frappe.throw(_("Binary Path is not executable: {0}").format(path))

    def _validate_argv_shape(self):
        raw = self.argv_shape
        if not raw:
            frappe.throw(_("Argument Shape is required."))
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError as e:
            frappe.throw(_("Argument Shape must be valid JSON: {0}").format(str(e)))
        if not isinstance(parsed, list):
            frappe.throw(_("Argument Shape must be a JSON list."))
        for idx, item in enumerate(parsed):
            if not isinstance(item, str):
                frappe.throw(_("Argument Shape item {0} must be a string: {1}").format(idx, item))
        self.argv_shape = json.dumps(parsed)

    def _parsed_argv(self) -> list[str]:
        raw = self.argv_shape or "[]"
        parsed = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(parsed, list):
            return []
        return [str(x) for x in parsed]

    def _validate_working_directory(self):
        cwd = (self.working_directory or "").strip()
        if not cwd:
            frappe.throw(_("Working Directory is required."))
        if not os.path.isabs(cwd):
            frappe.throw(_("Working Directory must be absolute: {0}").format(cwd))

    def _validate_auth_env_key(self):
        if not self.auth_required:
            return
        key = (self.auth_env_key or "").strip()
        if not key:
            frappe.throw(_("Auth Env Key is required when Auth Required is enabled."))
        if not _AUTH_ENV_KEY_RE.match(key):
            frappe.throw(_("Auth Env Key must match A-Z_0-9 and start with a letter/underscore: {0}").format(key))
        if key in _ENV_DENY_LIST:
            frappe.throw(_("Auth Env Key is not allowed: {0}").format(key))

    def _validate_env_allow_list(self):
        seen = set()
        for row in self.get("env_allow_list", []):
            name = (row.variable_name or "").strip()
            if not name:
                frappe.throw(_("Env variable name is required."))
            if name in _ENV_DENY_LIST or any(frag in name for frag in _ENV_DENY_FRAGMENTS):
                frappe.throw(_("Environment variable is not allowed: {0}").format(name))
            if name in seen:
                frappe.throw(_("Duplicate environment variable: {0}").format(name))
            seen.add(name)

    def _ensure_allowed_roles(self):
        if not self.get("allowed_roles"):
            self.append("allowed_roles", {"role": "System Manager"})

    def _seed_default_env_vars(self):
        existing = {row.variable_name for row in self.get("env_allow_list", [])}
        for default in _DEFAULT_ENV_ROWS:
            if default["variable_name"] not in existing:
                self.append("env_allow_list", default)

    def _build_env(self) -> dict[str, str]:
        env: dict[str, str] = {}
        for row in self.get("env_allow_list", []):
            name = row.variable_name
            value = row.fixed_value
            if value is None or value == "":
                # Empty fixed value means "do not pass"; never inherit from worker.
                continue
            env[name] = str(value)
        return env
