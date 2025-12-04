"""
Cognito JWT authentication for FastAPI.

Validates JWT tokens from AWS Cognito and provides the current user.
"""
import logging
from functools import lru_cache
from typing import Optional
from uuid import UUID

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from jose.exceptions import ExpiredSignatureError
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.user import User

logger = logging.getLogger(__name__)
settings = get_settings()

# Security scheme for Swagger UI
security = HTTPBearer(auto_error=False)


class TokenPayload(BaseModel):
    """Decoded JWT token payload from Cognito."""
    sub: str  # Cognito user ID
    email: str
    name: Optional[str] = None
    token_use: str  # "id" or "access"
    exp: int


class CognitoJWKS:
    """
    Manages Cognito JSON Web Key Set for JWT verification.
    
    Fetches and caches the public keys from Cognito's JWKS endpoint.
    """
    
    def __init__(self):
        self._keys: Optional[dict] = None
    
    @property
    def jwks_url(self) -> str:
        """Get the JWKS URL for the configured Cognito User Pool."""
        region = settings.aws_region
        user_pool_id = settings.cognito_user_pool_id
        return f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}/.well-known/jwks.json"
    
    @property
    def issuer(self) -> str:
        """Get the expected issuer for tokens."""
        region = settings.aws_region
        user_pool_id = settings.cognito_user_pool_id
        return f"https://cognito-idp.{region}.amazonaws.com/{user_pool_id}"
    
    async def get_keys(self) -> dict:
        """
        Fetch JWKS from Cognito (cached after first call).
        
        In production, consider implementing periodic refresh.
        """
        if self._keys is None:
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(self.jwks_url, timeout=10.0)
                    response.raise_for_status()
                    jwks = response.json()
                    # Convert to dict keyed by kid for easy lookup
                    self._keys = {key["kid"]: key for key in jwks["keys"]}
                    logger.info(f"Fetched {len(self._keys)} keys from Cognito JWKS")
            except httpx.HTTPError as e:
                logger.error(f"Failed to fetch Cognito JWKS: {e}")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Authentication service unavailable",
                )
        return self._keys
    
    def clear_cache(self):
        """Clear cached keys (useful for key rotation)."""
        self._keys = None


# Global JWKS instance
_jwks = CognitoJWKS()


async def get_jwks() -> CognitoJWKS:
    """Dependency to get the JWKS manager."""
    return _jwks


async def decode_token(
    token: str,
    jwks: Optional[CognitoJWKS] = None,
) -> TokenPayload:
    """
    Decode and verify a Cognito JWT token.
    
    Args:
        token: The JWT token string
        jwks: The JWKS manager
        
    Returns:
        TokenPayload with user information
        
    Raises:
        HTTPException: If token is invalid, expired, or verification fails
    """
    # Use global JWKS instance if not provided
    if jwks is None:
        jwks = _jwks
    
    # Check if Cognito is configured
    if not settings.cognito_user_pool_id or not settings.cognito_client_id:
        logger.warning("Cognito not configured, authentication disabled")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication not configured",
        )
    
    try:
        # Get the key ID from the token header
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        
        if not kid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing key ID",
            )
        
        # Fetch the public key
        keys = await jwks.get_keys()
        key = keys.get(kid)
        
        if not key:
            # Key not found - might be rotated, clear cache and retry once
            jwks.clear_cache()
            keys = await jwks.get_keys()
            key = keys.get(kid)
            
            if not key:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token: unknown key",
                )
        
        # Verify and decode the token
        payload = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=settings.cognito_client_id,
            issuer=jwks.issuer,
            options={
                "verify_exp": True,
                "verify_aud": True,
                "verify_iss": True,
            },
        )
        
        # Extract user info - Cognito ID tokens include email in claims
        return TokenPayload(
            sub=payload["sub"],
            email=payload.get("email", ""),
            name=payload.get("name"),
            token_use=payload.get("token_use", "id"),
            exp=payload["exp"],
        )
        
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except JWTError as e:
        logger.warning(f"JWT verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    FastAPI dependency that returns the current authenticated user.
    
    This dependency:
    1. Extracts the JWT from the Authorization header
    2. Checks if it's a demo token (for demo mode)
    3. Verifies the token with Cognito's public keys (for real auth)
    4. Looks up or creates the User in our database
    
    Usage:
        @app.get("/api/me")
        async def get_me(user: User = Depends(get_current_user)):
            return {"email": user.email}
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = credentials.credentials
    
    # Check if it's a demo token
    if await validate_demo_token(token):
        # Get or create demo user
        result = await db.execute(
            select(User).where(User.cognito_sub == DEMO_USER_SUB)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            user = User(
                cognito_sub=DEMO_USER_SUB,
                email=DEMO_USER_EMAIL,
                name=DEMO_USER_NAME,
            )
            db.add(user)
            await db.flush()
            logger.info(f"Created demo user: {user.email}")
        
        return user
    
    # Standard Cognito JWT validation
    token_payload = await decode_token(token)
    
    # Look up user by Cognito sub
    result = await db.execute(
        select(User).where(User.cognito_sub == token_payload.sub)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        # First login - create user record
        user = User(
            cognito_sub=token_payload.sub,
            email=token_payload.email,
            name=token_payload.name,
        )
        db.add(user)
        await db.flush()  # Get the ID without committing
        logger.info(f"Created new user: {user.email}")
    else:
        # Update email/name if changed in Cognito
        if user.email != token_payload.email:
            user.email = token_payload.email
        if token_payload.name and user.name != token_payload.name:
            user.name = token_payload.name
    
    return user


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """
    Optional user dependency - returns None if not authenticated.
    
    Useful for routes that work differently for authenticated vs anonymous users.
    """
    if not credentials:
        return None
    
    try:
        return await get_current_user(credentials, db)
    except HTTPException:
        return None


# =============================================================================
# Demo Authentication
# =============================================================================

DEMO_USER_SUB = "demo-user-12345"
DEMO_USER_EMAIL = "demo@microgrid-layout.ai"
DEMO_USER_NAME = "Demo User"
# Simple demo token - in production, use proper JWT
DEMO_TOKEN = "demo-token-microgrid-layout-ai"


async def validate_demo_token(token: str) -> bool:
    """Check if token is a valid demo token."""
    return token == DEMO_TOKEN


async def get_current_user_or_demo(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    Get current user - supports both Cognito JWT and demo tokens.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = credentials.credentials
    
    # Check if it's a demo token
    if await validate_demo_token(token):
        # Get or create demo user
        result = await db.execute(
            select(User).where(User.cognito_sub == DEMO_USER_SUB)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            user = User(
                cognito_sub=DEMO_USER_SUB,
                email=DEMO_USER_EMAIL,
                name=DEMO_USER_NAME,
            )
            db.add(user)
            await db.flush()
            logger.info(f"Created demo user: {user.email}")
        
        return user
    
    # Otherwise, use standard Cognito JWT validation
    return await get_current_user(credentials, db)

