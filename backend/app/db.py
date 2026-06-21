from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine  # async SQLAlchemy building blocks

from app.config import settings  # Settings instance, used here for the cache DB connection URL

# Create the async engine once at import time; pool_size/max_overflow control how many
# concurrent DB connections this process can hold open
engine = create_async_engine(settings.cache_db_url, pool_size=10, max_overflow=20)

# Factory that creates new AsyncSession objects bound to the engine above;
# expire_on_commit=False keeps loaded objects usable after a commit
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncSession:
    # FastAPI dependency — opens a new session per request and closes it automatically afterwards
    async with AsyncSessionLocal() as session:  # open a session as an async context manager
        yield session                            # hand the session to the endpoint; cleanup runs after the request finishes
