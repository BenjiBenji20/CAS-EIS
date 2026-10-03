import argparse
import asyncio
import os
import sys

# Ensure root directory and src directory are at the top of sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC_DIR = os.path.join(BASE_DIR, "src")

for p in [BASE_DIR, SRC_DIR]:
    if p not in sys.path:
        sys.path.insert(0, p)

from loguru import logger


async def main(seed_type: str) -> None:
    """CLI Entry point to execute database seeders."""
    # Delayed import to ensure settings overrides (e.g. --db test) take effect before DB engine is created
    from alembic.seeds.system_seeder import SystemSeeder
    from alembic.seeds.dummy_seeder import DummySeeder

    logger.info(f"Running database seeds with type: {seed_type.upper()}")

    if seed_type in ("system", "all"):
        seeder = SystemSeeder()
        await seeder.run()

    if seed_type in ("dummy", "all"):
        seeder = DummySeeder()
        await seeder.run()

    logger.info("Database seeding completed successfully.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Database Seeder CLI Runner")
    parser.add_argument(
        "--type",
        choices=["system", "dummy", "all"],
        default="all",
        help="Type of seeds to execute: system (prod safe), dummy (dev test data), or all.",
    )
    parser.add_argument(
        "--db",
        choices=["main", "test"],
        default="main",
        help="Target database to seed: main (uses DATABASE_URL) or test (uses TEST_DATABASE_URL).",
    )
    args = parser.parse_args()

    if args.db == "test":
        from core.settings import settings
        if not settings.TEST_DATABASE_URL:
            raise ValueError("TEST_DATABASE_URL is not defined in settings / .env file!")
        logger.info(f"Targeting TEST database: {settings.TEST_DATABASE_URL}")
        settings.DATABASE_URL = settings.TEST_DATABASE_URL

    asyncio.run(main(args.type))
