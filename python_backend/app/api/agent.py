
"""JARVIS AI Agent planning, execution and web search endpoints."""

import json
import httpx

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.windows import OpenAppRequest, open_app
from app.core.config import settings
from app.core.security import verify_token
from app.services import session as sessions
from app.services.supabase_client import SupabaseClient, get_client


router = APIRouter(
    prefix="/agent",
    tags=["AI Agent"],
    dependencies=[Depends(verify_token)],
)

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
TAVILY_URL = "https://api.tavily.com/search"


ALLOWED_ACTIONS = {"open_app"}

ALLOWED_APPS = {
    "notepad",
    "calculator",
    "explorer",
    "chrome",
    "edge",
    "vscode",
    "whatsapp",
    "linkedin",
    "facebook",
    "microsoft_store",
    "copilot",
    "wps_office",
    "word",
    "excel",
    "powerpoint",
}


# ---------------------------------------------------------
# REQUEST MODELS
# ---------------------------------------------------------

class ExecuteRequest(BaseModel):
    action: str = Field(min_length=1, max_length=50)
    app: str = Field(min_length=1, max_length=50)


class PlanRequest(BaseModel):
    command: str = Field(
        min_length=2,
        max_length=2000,
        description="Natural language command for JARVIS.",
    )


class WebSearchRequest(BaseModel):
    query: str = Field(
        min_length=2,
        max_length=500,
        description="What JARVIS should search on the internet.",
    )
    max_results: int = Field(default=5, ge=1, le=10)
    search_depth: Literal["basic", "advanced"] = "basic"
    include_answer: bool = True


# ---------------------------------------------------------
# PLAN VALIDATION
# ---------------------------------------------------------

def validate_plan(data: dict) -> list[dict]:
    """Validate the AI-generated plan against the safe allowlist."""

    steps = data.get("steps")

    if not isinstance(steps, list):
        raise ValueError("Plan must contain a steps list.")

    if len(steps) > 10:
        raise ValueError("Maximum 10 steps are allowed.")

    validated_steps = []

    for step in steps:
        if not isinstance(step, dict):
            raise ValueError("Invalid step format.")

        action = str(step.get("action", "")).strip().lower()
        app = str(step.get("app", "")).strip().lower()
        description = str(step.get("description", "")).strip()

        if action not in ALLOWED_ACTIONS:
            raise ValueError("Unsupported action in generated plan.")

        if app not in ALLOWED_APPS:
            raise ValueError(
                f"Application '{app}' is not in the approved allowlist."
            )

        validated_steps.append({
            "action": action,
            "app": app,
            "description": description[:200],
        })

    return validated_steps


# ---------------------------------------------------------
# AGENT PLAN
# ---------------------------------------------------------

@router.post("/plan")
async def create_plan(
    body: PlanRequest,
    client: SupabaseClient = Depends(get_client),
) -> dict:
    """Convert a natural-language command into a safe execution plan."""

    sessions.require_session(client)

    if not settings.groq_api_key.strip():
        raise HTTPException(
            status_code=503,
            detail="Groq API key configure nahi hai.",
        )

    if not settings.groq_model.strip():
        raise HTTPException(
            status_code=503,
            detail="GROQ_MODEL configure nahi hai.",
        )

    system_prompt = """
You are JARVIS, a safe Windows desktop assistant.

Your task is to convert the user's command into an execution plan.

You can ONLY create these actions:
- open_app

Allowed application values:
- notepad
- calculator
- explorer
- chrome
- edge
- vscode
- whatsapp
- linkedin
- facebook
- microsoft_store
- copilot
- wps_office
- word
- excel
- powerpoint

Rules:
1. Return ONLY valid JSON.
2. Use this exact JSON structure:
   {
     "steps": [
       {
         "action": "open_app",
         "app": "chrome",
         "description": "Open Google Chrome"
       }
     ]
   }
3. Maximum 10 steps.
4. Never invent applications outside the allowed list.
5. Never create shell commands, terminal commands, scripts,
   or arbitrary code execution actions.
6. If the user requests an unsupported action or application,
   return {"steps": []}.
7. Keep steps in the order requested by the user.
8. Use lowercase application values exactly as listed.
"""

    payload = {
        "model": settings.groq_model,
        "messages": [
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": body.command.strip(),
            },
        ],
        "temperature": 0,
        "max_tokens": 1200,
        "response_format": {
            "type": "json_object",
        },
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
                detail="Groq API key invalid hai.",
            )

        if response.status_code == 429:
            raise HTTPException(
                status_code=429,
                detail="Groq rate limit reached. Baad mein try karein.",
            )

        if response.status_code >= 400:
            raise HTTPException(
                status_code=502,
                detail=f"Groq API error: {response.status_code}",
            )

        response_data = response.json()
        content = response_data["choices"][0]["message"]["content"]

        if not isinstance(content, str) or not content.strip():
            raise HTTPException(
                status_code=502,
                detail="Groq ne empty plan return kiya.",
            )

        try:
            parsed = json.loads(content)
            steps = validate_plan(parsed)

        except (json.JSONDecodeError, ValueError, TypeError):
            raise HTTPException(
                status_code=502,
                detail="Groq ne invalid ya unsupported execution plan return kiya.",
            )

        return {
            "status": "success",
            "command": body.command,
            "total_steps": len(steps),
            "plan": steps,
            "execution_required": True,
            "message": "Plan generated. Execute each approved step separately.",
        }

    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="Groq response timeout.",
        )

    except httpx.RequestError:
        raise HTTPException(
            status_code=502,
            detail="Groq API connection failed.",
        )


# ---------------------------------------------------------
# AGENT EXECUTE
# ---------------------------------------------------------

@router.post("/execute")
async def execute_action(
    body: ExecuteRequest,
    client: SupabaseClient = Depends(get_client),
) -> dict:
    """Execute one explicitly approved JARVIS action."""

    sessions.require_session(client)

    action = body.action.lower().strip()
    app = body.app.lower().strip()

    if action not in ALLOWED_ACTIONS:
        raise HTTPException(
            status_code=400,
            detail="Unsupported action.",
        )

    if app not in ALLOWED_APPS:
        raise HTTPException(
            status_code=400,
            detail=f"{app} is not an approved application.",
        )

    result = open_app(OpenAppRequest(app=app))

    return {
        "status": "ok",
        "action": action,
        "result": result,
    }


# ---------------------------------------------------------
# AGENT WEB SEARCH
# ---------------------------------------------------------

@router.post("/web-search")
async def web_search(
    body: WebSearchRequest,
    client: SupabaseClient = Depends(get_client),
) -> dict:
    """
    Search the internet using Tavily.

    Returns search results with titles, URLs, content and relevance scores.
    """

    sessions.require_session(client)

    tavily_api_key = settings.tavily_api_key.strip()

    if not tavily_api_key:
        raise HTTPException(
            status_code=503,
            detail="Tavily API key configure nahi hai.",
        )

    payload = {
        "api_key": tavily_api_key,
        "query": body.query.strip(),
        "search_depth": body.search_depth,
        "max_results": body.max_results,
        "include_answer": body.include_answer,
        "include_raw_content": False,
    }

    try:
        async with httpx.AsyncClient(timeout=40.0) as http:
            response = await http.post(
                TAVILY_URL,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                },
            )

        if response.status_code in (401, 403):
            raise HTTPException(
                status_code=503,
                detail="Tavily API key invalid hai ya access denied hai.",
            )

        if response.status_code == 429:
            raise HTTPException(
                status_code=429,
                detail="Tavily rate limit reached. Baad mein try karein.",
            )

        if response.status_code >= 400:
            raise HTTPException(
                status_code=502,
                detail=f"Tavily API error: {response.status_code}",
            )

        data = response.json()

        raw_results = data.get("results", [])

        results = []

        for item in raw_results:
            if not isinstance(item, dict):
                continue

            results.append({
                "title": item.get("title"),
                "url": item.get("url"),
                "content": item.get("content"),
                "score": item.get("score"),
                "published_date": item.get("published_date"),
            })

        return {
            "status": "success",
            "query": body.query,
            "answer": data.get("answer"),
            "total_results": len(results),
            "results": results,
            "response_time": data.get("response_time"),
        }

    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="Tavily search timeout. Dobara try karein.",
        )

    except httpx.RequestError:
        raise HTTPException(
            status_code=502,
            detail="Tavily API connection failed.",
        )

    except ValueError:
        raise HTTPException(
            status_code=502,
            detail="Tavily returned an invalid response.",
        )
