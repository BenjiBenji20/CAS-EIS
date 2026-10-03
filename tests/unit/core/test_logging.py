import os
import sys
from loguru import logger

# Ensure src is in sys.path for test resolution
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "src")))

from core.logging import setup_logging

def test_setup_logging_runs_without_errors():
    """Verify that setup_logging executes cleanly and configures loguru handlers."""
    setup_logging()
    # Test emitting loguru messages across different log levels
    logger.info("Test info message via Loguru")
    logger.warning("Test warning message via Loguru")
    logger.error("Test error message via Loguru")
