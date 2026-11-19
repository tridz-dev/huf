import sys
from unittest.mock import MagicMock

# The pure modules under test never import frappe, but sibling modules in this package do at
# import time. Stubbing it here lets those imports succeed under plain pytest, without a bench.
if "frappe" not in sys.modules:
	sys.modules["frappe"] = MagicMock()
