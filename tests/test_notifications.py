"""sprint 2 tests for the job board"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlmodel import Session, select

from app.models.application import Application
from app.models.application_status_history import ApplicationStatusHistory
from app.models.listing import Listing
from app.models.notification import Notification
from app.models.user import User
from app.routers.board import router
from app.services import applications, board_auth, listings
from app.utilities.security import encrypt_password

EMPLOYER = 1
OTHER_EMPLOYER = 2
ADMIN = 3
GRADUATE = 4
SECOND_GRADUATE = 5
INELIGIBLE_GRADUATE = 6


@pytest.fixture
def board(test_session, monkeypatch, api_auth):
    engine = test_session.get_bind()
    for service in (applications, listings, board_auth):
        monkeypatch.setattr(service, "engine", engine)

    people = [
        (EMPLOYER, "employer", "employer", None),
        (OTHER_EMPLOYER, "other-employer", "employer", None),
        (ADMIN, "admin", "admin", None),
        (GRADUATE, "graduate", "graduate", "DCIT"),
        (SECOND_GRADUATE, "second-graduate", "graduate", "DCIT"),
        (INELIGIBLE_GRADUATE, "ineligible", "graduate", "OTHER"),
    ]
    test_session.add_all(
        User(
            id=user_id,
            username=username,
            email=f"{username}@example.com",
            password="not-used-in-these-route-tests",
            role=role,
            programme=programme,
        )
        for user_id, username, role, programme in people
    )
    test_session.commit()

    app = FastAPI()
    app.include_router(router, prefix="/api")
    install_auth, authenticate = api_auth
    install_auth(app)
    with TestClient(app) as client:
        client.authenticate = lambda user_id: authenticate(client, user_id)
        yield client, engine


def create_listing(engine, *, status="pending"):
    with Session(engine) as session:
        listing = Listing(
            employer_id=EMPLOYER,
            title="Junior Developer",
            company="Example Ltd",
            description="Develop software",
            apply_mode="collect",
            deadline="2099-12-31",
            status=status,
        )
        session.add(listing)
        session.commit()
        session.refresh(listing)
        return listing.id


def create_application(engine, listing_id, *, graduate_id=GRADUATE):
    with Session(engine) as session:
        application = Application(
            listing_id=listing_id,
            graduate_id=graduate_id,
            cover_letter="I would like the role",
            resume_text="Python and SQL",
        )
        session.add(application)
        session.commit()
        session.refresh(application)
        return application.id


def rows(engine, cls):
    with Session(engine) as session:
        return session.exec(select(cls).order_by(cls.id)).all()


def post_ok(client, path, actor, **payload):
    client.authenticate(actor)
    response = client.post(path, json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def test_api_login_cookie_is_authoritative_over_actor_id(board):
    client, engine = board
    with Session(engine) as session:
        user = session.get(User, EMPLOYER)
        user.password = encrypt_password("employer-test-password")
        session.add(user)
        session.commit()

    login = client.post(
        "/api/auth/login",
        json={
            "email": "employer@example.com",
            "password": "employer-test-password",
        },
    )

    assert login.status_code == 200
    assert login.json()["user"]["id"] == EMPLOYER
    assert "password" not in login.json()["user"]
    assert "httponly" in login.headers["set-cookie"].lower()
    denied = client.get(
        "/api/admin/listings/pending", params={"actor_id": ADMIN}
    )
    assert denied.status_code == 403


def test_publication_notifies_subscribers_automatically_once(board):
    client, engine = board
    listing_id = create_listing(engine)
    post_ok(client, "/api/graduates/subscribe", GRADUATE)
    post_ok(client, "/api/graduates/subscribe", SECOND_GRADUATE)

    published = post_ok(client, f"/api/admin/listings/{listing_id}/publish", ADMIN)
    assert published == {"ok": True, "notified": True}
    notifications = rows(engine, Notification)
    assert {n.user_id for n in notifications} == {GRADUATE, SECOND_GRADUATE}
    assert len(notifications) == 2
    assert all(f"#{listing_id}" in n.message for n in notifications)

    client.authenticate(GRADUATE)
    inbox = client.get(
        "/api/graduates/notifications"
    )
    assert inbox.status_code == 200
    assert len(inbox.json()["notifications"]) == 1
    assert inbox.json()["notifications"][0]["user_id"] == GRADUATE

    # dont send the same message twice
    manual = post_ok(client, f"/api/admin/listings/{listing_id}/notify", ADMIN)
    assert manual == {"ok": True, "count": 0}
    assert len(rows(engine, Notification)) == 2
    client.authenticate(ADMIN)
    republish = client.post(f"/api/admin/listings/{listing_id}/publish", json={})
    assert republish.status_code == 400
    assert len(rows(engine, Notification)) == 2


def test_rejected_or_unauthorized_publication_does_not_notify(board):
    client, engine = board
    listing_id = create_listing(engine)
    post_ok(client, "/api/graduates/subscribe", GRADUATE)

    invalid = client.post(
        f"/api/admin/listings/{listing_id}/publish",
        json={},
    )
    assert invalid.status_code == 403
    assert rows(engine, Notification) == []

    rejected = post_ok(client, f"/api/admin/listings/{listing_id}/reject", ADMIN)
    assert rejected["status"] == "rejected"
    assert rows(engine, Notification) == []
    invalid = client.post(
        f"/api/admin/listings/{listing_id}/publish",
        json={},
    )
    assert invalid.status_code == 400
    assert rows(engine, Notification) == []


def test_application_flow_notifies_only_applicant_and_records_history(board):
    client, engine = board
    listing_id = create_listing(engine, status="published")
    application_id = create_application(engine, listing_id)

    for action, expected in (
        ("mark_reviewed", "reviewed"),
        ("shortlist", "shortlisted"),
        ("hire", "hired"),
    ):
        result = post_ok(
            client,
            f"/api/applications/{application_id}/transition",
            EMPLOYER,
            action=action,
        )
        assert result["changed"] is True
        assert result["application"]["status"] == expected

    notifications = rows(engine, Notification)
    assert [n.user_id for n in notifications] == [GRADUATE] * 3
    client.authenticate(GRADUATE)
    inbox = client.get("/api/graduates/notifications")
    assert inbox.status_code == 200
    assert len(inbox.json()["notifications"]) == 3
    client.authenticate(SECOND_GRADUATE)
    other_inbox = client.get("/api/graduates/notifications")
    assert other_inbox.status_code == 200
    assert other_inbox.json()["notifications"] == []
    assert [n.message.split("to ")[-1] for n in notifications] == [
        "reviewed.", "shortlisted.", "hired."
    ]
    history = rows(engine, ApplicationStatusHistory)
    assert [(r.previous_status, r.new_status) for r in history] == [
        ("submitted", "reviewed"),
        ("reviewed", "shortlisted"),
        ("shortlisted", "hired"),
    ]
    assert all(r.actor_id == EMPLOYER for r in history)

    # invalid changes shouldnt save anything
    for actor, action in ((EMPLOYER, "reject"), (OTHER_EMPLOYER, "reject")):
        client.authenticate(actor)
        response = client.post(
            f"/api/applications/{application_id}/transition",
            json={"action": action},
        )
        assert response.status_code in (400, 403)
    assert len(rows(engine, Notification)) == 3
    assert len(rows(engine, ApplicationStatusHistory)) == 3


def test_failed_status_change_has_no_history_or_notification(board):
    client, engine = board
    listing_id = create_listing(engine, status="published")
    app_id = create_application(engine, listing_id)
    for actor, action in (
        (EMPLOYER, "hire"),
        (OTHER_EMPLOYER, "mark_reviewed"),
        (ADMIN, "mark_reviewed"),
    ):
        client.authenticate(actor)
        response = client.post(
            f"/api/applications/{app_id}/transition",
            json={"action": action},
        )
        assert response.status_code in (400, 403)
    assert rows(engine, Notification) == []
    assert rows(engine, ApplicationStatusHistory) == []
    assert rows(engine, Application)[0].status == "submitted"


def test_ineligible_graduate_cannot_apply_or_subscribe(board):
    client, engine = board
    listing_id = create_listing(engine, status="published")
    client.authenticate(INELIGIBLE_GRADUATE)
    subscribe = client.post("/api/graduates/subscribe", json={})
    assert subscribe.status_code == 400
    assert "programme" in subscribe.json()["detail"]
    apply = client.post(
        "/api/graduates/applications",
        json={
            "listing_id": listing_id,
            "cover_letter": "Hello",
        },
    )
    assert apply.status_code == 403
    assert "programme" in apply.json()["detail"]
    assert rows(engine, Application) == []
    assert rows(engine, Notification) == []


def test_failed_notification_insert_rolls_back_listing_status(board):
    """dont publish if notification save fails"""
    client, engine = board
    listing_id = create_listing(engine)
    post_ok(client, "/api/graduates/subscribe", GRADUATE)

    def block_notification(_conn, _cursor, sql, _params, _context, _many):
        if sql.lstrip().upper().startswith("INSERT INTO NOTIFICATION"):
            raise RuntimeError("simulated notification database failure")

    event.listen(engine, "before_cursor_execute", block_notification)
    try:
        with pytest.raises(RuntimeError, match="simulated notification"):
            client.authenticate(ADMIN)
            client.post(
                f"/api/admin/listings/{listing_id}/publish",
                json={},
            )
    finally:
        event.remove(engine, "before_cursor_execute", block_notification)

    assert rows(engine, Listing)[0].status == "pending"
    assert rows(engine, Notification) == []


def test_failed_notification_insert_rolls_back_application_and_history(board):
    client, engine = board
    listing_id = create_listing(engine, status="published")
    app_id = create_application(engine, listing_id)

    def block_notification(_conn, _cursor, sql, _params, _context, _many):
        if sql.lstrip().upper().startswith("INSERT INTO NOTIFICATION"):
            raise RuntimeError("simulated notification database failure")

    event.listen(engine, "before_cursor_execute", block_notification)
    try:
        with pytest.raises(RuntimeError, match="simulated notification"):
            client.authenticate(EMPLOYER)
            client.post(
                f"/api/applications/{app_id}/transition",
                json={"action": "mark_reviewed"},
            )
    finally:
        event.remove(engine, "before_cursor_execute", block_notification)

    assert rows(engine, Application)[0].status == "submitted"
    assert rows(engine, ApplicationStatusHistory) == []
    assert rows(engine, Notification) == []


def test_complete_listing_and_application_workflow(board):
    """check the full job application flow"""
    client, engine = board

    # student subscribes first
    post_ok(client, "/api/graduates/subscribe", GRADUATE)

    # new listing starts as pending
    created = post_ok(
        client,
        "/api/employer/listings",
        EMPLOYER,
        title="Junior Developer",
        company="Example Ltd",
        description="Develop software",
        apply_mode="collect",
        deadline="2099-12-31",
    )
    listing_id = created["listing_id"]
    assert created["status"] == "pending"

    # reject then resubmit the listing
    rejected = post_ok(client, f"/api/admin/listings/{listing_id}/reject", ADMIN)
    assert rejected["status"] == "rejected"
    client.authenticate(EMPLOYER)
    edited = client.put(
        f"/api/employer/listings/{listing_id}",
        json={
            "title": "Junior Python Developer",
            "company": "Example Ltd",
            "description": "Develop Python applications",
            "apply_mode": "collect",
            "deadline": "2099-12-31",
        },
    )
    assert edited.status_code == 200
    resubmitted = post_ok(
        client, f"/api/employer/listings/{listing_id}/resubmit", EMPLOYER
    )
    assert resubmitted["status"] == "pending"

    # notify the subscriber when published
    published = post_ok(client, f"/api/admin/listings/{listing_id}/publish", ADMIN)
    assert published["notified"] is True

    # student applies and employer reviews it
    application = post_ok(
        client,
        "/api/graduates/applications",
        GRADUATE,
        listing_id=listing_id,
        cover_letter="I am interested in this job",
    )
    application_id = application["application_id"]
    changed = post_ok(
        client,
        f"/api/applications/{application_id}/transition",
        EMPLOYER,
        action="mark_reviewed",
    )
    assert changed["application"]["status"] == "reviewed"

    # check the saved history
    history = client.get(
        f"/api/applications/{application_id}/history",
    )
    assert history.status_code == 200
    assert len(history.json()["history"]) == 1
    assert history.json()["history"][0]["new_status"] == "reviewed"

    # check both notifications
    client.authenticate(GRADUATE)
    inbox = client.get(
        "/api/graduates/notifications"
    )
    assert inbox.status_code == 200
    messages = [item["message"] for item in inbox.json()["notifications"]]
    assert len(messages) == 2
    assert any("New job published" in message for message in messages)
    assert any("status changed to reviewed" in message for message in messages)

    # other employers cant change this application
    client.authenticate(OTHER_EMPLOYER)
    denied = client.post(
        f"/api/applications/{application_id}/transition",
        json={"action": "shortlist"},
    )
    assert denied.status_code == 403
    assert len(rows(engine, Notification)) == 2
