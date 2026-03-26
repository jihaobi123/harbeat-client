"""
Compatibility entrypoint.

The canonical backend now lives under `app/main.py`.
This module keeps the historical `backend.main` import path working.
"""

from app.main import app
