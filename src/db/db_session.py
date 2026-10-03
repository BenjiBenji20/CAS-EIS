from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from clients.postgresql import postgres_client_async_session

# FastAPI dependency for async db session
async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    async with postgres_client_async_session() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

