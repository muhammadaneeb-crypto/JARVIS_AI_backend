import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import session as sessions
from app.services.supabase_client import SupabaseError, get_client, get_client_optional

AUTH = {"Authorization": "Bearer test-token"}


class FakeSupabase:
    def __init__(self, autoconfirm=True):
        self.users, self.rows, self.autoconfirm = {}, [], autoconfirm
        self.signed_out = False

    def sign_up(self, email, password):
        if email in self.users:
            raise SupabaseError(422, "User already registered")
        self.users[email] = password
        user = {"id": "u1", "email": email}
        if self.autoconfirm:
            return {"access_token": "at", "refresh_token": "rt", "expires_in": 3600, "user": user}
        return user

    def sign_in(self, email, password):
        if self.users.get(email) != password:
            raise SupabaseError(400, "Invalid login credentials")
        return {"access_token": "at", "refresh_token": "rt", "expires_in": 3600,
                "user": {"id": "u1", "email": email}}

    def refresh(self, rt):
        raise SupabaseError(400, "expired")

    def sign_out(self, token):
        self.signed_out = True

    def select(self, table, token, params):
        return list(reversed(self.rows))

    def insert(self, table, token, row):
        assert row["user_id"] == "u1"
        r = {**row, "id": f"r{len(self.rows)}", "created_at": "now"}
        self.rows.append(r)
        return r


@pytest.fixture(autouse=True)
def _reset():
    sessions.clear()
    app.dependency_overrides.clear()
    yield
    sessions.clear()
    app.dependency_overrides.clear()


def use(fake):
    app.dependency_overrides[get_client] = lambda: fake
    app.dependency_overrides[get_client_optional] = lambda: fake
    return TestClient(app)


def test_auth_requires_local_token():
    assert TestClient(app).post("/auth/login", json={"email": "a@b.co", "password": "x"}).status_code == 401


def test_unconfigured_supabase_gives_503_and_me_says_so():
    c = TestClient(app)
    r = c.post("/auth/login", json={"email": "a@b.co", "password": "x"}, headers=AUTH)
    assert r.status_code == 503
    assert c.get("/auth/me", headers=AUTH).json()["supabase_configured"] is False


def test_signup_login_me_logout_flow():
    fake = FakeSupabase()
    c = use(fake)
    r = c.post("/auth/signup", json={"email": "Ali@Test.com", "password": "secret123"}, headers=AUTH)
    assert r.status_code == 200 and r.json()["user"]["email"] == "ali@test.com"
    assert c.get("/auth/me", headers=AUTH).json()["logged_in"] is True
    assert c.post("/auth/logout", headers=AUTH).json()["logged_in"] is False
    assert fake.signed_out is True
    assert c.get("/auth/me", headers=AUTH).json()["logged_in"] is False
    r = c.post("/auth/login", json={"email": "ali@test.com", "password": "secret123"}, headers=AUTH)
    assert r.status_code == 200


def test_signup_with_email_confirmation():
    c = use(FakeSupabase(autoconfirm=False))
    r = c.post("/auth/signup", json={"email": "a@b.co", "password": "secret123"}, headers=AUTH)
    assert r.json()["status"] == "confirmation_required"
    assert c.get("/auth/me", headers=AUTH).json()["logged_in"] is False


def test_wrong_password_and_validation():
    c = use(FakeSupabase())
    c.post("/auth/signup", json={"email": "a@b.co", "password": "secret123"}, headers=AUTH)
    r = c.post("/auth/login", json={"email": "a@b.co", "password": "wrong"}, headers=AUTH)
    assert r.status_code == 400
    assert c.post("/auth/signup", json={"email": "bad", "password": "secret123"}, headers=AUTH).status_code == 422
    assert c.post("/auth/signup", json={"email": "a@b.co", "password": "short"}, headers=AUTH).status_code == 422


def test_duplicate_signup_rejected():
    c = use(FakeSupabase(autoconfirm=False))
    c.post("/auth/signup", json={"email": "a@b.co", "password": "secret123"}, headers=AUTH)
    assert c.post("/auth/signup", json={"email": "a@b.co", "password": "secret123"}, headers=AUTH).status_code == 422


def test_history_requires_login():
    c = use(FakeSupabase())
    assert c.get("/history", headers=AUTH).status_code == 401
    assert c.post("/history", json={"kind": "app", "summary": "x"}, headers=AUTH).status_code == 401


def test_history_add_and_list_after_login():
    c = use(FakeSupabase())
    c.post("/auth/signup", json={"email": "a@b.co", "password": "secret123"}, headers=AUTH)
    r = c.post("/history", json={"kind": "open_application", "summary": "Opened Notepad"}, headers=AUTH)
    assert r.status_code == 201
    items = c.get("/history", headers=AUTH).json()["items"]
    assert items[0]["summary"] == "Opened Notepad"


def test_history_validation():
    c = use(FakeSupabase())
    c.post("/auth/signup", json={"email": "a@b.co", "password": "secret123"}, headers=AUTH)
    assert c.post("/history", json={"kind": "x", "summary": "y", "status": "weird"}, headers=AUTH).status_code == 422
    assert c.get("/history?limit=9999", headers=AUTH).status_code == 422


def test_service_role_key_is_rejected():
    import base64, json
    from app.core.config import _is_service_role_key
    seg = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
    assert _is_service_role_key(f"{seg({'a':1})}.{seg({'role':'service_role'})}.sig") is True
    assert _is_service_role_key(f"{seg({'a':1})}.{seg({'role':'anon'})}.sig") is False
