from __future__ import annotations

import logging

import harbeat_asset_sync.sync_worker  # noqa: F401


def test_http_client_request_urls_are_not_logged_at_info() -> None:
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
    assert logging.getLogger("httpcore").getEffectiveLevel() >= logging.WARNING
