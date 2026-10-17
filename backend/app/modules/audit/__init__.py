"""Audit trail. Public API: `record`, `record_once`."""

from app.modules.audit.service import record, record_once

__all__ = ["record", "record_once"]
