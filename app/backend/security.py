"""Opaque database-backed bearer sessions and scrypt passwords; demo auth is opt-in."""
from __future__ import annotations
import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from .db import get_db
from .models import AuthToken, User

bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    if len(password) < 10 or len(password) > 256:
        raise ValueError("Password length must be 10–256 characters")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
    return "scrypt-v1$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, salt_text, digest_text = encoded.split("$")
        if scheme != "scrypt-v1":
            return False
        salt = base64.b64decode(salt_text)
        expected = base64.b64decode(digest_text)
        actual = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1)
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def new_token(db: Session, user: User) -> str:
    plain = secrets.token_urlsafe(40)
    hashed = hashlib.sha256(plain.encode()).hexdigest()
    db.add(AuthToken(token_hash=hashed, user_id=user.id,
                     expires_at=datetime.now(timezone.utc) + timedelta(days=3)))
    db.commit()
    return plain


def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
                 db: Session = Depends(get_db)) -> User:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Login required")
    hashed = hashlib.sha256(credentials.credentials.encode()).hexdigest()
    record = db.get(AuthToken, hashed)
    expiry = record.expires_at if record else None
    if expiry is not None and expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    if not record or expiry <= datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Session expired or invalid")
    user = db.get(User, record.user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user
