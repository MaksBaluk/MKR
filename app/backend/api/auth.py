from datetime import datetime, timezone
import hashlib
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, delete
from sqlalchemy.orm import Session
from backend.api.common import make_default_profile
from backend.config import get_settings
from backend.db import get_db
from backend.models import AuthToken, User
from backend.security import current_user, hash_password, verify_password, new_token, bearer

router = APIRouter(prefix="/auth", tags=["authentication"])


class RegisterInput(BaseModel):
    email: str
    display_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=10, max_length=256)


class LoginInput(BaseModel):
    email: str
    password: str


def user_dict(user: User) -> dict:
    return {"id": user.id, "email": user.email, "display_name": user.display_name, "track": user.track,
            "desired_title": user.desired_title, "years_experience": user.years_experience, "location": user.location}


@router.post("/register", status_code=201)
def register(data: RegisterInput, db: Session = Depends(get_db)):
    email = data.email.strip().lower()
    if "@" not in email or "." not in email.split("@")[-1]:
        raise HTTPException(422, "Invalid email")
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(409, "Email already registered")
    user = User(email=email, display_name=data.display_name.strip(), password_hash=hash_password(data.password))
    db.add(user)
    db.flush()
    make_default_profile(db, user)
    db.commit()
    return {"token": new_token(db, user), "user": user_dict(user)}


@router.post("/login")
def login(data: LoginInput, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == data.email.strip().lower()))
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "Invalid email or password")
    return {"token": new_token(db, user), "user": user_dict(user)}


@router.post("/demo")
def demo_login(db: Session = Depends(get_db)):
    config = get_settings()
    if not config.demo_mode:
        raise HTTPException(404, "Demo login is disabled")
    user = db.scalar(select(User).where(User.email == config.demo_email.lower()))
    if not user:
        raise HTTPException(503, "Demo account not seeded")
    return {"token": new_token(db, user), "user": user_dict(user)}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return user_dict(user)


@router.post("/logout", status_code=204)
def logout(credentials=Depends(bearer), db: Session = Depends(get_db), user: User = Depends(current_user)):
    if credentials:
        hashed = hashlib.sha256(credentials.credentials.encode()).hexdigest()
        db.execute(delete(AuthToken).where(AuthToken.token_hash == hashed, AuthToken.user_id == user.id))
        db.commit()
