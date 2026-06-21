from fastapi import Depends, FastAPI  # Depends wires get_session into endpoints; FastAPI is the app class itself
from fastapi.middleware.cors import CORSMiddleware  # lets the browser-based React app call this API from another origin
from sqlalchemy import text  # wraps raw SQL strings so SQLAlchemy can execute them safely
from sqlalchemy.ext.asyncio import AsyncSession  # type hint for the injected DB session

from app.config import app_config  # parsed config.yaml dict, used here for CORS origins
from app.db import get_session  # dependency that yields a DB session per request

app = FastAPI(title="App API")  # create the FastAPI application instance; title shows up in the auto-generated docs

app.add_middleware(
    CORSMiddleware,
    allow_origins=app_config.get("api", {}).get("cors_origins", ["*"]),  # allowed origins from config.yaml, default allow-all
    allow_methods=["*"],   # allow all HTTP methods (GET, POST, etc.) from those origins
    allow_headers=["*"],   # allow all request headers from those origins
)


@app.get("/health")  # registers this function to handle GET requests to /health
async def health(session: AsyncSession = Depends(get_session)):  # FastAPI calls get_session() and injects the result here
    """Liveness check — also confirms the cache DB is reachable."""
    await session.execute(text("SELECT 1"))  # trivial query — succeeds only if the DB connection actually works
    return {"status": "ok"}                   # FastAPI automatically serializes this dict to a JSON response


@app.get("/sync-status")  # registers GET /sync-status
async def sync_status(session: AsyncSession = Depends(get_session)):
    """Lets the frontend show 'data as of <timestamp>'."""
    result = await session.execute(           # query the sync_metadata table written by sync.py
        text("SELECT last_synced_at FROM sync_metadata WHERE id = 1")
    )
    row = result.first()                       # fetch the single row, or None if the table/row doesn't exist yet
    return {"last_synced_at": row.last_synced_at if row else None}  # return the timestamp, or null if no sync has run yet


# Example endpoint — replace with your real queries against the synced tables
@app.get("/api/customers")  # registers GET /api/customers
async def list_customers(session: AsyncSession = Depends(get_session)):
    result = await session.execute(text("SELECT * FROM customers LIMIT 100"))  # query the cache DB, capped at 100 rows
    return [dict(row._mapping) for row in result]  # convert each SQLAlchemy row into a plain dict so FastAPI can JSON-encode it
