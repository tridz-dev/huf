__version__ = "1.0.0-beta.1"

import logging
import frappe

# Standard HUF App Boot Logger Initialization
# Ensures WARNING and INFO logs across HUF emit to logs/huf.log out-of-the-box
try:
	_huf_logger = frappe.logger("huf")
	if _huf_logger.level > logging.INFO:
		_huf_logger.setLevel(logging.INFO)
except Exception:  # best-effort non-critical cleanup
	pass

# Use pysqlite3 (loadable extensions) instead of stdlib sqlite3 for sqlite_vec
try:
	import sys
	__import__("pysqlite3")
	sys.modules["sqlite3"] = sys.modules.pop("pysqlite3")
except ImportError:
	pass  # Fall back to stdlib; sqlite_vec will fail with clear error

# v16-only test classes backported for v15 compat
try:
	import frappe.tests as _frappe_tests
	from frappe.tests.utils import FrappeTestCase

	if not hasattr(_frappe_tests, "IntegrationTestCase"):
		_frappe_tests.IntegrationTestCase = FrappeTestCase
	if not hasattr(_frappe_tests, "UnitTestCase"):
		_frappe_tests.UnitTestCase = FrappeTestCase
except ImportError:
	pass  # frappe.tests.utils.FrappeTestCase unavailable; leave frappe.tests as-is
