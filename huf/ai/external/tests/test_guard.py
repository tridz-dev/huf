# ruff: noqa: S101
from __future__ import annotations

import pytest

from huf.ai.agent.access import NATIVE_MODE, assert_native_execution, is_native_mode


@pytest.mark.parametrize("value", [None, "", NATIVE_MODE])
def test_native_values_are_native(value):
	assert is_native_mode(value) is True


@pytest.mark.parametrize("value", ["Connected External", "Managed External"])
def test_external_values_are_not_native(value):
	assert is_native_mode(value) is False


class _Doc:
	def __init__(self, execution_mode):
		self.execution_mode = execution_mode


@pytest.mark.parametrize("mode", [None, NATIVE_MODE])
def test_object_doc_with_native_mode_passes(mode):
	assert_native_execution(_Doc(mode))


@pytest.mark.parametrize("mode", [None, NATIVE_MODE])
def test_dict_doc_with_native_mode_passes(mode):
	assert_native_execution({"execution_mode": mode})
