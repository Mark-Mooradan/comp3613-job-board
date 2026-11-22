import pytest
from app.models.application import Application


def create_application():
    return Application(
        listing_id=1,
        graduate_id=1,
        cover_letter="test",
        resume_text="test"
    )


def test_valid_transitions():
    """Test the complete successful application lifecycle."""
    app = create_application()

    app.transition_to("reviewed")
    assert app.status == "reviewed"

    app.transition_to("shortlisted")
    assert app.status == "shortlisted"

    app.transition_to("hired")
    assert app.status == "hired"


@pytest.mark.parametrize(
    "current_status, target_status",
    [
        ("reviewed", "shortlisted"),
        ("reviewed", "rejected"),
        ("shortlisted", "hired"),
        ("shortlisted", "rejected"),
    ]
)
def test_other_valid_transitions(current_status, target_status):
    """Test all valid transitions from intermediate states."""
    app = create_application()
    app.status = current_status

    app.transition_to(target_status)

    assert app.status == target_status


@pytest.mark.parametrize(
    "current_status, target_status",
    [
        ("submitted", "hired"),
        ("submitted", "rejected"),
        ("reviewed", "submitted"),
        ("shortlisted", "reviewed"),
        ("rejected", "reviewed"),
        ("hired", "reviewed"),
        ("withdrawn", "reviewed"),
    ]
)
def test_invalid_transitions(current_status, target_status):
    """Test invalid transitions and ensure status is unchanged."""
    app = create_application()
    app.status = current_status

    with pytest.raises(ValueError, match="Invalid transition"):
        app.transition_to(target_status)

    assert app.status == current_status


@pytest.mark.parametrize(
    "terminal_status",
    ["rejected", "hired", "withdrawn"]
)
def test_terminal_states(terminal_status):
    """Terminal states must not allow further transitions."""
    app = create_application()
    app.status = terminal_status

    with pytest.raises(ValueError):
        app.transition_to("reviewed")

    assert app.status == terminal_status


def test_unknown_current_status():
    """Unknown stored statuses must be rejected."""
    app = create_application()
    app.status = "unknown"

    with pytest.raises(ValueError, match="Unknown application status"):
        app.transition_to("reviewed")

    assert app.status == "unknown"