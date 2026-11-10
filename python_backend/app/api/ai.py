
"""JARVIS AI chat endpoint powered by Groq."""

import httpx
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from app.core.config import settings
from app.core.security import verify_token
from app.services import session as sessions
from app.services.supabase_client import (
    SupabaseClient,
    get_client,
)

router = APIRouter(
    prefix="/ai",
    tags=["AI Assistant"],
    dependencies=[Depends(verify_token)],
)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

SYSTEM_PROMPT = """
You are JARVIS, an intelligent personal AI assistant.

Your responsibilities:
- Answer questions clearly and accurately.
- Help with programming, Python, Flutter, AI, and technology.
- Explain difficult topics in beginner-friendly language.
- Respond in Roman Urdu when the user writes in Roman Urdu.
- Respond in Urdu when the user writes in Urdu.
- Respond in English when the user writes in English.
- Provide complete code examples when requested.
- Be polite, helpful, and concise.

Important limitations:
- You cannot directly control the user's computer yet.
- Never claim to have executed a command or performed an action.
- Never invent information about actions performed on the computer.
"""


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Message empty nahi ho sakta.")

        return value


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)

    history: list[ChatMessage] = Field(
        default_factory=list,
        max_length=20,
    )

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Message empty nahi ho sakta.")

        return value


@router.post("/chat")
async def chat(
    body: ChatRequest,
    client: SupabaseClient = Depends(get_client),
) -> dict:

    # Verify Supabase login session.
    sessions.require_session(client)

    # Verify Groq configuration.
    if not settings.groq_api_key.strip():
        raise HTTPException(
            status_code=503,
            detail="Groq API key configure nahi hai. Root .env check karein.",
        )

    if not settings.groq_model.strip():
        raise HTTPException(
            status_code=503,
            detail="GROQ_MODEL configure nahi hai. Root .env check karein.",
        )

    # Prepare conversation messages.
    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        }
    ]

    for item in body.history:
        messages.append({
            "role": item.role,
            "content": item.content,
        })

    messages.append({
        "role": "user",
        "content": body.message,
    })

    payload = {
        "model": settings.groq_model,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 1024,
    }

    headers = {
        "Authorization": f"Bearer {settings.groq_api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=45.0) as http:
            response = await http.post(
                GROQ_URL,
                headers=headers,
                json=payload,
            )

        if response.status_code == 401:
            raise HTTPException(
                status_code=503,
                detail="Groq API key invalid hai. .env check karein.",
            )

        if response.status_code == 429:
            raise HTTPException(
                status_code=429,
                detail="Groq rate limit reached. Kuch dair baad try karein.",
            )

        if response.status_code == 400:
            raise HTTPException(
                status_code=400,
                detail="Groq request invalid hai. Model aur request settings check karein.",
            )

        if response.status_code >= 400:
            raise HTTPException(
                status_code=502,
                detail=f"Groq API error: {response.status_code}",
            )

        data = response.json()

        reply = data["choices"][0]["message"]["content"]

        if not isinstance(reply, str) or not reply.strip():
            raise HTTPException(
                status_code=502,
                detail="Groq ne empty response return kiya.",
            )

        return {
            "status": "ok",
            "reply": reply.strip(),
            "model": settings.groq_model,
        }

    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="Groq response timeout. Dobara try karein.",
        )

    except httpx.RequestError:
        raise HTTPException(
            status_code=502,
            detail="Groq API connection failed. Internet check karein.",
        )

    except (KeyError, IndexError, TypeError, ValueError):
        raise HTTPException(
            status_code=502,
            detail="Groq se unexpected response mila.",
        )
