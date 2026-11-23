from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ApplicationStatusHistory(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    application_id: int = Field(index=True)
    previous_status: str
    new_status: str
    actor_id: int = Field(index=True)
    timestamp: datetime = Field(default_factory=utc_now)
