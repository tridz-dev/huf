"""Backend health monitoring and fallback system for multi-vector-database support."""

import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import frappe


@dataclass
class BackendHealthStatus:
	"""Health status for a single backend."""
	backend_name: str
	is_healthy: bool = False
	last_check: Optional[datetime] = None
	error_message: Optional[str] = None
	response_time_ms: float = 0.0
	supports_filters: bool = False
	supports_hybrid_search: bool = False


@dataclass
class KnowledgeSourceHealth:
	"""Health status for a knowledge source with its backends."""
	source_name: str
	primary_backend: Optional[BackendHealthStatus] = None
	fallback_backend: Optional[BackendHealthStatus] = None
	last_updated: datetime = field(default_factory=datetime.now)


class BackendHealthMonitor:
	"""
	Monitors health of knowledge backends with caching.
	
	TTL: 5 minutes (300 seconds)
	"""
	
	CACHE_TTL_SECONDS = 300  # 5 minutes
	
	def __init__(self):
		self._health_cache: Dict[str, KnowledgeSourceHealth] = {}
		self._cache_timestamps: Dict[str, float] = {}
	
	def check_health(self, knowledge_source: str) -> KnowledgeSourceHealth:
		"""
		Check health of a knowledge source and its backends.
		
		Uses cached results if within TTL, otherwise performs fresh check.
		"""
		now = time.time()
		cached = self._health_cache.get(knowledge_source)
		last_check = self._cache_timestamps.get(knowledge_source, 0)
		
		# Return cached result if still valid
		if cached and (now - last_check) < self.CACHE_TTL_SECONDS:
			return cached
		
		# Perform fresh health check
		health = self._update_health_status(knowledge_source)
		self._health_cache[knowledge_source] = health
		self._cache_timestamps[knowledge_source] = now
		
		return health
	
	def _get_backend_config(self, knowledge_source: str) -> Dict[str, Any]:
		"""
		Get backend configuration for a knowledge source.
		
		Returns dict with primary_backend, fallback_backend, and other config.
		"""
		try:
			source = frappe.get_doc("Knowledge Source", knowledge_source)
			
			config = {
				"primary_backend": source.get("knowledge_type", "sqlite_fts"),
				"fallback_backend": source.get("fallback_knowledge_type"),
				"source_name": knowledge_source,
				"disabled": source.disabled,
				"status": source.status,
			}
			
			# Check for advanced backend configuration
			if hasattr(source, "backend_config") and source.backend_config:
				try:
					config["advanced_config"] = frappe.parse_json(source.backend_config)
				except Exception:
					config["advanced_config"] = {}
			
			return config
			
		except frappe.DoesNotExistError:
			return {
				"primary_backend": None,
				"fallback_backend": None,
				"source_name": knowledge_source,
				"disabled": True,
				"status": "Not Found",
			}
		except Exception as e:
			frappe.log_error(
				f"Error getting backend config for {knowledge_source}: {e}",
				"Backend Health Monitor"
			)
			return {
				"primary_backend": None,
				"fallback_backend": None,
				"source_name": knowledge_source,
				"disabled": True,
				"status": "Error",
				"error": str(e),
			}
	
	def _update_health_status(self, knowledge_source: str) -> KnowledgeSourceHealth:
		"""
		Perform actual health check against backends.
		
		Tests connectivity and feature support for primary and fallback backends.
		"""
		from .backends import get_backend
		
		config = self._get_backend_config(knowledge_source)
		health = KnowledgeSourceHealth(source_name=knowledge_source)
		
		# Check primary backend
		if config.get("primary_backend"):
			health.primary_backend = self._check_single_backend(
				config["primary_backend"],
				knowledge_source,
				config
			)
		
		# Check fallback backend
		if config.get("fallback_backend"):
			health.fallback_backend = self._check_single_backend(
				config["fallback_backend"],
				knowledge_source,
				config
			)
		
		health.last_updated = datetime.now()
		return health
	
	def _check_single_backend(
		self,
		backend_type: str,
		knowledge_source: str,
		config: Dict[str, Any]
	) -> BackendHealthStatus:
		"""Check health of a single backend instance."""
		from .backends import get_backend
		
		status = BackendHealthStatus(backend_name=backend_type)
		start_time = time.time()
		
		try:
			backend_class = get_backend(backend_type)
			backend = backend_class()
			backend.initialize(knowledge_source, config.get("advanced_config", {}))
			
			# Check for health_check method
			if hasattr(backend, 'health_check'):
				status.is_healthy = backend.health_check()
			else:
				# Fallback: check via stats call
				stats = backend.get_stats()
				status.is_healthy = True
			
			# Check feature support
			status.supports_filters = getattr(backend, 'supports_filters', False)
			if callable(status.supports_filters):
				status.supports_filters = status.supports_filters()
			
			status.supports_hybrid_search = getattr(backend, 'supports_hybrid_search', False)
			if callable(status.supports_hybrid_search):
				status.supports_hybrid_search = status.supports_hybrid_search()
			
			status.last_check = datetime.now()
			
		except Exception as e:
			status.is_healthy = False
			status.error_message = str(e)
			status.last_check = datetime.now()
			frappe.log_error(
				f"Backend health check failed for {backend_type} ({knowledge_source}): {e}",
				"Backend Health Monitor"
			)
		finally:
			status.response_time_ms = (time.time() - start_time) * 1000
		
		return status
	
	def get_fallback_backend(self, knowledge_source: str) -> Optional[str]:
		"""
		Get the fallback backend type for a knowledge source if primary is unhealthy.
		
		Returns None if no fallback is configured or if fallback is also unhealthy.
		"""
		health = self.check_health(knowledge_source)
		
		# If primary is healthy, no need for fallback
		if health.primary_backend and health.primary_backend.is_healthy:
			return None
		
		# Check if fallback is available and healthy
		if health.fallback_backend and health.fallback_backend.is_healthy:
			return health.fallback_backend.backend_name
		
		return None
	
	def invalidate_cache(self, knowledge_source: Optional[str] = None):
		"""Invalidate health check cache for a source or all sources."""
		if knowledge_source:
			self._health_cache.pop(knowledge_source, None)
			self._cache_timestamps.pop(knowledge_source, None)
		else:
			self._health_cache.clear()
			self._cache_timestamps.clear()


# Global monitor instance
_health_monitor: Optional[BackendHealthMonitor] = None


def get_health_monitor() -> BackendHealthMonitor:
	"""Get the global health monitor instance."""
	global _health_monitor
	if _health_monitor is None:
		_health_monitor = BackendHealthMonitor()
	return _health_monitor


def check_backend_health(knowledge_source: str) -> KnowledgeSourceHealth:
	"""
	Convenience function to check backend health for a knowledge source.
	
	Example:
	    health = check_backend_health("My Knowledge Base")
	    if health.primary_backend and health.primary_backend.is_healthy:
	        print("Primary backend is healthy")
	"""
	monitor = get_health_monitor()
	return monitor.check_health(knowledge_source)


@frappe.whitelist()
def get_health_status(knowledge_source: str) -> Dict[str, Any]:
	"""
	API endpoint to get health status for a knowledge source.
	
	Returns JSON-serializable health status.
	"""
	health = check_backend_health(knowledge_source)
	
	def serialize_status(status: Optional[BackendHealthStatus]) -> Optional[Dict[str, Any]]:
		if not status:
			return None
		return {
			"backend_name": status.backend_name,
			"is_healthy": status.is_healthy,
			"last_check": status.last_check.isoformat() if status.last_check else None,
			"error_message": status.error_message,
			"response_time_ms": status.response_time_ms,
			"supports_filters": status.supports_filters,
			"supports_hybrid_search": status.supports_hybrid_search,
		}
	
	return {
		"source_name": health.source_name,
		"primary_backend": serialize_status(health.primary_backend),
		"fallback_backend": serialize_status(health.fallback_backend),
		"last_updated": health.last_updated.isoformat(),
	}


@frappe.whitelist()
def check_all_backends() -> List[Dict[str, Any]]:
	"""
	API endpoint to check health of all knowledge sources.
	
	Returns list of health statuses.
	"""
	monitor = get_health_monitor()
	results = []
	
	try:
		sources = frappe.get_all("Knowledge Source", filters={"disabled": 0}, pluck="name")
		for source_name in sources:
			results.append(get_health_status(source_name))
	except Exception as e:
		frappe.log_error(f"Error checking all backends: {e}", "Backend Health Monitor")
	
	return results
