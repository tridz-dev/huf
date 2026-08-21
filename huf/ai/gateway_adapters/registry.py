# Copyright (c) 2026, Huf and contributors
# For license information, please see license.txt

"""Deterministic registry of gateway adapters, keyed by ``provider_id``."""

from __future__ import annotations

from huf.ai.gateway_adapters.adapter import GatewayAdapter


class GatewayAdapterRegistry:
	"""Deterministic registry of gateway adapters.

	Registration is idempotent for the identical class; listing is always
	sorted by ``provider_id`` so lookups and iteration are deterministic
	regardless of registration order.
	"""

	def __init__(self) -> None:
		self._adapters: dict[str, type[GatewayAdapter]] = {}

	def register(self, adapter_cls: type[GatewayAdapter]) -> type[GatewayAdapter]:
		"""Register an adapter class under its ``provider_id``.

		Raises ``TypeError`` for non-adapters and ``ValueError`` when a
		different class already owns the ``provider_id``. Returns the class
		so it can be used as a decorator.
		"""
		if not isinstance(adapter_cls, type) or not issubclass(adapter_cls, GatewayAdapter):
			raise TypeError(f"{adapter_cls!r} is not a GatewayAdapter subclass")
		provider_id = getattr(adapter_cls, "provider_id", None)
		if not isinstance(provider_id, str) or not provider_id.strip():
			raise ValueError(f"Adapter {adapter_cls!r} must define a non-empty 'provider_id'")
		existing = self._adapters.get(provider_id)
		if existing is not None and existing is not adapter_cls:
			raise ValueError(
				f"Gateway provider_id '{provider_id}' is already registered "
				f"({existing.__module__}.{existing.__qualname__})"
			)
		self._adapters[provider_id] = adapter_cls
		return adapter_cls

	def get(self, provider_id: str) -> type[GatewayAdapter]:
		"""Return the adapter class registered under ``provider_id``.

		Raises ``KeyError`` listing the known provider ids when not found.
		"""
		try:
			return self._adapters[provider_id]
		except KeyError:
			known = ", ".join(self.names()) or "<none>"
			raise KeyError(
				f"Unknown gateway adapter '{provider_id}'. Registered: {known}"
			) from None

	def names(self) -> list[str]:
		"""All registered provider ids, sorted ascending."""
		return sorted(self._adapters)

	def adapters(self) -> tuple[type[GatewayAdapter], ...]:
		"""All registered adapter classes, in ascending ``provider_id`` order."""
		return tuple(self._adapters[name] for name in self.names())

	def __contains__(self, provider_id: str) -> bool:
		return provider_id in self._adapters

	def __len__(self) -> int:
		return len(self._adapters)
