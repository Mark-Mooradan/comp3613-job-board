from typing import Optional

from sqlmodel import Field, SQLModel

from app.models.application_state import (
    ApplicationState,
    HiredState,
    RejectedState,
    ReviewedState,
    ShortlistedState,
    SubmittedState,
    WithdrawnState,
)


_STATE_BY_STATUS: dict[str, type[ApplicationState]] = {
    "submitted": SubmittedState,
    "reviewed": ReviewedState,
    "shortlisted": ShortlistedState,
    "rejected": RejectedState,
    "hired": HiredState,
    "withdrawn": WithdrawnState,
}


class Application(SQLModel, table=True):
    """A graduate's application to a job listing."""

    id: Optional[int] = Field(default=None, primary_key=True)
    listing_id: int = Field(index=True)
    graduate_id: int = Field(index=True)
    cover_letter: str
    resume_text: str
    status: str = "submitted"

    def transition_to(self, target_status: str) -> None:
        """Transition to a valid application status."""
        state_class = _STATE_BY_STATUS.get(self.status)
        if state_class is None:
            raise ValueError(f"Unknown application status: {self.status}")

        state = state_class()
        state.validate_transition(target_status)
        self.status = target_status
