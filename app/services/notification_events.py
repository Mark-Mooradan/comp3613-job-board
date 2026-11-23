"""helpers for job board notifications"""

from sqlmodel import Session, select

from app.models.notification import Notification
from app.models.subscription import Subscription


def add_notification(session: Session, user_id: int, message: str) -> int:
    """dont save a duplicate notification"""
    old = session.exec(
        select(Notification).where(
            Notification.user_id == user_id,
            Notification.message == message,
        )
    ).first()
    if old:
        return 0
    session.add(Notification(user_id=user_id, message=message))
    return 1


class ApplicationObserver:
    """notify the student about status changes"""

    def update(self, session: Session, event: str, data: dict) -> int:
        if event != "application_changed":
            return 0

        message = (
            f"Application #{data['application_id']} "
            f"status changed to {data['status']}."
        )
        return add_notification(session, data["graduate_id"], message)


class ListingObserver:
    """notify subscribers about published jobs"""

    def update(self, session: Session, event: str, data: dict) -> int:
        if event != "listing_published":
            return 0

        message = (
            f"New job published (#{data['listing_id']}): "
            f"{data['title']} at {data['company']}"
        )
        students = session.exec(select(Subscription)).all()
        count = 0
        for student in students:
            count += add_notification(session, student.graduate_id, message)
        return count


observers = [ApplicationObserver(), ListingObserver()]


def notify_observers(session: Session, event: str, data: dict) -> int:
    """save messages with the status change"""
    count = 0
    for observer in observers:
        count += observer.update(session, event, data)
    return count
