
"""JARVIS Browser Automation using Playwright."""

import asyncio
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from playwright.async_api import (
    async_playwright,
    Error as PlaywrightError,
)

from app.core.security import verify_token
from app.services import session as sessions
from app.services.supabase_client import SupabaseClient, get_client


router = APIRouter(
    prefix="/browser",
    tags=["Browser Automation"],
    dependencies=[Depends(verify_token)],
)


# =========================================================
# REQUEST MODELS
# =========================================================

class BrowserNavigateRequest(BaseModel):
    url: str = Field(min_length=4, max_length=2048)

    wait_until: Literal[
        "domcontentloaded",
        "load",
        "networkidle",
    ] = "domcontentloaded"

    timeout_ms: int = Field(
        default=30000,
        ge=1000,
        le=60000,
    )


class BrowserExecuteRequest(BaseModel):
    action: Literal[
        "back",
        "forward",
        "reload",
        "new_tab",
        "get_page_info",
        "click",
        "fill",
        "press",
        "close_browser",
    ]

    url: str | None = Field(
        default=None,
        max_length=2048,
    )

    selector: str | None = Field(
        default=None,
        max_length=1000,
    )

    value: str | None = Field(
        default=None,
        max_length=5000,
    )

    key: str | None = Field(
        default=None,
        max_length=30,
    )

    timeout_ms: int = Field(
        default=15000,
        ge=1000,
        le=30000,
    )


# =========================================================
# URL VALIDATION
# =========================================================

def validate_http_url(url: str) -> str:
    """Allow only valid HTTP and HTTPS URLs."""

    url = url.strip()

    try:
        parsed = urlsplit(url)

        # Validate port if one is supplied.
        if parsed.port is not None:
            if not 1 <= parsed.port <= 65535:
                raise ValueError("Invalid port")

    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid website URL.",
        )

    if parsed.scheme.lower() not in ("http", "https"):
        raise HTTPException(
            status_code=400,
            detail="Only HTTP and HTTPS URLs are allowed.",
        )

    if not parsed.hostname:
        raise HTTPException(
            status_code=400,
            detail="Website hostname is missing.",
        )

    if parsed.username or parsed.password:
        raise HTTPException(
            status_code=400,
            detail="URLs containing credentials are not allowed.",
        )

    return url


# =========================================================
# BROWSER MANAGER
# =========================================================

class BrowserManager:
    """Manage a visible Chromium browser instance."""

    def __init__(self):
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

        # One lock protects browser lifecycle operations.
        self.lock = asyncio.Lock()

    async def _start_browser(self):
        """Start Playwright and visible Chromium."""

        self.playwright = await async_playwright().start()

        try:
            self.browser = await self.playwright.chromium.launch(
                headless=False,
            )

            self.context = await self.browser.new_context()

            self.page = await self.context.new_page()

        except Exception:
            await self._reset()
            raise

    async def get_page(self):
        """Return active page or start a new browser."""

        async with self.lock:

            if (
                self.browser is None
                or not self.browser.is_connected()
            ):
                await self._reset()
                await self._start_browser()

            if self.context is None:
                self.context = await self.browser.new_context()

            if self.page is None or self.page.is_closed():
                self.page = await self.context.new_page()

            return self.page

    async def new_tab(self):
        """Open a new tab without recursively acquiring the lock."""

        async with self.lock:

            if (
                self.browser is None
                or not self.browser.is_connected()
            ):
                await self._reset()
                await self._start_browser()

            if self.context is None:
                self.context = await self.browser.new_context()

            self.page = await self.context.new_page()

            return self.page

    async def close_browser(self):
        """Close Chromium and release Playwright resources."""

        async with self.lock:
            await self._reset()

    async def _reset(self):
        """Internal cleanup. Caller must hold the lock."""

        try:
            if self.browser and self.browser.is_connected():
                await self.browser.close()

        except Exception:
            pass

        try:
            if self.playwright:
                await self.playwright.stop()

        except Exception:
            pass

        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None


browser_manager = BrowserManager()


# =========================================================
# HELPER FUNCTIONS
# =========================================================

async def get_page_details(page):
    """Return current page information."""

    return {
        "url": page.url,
        "title": await page.title(),
        "is_closed": page.is_closed(),
    }


def raise_browser_error(exc: Exception):
    """Convert unexpected errors into useful API responses."""

    import traceback

    traceback.print_exc()

    raise HTTPException(
        status_code=500,
        detail={
            "error_type": type(exc).__name__,
            "error_message": str(exc) or repr(exc),
        },
    )


# =========================================================
# POST /browser/navigate
# =========================================================

@router.post("/navigate")
async def browser_navigate(
    body: BrowserNavigateRequest,
    client: SupabaseClient = Depends(get_client),
):
    """Navigate to a website in visible Chromium."""

    sessions.require_session(client)

    url = validate_http_url(body.url)

    try:
        page = await browser_manager.get_page()

        response = await page.goto(
            url,
            wait_until=body.wait_until,
            timeout=body.timeout_ms,
        )

        return {
            "status": "success",
            "message": "Website opened successfully.",
            "requested_url": url,
            "current_url": page.url,
            "title": await page.title(),
            "http_status": (
                response.status if response else None
            ),
        }

    except HTTPException:
        raise

    except PlaywrightError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            },
        )

    except Exception as exc:
        raise_browser_error(exc)


# =========================================================
# POST /browser/execute
# =========================================================

@router.post("/execute")
async def browser_execute(
    body: BrowserExecuteRequest,
    client: SupabaseClient = Depends(get_client),
):
    """Execute an approved action in the active browser."""

    sessions.require_session(client)

    action = body.action

    # -----------------------------------------------------
    # CLOSE BROWSER
    # -----------------------------------------------------

    if action == "close_browser":

        try:
            await browser_manager.close_browser()

            return {
                "status": "success",
                "action": action,
                "message": "Browser closed successfully.",
            }

        except Exception as exc:
            raise_browser_error(exc)

    try:

        # -------------------------------------------------
        # NEW TAB
        # -------------------------------------------------

        if action == "new_tab":

            page = await browser_manager.new_tab()

            if body.url:
                url = validate_http_url(body.url)

                await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=body.timeout_ms,
                )

        else:
            page = await browser_manager.get_page()

            # ---------------------------------------------
            # BACK
            # ---------------------------------------------

            if action == "back":

                await page.go_back(
                    wait_until="domcontentloaded",
                    timeout=body.timeout_ms,
                )

            # ---------------------------------------------
            # FORWARD
            # ---------------------------------------------

            elif action == "forward":

                await page.go_forward(
                    wait_until="domcontentloaded",
                    timeout=body.timeout_ms,
                )

            # ---------------------------------------------
            # RELOAD
            # ---------------------------------------------

            elif action == "reload":

                await page.reload(
                    wait_until="domcontentloaded",
                    timeout=body.timeout_ms,
                )

            # ---------------------------------------------
            # GET PAGE INFORMATION
            # ---------------------------------------------

            elif action == "get_page_info":

                return {
                    "status": "success",
                    "action": action,
                    **await get_page_details(page),
                }

            # ---------------------------------------------
            # CLICK ELEMENT
            # ---------------------------------------------

            elif action == "click":

                if not body.selector:
                    raise HTTPException(
                        status_code=400,
                        detail="CSS selector is required.",
                    )

                await page.locator(
                    body.selector
                ).first.click(
                    timeout=body.timeout_ms,
                )

            # ---------------------------------------------
            # FILL INPUT
            # ---------------------------------------------

            elif action == "fill":

                if not body.selector:
                    raise HTTPException(
                        status_code=400,
                        detail="CSS selector is required.",
                    )

                if body.value is None:
                    raise HTTPException(
                        status_code=400,
                        detail="Input value is required.",
                    )

                await page.locator(
                    body.selector
                ).first.fill(
                    body.value,
                    timeout=body.timeout_ms,
                )

            # ---------------------------------------------
            # PRESS KEY
            # ---------------------------------------------

            elif action == "press":

                if not body.selector:
                    raise HTTPException(
                        status_code=400,
                        detail="CSS selector is required.",
                    )

                if not body.key:
                    raise HTTPException(
                        status_code=400,
                        detail="Keyboard key is required.",
                    )

                await page.locator(
                    body.selector
                ).first.press(
                    body.key,
                    timeout=body.timeout_ms,
                )

        # -------------------------------------------------
        # COMMON RESPONSE
        # -------------------------------------------------

        return {
            "status": "success",
            "action": action,
            "message": f"Action '{action}' completed.",
            **await get_page_details(page),
        }

    except HTTPException:
        raise

    except PlaywrightError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "error_type": type(exc).__name__,
                "error_message": str(exc),
            },
        )

    except Exception as exc:
        raise_browser_error(exc)
