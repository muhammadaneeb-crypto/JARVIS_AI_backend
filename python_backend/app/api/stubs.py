
"""Placeholder endpoints for JARVIS features not implemented yet."""

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.core.security import verify_token


router = APIRouter(
    tags=["Planned Features"],
    dependencies=[Depends(verify_token)],
)


# These endpoints are implemented in their own API modules.
# Never register them here:
# POST /ai/chat
# POST /windows/open-app


PLANNED = [
    
  
  

    
]


def create_placeholder(path: str, phase: int):
    async def handler():
        return JSONResponse(
            status_code=501,
            content={
                "status": "not_implemented",
                "endpoint": path,
                "phase": phase,
                "message": (
                    f"This feature is not implemented yet. "
                    f"It is planned for Phase {phase}."
                ),
            },
        )

    handler.__name__ = (
        "placeholder_" + path.strip("/").replace("/", "_").replace("-", "_")
    )

    return handler


for method, path, phase in PLANNED:
    router.add_api_route(
        path,
        create_placeholder(path, phase),
        methods=[method],
        name=f"placeholder_{path.strip('/').replace('/', '_')}",
    )
