"""Application service regressions using the existing in-memory SQLite fixture."""

from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlmodel import Session, select

from app.models.application import Application
from app.models.application_status_history import ApplicationStatusHistory
from app.models.listing import Listing
from app.models.user import User
from app.routers.board import router
from app.services import applications, board_auth, listings

EMPLOYER_ID = 1
OTHER_EMPLOYER_ID = 4
ADMIN_ID = 5
GRADUATE_ID = 2
OTHER_GRADUATE_ID = 3
LISTING_ID = 1
TODAY = date(2026, 11, 22)


@pytest.fixture
def service_engine(test_session, monkeypatch):
    engine = test_session.get_bind()
    monkeypatch.setattr(applications, "engine", engine)
    monkeypatch.setattr(board_auth, "engine", engine)
    monkeypatch.setattr(listings, "_today", lambda: TODAY)
    # These tests look up users; they do not authenticate passwords.
    test_session.add_all(
        [
            User(
                id=EMPLOYER_ID,
                username="employer",
                email="employer@example.com",
                password="unused",
                role="employer",
            ),
            User(
                id=GRADUATE_ID,
                username="graduate",
                email="graduate@example.com",
                password="unused",
                role="graduate",
                programme="DCIT",
                resume_text="Profile resume",
            ),
            User(
                id=OTHER_GRADUATE_ID,
                username="other",
                email="other@example.com",
                password="unused",
                role="graduate",
                programme="DCIT",
            ),
            User(
                id=OTHER_EMPLOYER_ID,
                username="other-employer",
                email="other-employer@example.com",
                password="unused",
                role="employer",
            ),
            User(
                id=ADMIN_ID,
                username="admin",
                email="admin@example.com",
                password="unused",
                role="admin",
            ),
            Listing(
                id=LISTING_ID,
                employer_id=EMPLOYER_ID,
                title="Developer",
                company="Example",
                description="Build software",
                apply_mode="collect",
                deadline="2099-12-31",
                status="published",
            ),
        ]
    )
    test_session.commit()
    return engine


def save_application(engine, status="submitted", graduate_id=GRADUATE_ID):
    with Session(engine) as session:
        application = Application(
            listing_id=LISTING_ID,
            graduate_id=graduate_id,
            cover_letter="Cover letter",
            resume_text="Resume",
            status=status,
        )
        session.add(application)
        session.commit()
        session.refresh(application)
        return application.model_dump()


@pytest.fixture
def database_activity(service_engine):
    activity = {"writes": [], "commits": []}

    def record_write(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
            activity["writes"].append(statement)

    def record_commit(connection):
        activity["commits"].append(True)

    event.listen(service_engine, "before_cursor_execute", record_write)
    event.listen(service_engine, "commit", record_commit)
    try:
        yield activity
    finally:
        event.remove(service_engine, "before_cursor_execute", record_write)
        event.remove(service_engine, "commit", record_commit)


@pytest.mark.parametrize(
    "resume, expected_resume, deadline",
    [
        ("Uploaded resume", "Uploaded resume", "2026-11-23"),
        (None, "Profile resume", "2026-11-23"),
        ("Uploaded resume", "Uploaded resume", TODAY.isoformat()),
    ],
)
def test_creation_starts_submitted(service_engine, resume, expected_resume, deadline):
    with Session(service_engine) as session:
        listing = session.get(Listing, LISTING_ID)
        listing.deadline = deadline
        session.add(listing)
        session.commit()

    result = applications.apply(GRADUATE_ID, LISTING_ID, "Cover letter", resume)

    assert result == {
        "ok": True,
        "application_id": result["application_id"],
        "status": "submitted",
    }
    with Session(service_engine) as session:
        saved = session.get(Application, result["application_id"])
        assert saved is not None
        assert saved.status == "submitted"
        assert saved.listing_id == LISTING_ID
        assert saved.graduate_id == GRADUATE_ID
        assert saved.cover_letter == "Cover letter"
        assert saved.resume_text == expected_resume


@pytest.mark.parametrize(
    "listing_changes, expected_error",
    [
        ({"status": "pending"}, "not published"),
        ({"status": "rejected"}, "not published"),
        ({"deadline": "2026-11-21"}, "deadline has passed"),
        ({"deadline": "invalid"}, "YYYY-MM-DD"),
        (
            {"apply_mode": "external", "external_url": "https://example.com/apply"},
            "https://example.com/apply",
        ),
        ({"apply_mode": "unknown"}, "does not accept on-platform applications"),
    ],
)
def test_rejected_submission_does_not_write_or_commit(
    service_engine,
    database_activity,
    listing_changes,
    expected_error,
):
    original = save_application(service_engine)
    with Session(service_engine) as session:
        listing = session.get(Listing, LISTING_ID)
        for field, value in listing_changes.items():
            setattr(listing, field, value)
        session.add(listing)
        session.commit()
    # Exclude setup writes and observe only the attempted submission.
    database_activity["writes"].clear()
    database_activity["commits"].clear()

    result = applications.apply(GRADUATE_ID, LISTING_ID, "Cover letter", "Resume")

    assert set(result) == {"ok", "error"}
    assert result["ok"] is False
    assert expected_error in result["error"]
    with Session(service_engine) as session:
        saved = session.exec(select(Application).order_by(Application.id)).all()
        assert [row.model_dump() for row in saved] == [original]
    assert database_activity == {"writes": [], "commits": []}


@pytest.mark.parametrize(
    "status, action, target",
    [
        ("submitted", "mark_reviewed", "reviewed"),
        ("reviewed", "shortlist", "shortlisted"),
        ("reviewed", "reject", "rejected"),
        ("shortlisted", "hire", "hired"),
        ("shortlisted", "reject", "rejected"),
    ],
)
def test_successful_transition_is_persisted(service_engine, status, action, target):
    original = save_application(service_engine, status)

    result = applications.transition_application(EMPLOYER_ID, original["id"], action)

    expected = {**original, "status": target}
    assert result == {"ok": True, "application": expected, "changed": True}
    with Session(service_engine) as session:
        assert session.get(Application, original["id"]).model_dump() == expected


@pytest.mark.parametrize(
    "status, action",
    [
        ("submitted", "hire"),
        ("reviewed", "mark_reviewed"),
        ("rejected", "mark_reviewed"),
        ("hired", "hire"),
        ("withdrawn", "reject"),
        ("submitted", "reopen"),
    ],
)
def test_failed_transition_does_not_write_or_commit(
    service_engine,
    database_activity,
    status,
    action,
):
    original = save_application(service_engine, status)
    # Ignore the setup INSERT and commit; observe only the service operation.
    database_activity["writes"].clear()
    database_activity["commits"].clear()

    result = applications.transition_application(EMPLOYER_ID, original["id"], action)

    assert set(result) == {"ok", "error"}
    assert result["ok"] is False
    assert isinstance(result["error"], str) and result["error"]
    with Session(service_engine) as session:
        assert session.get(Application, original["id"]).model_dump() == original
    assert database_activity == {"writes": [], "commits": []}


def test_graduate_response_uses_stored_status(service_engine):
    statuses = (
        "submitted",
        "reviewed",
        "shortlisted",
        "rejected",
        "hired",
        "withdrawn",
    )
    expected = [save_application(service_engine, status) for status in statuses]
    save_application(service_engine, graduate_id=OTHER_GRADUATE_ID)

    result = applications.my_applications(GRADUATE_ID)

    assert result == expected
    assert [row["status"] for row in result] == list(statuses)
    for row in result:
        assert set(row) == {
            "id",
            "listing_id",
            "graduate_id",
            "cover_letter",
            "resume_text",
            "status",
        }


@pytest.mark.parametrize("actor_id", [OTHER_EMPLOYER_ID, ADMIN_ID, GRADUATE_ID])
def test_unauthorized_transition_is_forbidden(
    service_engine, database_activity, actor_id
):
    original = save_application(service_engine)
    database_activity["writes"].clear()
    database_activity["commits"].clear()

    result = applications.transition_application(
        actor_id, original["id"], "mark_reviewed"
    )

    assert result == {"ok": False, "error": "forbidden"}
    with Session(service_engine) as session:
        assert session.get(Application, original["id"]).model_dump() == original
    assert database_activity == {"writes": [], "commits": []}


@pytest.mark.parametrize("actor_id", [OTHER_EMPLOYER_ID, ADMIN_ID, GRADUATE_ID])
def test_transition_route_returns_403_for_unauthorized_actor(
    service_engine, database_activity, actor_id
):
    original = save_application(service_engine)
    app = FastAPI()
    app.include_router(router, prefix="/api")

    database_activity["writes"].clear()
    database_activity["commits"].clear()

    with TestClient(app) as client:
        response = client.post(
            f"/api/applications/{original['id']}/transition",
            json={"actor_id": actor_id, "action": "mark_reviewed"},
        )

    assert response.status_code == 403
    assert response.json() == {"detail": "forbidden"}
    with Session(service_engine) as session:
        assert session.get(Application, original["id"]).model_dump() == original
    assert database_activity == {"writes": [], "commits": []}


def test_owner_can_view_listing_applicants(service_engine):
    original = save_application(service_engine)

    result = applications.listing_applicants(EMPLOYER_ID, LISTING_ID)

    assert result == {"ok": True, "applicants": [original]}


@pytest.mark.parametrize("actor_id", [OTHER_EMPLOYER_ID, GRADUATE_ID])
def test_unauthorized_actor_cannot_view_listing_applicants(
    service_engine, actor_id
):
    save_application(service_engine)

    result = applications.listing_applicants(actor_id, LISTING_ID)

    assert result == {"ok": False, "error": "forbidden"}


def test_applicant_route_returns_403_for_cross_employer(service_engine):
    save_application(service_engine)
    app = FastAPI()
    app.include_router(router, prefix="/api")

    with TestClient(app) as client:
        response = client.get(
            f"/api/listings/{LISTING_ID}/applicants",
            params={"actor_id": OTHER_EMPLOYER_ID},
        )

    assert response.status_code == 403
    assert response.json() == {"detail": "forbidden"}


def test_admin_can_view_but_cannot_transition_applications(service_engine):
    original = save_application(service_engine)

    viewed = applications.listing_applicants(ADMIN_ID, LISTING_ID)
    transitioned = applications.transition_application(
        ADMIN_ID, original["id"], "mark_reviewed"
    )

    assert viewed == {"ok": True, "applicants": [original]}
    assert transitioned == {"ok": False, "error": "forbidden"}


def test_successful_transition_persists_history(service_engine):
    original = save_application(service_engine)

    result = applications.transition_application(
        EMPLOYER_ID, original["id"], "mark_reviewed"
    )

    assert result["ok"] is True
    with Session(service_engine) as session:
        history = session.exec(
            select(ApplicationStatusHistory)
            .where(ApplicationStatusHistory.application_id == original["id"])
        ).all()

    assert len(history) == 1
    assert history[0].application_id == original["id"]
    assert history[0].previous_status == "submitted"
    assert history[0].new_status == "reviewed"
    assert history[0].actor_id == EMPLOYER_ID
    assert history[0].timestamp is not None


@pytest.mark.parametrize(
    "status,action,actor_id",
    [
        ("submitted", "hire", EMPLOYER_ID),
        ("submitted", "mark_reviewed", OTHER_EMPLOYER_ID),
        ("submitted", "mark_reviewed", ADMIN_ID),
        ("submitted", "mark_reviewed", GRADUATE_ID),
    ],
)
def test_failed_or_unauthorized_transition_creates_no_history(
    service_engine, status, action, actor_id
):
    original = save_application(service_engine, status)

    result = applications.transition_application(
        actor_id, original["id"], action
    )

    assert result["ok"] is False
    with Session(service_engine) as session:
        history = session.exec(
            select(ApplicationStatusHistory)
            .where(ApplicationStatusHistory.application_id == original["id"])
        ).all()
    assert history == []


@pytest.mark.parametrize(
    "actor_id",
    [EMPLOYER_ID, GRADUATE_ID, ADMIN_ID],
)
def test_authorized_history_view_is_exposed(service_engine, actor_id):
    original = save_application(service_engine)
    applications.transition_application(
        EMPLOYER_ID, original["id"], "mark_reviewed"
    )

    result = applications.application_history(actor_id, original["id"])

    assert result["ok"] is True
    assert len(result["history"]) == 1
    assert result["history"][0]["previous_status"] == "submitted"
    assert result["history"][0]["new_status"] == "reviewed"
    assert result["history"][0]["actor_id"] == EMPLOYER_ID


def test_history_route_returns_entry(service_engine):
    original = save_application(service_engine)
    applications.transition_application(
        EMPLOYER_ID, original["id"], "mark_reviewed"
    )
    app = FastAPI()
    app.include_router(router, prefix="/api")

    with TestClient(app) as client:
        response = client.get(
            f"/api/applications/{original['id']}/history",
            params={"actor_id": GRADUATE_ID},
        )

    assert response.status_code == 200
    assert response.json()["history"][0]["new_status"] == "reviewed"
