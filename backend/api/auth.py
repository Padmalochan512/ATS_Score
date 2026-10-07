import logging
from dataclasses import dataclass
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from backend.core.config import ENABLE_MOCK_AUTH, OWNER_EMAILS, SUPABASE_JWT_SECRET

logger = logging.getLogger('ats_resume_scorer')

# FastAPI security dependency for Bearer authentication
security = HTTPBearer(auto_error=False)

@dataclass
class CurrentUser:
    user_id: str
    email: str = ""
    role: str = "user"
    provider: str = ""
    is_mock: bool = False

    @property
    def is_owner(self) -> bool:
        return self.email.lower() in OWNER_EMAILS or self.role == "owner"


def get_current_user_context(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> CurrentUser:
    """
    Extracts the user ID (sub) from the Supabase JWT.
    If SUPABASE_JWT_SECRET is configured, it verifies the signature.
    If SUPABASE_JWT_SECRET is not set, it attempts to decode the token without signature verification.
    If no token is provided, it falls back to a default mock user ID (for easier local testing).
    """
    if not credentials:
        if not ENABLE_MOCK_AUTH:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required.",
            )
        logger.warning("No Authorization header provided. Falling back to mock user.")
        return CurrentUser(
            user_id="mock-user-123",
            email="mock@example.com",
            role="mock",
            provider="mock",
            is_mock=True,
        )

    token = credentials.credentials
    try:
        if SUPABASE_JWT_SECRET:
            # Decode and verify token signature using the secret.
            # Supabase tokens are signed with HS256.
            payload = jwt.decode(
                token,
                SUPABASE_JWT_SECRET,
                algorithms=["HS256"],
                options={"verify_aud": False}
            )
        else:
            # If secret is not provided, decode without verification (development fallback).
            logger.warning("SUPABASE_JWT_SECRET is not set. Decoding JWT without signature verification.")
            payload = jwt.decode(
                token,
                options={"verify_signature": False}
            )
        
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: 'sub' (user_id) claim is missing."
            )
        return CurrentUser(
            user_id=user_id,
            email=(payload.get("email") or "").strip(),
            role=(payload.get("role") or payload.get("app_metadata", {}).get("role") or "user"),
            provider=(payload.get("app_metadata", {}) or {}).get("provider", ""),
        )

    except jwt.PyJWTError as exc:
        logger.error(f"JWT decoding failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate credentials: {str(exc)}"
        )


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    return get_current_user_context(credentials).user_id


def require_owner(user: CurrentUser = Depends(get_current_user_context)) -> CurrentUser:
    if user.is_mock:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Owner access requires a real signed-in account.",
        )
    if not user.is_owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owner access only.",
        )
    return user
