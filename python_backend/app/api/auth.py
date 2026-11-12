import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.core.config import settings
from app.core.security import verify_token
from app.services import session as sessions
from app.services.supabase_client import SupabaseClient, SupabaseError, get_client, get_client_optional

router = APIRouter(prefix="/auth")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class _EmailMixin(BaseModel):
    email: str = Field(max_length=254)

    @field_validator("email")
    @classmethod
    def _check_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL.match(v):
            raise ValueError("Email sahi nahi hai.")
        return v


class SignupRequest(_EmailMixin):
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(_EmailMixin):
    password: str = Field(min_length=1, max_length=128)


def _user_public(user: dict) -> dict:
    return {"id": user.get("id"), "email": user.get("email")}


def _call(fn, *args):
    try:
        return fn(*args)
    except SupabaseError as exc:
        status = exc.status if exc.status in (400, 401, 403, 409, 422, 429, 502) else 400
        raise HTTPException(status, exc.message)


@router.post("/signup")
def signup(body: SignupRequest, client: SupabaseClient = Depends(get_client)) -> dict:
    data = _call(client.sign_up, body.email, body.password)
    if data.get("access_token"):
        sess = sessions.store_from_response(data)
        return {"status": "ok", "logged_in": True, "user": _user_public(sess.user)}
    return {"status": "confirmation_required", "logged_in": False,
            "message": "Account ban gaya. Apni email check karein aur confirmation link par click karein, phir login karein."}


@router.post("/login")
def login(body: LoginRequest, client: SupabaseClient = Depends(get_client)) -> dict:
    data = _call(client.sign_in, body.email, body.password)
    sess = sessions.store_from_response(data)
    return {"status": "ok", "logged_in": True, "user": _user_public(sess.user)}


@router.post("/logout", dependencies=[Depends(verify_token)])
def logout(client: SupabaseClient | None = Depends(get_client_optional)) -> dict:
    sess = sessions.current()
    sessions.clear()  # always forget the session locally
    if sess is not None and client is not None:
        try:
            client.sign_out(sess.access_token)
        except SupabaseError:
            pass  # local logout already done
    return {"status": "ok", "logged_in": False}


@router.get("/me", dependencies=[Depends(verify_token)])
def me() -> dict:
    sess = sessions.current()
    return {
        "status": "ok",
        "supabase_configured": bool(settings.supabase_url and settings.supabase_anon_key),
        "logged_in": sess is not None,
        "user": _user_public(sess.user) if sess else None,
    }
