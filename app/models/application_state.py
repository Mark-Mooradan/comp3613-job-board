"""State classes and transition rules for job applications."""

from abc import ABC, abstractmethod


class ApplicationState(ABC):
    """Base class for application statuses and their allowed transitions."""

    status: str

    @abstractmethod
    def allowed_next_actions(self) -> list[str]:
        """Return the statuses this state may transition to."""

    def validate_transition(self, target_status: str) -> bool:
        """Validate a requested transition, raising ``ValueError`` if invalid."""
        if target_status in self.allowed_next_actions():
            return True

        raise ValueError(
            f"Invalid transition from {self.status.title()} "
            f"to {target_status.title()}"
        )


class SubmittedState(ApplicationState):
    """State for an application that has been submitted."""

    status = "submitted"

    def allowed_next_actions(self) -> list[str]:
        return ["reviewed"]


class ReviewedState(ApplicationState):
    """State for an application that has been reviewed."""

    status = "reviewed"

    def allowed_next_actions(self) -> list[str]:
        return ["shortlisted", "rejected"]


class ShortlistedState(ApplicationState):
    """State for an application that has been shortlisted."""

    status = "shortlisted"

    def allowed_next_actions(self) -> list[str]:
        return ["hired", "rejected"]


class RejectedState(ApplicationState):
    """Terminal state for a rejected application."""

    status = "rejected"

    def allowed_next_actions(self) -> list[str]:
        return []


class HiredState(ApplicationState):
    """Terminal state for a hired application."""

    status = "hired"

    def allowed_next_actions(self) -> list[str]:
        return []


class WithdrawnState(ApplicationState):
    """Terminal state for a withdrawn application."""

    status = "withdrawn"

    def allowed_next_actions(self) -> list[str]:
        return []
