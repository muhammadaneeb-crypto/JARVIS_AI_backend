
import asyncio
import sys
import uvicorn

from fastapi import FastAPI

# Windows Playwright subprocess compatibility
if sys.platform == "win32":
    asyncio.set_event_loop_policy(
        asyncio.WindowsProactorEventLoopPolicy()
    )

from app.api import (
    agent,
    ai,
    auth,
    browser,
    files,
    health,
    history,
    stubs,
    system,
    voice,
    windows,
)

from app.core.config import APP_VERSION, settings


def create_app() -> FastAPI:
    app = FastAPI(
        title="JARVIS_AI Backend",
        version=APP_VERSION,
    )

    # Health and system
    app.include_router(health.router)
    app.include_router(system.router)

    # Authentication and history
    app.include_router(auth.router)
    app.include_router(history.router)

    # AI and voice
    app.include_router(ai.router)
    app.include_router(voice.router)

    # Windows automation
    app.include_router(windows.router)
    app.include_router(agent.router)

    # Browser automation
    app.include_router(browser.router)

    # File management
    app.include_router(files.router)

    # Remaining planned endpoints
    app.include_router(stubs.router)

    return app


app = create_app()


if __name__ == "__main__":
    print(
        f"[JARVIS] Backend starting on "
        f"http://{settings.host}:{settings.port}"
    )

    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_level="info",
        loop="asyncio",
        reload=False,
    )
