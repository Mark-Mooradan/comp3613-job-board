"""Listing lifecycle and persistence regressions using in-memory SQLite."""

from datetime import date

import pytest
from sqlalchemy import event
from sqlmodel import Session, select

from app.models.listing import Listing
from app.models.user import User
from app.services import board_auth, listings

ADMIN, OWNER, OTHER, GRADUATE = 1, 2, 3, 4
TODAY = date(2026, 11, 22)
DETAILS = {
    "title": "Developer",
    "company": "Example",
    "description": "Build software",
    "apply_mode": "collect",
    "deadline": "2026-11-23",
    "external_url": None,
}


@pytest.fixture
def listing_engine(test_session, monkeypatch):
    engine = test_session.get_bind()
    monkeypatch.setattr(listings, "engine", engine)
    monkeypatch.setattr(board_auth, "engine", engine)
    monkeypatch.setattr(listings, "_today", lambda: TODAY)
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
    return engine


def save_listing(engine, status="pending", employer_id=OWNER, **changes):
    with Session(engine) as session:
        listing = Listing(
            employer_id=employer_id, status=status, **{**DETAILS, **changes}
        )
        session.add(listing)
        session.commit()
        session.refresh(listing)
        return listing.model_dump()


def snapshot(engine):
    with Session(engine) as session:
        return [
            row.model_dump()
            for row in session.exec(select(Listing).order_by(Listing.id)).all()
        ]


def change_listing(action, actor_id, listing_id, **details):
    if action == "update":
        return listings.update_listing(actor_id, listing_id, **{**DETAILS, **details})
    return getattr(listings, f"{action}_listing")(actor_id, listing_id)


@pytest.fixture
def assert_refused(listing_engine):
    """Observe only the operation, excluding fixture setup writes."""

    def check(operation):
        before = snapshot(listing_engine)
        activity = []

        def record_write(
            connection, cursor, statement, parameters, context, executemany
        ):
            if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
                activity.append(statement)

        def record_commit(connection):
            activity.append("COMMIT")

        event.listen(listing_engine, "before_cursor_execute", record_write)
        event.listen(listing_engine, "commit", record_commit)
        try:
            result = operation()
        finally:
            event.remove(listing_engine, "before_cursor_execute", record_write)
            event.remove(listing_engine, "commit", record_commit)
        assert set(result) == {"ok", "error"}
        assert result["ok"] is False
        assert isinstance(result["error"], str) and result["error"]
        assert activity == []
        assert snapshot(listing_engine) == before
        return result

    return check


@pytest.mark.parametrize(
    "mode, url",
    [
        ("collect", None),
        ("external", "https://example.com/apply"),
    ],
)
def test_new_listing_starts_pending(listing_engine, mode, url):
    details = {**DETAILS, "apply_mode": mode, "external_url": url}

    result = listings.submit_listing(OWNER, **details)

    assert result == {
        "ok": True,
        "listing_id": result["listing_id"],
        "status": "pending",
    }
    assert snapshot(listing_engine) == [
        {
            "id": result["listing_id"],
            "employer_id": OWNER,
            "status": "pending",
            **details,
        }
    ]
    assert listings.list_jobs_for_graduates() == []


def test_public_browsing_filters_status_and_deadline(listing_engine):
    today = save_listing(listing_engine, "published", deadline=TODAY.isoformat())
    future = save_listing(listing_engine, "published")
    save_listing(listing_engine, "published", deadline="2026-11-21")
    save_listing(listing_engine, "pending")
    save_listing(listing_engine, "rejected")
    save_listing(listing_engine, "published", deadline="invalid")
    save_listing(listing_engine, "published", deadline="20261123")

    assert listings.list_jobs_for_graduates() == [today, future]


@pytest.mark.parametrize(
    "action, target", [("publish", "published"), ("reject", "rejected")]
)
def test_admin_can_review_pending_listing(listing_engine, action, target):
    original = save_listing(listing_engine)

    result = change_listing(action, ADMIN, original["id"])

    expected_result = (
        {"ok": True, "notified": False}
        if action == "publish"
        else {
            "ok": True,
            "listing_id": original["id"],
            "status": target,
        }
    )
    assert result == expected_result
    assert snapshot(listing_engine) == [{**original, "status": target}]
    assert listings.list_pending_for_admin() == []


@pytest.mark.parametrize("action", ["publish", "reject"])
@pytest.mark.parametrize("actor", [OWNER, GRADUATE, 999])
def test_non_admin_cannot_review(listing_engine, assert_refused, action, actor):
    original = save_listing(listing_engine)
    assert_refused(lambda: change_listing(action, actor, original["id"]))


@pytest.mark.parametrize("action", ["publish", "reject"])
@pytest.mark.parametrize("status", ["published", "rejected"])
def test_review_requires_pending(listing_engine, assert_refused, action, status):
    original = save_listing(listing_engine, status)
    assert_refused(lambda: change_listing(action, ADMIN, original["id"]))


@pytest.mark.parametrize("action", ["update", "resubmit"])
@pytest.mark.parametrize("actor", [OTHER, ADMIN, 999])
def test_revision_requires_owning_employer(
    listing_engine, assert_refused, action, actor
):
    original = save_listing(listing_engine, "rejected")
    assert_refused(lambda: change_listing(action, actor, original["id"]))


@pytest.mark.parametrize("action", ["update", "resubmit"])
@pytest.mark.parametrize("status", ["pending", "published"])
def test_revision_requires_rejected(listing_engine, assert_refused, action, status):
    original = save_listing(listing_engine, status)
    assert_refused(lambda: change_listing(action, OWNER, original["id"]))


@pytest.mark.parametrize(
    "action, actor",
    [
        ("publish", ADMIN),
        ("reject", ADMIN),
        ("update", OWNER),
        ("resubmit", OWNER),
    ],
)
def test_missing_listing_is_not_written(listing_engine, assert_refused, action, actor):
    save_listing(listing_engine)
    assert_refused(lambda: change_listing(action, actor, 999))


@pytest.mark.parametrize(
    "changes",
    [
        {"title": " "},
        {"company": ""},
        {"description": "\t"},
        {"apply_mode": "invalid"},
        {"apply_mode": "external", "external_url": None},
        {"apply_mode": "external", "external_url": " "},
        {"deadline": "2026-02-30"},
        {"deadline": "20261123"},
    ],
)
def test_invalid_submission_details_do_not_write(
    listing_engine, assert_refused, changes
):
    save_listing(listing_engine, "rejected")
    details = {**DETAILS, **changes}
    assert_refused(lambda: listings.submit_listing(OWNER, **details))


def test_invalid_edit_details_do_not_write(listing_engine, assert_refused):
    original = save_listing(listing_engine, "rejected")
    assert_refused(
        lambda: listings.update_listing(
            OWNER, original["id"], **{**DETAILS, "title": " "}
        )
    )


@pytest.mark.parametrize(
    "action, status", [("publish", "pending"), ("resubmit", "rejected")]
)
def test_invalid_stored_details_cannot_advance(
    listing_engine, assert_refused, action, status
):
    original = save_listing(listing_engine, status, deadline="invalid")
    actor = ADMIN if action == "publish" else OWNER
    assert_refused(lambda: change_listing(action, actor, original["id"]))
