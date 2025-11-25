"""
SQS Service - Phase C: Async layout generation job queue management.

This service handles:
1. Sending layout generation jobs to SQS queue
2. Receiving and processing jobs (for worker)
3. Error handling and DLQ management
"""
import json
import logging
from typing import Optional

import aioboto3
from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

# Boto3 session for SQS
session = aioboto3.Session(region_name=settings.aws_region)


class SQSService:
    """Service for interacting with SQS queues."""

    def __init__(self):
        """Initialize SQS service."""
        self.queue_url = settings.sqs_queue_url
        self.queue_name = settings.sqs_queue_name
        self.region = settings.aws_region

    async def get_queue_url(self) -> str:
        """
        Get queue URL, fetching from AWS if not configured.
        
        Returns:
            str: The SQS queue URL
        """
        if self.queue_url:
            return self.queue_url
        
        async with session.client("sqs") as sqs_client:
            response = await sqs_client.get_queue_url(QueueName=self.queue_name)
            self.queue_url = response["QueueUrl"]
            return self.queue_url

    async def send_layout_job(
        self,
        layout_id: str,
        site_id: str,
        target_capacity_kw: float = 1000.0,
        dem_resolution_m: int = 30,
    ) -> bool:
        """
        Send a layout generation job to the SQS queue.
        
        Used by POST /api/layouts/generate to enqueue jobs (C-03).
        
        Args:
            layout_id: UUID of the layout record
            site_id: UUID of the site
            target_capacity_kw: Target capacity in kW
            dem_resolution_m: DEM resolution (10 or 30 meters)
            
        Returns:
            bool: True if successfully sent, False otherwise
        """
        try:
            queue_url = await self.get_queue_url()
            
            message_body = {
                "layout_id": str(layout_id),
                "site_id": str(site_id),
                "target_capacity_kw": target_capacity_kw,
                "dem_resolution_m": dem_resolution_m,
            }
            
            async with session.client("sqs") as sqs_client:
                response = await sqs_client.send_message(
                    QueueUrl=queue_url,
                    MessageBody=json.dumps(message_body),
                    # Message group ID for FIFO (if applicable)
                    # GroupId="layout-generation",
                    # Deduplication ID for FIFO
                    # DeduplicationId=str(layout_id),
                )
            
            logger.info(
                f"Layout job enqueued: layout_id={layout_id}, "
                f"message_id={response.get('MessageId')}"
            )
            return True
            
        except Exception as e:
            logger.error(f"Failed to send layout job to SQS: {e}", exc_info=True)
            return False

    async def receive_job(self) -> Optional[dict]:
        """
        Receive a single job from the queue.
        
        Used by the SQS worker (C-02).
        
        Returns:
            dict with keys:
                - message_id: SQS message ID
                - receipt_handle: For acknowledging the message
                - layout_id: UUID of layout to process
                - site_id: UUID of site
                - target_capacity_kw: Target capacity
                - dem_resolution_m: DEM resolution
            
            None if no message available
        """
        try:
            queue_url = await self.get_queue_url()
            
            async with session.client("sqs") as sqs_client:
                response = await sqs_client.receive_message(
                    QueueUrl=queue_url,
                    MaxNumberOfMessages=1,
                    WaitTimeSeconds=20,  # Long polling
                    VisibilityTimeout=300,  # 5 minutes
                )
            
            messages = response.get("Messages", [])
            if not messages:
                return None
            
            message = messages[0]
            body = json.loads(message["Body"])
            
            return {
                "message_id": message["MessageId"],
                "receipt_handle": message["ReceiptHandle"],
                "layout_id": body["layout_id"],
                "site_id": body["site_id"],
                "target_capacity_kw": body["target_capacity_kw"],
                "dem_resolution_m": body["dem_resolution_m"],
            }
            
        except Exception as e:
            logger.error(f"Failed to receive job from SQS: {e}", exc_info=True)
            return None

    async def delete_message(self, receipt_handle: str) -> bool:
        """
        Delete a message from the queue (acknowledge successful processing).
        
        Args:
            receipt_handle: Receipt handle from receive_message response
            
        Returns:
            bool: True if successfully deleted, False otherwise
        """
        try:
            queue_url = await self.get_queue_url()
            
            async with session.client("sqs") as sqs_client:
                await sqs_client.delete_message(
                    QueueUrl=queue_url,
                    ReceiptHandle=receipt_handle,
                )
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete message from SQS: {e}", exc_info=True)
            return False

    async def get_queue_attributes(self) -> Optional[dict]:
        """
        Get queue attributes for monitoring.
        
        Returns:
            dict with queue statistics:
                - ApproximateNumberOfMessages
                - ApproximateNumberOfMessagesNotVisible
                - ApproximateNumberOfMessagesDelayed
                - VisibilityTimeout
                
            None on error
        """
        try:
            queue_url = await self.get_queue_url()
            
            async with session.client("sqs") as sqs_client:
                response = await sqs_client.get_queue_attributes(
                    QueueUrl=queue_url,
                    AttributeNames=["All"],
                )
            
            return response.get("Attributes", {})
            
        except Exception as e:
            logger.error(f"Failed to get queue attributes: {e}", exc_info=True)
            return None


# Singleton instance
_sqs_service: Optional[SQSService] = None


def get_sqs_service() -> SQSService:
    """Get or create SQS service singleton."""
    global _sqs_service
    if _sqs_service is None:
        _sqs_service = SQSService()
    return _sqs_service

