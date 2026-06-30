import logging
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from backend.core.config import SUPABASE_JWT_SECRET

logger = logging.getLogger('ats_resume_scorer')

# FastAPI security dependency for Bearer authentication
security = HTTPBearer(auto_error=False)

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """
    Extracts the user ID (sub) from the Supabase JWT.
    If SUPABASE_JWT_SECRET is configured, it verifies the signature.
    If SUPABASE_JWT_SECRET is not set, it attempts to decode the token without signature verification.
    If no token is provided, it falls back to a default mock user ID (for easier local testing).
    """
    if not credentials:
        logger.warning("No Authorization header provided. Falling back to mock user.")
        return "mock-user-123"

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
        return user_id

    except jwt.PyJWTError as exc:
        logger.error(f"JWT decoding failed: {exc}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate credentials: {str(exc)}"
        )
