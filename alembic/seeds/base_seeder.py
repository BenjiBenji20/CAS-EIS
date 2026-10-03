import abc
from typing import AsyncGenerator
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from clients.postgresql import postgres_client_async_session, engine


class BaseSeeder(abc.ABC):
    """Abstract Base Seeder providing async database sessions and logging context."""

    def __init__(self) -> None:
        self.session_factory = postgres_client_async_session

    @abc.abstractmethod
    async def seed(self, session: AsyncSession) -> None:
        """Execute seeding logic within an active session transaction."""
        pass

    async def run(self) -> None:
        """Run the seeder with session context and error handling."""
        seeder_name = self.__class__.__name__
        logger.info(f"Starting execution of seeder: {seeder_name}...")
        
        async with self.session_factory() as session:
            try:
                await self.seed(session)
                await session.commit()
                logger.info(f"Successfully executed seeder: {seeder_name}.")
            except Exception as exc:
                await session.rollback()
                logger.error(f"Error executing seeder {seeder_name}: {exc}")
                raise exc
        
        # Dispose engine pool after execution if standalone
        await engine.dispose()
