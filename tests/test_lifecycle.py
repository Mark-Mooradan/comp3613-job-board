"""Regression tests for the dictionary/action adapter, not the state classes."""

from itertools import product

import pytest

from app.services.lifecycle import ACTIONS, apply_action

STATUSES = ("submitted", "reviewed", "shortlisted", "rejected", "hired", "withdrawn")
SUPPORTED_ACTIONS = ("mark_reviewed", "shortlist", "reject", "hire")
VALID_TRANSITIONS = {
    ("submitted", "mark_reviewed"): "reviewed",
    ("reviewed", "shortlist"): "shortlisted",
    ("reviewed", "reject"): "rejected",
    ("shortlisted", "hire"): "hired",
    ("shortlisted", "reject"): "rejected",
}


@pytest.fixture
def application_row():
    return {
        "id": 7,
        "listing_id": 1,
        "graduate_id": 2,
        "cover_letter": "Cover letter",
        "resume_text": "Resume",
        "status": "submitted",
    }


@pytest.mark.parametrize("status, action", list(product(STATUSES, SUPPORTED_ACTIONS)))
def test_apply_action_contract(application_row, status, action):
    application_row["status"] = status
    original = dict(application_row)

    result = apply_action(application_row, action)

    assert application_row == original
    target = VALID_TRANSITIONS.get((status, action))
    if target is None:
        assert set(result) == {"ok", "error"}
        assert result["ok"] is False
        assert result["error"].startswith("Invalid transition")
    else:
        assert result == {
            "ok": True,
            "application": {"id": original["id"], "status": target},
            "row": {**original, "status": target},
            "changed": True,
        }
        assert result["row"] is not application_row


@pytest.mark.parametrize("action", ["reopen", "unknown"])
def test_unsupported_action_returns_error_without_mutation(application_row, action):
    original = dict(application_row)

    result = apply_action(application_row, action)

    assert action not in ACTIONS
    assert set(result) == {"ok", "error"}
    assert result["ok"] is False
    assert result["error"].startswith("unknown action")
    assert application_row == original


def test_unknown_stored_status_returns_error_without_mutation(application_row):
    application_row["status"] = "unknown"
    original = dict(application_row)

    result = apply_action(application_row, "mark_reviewed")

    assert result == {"ok": False, "error": "Unknown application status: unknown"}
    assert application_row == original
