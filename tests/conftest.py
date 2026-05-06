"""pytest conftest — ensures project root is in sys.path for all tests."""
import sys
import os

# Add project root (parent of tests/) to Python path
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)
