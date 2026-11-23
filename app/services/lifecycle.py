"""Adapt API actions to the application's State Pattern transition rules."""

from __future__ import annotations

from typing import Any

from app.models.application import Application

_STATUS_BY_ACTION = {
    "mark_reviewed": "reviewed",
    "shortlist": "shortlisted",
    "reject": "rejected",
    "hire": "hired",
}

# Keep the action names and tuple interface used by the application service.
ACTIONS = tuple(_STATUS_BY_ACTION)


def snapshot(app: dict[str, Any]) -> dict[str, Any]:
    return {"id": app["id"], "status": app["status"]}


def apply_action(app: dict[str, Any], action: str) -> dict[str, Any]:
    """Return a validated transition result without changing the input row.

    The caller remains responsible for persisting a successful result.
    """
    if action not in ACTIONS:
        return {
            "ok": False,
            "error": f"unknown action {action!r}; expected one of {ACTIONS}",
        }

    application = Application(**app)
    try:
        application.transition_to(_STATUS_BY_ACTION[action])
    except ValueError as exc:
        return {"ok": False, "error": str(exc)}

    updated = dict(app)
    updated["status"] = application.status
    return {
        "ok": True,
        "application": snapshot(updated),
        "row": updated,
        "changed": True,
    }


def derived_status_from_flags(app: dict[str, Any]) -> str:
    """Read stored status for callers still importing this legacy helper.

    Remove this helper when applications.py stops importing it.
    """
    return app["status"]
