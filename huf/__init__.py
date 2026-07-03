__version__ = "0.11.0"

# Use pysqlite3 (loadable extensions) instead of stdlib sqlite3 for sqlite_vec
try:
	import sys
	__import__("pysqlite3")
	sys.modules["sqlite3"] = sys.modules.pop("pysqlite3")
except ImportError:
	pass  # Fall back to stdlib; sqlite_vec will fail with clear error
