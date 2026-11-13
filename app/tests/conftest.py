import os

os.environ['DATABASE_URL'] = 'sqlite+pysqlite://'
os.environ['LLM_PROVIDER'] = 'disabled'

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from backend.db import Base, get_db
from backend.main import app
from backend.seed import seed_database
import backend.models  # noqa: F401

@pytest.fixture()
def db():
    engine = create_engine('sqlite+pysqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    with Session() as session:
        seed_database(session, demo_mode=True, demo_password='test-demo-password-123')
    yield Session
    engine.dispose()

@pytest.fixture()
def client(db):
    def override():
        with db() as session:
            yield session
    app.dependency_overrides[get_db] = override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

@pytest.fixture()
def auth(client):
    response = client.post('/api/v1/auth/demo')
    assert response.status_code == 200, response.text
    return {'Authorization': f"Bearer {response.json()['token']}"}
