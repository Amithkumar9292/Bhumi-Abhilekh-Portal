"""
pytest configuration — shared fixtures for the entire test suite.

Test categories:
  tests/api/           — HTTP API tests (FastAPI TestClient)
  tests/unit/          — Service unit tests
  tests/db/            — Database schema and migration tests
  tests/auth/          — Authentication and RBAC tests
  tests/pipeline/      — Document processing pipeline tests
  tests/validation/    — Validation engine tests
  tests/integration/   — Integration adapter tests

Run: pytest --cov=app --cov-report=term-missing -v
"""
import asyncio
import uuid
from typing import AsyncGenerator, Generator

import fakeredis.aioredis
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.main import app
from app.db.postgres import Base, get_db
from app.db.redis_client import get_redis
from app.core.security import hash_password
from app.models.user import User, RoleEnum


# ── Test database (SQLite in-memory for speed) ────────────────────────────────

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def test_db(test_engine) -> AsyncGenerator[AsyncSession, None]:
    TestSession = async_sessionmaker(test_engine, expire_on_commit=False)
    async with TestSession() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture(autouse=True)
async def clean_tables(test_engine):
    """Start every test with an empty database.

    `test_db`'s rollback is not sufficient isolation on its own. Any code path
    that commits while handling a request -- the GIS coordinate sync, a pipeline
    rerun -- makes every pending row in that session durable, and those rows then
    outlive the test that created them. Without this fixture a test that counts
    rows globally passes or fails purely on file ordering, so reordering the
    suite or running two files together silently changes the result.

    The deletes run through their own committed session rather than `test_db`,
    because that session is still mid-transaction here and its rollback would
    undo the cleanup along with the test's own writes. Tables are deleted in
    reverse dependency order; `alembic_version` is not part of `Base.metadata`
    and is therefore left alone.
    """
    yield
    Cleaner = async_sessionmaker(test_engine, expire_on_commit=False)
    async with Cleaner() as session:
        for table in reversed(Base.metadata.sorted_tables):
            await session.execute(delete(table))
        await session.commit()


@pytest_asyncio.fixture
async def seeded_db(test_db: AsyncSession) -> AsyncSession:
    """
    DB with demo users already seeded.

    Login commits its `last_login` update, which outlives the per-test
    rollback, so any rows left by a previous test are cleared first --
    otherwise the second test to request this fixture fails the unique
    constraint on `users.email`.
    """
    await test_db.execute(
        delete(User).where(User.email.in_([
            "admin@demo.in", "officer@demo.in", "verifier@demo.in", "viewer@demo.in",
        ]))
    )
    await test_db.flush()

    users = [
        User(id=uuid.uuid4(), username="admin",    email="admin@demo.in",    full_name="Admin User",
             hashed_password=hash_password("Admin@1234"),    role=RoleEnum.ADMIN,    is_active=True),
        User(id=uuid.uuid4(), username="officer",  email="officer@demo.in",  full_name="Officer User",
             hashed_password=hash_password("Officer@1234"),  role=RoleEnum.OFFICER,  is_active=True),
        User(id=uuid.uuid4(), username="verifier", email="verifier@demo.in", full_name="Verifier User",
             hashed_password=hash_password("Verifier@1234"), role=RoleEnum.VERIFIER, is_active=True),
        User(id=uuid.uuid4(), username="viewer",   email="viewer@demo.in",   full_name="Viewer User",
             hashed_password=hash_password("Viewer@1234"),   role=RoleEnum.VIEWER,   is_active=True),
    ]
    for u in users:
        test_db.add(u)
    await test_db.flush()
    return test_db


# ── HTTP client fixtures ───────────────────────────────────────────────────────

@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """Sync test client for simple endpoint tests."""
    with TestClient(app) as c:
        yield c


@pytest_asyncio.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ── Auth token fixtures ────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def admin_token(async_client: AsyncClient, seeded_db: AsyncSession) -> str:
    r = await async_client.post("/api/v1/auth/login", data={"username": "admin", "password": "Admin@1234"})
    return r.json()["access_token"]


@pytest_asyncio.fixture
async def officer_token(async_client: AsyncClient, seeded_db: AsyncSession) -> str:
    r = await async_client.post("/api/v1/auth/login", data={"username": "officer", "password": "Officer@1234"})
    return r.json()["access_token"]


@pytest_asyncio.fixture
async def viewer_token(async_client: AsyncClient, seeded_db: AsyncSession) -> str:
    r = await async_client.post("/api/v1/auth/login", data={"username": "viewer", "password": "Viewer@1234"})
    return r.json()["access_token"]


# ── Override DB dependency with test DB ────────────────────────────────────────
@pytest_asyncio.fixture(autouse=True)
async def override_redis():
    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    app.dependency_overrides[get_redis] = lambda: fake_redis
    
    # Also patch the module-level function for background tasks
    import app.db.redis_client as redis_mod
    original_get = redis_mod.get_redis
    original_client = redis_mod.get_redis_client
    
    import app.services.auth_service as auth_service
    
    async def mock_get_redis():
        return fake_redis
        
    redis_mod.get_redis = mock_get_redis
    redis_mod.get_redis_client = mock_get_redis
    auth_service.get_redis_client = mock_get_redis
    yield
    redis_mod.get_redis = original_get
    redis_mod.get_redis_client = original_client
    auth_service.get_redis_client = original_client
    app.dependency_overrides.pop(get_redis, None)


@pytest_asyncio.fixture(autouse=True)
async def override_db(test_db: AsyncSession):
    async def get_test_db():
        yield test_db
    app.dependency_overrides[get_db] = get_test_db
    yield
    app.dependency_overrides.pop(get_db, None)
