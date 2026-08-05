import sys
from unittest.mock import MagicMock
if 'frappe' not in sys.modules:
    sys.modules['frappe'] = MagicMock()
