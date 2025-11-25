"""
Phase C-02: SQS Worker for Async Layout Generation

This script runs as a separate ECS task and polls the layout generation SQS queue.
For each job, it:
1. Checks if layout is already processed (idempotency - C-02 requirement)
2. Updates layout status to 'processing'
3. Generates the layout using terrain-aware or dummy placement
4. Updates layout with results
5. Acknowledges message from queue

Run with: python -m app.worker
"""
import asyncio
import logging
import signal
import sys
from contextlib import asynccontextmanager
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.database import get_db_session
from app.models.layout import Layout, LayoutStatus
from app.models.site import Site
from app.services.sqs_service import get_sqs_service
from app.api.layouts import (
    _generate_terrain_aware_layout,
    _generate_dummy_layout,
    random_asset_count,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

settings = get_settings()

# Database engine for worker
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_size=5,
    max_overflow=10,
)

# Session factory
AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class LayoutWorker:
    """Worker for processing layout generation jobs from SQS queue."""

    def __init__(self):
        """Initialize worker."""
        self.sqs_service = get_sqs_service()
        self.should_shutdown = False
        self._setup_signal_handlers()

    def _setup_signal_handlers(self):
        """Set up signal handlers for graceful shutdown."""
        def handle_signal(signum, frame):
            logger.info(f"Received signal {signum}, gracefully shutting down...")
            self.should_shutdown = True

        signal.signal(signal.SIGTERM, handle_signal)
        signal.signal(signal.SIGINT, handle_signal)

    async def run(self):
        """
        Main worker loop - continuously poll SQS queue for jobs.
        
        Runs indefinitely until SIGTERM/SIGINT received.
        """
        logger.info("Layout generation worker started")
        
        while not self.should_shutdown:
            try:
                await self._process_one_job()
            except Exception as e:
                logger.exception(f"Error in worker main loop: {e}")
                # Continue processing despite errors
                await asyncio.sleep(5)

        logger.info("Worker shutdown complete")

    async def _process_one_job(self):
        """
        Receive one job from queue and process it.
        
        Implements idempotency (C-02 requirement): checks layout status before processing
        to prevent duplicate work if message is received multiple times.
        """
        # Receive job from queue (with 20-second timeout)
        job = await self.sqs_service.receive_job()
        
        if not job:
            # No message available, wait before polling again
            await asyncio.sleep(2)
            return

        layout_id = job["layout_id"]
        site_id = job["site_id"]
        target_capacity_kw = job["target_capacity_kw"]
        dem_resolution_m = job["dem_resolution_m"]
        receipt_handle = job["receipt_handle"]

        logger.info(
            f"Received layout job: layout_id={layout_id}, "
            f"capacity={target_capacity_kw} kW"
        )

        try:
            # Create database session for this job
            async with AsyncSessionLocal() as db:
                # Idempotency check (C-02): Look up current layout status
                result = await db.execute(
                    select(Layout).where(Layout.id == layout_id)
                )
                layout = result.scalar_one_or_none()

                if not layout:
                    logger.warning(
                        f"Layout {layout_id} not found in database. "
                        f"Acknowledging message anyway."
                    )
                    await self.sqs_service.delete_message(receipt_handle)
                    return

                # Idempotency: If already completed or failed, skip processing
                if layout.status in [LayoutStatus.COMPLETED.value, LayoutStatus.FAILED.value]:
                    logger.info(
                        f"Layout {layout_id} already in {layout.status} state. "
                        f"Skipping (duplicate message)."
                    )
                    await self.sqs_service.delete_message(receipt_handle)
                    return

                # Idempotency: If currently processing, could indicate failure/retry - restart
                if layout.status == LayoutStatus.PROCESSING.value:
                    logger.info(
                        f"Layout {layout_id} was already processing. "
                        f"Restarting (possible worker failure)."
                    )

                # Update status to 'processing' before heavy work
                layout.status = LayoutStatus.PROCESSING.value
                layout.error_message = None
                await db.commit()

                logger.info(f"Processing layout {layout_id}...")

                # Load site with boundary
                site_result = await db.execute(
                    select(Site).where(Site.id == site_id)
                )
                site = site_result.scalar_one_or_none()

                if not site:
                    layout.status = LayoutStatus.FAILED.value
                    layout.error_message = "Site not found"
                    await db.commit()
                    await self.sqs_service.delete_message(receipt_handle)
                    logger.error(f"Site {site_id} not found")
                    return

                # Get site boundary
                from shapely import wkt
                boundary_wkt_result = await db.execute(
                    select(Site.boundary.ST_AsText()).where(Site.id == site.id)
                )
                boundary_wkt = boundary_wkt_result.scalar()
                boundary = wkt.loads(boundary_wkt)

                # Generate layout (using Phase B/C terrain-aware or dummy)
                num_assets = random_asset_count(target_capacity_kw)

                try:
                    if settings.use_terrain:
                        await _generate_terrain_aware_layout(
                            layout=layout,
                            site=site,
                            boundary=boundary,
                            target_capacity_kw=target_capacity_kw,
                            dem_resolution_m=dem_resolution_m,
                            num_assets=num_assets,
                            db=db,
                        )
                    else:
                        await _generate_dummy_layout(
                            layout=layout,
                            boundary=boundary,
                            target_capacity_kw=target_capacity_kw,
                            num_assets=num_assets,
                            db=db,
                        )

                    # Update status to 'completed' (if not already)
                    if layout.status != LayoutStatus.FAILED.value:
                        layout.status = LayoutStatus.COMPLETED.value
                    
                    await db.commit()
                    logger.info(f"Layout {layout_id} processed successfully")

                except Exception as e:
                    logger.exception(f"Error generating layout {layout_id}: {e}")
                    layout.status = LayoutStatus.FAILED.value
                    layout.error_message = str(e)
                    await db.commit()

            # Acknowledge message - remove from queue
            await self.sqs_service.delete_message(receipt_handle)
            logger.info(f"Acknowledged message for layout {layout_id}")

        except Exception as e:
            logger.exception(f"Unexpected error processing job: {e}")
            # Don't acknowledge - message will become visible again after visibility timeout
            # Will be retried or sent to DLQ if max retries exceeded

    async def shutdown(self):
        """Clean shutdown - wait for current job to complete."""
        logger.info("Waiting for worker to finish current job...")
        self.should_shutdown = True
        
        # Close database connections
        await engine.dispose()
        logger.info("Database connections closed")


async def main():
    """Main entry point for worker."""
    worker = LayoutWorker()
    
    try:
        await worker.run()
    except KeyboardInterrupt:
        logger.info("Interrupted")
    finally:
        await worker.shutdown()
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())

