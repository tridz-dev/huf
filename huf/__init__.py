__version__ = "1.0.0-beta.1"

import logging
import frappe

# Standard HUF App Boot Logger Initialization
# Ensures WARNING and INFO logs across HUF emit to logs/huf.log out-of-the-box
try:
	_huf_logger = frappe.logger("huf")
	if _huf_logger.level > logging.INFO:
		_huf_logger.setLevel(logging.INFO)
except Exception:
	pass

# Use pysqlite3 (loadable extensions) instead of stdlib sqlite3 for sqlite_vec
try:
	import sys
	__import__("pysqlite3")
	sys.modules["sqlite3"] = sys.modules.pop("pysqlite3")
except ImportError:
	pass  # Fall back to stdlib; sqlite_vec will fail with clear error
