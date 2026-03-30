"""Backend Factory for knowledge backends."""

from typing import Dict, Type, Optional, Any, Tuple

import frappe

from . import KnowledgeBackend


class BackendFactory:
	"""Factory for creating knowledge backends."""
	
	_registry: Dict[str, Type[KnowledgeBackend]] = {}
	_instances: Dict[str, KnowledgeBackend] = {}
	
	@classmethod
	def register(cls, backend_type: str, backend_class: Type[KnowledgeBackend]) -> None:
		"""Register a backend class."""
		cls._registry[backend_type] = backend_class
	
	@classmethod
	def get_backend(
		cls,
		backend_type: str,
		knowledge_source: str,
		config: Optional[Dict[str, Any]] = None
	) -> KnowledgeBackend:
		"""Get or create a backend instance."""
		# Create cache key using Frappe's site-aware pattern
		cache_key = f"{frappe.local.site}:{knowledge_source}:{backend_type}"
		
		# Return cached if exists
		if cache_key in cls._instances:
			return cls._instances[cache_key]
		
		# Create new instance
		if backend_type not in cls._registry:
			raise ValueError(f"Unknown backend type: {backend_type}")
		
		backend_class = cls._registry[backend_type]
		instance = backend_class()
		instance.initialize(knowledge_source, config or {})
		
		cls._instances[cache_key] = instance
		return instance
	
	@classmethod
	def health_check_all(cls) -> Dict[str, Tuple[bool, str]]:
		"""Check health of all cached backends."""
		results = {}
		for cache_key, backend in cls._instances.items():
			results[cache_key] = backend.health_check()
		return results
	
	@classmethod
	def clear_cache(cls) -> None:
		"""Clear all cached backend instances."""
		cls._instances.clear()
