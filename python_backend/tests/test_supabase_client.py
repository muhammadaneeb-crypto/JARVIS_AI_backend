import json

import httpx
import pytest

from app.services.supabase_client import SupabaseClient, SupabaseError


def make(handler):
    return SupabaseClient("https://x.supabase.co/", "anon-key", transport=httpx.MockTransport(handler))


def test_sign_in_request_shape():
    seen = {}

    def handler(req: httpx.Request):
        seen["url"] = str(req.url)
        seen["apikey"] = req.headers["apikey"]
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={"access_token": "t", "user": {"id": "1"}})

    data = make(handler).sign_in("a@b.co", "pw")
    assert seen["url"] == "https://x.supabase.co/auth/v1/token?grant_type=password"
    assert seen["apikey"] == "anon-key"
    assert seen["body"] == {"email": "a@b.co", "password": "pw"}
    assert data["access_token"] == "t"


def test_insert_uses_user_token_not_anon():
    def handler(req: httpx.Request):
        assert req.headers["authorization"] == "Bearer user-token"
        assert req.headers["prefer"] == "return=representation"
        return httpx.Response(201, json=[{"id": "r1"}])

    assert make(handler).insert("task_history", "user-token", {"kind": "k"}) == {"id": "r1"}


def test_error_message_is_extracted():
    def handler(req):
        return httpx.Response(400, json={"error_description": "Invalid login credentials"})

    with pytest.raises(SupabaseError) as e:
        make(handler).sign_in("a@b.co", "bad")
    assert e.value.status == 400 and "Invalid login" in e.value.message


def test_network_failure_becomes_502():
    def handler(req):
        raise httpx.ConnectError("down")

    with pytest.raises(SupabaseError) as e:
        make(handler).sign_in("a@b.co", "pw")
    assert e.value.status == 502
