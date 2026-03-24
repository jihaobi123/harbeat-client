"""
Compatibility wrapper for the historical async database module.

The canonical synchronous application database now lives in `app.shared.database`.
This file exposes a small compatibility surface for older imports.
"""

from app.shared.database import Base, SessionLocal, engine, get_db as get_db_session


async def check_db_connection() -> bool:
  try:
    with engine.connect() as connection:
      connection.exec_driver_sql("SELECT 1")
    return True
  except Exception:
    return False
