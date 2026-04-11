"""Simple JWT authentication helpers."""

from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings
from app.database import get_user_by_email
from app.models import TokenPayload


# Passlib hashes passwords so we never store plain text passwords in MySQL.
# We use pbkdf2_sha256 here because it is simple to run and avoids bcrypt
# backend/version issues in local beginner setups.
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

# The client sends the token in the Authorization header like:
# Authorization: Bearer your.jwt.token
security = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    """Convert a plain password into a secure hash."""
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """Check if the plain password matches the stored hash."""
    return pwd_context.verify(plain, hashed)


def create_access_token(data: dict) -> str:
    """Create a JWT that expires in 1 hour.

    JWT is a signed token. We put the user's email inside it so the
    server can identify the user on later requests.
    """
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(hours=1)
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> TokenPayload:
    """Decode the JWT and return the stored email."""
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        return TokenPayload(sub=payload["sub"])
    except (JWTError, KeyError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        ) from exc


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
):
    """Read the Bearer token, decode it, and load the current user."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    token_data = decode_access_token(credentials.credentials)
    user = get_user_by_email(token_data.sub)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    return user
