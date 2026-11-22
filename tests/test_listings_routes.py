"""Listing API regressions using the real board router and in-memory SQLite."""

from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlmodel import Session, select

from app.models.listing import Listing
from app.models.user import User
from app.routers.board import router
from app.services import board_auth, listings

ADMIN, OWNER, OTHER, GRADUATE = 1, 2, 3, 4
DETAILS = {
    "title": "Developer",
    "company": "Example",
    "description": "Build software",
    "apply_mode": "collect",
    "deadline": "2026-11-22",
    "external_url": None,
}


@pytest.fixture
def api_client(test_session, monkeypatch):
    engine = test_session.get_bind()
    monkeypatch.setattr(listings, "engine", engine)
    monkeypatch.setattr(board_auth, "engine", engine)
    monkeypatch.setattr(listings, "_today", lambda: date(2026, 11, 22))
    for user_id, username, role in (
        (ADMIN, "admin", "admin"),
        (OWNER, "owner", "employer"),
        (OTHER, "other", "employer"),
        (GRADUATE, "graduate", "graduate"),
    ):
        test_session.add(
            User(
                id=user_id,
                username=username,
                email=f"{username}@example.com",
                password="unused",
                role=role,
            )
        )
    test_session.commit()
    # Mount the production router without the main app's startup seeding.
    app = FastAPI()
    app.include_router(router, prefix="/api")
    with TestClient(app) as client:
        yield client


def save_listing(test_session, status="pending", employer_id=OWNER):
    listing = Listing(employer_id=employer_id, status=status, **DETAILS)
    test_session.add(listing)
    test_session.commit()
    test_session.refresh(listing)
    return listing.model_dump()


def snapshot(test_session):
    with Session(test_session.get_bind()) as session:
        return [
            row.model_dump()
            for row in session.exec(select(Listing).order_by(Listing.id)).all()
        ]


@pytest.fixture
def assert_rejected_request(api_client, test_session):
    def check(method, path, status_code=400, error=None, **kwargs):
        engine = test_session.get_bind()
        before = snapshot(test_session)
        activity = []

        def record_write(
            connection, cursor, statement, parameters, context, executemany
        ):
            if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
                activity.append(statement)

        def record_commit(connection):
            activity.append("COMMIT")

        event.listen(engine, "before_cursor_execute", record_write)
        event.listen(engine, "commit", record_commit)
        try:
            response = api_client.request(method, path, **kwargs)
        finally:
            event.remove(engine, "before_cursor_execute", record_write)
            event.remove(engine, "commit", record_commit)
        assert response.status_code == status_code
        body = response.json()
        assert set(body) == {"detail"}
        if error is not None:
            assert body["detail"] == error
        assert activity == []
        assert snapshot(test_session) == before
        return body

    return check


def ok(client, method, path, **kwargs):
    response = client.request(method, path, **kwargs)
    assert response.status_code == 200, response.text
    return response.json()


def test_complete_listing_review_cycle(api_client, test_session):
    created_details = {**DETAILS, "deadline": "2026-11-23"}
    created = ok(
        api_client,
        "POST",
        "/api/employer/listings",
        json={**created_details, "actor_id": OWNER},
    )
    listing_id = created["listing_id"]
    assert created == {"ok": True, "listing_id": listing_id, "status": "pending"}
    assert snapshot(test_session) == [
        {
            "id": listing_id,
            "employer_id": OWNER,
            "status": "pending",
            **created_details,
        }
    ]
    assert ok(api_client, "GET", "/api/jobs") == {"jobs": []}
    rejected = ok(
        api_client,
        "POST",
        f"/api/admin/listings/{listing_id}/reject",
        json={"actor_id": ADMIN},
    )
    assert rejected == {"ok": True, "listing_id": listing_id, "status": "rejected"}
    # Change every editable field, including the deadline from tomorrow to today.
    revised = {
        "title": "Revised role",
        "company": "Revised company",
        "description": "Revised description",
        "apply_mode": "external",
        "deadline": "2026-11-22",
        "external_url": "https://example.com/apply",
    }
    edited = ok(
        api_client,
        "PUT",
        f"/api/employer/listings/{listing_id}",
        json={**revised, "actor_id": OWNER},
    )
    assert edited == {"ok": True, "listing_id": listing_id, "status": "rejected"}
    expected = {"id": listing_id, "employer_id": OWNER, "status": "rejected", **revised}
    assert snapshot(test_session) == [expected]
    assert ok(api_client, "GET", "/api/jobs") == {"jobs": []}
    assert ok(
        api_client, "GET", "/api/employer/listings", params={"actor_id": OWNER}
    ) == {
        "ok": True,
        "listings": [expected],
    }
    resubmitted = ok(
        api_client,
        "POST",
        f"/api/employer/listings/{listing_id}/resubmit",
        json={"actor_id": OWNER},
    )
    assert resubmitted == {"ok": True, "listing_id": listing_id, "status": "pending"}
    expected["status"] = "pending"
    assert snapshot(test_session) == [expected]
    assert ok(api_client, "GET", "/api/jobs") == {"jobs": []}
    assert ok(
        api_client, "GET", "/api/admin/listings/pending", params={"actor_id": ADMIN}
    ) == {"listings": [expected]}
    assert ok(
        api_client,
        "POST",
        f"/api/admin/listings/{listing_id}/publish",
        json={"actor_id": ADMIN},
    ) == {
        "ok": True,
        "notified": False,
    }
    expected["status"] = "published"
    assert snapshot(test_session) == [expected]
    # The deadline is today, so the published listing must be visible.
    assert ok(api_client, "GET", "/api/jobs") == {"jobs": [expected]}


@pytest.mark.parametrize("actor", [OWNER, OTHER])
def test_employer_endpoint_returns_only_owned_listings(api_client, test_session, actor):
    for employer in (OWNER, OTHER):
        for status in ("pending", "rejected", "published"):
            save_listing(test_session, status, employer)
    expected = [row for row in snapshot(test_session) if row["employer_id"] == actor]

    assert ok(
        api_client, "GET", "/api/employer/listings", params={"actor_id": actor}
    ) == {
        "ok": True,
        "listings": expected,
    }


@pytest.mark.parametrize("actor", [ADMIN, GRADUATE, 999])
def test_employer_endpoint_rejects_invalid_actors(assert_rejected_request, actor):
    assert_rejected_request(
        "GET",
        "/api/employer/listings",
        403,
        "employers only",
        params={"actor_id": actor},
    )


@pytest.mark.parametrize(
    "method, path, status, actor, error",
    [
        ("POST", "/admin/listings/{id}/reject", "pending", OWNER, "admin only"),
        ("PUT", "/employer/listings/{id}", "rejected", OTHER, "forbidden"),
        ("POST", "/employer/listings/{id}/resubmit", "rejected", OTHER, "forbidden"),
    ],
)
def test_invalid_api_operations_do_not_write(
    test_session,
    assert_rejected_request,
    method,
    path,
    status,
    actor,
    error,
):
    original = save_listing(test_session, status)
    body = {"actor_id": actor}
    if method == "PUT":
        body.update(DETAILS)
    assert_rejected_request(
        method, "/api" + path.format(id=original["id"]), error=error, json=body
    )


def test_invalid_edit_deadline_returns_400_without_writes(
    test_session, assert_rejected_request
):
    original = save_listing(test_session, "rejected")
    assert_rejected_request(
        "PUT",
        f"/api/employer/listings/{original['id']}",
        json={**DETAILS, "deadline": "invalid", "actor_id": OWNER},
    )


@pytest.mark.parametrize(
    "method, path, body",
    [
        ("POST", "/api/admin/listings/1/reject", {}),
        ("PUT", "/api/employer/listings/1", {"actor_id": OWNER}),
    ],
)
def test_missing_request_fields_return_422(assert_rejected_request, method, path, body):
    assert_rejected_request(method, path, 422, json=body)


def test_employer_query_requires_actor_id(assert_rejected_request):
    assert_rejected_request("GET", "/api/employer/listings", 422)
