
"""JARVIS voice endpoints: Groq Whisper transcription and Edge TTS."""

import asyncio
from pathlib import Path
from typing import Literal

import edge_tts
import httpx

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.security import verify_token
from app.services import session as sessions
from app.services.supabase_client import SupabaseClient, get_client


router = APIRouter(
    prefix="/ai/voice",
    tags=["Voice Assistant"],
    dependencies=[Depends(verify_token)],
)

GROQ_TRANSCRIPTION_URL = (
    "https://api.groq.com/openai/v1/audio/transcriptions"
)

WHISPER_MODEL = "whisper-large-v3-turbo"
MAX_AUDIO_SIZE = 25 * 1024 * 1024

SUPPORTED_FORMATS = {
    ".mp3", ".mp4", ".mpeg", ".mpga",
    ".m4a", ".wav", ".webm", ".ogg", ".flac",
}


# -------------------------
# Text-to-Speech request
# -------------------------

class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)

    voice: Literal[
        "en-US-AriaNeural",
        "en-US-GuyNeural",
        "ur-PK-UzmaNeural",
        "ur-PK-AsadNeural",
    ] = "en-US-AriaNeural"

    rate: int = Field(default=0, ge=-50, le=50)
    pitch: int = Field(default=0, ge=-50, le=50)


# -------------------------
# POST /ai/voice/speak
# -------------------------

@router.post("/speak")
async def speak_text(
    request: SpeakRequest,
    client: SupabaseClient = Depends(get_client),
):
    """Convert text into MP3 speech using Edge TTS."""

    sessions.require_session(client)

    text = request.text.strip()

    if not text:
        raise HTTPException(
            status_code=400,
            detail="Speech text cannot be empty.",
        )

    communicate = edge_tts.Communicate(
        text=text,
        voice=request.voice,
        rate=f"{request.rate:+d}%",
        pitch=f"{request.pitch:+d}Hz",
    )

    audio_data = bytearray()

    try:
        async def collect_audio():
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data.extend(chunk["data"])

        await asyncio.wait_for(
            collect_audio(),
            timeout=90.0,
        )

    except asyncio.TimeoutError:
        raise HTTPException(
            status_code=504,
            detail="Speech generation timed out. Please try again.",
        )

    except Exception:
        raise HTTPException(
            status_code=502,
            detail="Speech generation failed. Check your internet connection and try again.",
        )

    if not audio_data:
        raise HTTPException(
            status_code=502,
            detail="No audio was generated.",
        )

    return Response(
        content=bytes(audio_data),
        media_type="audio/mpeg",
        headers={
            "Content-Disposition": 'attachment; filename="jarvis_speech.mp3"',
            "Cache-Control": "no-store",
        },
    )


# -------------------------
# POST /ai/voice/transcribe
# -------------------------

@router.post("/transcribe")
async def transcribe_audio(
    audio: UploadFile = File(...),
    language: str | None = Form(default=None),
    client: SupabaseClient = Depends(get_client),
) -> dict:
    """Convert uploaded audio into text using Groq Whisper."""

    sessions.require_session(client)

    if not settings.groq_api_key.strip():
        raise HTTPException(
            status_code=503,
            detail="Groq API key configure nahi hai.",
        )

    filename = Path(audio.filename or "").name

    if not filename:
        raise HTTPException(
            status_code=400,
            detail="Audio filename missing hai.",
        )

    extension = Path(filename).suffix.lower()

    if extension not in SUPPORTED_FORMATS:
        raise HTTPException(
            status_code=415,
            detail="Unsupported audio format.",
        )

    audio_bytes = await audio.read(MAX_AUDIO_SIZE + 1)
    await audio.close()

    if not audio_bytes:
        raise HTTPException(
            status_code=400,
            detail="Audio file empty hai.",
        )

    if len(audio_bytes) > MAX_AUDIO_SIZE:
        raise HTTPException(
            status_code=413,
            detail="Audio file maximum 25 MB honi chahiye.",
        )

    form_data = {
        "model": WHISPER_MODEL,
        "response_format": "json",
    }

    if language and language.strip():
        form_data["language"] = language.strip()

    headers = {
        "Authorization": f"Bearer {settings.groq_api_key}",
    }

    files = {
        "file": (
            filename,
            audio_bytes,
            audio.content_type or "application/octet-stream",
        )
    }

    try:
        async with httpx.AsyncClient(timeout=90.0) as http:
            response = await http.post(
                GROQ_TRANSCRIPTION_URL,
                headers=headers,
                data=form_data,
                files=files,
            )

        if response.status_code == 401:
            raise HTTPException(
                status_code=503,
                detail="Groq API key invalid hai.",
            )

        if response.status_code == 413:
            raise HTTPException(
                status_code=413,
                detail="Groq ne audio file size reject kar di.",
            )

        if response.status_code == 429:
            raise HTTPException(
                status_code=429,
                detail="Groq rate limit reached.",
            )

        if response.status_code >= 400:
            raise HTTPException(
                status_code=502,
                detail={
                    "message": "Groq transcription failed",
                    "groq_status": response.status_code,
                    "groq_error": response.text[:1000],
                },
            )

        data = response.json()
        transcription = data.get("text", "")

        if not isinstance(transcription, str) or not transcription.strip():
            raise HTTPException(
                status_code=502,
                detail="Audio se text generate nahi ho saka.",
            )

        return {
            "status": "ok",
            "text": transcription.strip(),
            "model": WHISPER_MODEL,
            "filename": filename,
        }

    except HTTPException:
        raise

    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="Transcription timeout.",
        )

    except httpx.RequestError:
        raise HTTPException(
            status_code=502,
            detail="Groq API connection failed. Internet check karein.",
        )
