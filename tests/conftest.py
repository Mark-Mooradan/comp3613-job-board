import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import app.models  # noqa: F401
from app.database import get_session
from app.models.user import User
from app.utilities.security import create_access_token


@pytest.fixture
def test_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    SQLModel.metadata.drop_all(engine)


@pytest.fixture
def api_auth(test_session):
    engine = test_session.get_bind()

    def install(app):
        def override_get_session():
            with Session(engine) as session:
                yield session

        app.dependency_overrides[get_session] = override_get_session

    def authenticate(client, user_id):
        with Session(engine) as session:
            user = session.get(User, user_id)
        role = user.role if user else "unknown"
        token = create_access_token({"sub": str(user_id), "role": role})
        client.cookies.set("access_token", token)

    return install, authenticate
