# Copyright (c) 2025, Tridz Technologies Pvt Ltd
# For license information, please see license.txt

"""
Local LLM server adapters package.

Provides adapters that implement the LocalRuntimeAdapter Protocol,
allowing Huf to probe and interact with various local LLM servers.
"""

from .base import LocalRuntimeAdapter

__all__ = ["LocalRuntimeAdapter"]
