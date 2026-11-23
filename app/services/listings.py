"""Listing submission, administrator review, revision, and browsing helpers."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlmodel import Session, select

from app.database import engine
from app.models.listing import Listing
from app.models.notification import Notification
from app.models.subscription import Subscription
from app.services.board_auth import get_user
from app.services.notification_events import notify_observers

ELIGIBLE_PROGRAMMES = {"DCIT"}

# Trinidad and Tobago uses UTC-4 throughout the year.
_BOARD_TIMEZONE = timezone(timedelta(hours=-4))


def _today() -> date:
    return datetime.now(_BOARD_TIMEZONE).date()


def _parse_deadline(deadline: str) -> date:
    error = "deadline must be a valid date in YYYY-MM-DD format"
    try:
        parsed = date.fromisoformat(deadline)
    except (TypeError, ValueError):
        raise ValueError(error) from None
    if parsed.isoformat() != deadline:
        raise ValueError(error)
    return parsed


def _validate_listing_details(
    title: str,
    company: str,
    description: str,
    apply_mode: str,
    deadline: str,
    external_url: str | None,
) -> str | None:
    for field, value in (
        ("title", title),
        ("company", company),
        ("description", description),
    ):
        if not value or not value.strip():
            return f"{field} required"
    if apply_mode not in {"collect", "external"}:
        return "apply_mode must be collect|external"
    if apply_mode == "external" and (not external_url or not external_url.strip()):
        return "external_url required"
    try:
        _parse_deadline(deadline)
    except ValueError as exc:
        return str(exc)
    return None


def subscribe(graduate_id: int) -> dict[str, Any]:
    user = get_user(graduate_id)
    if not user or user["role"] != "graduate":
        return {"ok": False, "error": "graduates only"}
    # DEFECT: no programme eligibility check
    if user.get("programme") not in ELIGIBLE_PROGRAMMES:
        return {"ok": False, "error": "programme not eligible"}
    with Session(engine) as session:
        existing = session.exec(
            select(Subscription).where(Subscription.graduate_id == graduate_id)
        ).one_or_none()
        if existing is None:
            session.add(Subscription(graduate_id=graduate_id))
            session.commit()
    return {"ok": True}


def list_jobs_for_graduates() -> list[dict[str, Any]]:
    today = _today()
    with Session(engine) as session:
        rows = session.exec(
            select(Listing).where(Listing.status == "published").order_by(Listing.id)
        ).all()
        results = []
        for listing in rows:
            try:
                deadline = _parse_deadline(listing.deadline)
            except ValueError:
                continue
            if deadline >= today:
                results.append(listing.model_dump())
        return results


def list_pending_for_admin() -> list[dict[str, Any]]:
    with Session(engine) as session:
        rows = session.exec(
            select(Listing).where(Listing.status == "pending").order_by(Listing.id)
        ).all()
        return [r.model_dump() for r in rows]


def list_listings_for_employer(employer_id: int) -> dict[str, Any]:
    user = get_user(employer_id)
    if not user or user["role"] != "employer":
        return {"ok": False, "error": "employers only"}
    with Session(engine) as session:
        rows = session.exec(
            select(Listing)
            .where(Listing.employer_id == employer_id)
            .order_by(Listing.id)
        ).all()
        return {"ok": True, "listings": [r.model_dump() for r in rows]}


def submit_listing(
    employer_id: int,
    title: str,
    company: str,
    description: str,
    apply_mode: str,
    deadline: str,
    external_url: str | None = None,
) -> dict[str, Any]:
    user = get_user(employer_id)
    if not user or user["role"] != "employer":
        return {"ok": False, "error": "employers only"}
    error = _validate_listing_details(
        title, company, description, apply_mode, deadline, external_url
    )
    if error:
        return {"ok": False, "error": error}

    with Session(engine) as session:
        listing = Listing(
            employer_id=employer_id,
            title=title,
            company=company,
            description=description,
            apply_mode=apply_mode,
            external_url=external_url,
            deadline=deadline,
            status="pending",
        )
        session.add(listing)
        session.commit()
        session.refresh(listing)
        return {"ok": True, "listing_id": listing.id, "status": listing.status}


def publish_listing(admin_id: int, listing_id: int) -> dict[str, Any]:
    admin = get_user(admin_id)
    if not admin or admin["role"] != "admin":
        return {"ok": False, "error": "admin only"}
    with Session(engine) as session:
        listing = session.get(Listing, listing_id)
        if listing is None:
            return {"ok": False, "error": "listing not found"}
        if listing.status != "pending":
            return {"ok": False, "error": "only pending listings can be published"}
        error = _validate_listing_details(
            listing.title,
            listing.company,
            listing.description,
            listing.apply_mode,
            listing.deadline,
            listing.external_url,
        )
        if error:
            return {"ok": False, "error": error}
        listing.status = "published"
        session.add(listing)
        # notify subscribers when the job gets published
        count = notify_observers(
            session,
            "listing_published",
            {"listing_id": listing.id, "title": listing.title, "company": listing.company},
        )
        session.commit()
    # DEFECT: publish does not notify subscribers
    return {"ok": True, "notified": count > 0}


def reject_listing(admin_id: int, listing_id: int) -> dict[str, Any]:
    admin = get_user(admin_id)
    if not admin or admin["role"] != "admin":
        return {"ok": False, "error": "admin only"}
    with Session(engine) as session:
        listing = session.get(Listing, listing_id)
        if listing is None:
            return {"ok": False, "error": "listing not found"}
        if listing.status != "pending":
            return {"ok": False, "error": "only pending listings can be rejected"}
        listing.status = "rejected"
        session.add(listing)
        session.commit()
        session.refresh(listing)
        return {"ok": True, "listing_id": listing.id, "status": listing.status}


def update_listing(
    employer_id: int,
    listing_id: int,
    title: str,
    company: str,
    description: str,
    apply_mode: str,
    deadline: str,
    external_url: str | None = None,
) -> dict[str, Any]:
    user = get_user(employer_id)
    if not user or user["role"] != "employer":
        return {"ok": False, "error": "employers only"}
    with Session(engine) as session:
        listing = session.get(Listing, listing_id)
        if listing is None:
            return {"ok": False, "error": "listing not found"}
        if listing.employer_id != employer_id:
            return {"ok": False, "error": "forbidden"}
        if listing.status != "rejected":
            return {"ok": False, "error": "only rejected listings can be edited"}
        error = _validate_listing_details(
            title, company, description, apply_mode, deadline, external_url
        )
        if error:
            return {"ok": False, "error": error}
        listing.title = title
        listing.company = company
        listing.description = description
        listing.apply_mode = apply_mode
        listing.deadline = deadline
        listing.external_url = external_url
        session.add(listing)
        session.commit()
        session.refresh(listing)
        return {"ok": True, "listing_id": listing.id, "status": listing.status}


def resubmit_listing(employer_id: int, listing_id: int) -> dict[str, Any]:
    user = get_user(employer_id)
    if not user or user["role"] != "employer":
        return {"ok": False, "error": "employers only"}
    with Session(engine) as session:
        listing = session.get(Listing, listing_id)
        if listing is None:
            return {"ok": False, "error": "listing not found"}
        if listing.employer_id != employer_id:
            return {"ok": False, "error": "forbidden"}
        if listing.status != "rejected":
            return {"ok": False, "error": "only rejected listings can be resubmitted"}
        error = _validate_listing_details(
            listing.title,
            listing.company,
            listing.description,
            listing.apply_mode,
            listing.deadline,
            listing.external_url,
        )
        if error:
            return {"ok": False, "error": error}
        listing.status = "pending"
        session.add(listing)
        session.commit()
        session.refresh(listing)
        return {"ok": True, "listing_id": listing.id, "status": listing.status}


def notify_subscribers(admin_id: int, listing_id: int) -> dict[str, Any]:
    admin = get_user(admin_id)
    if not admin or admin["role"] != "admin":
        return {"ok": False, "error": "admin only"}
    with Session(engine) as session:
        listing = session.get(Listing, listing_id)
        if listing is None:
            return {"ok": False, "error": "listing not found"}
        if listing.status != "published":
            return {"ok": False, "error": "listing is not published"}
        # dont send the same notification again
        count = notify_observers(
            session,
            "listing_published",
            {"listing_id": listing.id, "title": listing.title, "company": listing.company},
        )
        if count:
            session.commit()
        return {"ok": True, "count": count}
