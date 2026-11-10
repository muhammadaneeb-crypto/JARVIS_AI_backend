from fastapi import APIRouter

from app.core.config import APP_VERSION, settings

router = APIRouter()


@router.get("/health")
def health() -> dict:
    """Public endpoint. Reports which optional features have API keys configured."""
    return {
        "status": "ok",
        "app": "JARVIS_AI",
        "version": APP_VERSION,
        "features": {
            "ai_chat": bool(settings.groq_api_key),
            "web_search": bool(settings.tavily_api_key),
            "voice_provider": bool(settings.voice_provider_api_key),
            "supabase": bool(settings.supabase_url and settings.supabase_anon_key),
        },
        "notes": [
            "AI chat needs GROQ_API_KEY (Phase 3).",
            "Web search needs TAVILY_API_KEY (Phase 5).",
            "Login/database needs SUPABASE_URL and SUPABASE_ANON_KEY.",
        ],
    }
