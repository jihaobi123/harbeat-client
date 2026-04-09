from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.modules.users.models import AuditLog

logger = logging.getLogger(__name__)


def log_action(
    db: Session,
    *,
    actor_id: int,
    action: str,
    target_id: int | None = None,
    detail: str | None = None,
) -> None:
    entry = AuditLog(actor_id=actor_id, action=action, target_id=target_id, detail=detail)
    db.add(entry)
    db.commit()
    logger.info("[AUDIT] actor=%s action=%s target=%s detail=%s", actor_id, action, target_id, detail)
