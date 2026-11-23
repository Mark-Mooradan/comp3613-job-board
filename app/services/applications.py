"""Application create / read / status transitions via lifecycle tracker."""

from __future__ import annotations

from typing import Any

from sqlmodel import Session, select

from app.database import engine
from app.models.application import Application
from app.models.application_status_history import ApplicationStatusHistory
from app.models.listing import Listing
from app.services import listings
from app.services.board_auth import get_user
from app.services.lifecycle import ACTIONS, apply_action


def apply(
    graduate_id: int,
    listing_id: int,
    cover_letter: str,
    resume_text: str | None = None,
) -> dict[str, Any]:
    user = get_user(graduate_id)
    if not user or user["role"] != "graduate":
        return {"ok": False, "error": "graduates only"}
    # DEFECT: no programme eligibility check

    with Session(engine) as session:
        listing = session.get(Listing, listing_id)
        if listing is None:
            return {"ok": False, "error": "listing not found"}

        if listing.status != "published":
            return {"ok": False, "error": "listing is not published"}
        try:
            deadline = listings._parse_deadline(listing.deadline)
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        if deadline < listings._today():
            return {"ok": False, "error": "listing deadline has passed"}
        if listing.apply_mode == "external":
            error = (
                f"apply externally at {listing.external_url}"
                if listing.external_url
                else "external application URL is unavailable"
            )
            return {"ok": False, "error": error}
        if listing.apply_mode != "collect":
            return {
                "ok": False,
                "error": "listing does not accept on-platform applications",
            }

        resume = resume_text or user.get("resume_text") or ""
        application = Application(
            listing_id=listing_id,
            graduate_id=graduate_id,
            cover_letter=cover_letter,
            resume_text=resume,
        )
        session.add(application)
        session.commit()
        session.refresh(application)
        return {
            "ok": True,
            "application_id": application.id,
            "status": application.status,
        }


def my_applications(graduate_id: int) -> list[dict[str, Any]]:
    with Session(engine) as session:
        rows = session.exec(
            select(Application)
            .where(Application.graduate_id == graduate_id)
            .order_by(Application.id)
        ).all()
        return [row.model_dump() for row in rows]


def listing_applicants(viewer_id: int, listing_id: int) -> dict[str, Any]:
    viewer = get_user(viewer_id)
    if not viewer:
        return {"ok": False, "error": "unknown user"}
    with Session(engine) as session:
        listing = session.get(Listing, listing_id)
        if listing is None:
            return {"ok": False, "error": "listing not found"}
        if viewer["role"] not in {"employer", "admin"}:
            return {"ok": False, "error": "forbidden"}
        if viewer["role"] == "employer" and viewer_id != listing.employer_id:
            return {"ok": False, "error": "forbidden"}
        rows = session.exec(
            select(Application)
            .where(Application.listing_id == listing_id)
            .order_by(Application.id)
        ).all()
        return {"ok": True, "applicants": [r.model_dump() for r in rows]}


def export_applicants(admin_id: int, listing_id: int) -> dict[str, Any]:
    admin = get_user(admin_id)
    if not admin or admin["role"] != "admin":
        return {"ok": False, "error": "admin only"}
    result = listing_applicants(admin_id, listing_id)
    if not result.get("ok"):
        return result
    return {"ok": True, "format": "json", "package": result["applicants"]}


def transition_application(
    actor_id: int, application_id: int, action: str
) -> dict[str, Any]:
    """Validate a lifecycle action and persist only a successful change."""
    actor = get_user(actor_id)
    if not actor:
        return {"ok": False, "error": "unknown user"}
    if actor["role"] != "employer":
        return {"ok": False, "error": "forbidden"}
    if action not in ACTIONS:
        return {"ok": False, "error": f"action must be one of {ACTIONS}"}

    with Session(engine) as session:
        row = session.get(Application, application_id)
        if row is None:
            return {"ok": False, "error": "application not found"}
        listing = session.get(Listing, row.listing_id)
        if listing is None:
            return {"ok": False, "error": "listing not found"}
        if actor_id != listing.employer_id:
            return {"ok": False, "error": "forbidden"}

        result = apply_action(row.model_dump(), action)
        if not result.get("ok"):
            return result
        if not result.get("changed"):
            return {
                "ok": True,
                "application": result["application"],
                "changed": False,
            }

        updated = result["row"]
        previous_status = row.status
        row.status = updated["status"]
        session.add(row)
        session.add(
            ApplicationStatusHistory(
                application_id=application_id,
                previous_status=previous_status,
                new_status=row.status,
                actor_id=actor_id,
            )
        )
        session.commit()
        session.refresh(row)
        return {"ok": True, "application": row.model_dump(), "changed": True}


def application_history(viewer_id: int, application_id: int) -> dict[str, Any]:
    viewer = get_user(viewer_id)
    if not viewer:
        return {"ok": False, "error": "unknown user"}

    with Session(engine) as session:
        application = session.get(Application, application_id)
        if application is None:
            return {"ok": False, "error": "application not found"}

        listing = session.get(Listing, application.listing_id)
        if listing is None:
            return {"ok": False, "error": "listing not found"}

        is_applicant = (
            viewer["role"] == "graduate"
            and viewer_id == application.graduate_id
        )
        is_listing_owner = (
            viewer["role"] == "employer"
            and viewer_id == listing.employer_id
        )
        is_admin = viewer["role"] == "admin"
        if not (is_applicant or is_listing_owner or is_admin):
            return {"ok": False, "error": "forbidden"}

        rows = session.exec(
            select(ApplicationStatusHistory)
            .where(ApplicationStatusHistory.application_id == application_id)
            .order_by(ApplicationStatusHistory.timestamp, ApplicationStatusHistory.id)
        ).all()
        return {"ok": True, "history": [row.model_dump() for row in rows]}
