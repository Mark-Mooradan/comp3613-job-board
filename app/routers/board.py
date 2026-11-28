"""Job-board scenario JSON API (OpenAPI /docs)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

from app.dependencies.auth import AuthDep
from app.services import applications, listings
from app.services import board_auth as auth
from app.utilities.security import access_token_cookie_kwargs, create_access_token

router = APIRouter(tags=["job-board"])


class LoginBody(BaseModel):
    email: str
    password: str


class ListingBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    company: str
    description: str
    apply_mode: str = Field(description="collect | external")
    deadline: str = Field(description="ISO date YYYY-MM-DD")
    external_url: str | None = None


class ApplyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    listing_id: int
    cover_letter: str
    resume_text: str | None = None


class TransitionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str = Field(description="mark_reviewed | shortlist | reject | hire")


@router.post("/auth/login")
def login(body: LoginBody, response: Response) -> dict[str, Any]:
    user = auth.login(body.email, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="invalid credentials")
    response.set_cookie(
        key="access_token",
        value=create_access_token(
            {"sub": str(user["id"]), "role": user["role"]}
        ),
        **access_token_cookie_kwargs(),
    )
    return {"user": user}


@router.post("/graduates/subscribe")
def subscribe(actor: AuthDep) -> dict[str, Any]:
    result = listings.subscribe(actor.id)
    if not result.get("ok"):
        status_code = 403 if result.get("error") == "graduates only" else 400
        raise HTTPException(status_code=status_code, detail=result.get("error"))
    return result


@router.get("/graduates/notifications")
def graduate_notifications(actor: AuthDep) -> dict[str, Any]:
    result = applications.my_notifications(actor.id)
    if not result.get("ok"):
        raise HTTPException(status_code=403, detail=result.get("error"))
    return result


@router.get("/jobs")
def jobs() -> dict[str, Any]:
    return {"jobs": listings.list_jobs_for_graduates()}


@router.get("/admin/listings/pending")
def pending(actor: AuthDep) -> dict[str, Any]:
    if actor.role != "admin":
        raise HTTPException(status_code=403, detail="admin only")
    return {"listings": listings.list_pending_for_admin()}


@router.post("/employer/listings")
def submit_listing(body: ListingBody, actor: AuthDep) -> dict[str, Any]:
    result = listings.submit_listing(
        actor.id,
        body.title,
        body.company,
        body.description,
        body.apply_mode,
        body.deadline,
        body.external_url,
    )
    if not result.get("ok"):
        status_code = 403 if result.get("error") == "employers only" else 400
        raise HTTPException(status_code=status_code, detail=result.get("error"))
    return result


@router.get("/employer/listings")
def employer_listings(actor: AuthDep) -> dict[str, Any]:
    result = listings.list_listings_for_employer(actor.id)
    if not result.get("ok"):
        raise HTTPException(status_code=403, detail=result.get("error"))
    return result


@router.put("/employer/listings/{listing_id}")
def update_listing(listing_id: int, body: ListingBody, actor: AuthDep) -> dict[str, Any]:
    result = listings.update_listing(
        actor.id,
        listing_id,
        body.title,
        body.company,
        body.description,
        body.apply_mode,
        body.deadline,
        body.external_url,
    )
    if not result.get("ok"):
        error = result.get("error")
        status_code = 403 if error in {"forbidden", "employers only"} else 400
        raise HTTPException(status_code=status_code, detail=error)
    return result


@router.post("/employer/listings/{listing_id}/resubmit")
def resubmit(listing_id: int, actor: AuthDep) -> dict[str, Any]:
    result = listings.resubmit_listing(actor.id, listing_id)
    if not result.get("ok"):
        error = result.get("error")
        status_code = 403 if error in {"forbidden", "employers only"} else 400
        raise HTTPException(status_code=status_code, detail=error)
    return result


@router.post("/admin/listings/{listing_id}/publish")
def publish(listing_id: int, actor: AuthDep) -> dict[str, Any]:
    result = listings.publish_listing(actor.id, listing_id)
    if not result.get("ok"):
        error = result.get("error")
        status_code = 403 if error in {"forbidden", "admin only"} else 400
        raise HTTPException(status_code=status_code, detail=error)
    return result


@router.post("/admin/listings/{listing_id}/reject")
def reject(listing_id: int, actor: AuthDep) -> dict[str, Any]:
    result = listings.reject_listing(actor.id, listing_id)
    if not result.get("ok"):
        error = result.get("error")
        status_code = 403 if error in {"forbidden", "admin only"} else 400
        raise HTTPException(status_code=status_code, detail=error)
    return result


@router.post("/admin/listings/{listing_id}/notify")
def notify(listing_id: int, actor: AuthDep) -> dict[str, Any]:
    result = listings.notify_subscribers(actor.id, listing_id)
    if not result.get("ok"):
        error = result.get("error")
        status_code = 403 if error in {"forbidden", "admin only"} else 400
        raise HTTPException(status_code=status_code, detail=error)
    return result


@router.post("/graduates/applications")
def apply(body: ApplyBody, actor: AuthDep) -> dict[str, Any]:
    result = applications.apply(
        actor.id, body.listing_id, body.cover_letter, body.resume_text
    )
    if not result.get("ok"):
        error = result.get("error")
        status_code = (
            403 if error in {"graduates only", "programme not eligible"} else 400
        )
        raise HTTPException(status_code=status_code, detail=error)
    return result


@router.get("/graduates/applications")
def my_apps(actor: AuthDep) -> dict[str, Any]:
    if actor.role != "graduate":
        raise HTTPException(status_code=403, detail="graduates only")
    return {"applications": applications.my_applications(actor.id)}


@router.get("/listings/{listing_id}/applicants")
def applicants(listing_id: int, actor: AuthDep) -> dict[str, Any]:
    result = applications.listing_applicants(actor.id, listing_id)
    if not result.get("ok"):
        raise HTTPException(status_code=403, detail=result.get("error"))
    return result


@router.get("/admin/listings/{listing_id}/export")
def export(listing_id: int, actor: AuthDep) -> dict[str, Any]:
    result = applications.export_applicants(actor.id, listing_id)
    if not result.get("ok"):
        raise HTTPException(status_code=403, detail=result.get("error"))
    return result


@router.post("/applications/{application_id}/transition")
def transition(application_id: int, body: TransitionBody, actor: AuthDep) -> dict[str, Any]:
    result = applications.transition_application(
        actor.id, application_id, body.action
    )
    if not result.get("ok"):
        status_code = 403 if result.get("error") == "forbidden" else 400
        raise HTTPException(status_code=status_code, detail=result.get("error"))
    return result


@router.get("/applications/{application_id}/history")
def application_history(application_id: int, actor: AuthDep) -> dict[str, Any]:
    result = applications.application_history(actor.id, application_id)
    if not result.get("ok"):
        status_code = 403 if result.get("error") == "forbidden" else 400
        raise HTTPException(status_code=status_code, detail=result.get("error"))
    return result
