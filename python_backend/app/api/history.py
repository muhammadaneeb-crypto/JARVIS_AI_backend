from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.core.security import verify_token
from app.services import session as sessions
from app.services.supabase_client import SupabaseClient, SupabaseError, get_client
from fastapi import HTTPException

router = APIRouter(dependencies=[Depends(verify_token)])


class HistoryItem(BaseModel):
    kind: str = Field(min_length=1, max_length=40)
    summary: str = Field(min_length=1, max_length=500)
    status: str = Field(default="done", pattern="^(done|failed|pending)$")


@router.get("/history")
def list_history(limit: int = Query(50, ge=1, le=200), client: SupabaseClient = Depends(get_client)) -> dict:
    sess = sessions.require_session(client)
    try:
        rows = client.select("task_history", sess.access_token,
                             {"select": "id,kind,summary,status,created_at",
                              "order": "created_at.desc", "limit": str(limit)})
    except SupabaseError as exc:
        raise HTTPException(502, exc.message)
    return {"status": "ok", "items": rows}


@router.post("/history", status_code=201)
def add_history(item: HistoryItem, client: SupabaseClient = Depends(get_client)) -> dict:
    sess = sessions.require_session(client)
    try:
        row = client.insert("task_history", sess.access_token,
                            {"kind": item.kind, "summary": item.summary, "status": item.status,
                             "user_id": sess.user.get("id")})
    except SupabaseError as exc:
        raise HTTPException(502, exc.message)
    return {"status": "ok", "item": row}
