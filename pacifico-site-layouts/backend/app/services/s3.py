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
    
    # =========================================================================
    # Phase B: Terrain and Output File Operations
    # =========================================================================
    
    async def upload_terrain_file(
        self,
        s3_key: str,
        content: bytes,
        content_type: str = "image/tiff",
    ) -> str:
        """
        Upload terrain file (DEM, slope raster) to outputs bucket.
        
        Args:
            s3_key: S3 key path (e.g., "terrain/{site_id}/dem.tif")
            content: File content as bytes
            content_type: MIME type (default: image/tiff for GeoTIFF)
            
        Returns:
            S3 key where the file was stored
        """
        try:
            self._client.put_object(
                Bucket=self.outputs_bucket,
                Key=s3_key,
                Body=content,
                ContentType=content_type,
            )
            logger.info(f"Uploaded terrain file to s3://{self.outputs_bucket}/{s3_key}")
            return s3_key
            
        except ClientError as e:
            logger.error(f"Failed to upload terrain file: {e}")
            raise
    
    async def download_terrain_file(self, s3_key: str) -> bytes:
        """
        Download terrain file from outputs bucket.
        
        Args:
            s3_key: S3 key path
            
        Returns:
            File content as bytes
        """
        try:
            response = self._client.get_object(
                Bucket=self.outputs_bucket,
                Key=s3_key,
            )
            return response["Body"].read()
            
        except ClientError as e:
            logger.error(f"Failed to download terrain file: {e}")
            raise
    
    async def terrain_file_exists(self, s3_key: str) -> bool:
        """
        Check if a terrain file exists in the outputs bucket.
        
        Args:
            s3_key: S3 key path
            
        Returns:
            True if file exists, False otherwise
        """
        try:
            self._client.head_object(
                Bucket=self.outputs_bucket,
                Key=s3_key,
            )
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            raise
    
    async def upload_output_file(
        self,
        s3_key: str,
        content: bytes,
        content_type: str,
        metadata: Optional[dict] = None,
    ) -> str:
        """
        Upload output file (exports, reports) to outputs bucket.
        
        Args:
            s3_key: S3 key path (e.g., "outputs/{layout_id}/layout.geojson")
            content: File content as bytes
            content_type: MIME type
            metadata: Optional metadata dict
            
        Returns:
            S3 key where the file was stored
        """
        extra_args = {"ContentType": content_type}
        if metadata:
            extra_args["Metadata"] = metadata
        
        try:
            self._client.put_object(
                Bucket=self.outputs_bucket,
                Key=s3_key,
                Body=content,
                **extra_args,
            )
            logger.info(f"Uploaded output file to s3://{self.outputs_bucket}/{s3_key}")
            return s3_key
            
        except ClientError as e:
            logger.error(f"Failed to upload output file: {e}")
            raise
    
    async def upload_json(
        self,
        s3_key: str,
        data: dict,
    ) -> str:
        """
        Upload JSON data to outputs bucket.
        
        Args:
            s3_key: S3 key path
            data: Dict to serialize as JSON
            
        Returns:
            S3 key where the file was stored
        """
        import json
        content = json.dumps(data, indent=2).encode("utf-8")
        return await self.upload_output_file(
            s3_key=s3_key,
            content=content,
            content_type="application/json",
        )
    
    async def delete_terrain_files(self, site_id: str) -> None:
        """
        Delete all terrain files for a site from outputs bucket.
        
        Args:
            site_id: UUID of the site
        """
        prefix = f"terrain/{site_id}/"
        
        try:
            response = self._client.list_objects_v2(
                Bucket=self.outputs_bucket,
                Prefix=prefix,
            )
            
            objects = response.get("Contents", [])
            if objects:
                delete_keys = [{"Key": obj["Key"]} for obj in objects]
                self._client.delete_objects(
                    Bucket=self.outputs_bucket,
                    Delete={"Objects": delete_keys},
                )
                logger.info(f"Deleted {len(delete_keys)} terrain files for site {site_id}")
                
        except ClientError as e:
            logger.error(f"Failed to delete terrain files: {e}")
            raise
    
    async def get_output_presigned_url(
        self,
        key: str,
        expires_in: int = 3600,
    ) -> str:
        """
        Generate a presigned URL for downloading from outputs bucket.
        
        Args:
            key: S3 object key
            expires_in: URL expiration time in seconds (default: 1 hour)
            
        Returns:
            Presigned URL string
        """
        return await self.get_presigned_url(
            bucket=self.outputs_bucket,
            key=key,
            expires_in=expires_in,
        )


# Global service instance
_s3_service: Optional[S3Service] = None


def get_s3_service() -> S3Service:
    """Get the S3 service singleton."""
    global _s3_service
    if _s3_service is None:
        _s3_service = S3Service()
    return _s3_service

