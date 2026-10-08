import asyncio
from loguru import logger

from clients.postgresql import postgres_client_async_session
from clients.redis import redis_async_client
from core.settings import settings
from modules.eis.eis_enums import EisTransmissionStatus
from modules.eis.eis_repository import (
    EisSessionRepository,
    EisTransmissionItemRepository,
    EisTransmissionRepository,
)
from modules.eis.eis_service import EisService

EIS_INQUIRY_QUEUE_KEY = "eis:inquiry_queue"


async def enqueue_inquiry(submit_id: str) -> None:
    """Push submitId into Redis inquiry queue for durable background polling."""
    try:
        redis = redis_async_client.redis
        await redis.rpush(EIS_INQUIRY_QUEUE_KEY, submit_id)
        logger.info(f"Enqueued submit_id '{submit_id}' to Redis inquiry queue.")
    except Exception as e:
        logger.warning(
            f"Failed to enqueue submit_id '{submit_id}' to Redis: {e}. "
            "Transmission remains recorded in DB and can be recovered."
        )


class EisPollingWorker:
    """Background daemon that processes BIR EIS inquiry polls.

    Operates with independent SQLAlchemy session contexts decoupled from
    FastAPI request scopes to prevent session leakage and connection errors.
    """

    def __init__(self):
        self._is_running = False

    async def start(self) -> None:
        """Main worker loop listening for pending inquiry tasks."""
        self._is_running = True
        logger.info("BIR EIS Polling Worker started.")
        await self._recover_pending_transmissions()

        while self._is_running:
            try:
                await self._process_next()
            except asyncio.CancelledError:
                logger.info("EIS Polling Worker received cancellation signal.")
                break
            except Exception as e:
                logger.error(f"Unexpected error in EIS Polling Worker loop: {e}")
                await asyncio.sleep(settings.EIS_POLL_INTERVAL_S)

    def stop(self) -> None:
        """Signal worker to stop gracefully."""
        self._is_running = False

    async def _recover_pending_transmissions(self) -> None:
        """Scan DB for unacknowledged SENT transmissions upon startup."""
        try:
            async with postgres_client_async_session() as db:
                trans_repo = EisTransmissionRepository(db)
                pending = await trans_repo.get_pending_transmissions()
                recovered_count = 0
                for t in pending:
                    if t.status == EisTransmissionStatus.SENT:
                        await enqueue_inquiry(t.submit_id)
                        recovered_count += 1
                if recovered_count > 0:
                    logger.info(
                        f"Recovered {recovered_count} pending EIS transmission(s) from DB for polling."
                    )
        except Exception as e:
            logger.warning(f"Could not scan pending EIS transmissions on startup: {e}")

    async def _process_next(self) -> None:
        """Fetch next submitId from Redis and poll BIR EIS inquiry endpoint."""
        submit_id: str | None = None
        try:
            redis = redis_async_client.redis
            item = await redis.blpop(EIS_INQUIRY_QUEUE_KEY, timeout=5)
            if not item:
                return
            submit_id = item[1]
        except Exception:
            await asyncio.sleep(settings.EIS_POLL_INTERVAL_S)
            return

        if not submit_id:
            return

        async with postgres_client_async_session() as db:
            session_repo = EisSessionRepository(db)
            trans_repo = EisTransmissionRepository(db)
            item_repo = EisTransmissionItemRepository(db)
            service = EisService(session_repo, trans_repo, item_repo)

            retry_key = f"eis:inquiry_retries:{submit_id}"
            try:
                redis = redis_async_client.redis
                retries = await redis.incr(retry_key)
                await redis.expire(retry_key, 86400)
            except Exception:
                retries = 1

            await asyncio.sleep(settings.EIS_POLL_INTERVAL_S)
            logger.info(
                f"Polling BIR EIS inquiry for {submit_id} (attempt {retries}/{settings.EIS_MAX_POLL_RETRIES})"
            )

            done = await service.poll_inquiry_for_submit_id(submit_id)
            if not done and retries < settings.EIS_MAX_POLL_RETRIES:
                try:
                    redis = redis_async_client.redis
                    await redis.rpush(EIS_INQUIRY_QUEUE_KEY, submit_id)
                except Exception as e:
                    logger.error(f"Failed to re-enqueue {submit_id}: {e}")
            else:
                try:
                    redis = redis_async_client.redis
                    await redis.delete(retry_key)
                except Exception:
                    pass
                if not done:
                    logger.warning(
                        f"Inquiry polling reached max retries ({settings.EIS_MAX_POLL_RETRIES}) for {submit_id}"
                    )


eis_polling_worker = EisPollingWorker()
