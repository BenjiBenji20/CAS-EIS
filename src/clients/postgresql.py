from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncEngine

from core.settings import settings


engine: AsyncEngine = create_async_engine(
    settings.async_database_url, 
    echo=False,
    pool_size=5,              
    max_overflow=10,
    pool_pre_ping=True,       # Verify connections before using
    pool_recycle=3600,        # Recycle connections every hour
)


postgres_client_async_session = async_sessionmaker(engine, expire_on_commit=False)

async def init_db() -> None:
    """Initialize and verify connection to PostgreSQL database singleton."""
    logger.info("Initializing PostgreSQL database connection pool...")
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("PostgreSQL database connection pool successfully established.")
    except Exception as exc:
        logger.error(f"Failed to connect to PostgreSQL database: {exc}")
        raise exc

async def close_db() -> None:
    """Close and dispose PostgreSQL engine singleton."""
    logger.info("Closing PostgreSQL database connection pool...")
    await engine.dispose()
    logger.info("PostgreSQL database connection pool closed.")

