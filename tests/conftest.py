"""Pytest configuration for the reporting engine test suite.

Makes the project importable as the ``automated_business_reporting_engine``
package no matter how pytest is invoked (working directory, rootdir, or an
explicit path), so individual test modules do not need their own
``sys.path`` bootstrap code.
"""

import os
import sys

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PROJECT_PARENT = os.path.dirname(_PROJECT_ROOT)

for _entry in (_PROJECT_ROOT, _PROJECT_PARENT):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)
