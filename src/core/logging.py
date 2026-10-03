import logging
import sys
from loguru import logger

from core.settings import settings


class InterceptHandler(logging.Handler):
    """Custom logging handler that intercepts standard library logging records

    and redirects them to Loguru for unified, colorized output.
    """

    def emit(self, record: logging.LogRecord) -> None:
        # Get corresponding Loguru level if it exists
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        # Find caller frame from where the log message originated
        frame, depth = logging.currentframe(), 2
        while frame and frame.f_code.co_filename == logging.__file__:
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def setup_logging() -> None:
    """Configure Loguru logging handlers and intercept standard Python loggers."""
    log_level = settings.LOG_LEVEL.upper()

    # Remove all pre-existing Loguru handlers
    logger.remove()

    def format_record(record: dict) -> str:
        req_id = record["extra"].get("request_id", "-")
        # Format string to append the request ID if it is set
        record["extra"]["request_id_str"] = f" | {req_id}" if req_id != "-" else ""
        return (
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level>{extra[request_id_str]} | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>\n"
        )

    logger.add(
        sys.stdout,
        level=log_level,
        format=format_record,
        colorize=True,
        backtrace=settings.DEBUG,
        diagnose=settings.DEBUG,
    )

    # Intercept standard library loggers (Uvicorn, FastAPI, SQLAlchemy, Alembic, etc.)
    intercept_handler = InterceptHandler()
    logging.root.handlers = [intercept_handler]
    logging.root.setLevel(log_level)

    # Reconfigure framework loggers to route exclusively through InterceptHandler
    loggers_to_intercept = (
        "uvicorn",
        "uvicorn.error",
        "uvicorn.access",
        "fastapi",
        "sqlalchemy",
        "sqlalchemy.engine",
        "sqlalchemy.engine.Engine",
        "alembic",
    )

    for logger_name in loggers_to_intercept:
        mod_logger = logging.getLogger(logger_name)
        mod_logger.handlers = [intercept_handler]
        mod_logger.propagate = False

    # Enable SQL query logging via Loguru when DEBUG is active
    if settings.DEBUG:
        logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO)

