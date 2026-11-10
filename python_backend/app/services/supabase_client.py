"""Small Supabase client using plain HTTP (no heavy SDK, light on 8 GB RAM).
Uses ONLY the anon key. Database access goes through the logged-in user's token,
so Supabase Row Level Security (RLS) protects each user's data."""
import httpx
from fastapi import HTTPException

from app.core.config import settings


class SupabaseError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class SupabaseClient:
    def __init__(self, url: str, anon_key: str, transport: httpx.BaseTransport | None = None):
        self._url = url.rstrip("/")
        self._key = anon_key
        self._http = httpx.Client(timeout=15, transport=transport)

    def _headers(self, token: str | None = None, extra: dict | None = None) -> dict:
        h = {"apikey": self._key, "Authorization": f"Bearer {token or self._key}",
             "Content-Type": "application/json"}
        if extra:
            h.update(extra)
        return h

    def _send(self, method: str, path: str, **kw) -> httpx.Response:
        try:
            resp = self._http.request(method, f"{self._url}{path}", **kw)
        except httpx.RequestError as exc:
            raise SupabaseError(502, f"Supabase tak pohanch nahi saka (internet check karein): {exc.__class__.__name__}")
        if resp.status_code >= 400:
            try:
                j = resp.json()
                msg = j.get("msg") or j.get("error_description") or j.get("message") or j.get("error")
            except Exception:
                msg = None
            raise SupabaseError(resp.status_code, str(msg or f"Supabase error {resp.status_code}"))
        return resp

    # ---- auth ----
    def sign_up(self, email: str, password: str) -> dict:
        return self._send("POST", "/auth/v1/signup", headers=self._headers(),
                          json={"email": email, "password": password}).json()

    def sign_in(self, email: str, password: str) -> dict:
        return self._send("POST", "/auth/v1/token", params={"grant_type": "password"},
                          headers=self._headers(), json={"email": email, "password": password}).json()

    def refresh(self, refresh_token: str) -> dict:
        return self._send("POST", "/auth/v1/token", params={"grant_type": "refresh_token"},
                          headers=self._headers(), json={"refresh_token": refresh_token}).json()

    def sign_out(self, access_token: str) -> None:
        self._send("POST", "/auth/v1/logout", headers=self._headers(access_token))

    # ---- database (PostgREST) ----
    def select(self, table: str, token: str, params: dict) -> list:
        return self._send("GET", f"/rest/v1/{table}", headers=self._headers(token), params=params).json()

    def insert(self, table: str, token: str, row: dict) -> dict:
        resp = self._send("POST", f"/rest/v1/{table}",
                          headers=self._headers(token, {"Prefer": "return=representation"}), json=row)
        data = resp.json()
        return data[0] if isinstance(data, list) and data else data


_client: SupabaseClient | None = None


def get_client() -> SupabaseClient:
    """FastAPI dependency. Fails with a clear message when Supabase is not set up."""
    global _client
    if not settings.supabase_url or not settings.supabase_anon_key:
        raise HTTPException(503, "Supabase configure nahi hai. .env mein SUPABASE_URL aur SUPABASE_ANON_KEY daalein.")
    if _client is None:
        _client = SupabaseClient(settings.supabase_url, settings.supabase_anon_key)
    return _client


def get_client_optional() -> SupabaseClient | None:
    """Like get_client, but returns None when Supabase is not configured (used by logout)."""
    try:
        return get_client()
    except HTTPException:
        return None
