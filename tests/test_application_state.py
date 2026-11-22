import pytest
from app.models.application import Application

def test_valid_transitions():
    """Test that the happy path works perfectly."""
    app = Application(listing_id=1, graduate_id=1, cover_letter="test", resume_text="test")
    
    # Submitted -> Reviewed -> Shortlisted -> Hired
    app.transition_to("reviewed")
    assert app.status == "reviewed"
    
    app.transition_to("shortlisted")
    assert app.status == "shortlisted"
    
    app.transition_to("hired")
    assert app.status == "hired"

def test_invalid_jump():
    """Test that skipping stages is blocked."""
    app = Application(listing_id=1, graduate_id=1, cover_letter="test", resume_text="test")
    
    # Cannot go straight from Submitted to Hired
    with pytest.raises(ValueError, match="Invalid transition from Submitted to Hired"):
        app.transition_to("hired")

def test_terminal_states():
    """Test that Rejected and Hired cannot be changed."""
    app = Application(listing_id=1, graduate_id=1, cover_letter="test", resume_text="test")
    app.transition_to("reviewed")
    app.transition_to("rejected")
    
    # Cannot go backwards from Rejected
    with pytest.raises(ValueError, match="Invalid transition from Rejected to Reviewed"):
        app.transition_to("reviewed")