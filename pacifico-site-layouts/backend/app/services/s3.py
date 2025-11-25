"""
S3 file storage service.

Handles uploads and downloads to AWS S3 buckets.
"""
import logging
from typing import Optional

import boto3
from botocore.exceptions import ClientError

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class S3Service:
    """
    Service for S3 file operations.
    
    Handles uploading files to S3 and generating presigned URLs.
    """
    
    def __init__(self):
        """Initialize S3 client."""
        self._client = boto3.client(
            "s3",
            region_name=settings.aws_region,
        )
    
    @property
    def uploads_bucket(self) -> str:
        """Get the uploads bucket name."""
        return settings.s3_uploads_bucket
    
    @property
    def outputs_bucket(self) -> str:
        """Get the outputs bucket name."""
        return settings.s3_outputs_bucket
    
    async def upload_site_file(
        self,
        site_id: str,
        content: bytes,
        filename: str,
        content_type: Optional[str] = None,
    ) -> str:
        """
        Upload original site boundary file to S3.
        
        Args:
            site_id: UUID of the site
            content: File content as bytes
            filename: Original filename
            content_type: MIME type of the file
            
        Returns:
            S3 key where the file was stored
            
        Raises:
            ClientError: If upload fails
        """
        # Determine extension from filename
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
        
        # Construct S3 key
        s3_key = f"uploads/{site_id}/original.{ext}"
        
        # Prepare upload parameters
        extra_args = {}
        if content_type:
            extra_args["ContentType"] = content_type
        extra_args["Metadata"] = {
            "original_filename": filename,
            "site_id": site_id,
        }
        
        try:
            self._client.put_object(
                Bucket=self.uploads_bucket,
                Key=s3_key,
                Body=content,
                **extra_args,
            )
            logger.info(f"Uploaded site file to s3://{self.uploads_bucket}/{s3_key}")
            return s3_key
            
        except ClientError as e:
            logger.error(f"Failed to upload to S3: {e}")
            raise
    
    async def get_presigned_url(
        self,
        bucket: str,
        key: str,
        expires_in: int = 3600,
    ) -> str:
        """
        Generate a presigned URL for downloading a file.
        
        Args:
            bucket: S3 bucket name
            key: S3 object key
            expires_in: URL expiration time in seconds (default: 1 hour)
            
        Returns:
            Presigned URL string
        """
        try:
            url = self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=expires_in,
            )
            return url
        except ClientError as e:
            logger.error(f"Failed to generate presigned URL: {e}")
            raise
    
    async def delete_site_files(self, site_id: str) -> None:
        """
        Delete all files for a site from S3.
        
        Args:
            site_id: UUID of the site
        """
        prefix = f"uploads/{site_id}/"
        
        try:
            # List all objects with the prefix
            response = self._client.list_objects_v2(
                Bucket=self.uploads_bucket,
                Prefix=prefix,
            )
            
            # Delete each object
            objects = response.get("Contents", [])
            if objects:
                delete_keys = [{"Key": obj["Key"]} for obj in objects]
                self._client.delete_objects(
                    Bucket=self.uploads_bucket,
                    Delete={"Objects": delete_keys},
                )
                logger.info(f"Deleted {len(delete_keys)} files for site {site_id}")
                
        except ClientError as e:
            logger.error(f"Failed to delete site files: {e}")
            raise


# Global service instance
_s3_service: Optional[S3Service] = None


def get_s3_service() -> S3Service:
    """Get the S3 service singleton."""
    global _s3_service
    if _s3_service is None:
        _s3_service = S3Service()
    return _s3_service

