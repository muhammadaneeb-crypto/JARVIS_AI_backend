
"""Central configuration. Reads values from .env / environment variables."""

import base64
import json
import os
import secrets
import sys
import tempfile

from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


# .env lives in the project root (JARVIS_AI/.env)
_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_ROOT / ".env")

APP_VERSION = "0.1.0-phase1"
_LOOPBACK = {"127.0.0.1", "localhost", "::1"}


def token_file_path() -> Path:
    """
    Windows:
        Store token in APPDATA so Flutter can read the same file.

    Linux / Vercel:
        Use writable temporary storage instead of the read-only home directory.
    """
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", str(Path.home())))
        return base / "JARVIS_AI" / "api_token.txt"

    return Path(tempfile.gettempdir()) / ".jarvis_ai" / "api_token.txt"


def load_or_create_token() -> str:
    """
    Prefer JARVIS_API_TOKEN environment variable.
    Otherwise load or create a local token file.
    """
    env_token = os.environ.get("JARVIS_API_TOKEN", "").strip()

    if env_token:
        return env_token

    path = token_file_path()

    try:
        if path.exists():
            existing = path.read_text(encoding="utf-8").strip()
            if existing:
                return existing

        path.parent.mkdir(parents=True, exist_ok=True)

        token = secrets.token_urlsafe(32)
        path.write_text(token, encoding="utf-8")

        return token

    except OSError as exc:
        raise RuntimeError(
            "Unable to load or create JARVIS API token. "
            "Configure JARVIS_API_TOKEN in environment variables."
        ) from exc


@dataclass(frozen=True)
class Settings:
    host: str
    port: int
    api_token: str
    groq_api_key: str
    groq_model: str
    tavily_api_key: str
    voice_provider_api_key: str
    supabase_url: str
    supabase_anon_key: str


def _is_service_role_key(key: str) -> bool:
    """Service role keys bypass all security. Never allowed in this app."""
    try:
        payload = key.split(".")[1]
        payload += "=" * (-len(payload) % 4)

        return (
            json.loads(base64.urlsafe_b64decode(payload)).get("role")
            == "service_role"
        )

    except Exception:
        return False


def _supabase_key() -> str:
    key = os.environ.get("SUPABASE_ANON_KEY", "").strip()

    if key and _is_service_role_key(key):
        print(
            "[JARVIS] SUPABASE_ANON_KEY is a service_role key. "
            "Refusing it. Use the anon/public key."
        )
        return ""

    return key


def _safe_host() -> str:
    host = os.environ.get(
        "JARVIS_HOST",
        "127.0.0.1",
    ).strip() or "127.0.0.1"

    if (
        host not in _LOOPBACK
        and os.environ.get("JARVIS_ALLOW_REMOTE") != "1"
    ):
        print(
            f"[JARVIS] Refusing non-local host '{host}'. "
            "Using 127.0.0.1 instead."
        )
        return "127.0.0.1"

    return host


def get_settings() -> Settings:
    return Settings(
        host=_safe_host(),
        port=int(os.environ.get("JARVIS_PORT", "8765")),
        api_token=load_or_create_token(),
        groq_api_key=os.environ.get("GROQ_API_KEY", ""),
        groq_model=os.environ.get("GROQ_MODEL", ""),
        tavily_api_key=os.environ.get("TAVILY_API_KEY", ""),
        voice_provider_api_key=os.environ.get(
            "VOICE_PROVIDER_API_KEY",
            "",
        ),
        supabase_url=os.environ.get(
            "SUPABASE_URL",
            "",
        ).strip().rstrip("/"),
        supabase_anon_key=_supabase_key(),
    )


settings = get_settings()
