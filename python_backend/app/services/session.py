"""Keeps the logged-in user's session in backend MEMORY only.
Tokens are never sent to the database and never stored in the Flutter app.
After the backend restarts, the user logs in again."""
import threading
import time
from dataclasses import dataclass

from fastapi import HTTPException

from app.services.supabase_client import SupabaseClient, SupabaseError


@dataclass
class Session:
    access_token: str
    refresh_token: str
    expires_at: float
    user: dict


_lock = threading.Lock()
_session: Session | None = None


def store_from_response(data: dict) -> Session:
    global _session
    expires_at = data.get("expires_at") or (time.time() + int(data.get("expires_in", 3600)))
    sess = Session(data["access_token"], data.get("refresh_token", ""), float(expires_at), data.get("user") or {})
    with _lock:
        _session = sess
    return sess


def current() -> Session | None:
    with _lock:
        return _session


def clear() -> None:
    global _session
    with _lock:
        _session = None


def require_session(client: SupabaseClient) -> Session:
    """Returns a valid session (refreshing if close to expiry) or raises 401."""
    sess = current()
    if sess is None:
        raise HTTPException(401, "Pehle login karein.")
    if sess.expires_at - time.time() < 60:
        try:
            data = client.refresh(sess.refresh_token)
            if not data.get("user"):
                data["user"] = sess.user
            sess = store_from_response(data)
        except SupabaseError:
            clear()
            raise HTTPException(401, "Session expire ho gaya. Dobara login karein.")
    return sess
