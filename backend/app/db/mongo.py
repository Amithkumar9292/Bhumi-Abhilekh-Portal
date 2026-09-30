"""
MongoDB async client via Motor.
Used exclusively for audit logs and document-processing event streams.

MongoDB is an *optional* observability dependency: it holds the audit trail and
pipeline event log, never business state. Business state lives in PostgreSQL and
is always readable even when MongoDB is down.

Every client is therefore created with short, explicit timeouts. The PyMongo
default for ``serverSelectionTimeoutMS`` is 30000 ms, which means a single audit
write against an unreachable mongod blocks the calling request for a full 30
seconds. That is precisely the latency that used to surface as
``timeout of 30000ms exceeded`` on document upload, so the default is never
acceptable here — see ``settings.mongo_timeout_ms``.
"""

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.config import settings

_mongo_client: AsyncIOMotorClient | None = None


def get_mongo_client() -> AsyncIOMotorClient:
    """Return the shared Motor client, configured with short timeouts."""
    global _mongo_client
    if _mongo_client is None:
        timeout_ms = settings.mongo_timeout_ms
        _mongo_client = AsyncIOMotorClient(
            settings.mongodb_url,
            # Fail fast instead of blocking the caller for the PyMongo default of 30s.
            serverSelectionTimeoutMS=timeout_ms,
            connectTimeoutMS=timeout_ms,
            socketTimeoutMS=timeout_ms,
            # Don't let a dead mongod wedge a connection out of the pool forever.
            maxPoolSize=20,
            retryWrites=False,
        )
    return _mongo_client


def get_audit_db() -> AsyncIOMotorDatabase:
    """Returns the audit log MongoDB database."""
    return get_mongo_client()[settings.mongodb_db]


async def get_mongo_db() -> AsyncIOMotorDatabase:
    """Async alias for pipeline — returns MongoDB database for processing logs."""
    return get_mongo_client()[settings.mongodb_db]


async def close_mongo() -> None:
    global _mongo_client
    if _mongo_client:
        _mongo_client.close()
        _mongo_client = None
