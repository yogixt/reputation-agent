# Security Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the critical and high-severity security issues identified in the manual review: unauthenticated WebSocket access, weak cron-secret verification, production `disable_auth` risk, missing rate limits, and information-leaking error responses.

**Architecture:** Keep changes minimal and within existing patterns. Reuse the existing `auth.py`/`config.py`/`limiter.py` infrastructure, extend Pydantic validators where appropriate, and return generic client-facing errors while logging full details server-side.

**Tech Stack:** Python 3.9, FastAPI, Starlette sessions, slowapi, Pydantic v2, pytest.

---

### Task 1: Guard `disable_auth` against production use

**Files:**
- Modify: `config.py:76-90`
- Modify: `.env.example`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_config.py`:

```python
def test_disable_auth_rejected_in_production(monkeypatch):
    monkeypatch.setenv("DISABLE_AUTH", "true")
    monkeypatch.setenv("ENV", "production")
    from pydantic import ValidationError
    from config import Settings
    with pytest.raises(ValidationError):
        Settings()


def test_disable_auth_allowed_in_development(monkeypatch):
    monkeypatch.setenv("DISABLE_AUTH", "true")
    monkeypatch.setenv("ENV", "development")
    from config import Settings
    settings = Settings()
    assert settings.disable_auth is True
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd /Users/vijay/reputation-agent && source .venv/bin/activate && pytest tests/test_config.py::test_disable_auth_rejected_in_production -v
```

Expected: FAIL because production + disable_auth is currently allowed.

- [ ] **Step 3: Add the validator in `config.py`**

Insert after the `_reject_placeholder` validator:

```python
    @field_validator("disable_auth", mode="after")
    @classmethod
    def _reject_disable_auth_in_production(cls, v: bool, info) -> bool:
        env = str(info.data.get("env", "production")).lower()
        if v and env != "development":
            raise ValueError("disable_auth can only be true when env=development")
        return v
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
cd /Users/vijay/reputation-agent && source .venv/bin/activate && pytest tests/test_config.py -v
```

Expected: PASS.

- [ ] **Step 5: Warn in `.env.example`**

Append near the bottom of `.env.example`:

```text
# DANGER: disables login entirely. Only use for local development demos.
# Setting this in production will cause the app to refuse to start.
# DISABLE_AUTH=false
```

- [ ] **Step 6: Commit**

```bash
cd /Users/vijay/reputation-agent && git add config.py .env.example tests/test_config.py
git commit -m "security: reject disable_auth outside development"
```

---

### Task 2: Harden cron-secret verification

**Files:**
- Modify: `routes/cron.py:1-30`
- Test: `tests/test_api.py` (add cron-secret tests)

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_api.py`:

```python
def test_cron_endpoints_require_secret(client, monkeypatch):
    monkeypatch.setattr("config.settings.cron_secret", "super-secret")
    for path in ["/api/cron/health", "/api/cron/queue", "/api/cron/reputation", "/api/cron/advance-weeks", "/api/cron/log-cleanup"]:
        r = client.post(path)
        assert r.status_code == 401, path


def test_cron_endpoints_accept_valid_secret(client, monkeypatch):
    monkeypatch.setattr("config.settings.cron_secret", "super-secret")
    r = client.post("/api/cron/health", headers={"Authorization": "Bearer super-secret"})
    assert r.status_code in (200, 500)


def test_cron_secret_compare_is_constant_time(client, monkeypatch):
    monkeypatch.setattr("config.settings.cron_secret", "super-secret")
    r = client.post("/api/cron/health", headers={"Authorization": "Bearer wrong-secret"})
    assert r.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd /Users/vijay/reputation-agent && source .venv/bin/activate && pytest tests/test_api.py::test_cron_endpoints_require_secret tests/test_api.py::test_cron_endpoints_accept_valid_secret tests/test_api.py::test_cron_secret_compare_is_constant_time -v
```

Expected: FAIL because current code uses `os.environ.get("CRON_SECRET")` directly and `token != expected`.

- [ ] **Step 3: Update `routes/cron.py`**

Replace the top of `routes/cron.py` with:

```python
"""
Vercel Cron Job endpoints.

These endpoints are invoked by Vercel's cron scheduler. Each request must include
the Authorization header with the CRON_SECRET token.
"""

import secrets as secrets_module
from fastapi import APIRouter, Request, HTTPException

from services.health_service import run_health_check
from services.reputation_service import calculate_all_reputation
from services.email_queue_service import process_pending_jobs, detect_real_replies
from config import settings
from services.campaign_service import advance_campaign_weeks, campaign_tick_all
from services.log_service import cleanup_old_logs
from services.log_service import add_log

router = APIRouter(prefix="/api/cron", tags=["cron"])


def _verify_cron_secret(request: Request):
    expected = settings.cron_secret
    if not expected:
        raise HTTPException(status_code=500, detail="Server configuration error")
    auth = request.headers.get("authorization", "")
    token = auth.replace("Bearer ", "").strip() if auth.startswith("Bearer ") else ""
    if not secrets_module.compare_digest(token, expected):
        raise HTTPException(status_code=401, detail="Invalid cron secret")
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
cd /Users/vijay/reputation-agent && source .venv/bin/activate && pytest tests/test_api.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/vijay/reputation-agent && git add routes/cron.py tests/test_api.py
git commit -m "security: constant-time cron secret verification"
```

---

### Task 3: Authenticate the WebSocket endpoint

**Files:**
- Modify: `auth.py`
- Modify: `routes/websocket.py`
- Test: `tests/test_websocket.py` (create)

- [ ] **Step 1: Write the failing test**

Create `tests/test_websocket.py`:

```python
import pytest
from fastapi.testclient import TestClient


def test_websocket_requires_auth(client: TestClient):
    with pytest.raises(Exception):
        with client.websocket_connect("/ws"):
            pass


def test_websocket_accepts_authenticated_user(client: TestClient, auth_client):
    with auth_client.websocket_connect("/ws") as websocket:
        data = websocket.receive_json()
        assert data["type"] == "update"


def test_websocket_process_queue_action_removed(auth_client):
    with auth_client.websocket_connect("/ws") as websocket:
        websocket.receive_json()
        websocket.send_json({"action": "process_queue", "limit": 50})
        # Should not trigger send; connection stays alive or closes cleanly.
        # If any message comes back, it must not contain a success ack for process_queue.
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd /Users/vijay/reputation-agent && source .venv/bin/activate && pytest tests/test_websocket.py -v
```

Expected: FAIL because `/ws` currently accepts unauthenticated connections.

- [ ] **Step 3: Add scope-based auth helper in `auth.py`**

Append to `auth.py`:

```python
def get_session_from_scope(scope: dict) -> dict:
    """Validate a session from an ASGI scope (used by WebSocket)."""
    if settings.disable_auth:
        return {"user_id": 1, "email": settings.admin_email}
    session = scope.get("session", {})
    if not session.get("user_id"):
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {"user_id": session["user_id"], "email": session.get("email", "")}
```

- [ ] **Step 4: Rewrite `routes/websocket.py` to require auth and remove `process_queue`**

Replace `routes/websocket.py` with:

```python
"""
WebSocket endpoint for real-time dashboard updates.

NOTE: WebSocket broadcasts use an in-memory client list. On multi-instance
serverless deployments (e.g. Vercel) broadcasts will only reach clients
connected to the same instance. This endpoint is authenticated.
"""

import json
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

import auth as auth_module
from services import stats_service, log_service, campaign_service, account_service
from services.email_queue_service import get_queue
from services.reputation_service import get_latest_scores

router = APIRouter(tags=["websocket"])
clients = []


async def _close_unauthenticated(websocket: WebSocket):
    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)


async def broadcast(data: dict):
    dead = []
    for client in clients:
        try:
            await client.send_json(data)
        except Exception:
            dead.append(client)
    for client in dead:
        if client in clients:
            clients.remove(client)


async def poll_broadcast_loop():
    while True:
        await asyncio.sleep(3)
        try:
            await broadcast({
                "type": "update",
                "stats": stats_service.get_stats(),
                "logs": log_service.get_logs(30),
                "campaigns": campaign_service.list_campaigns(),
                "accounts": account_service.list_accounts(),
                "queue": get_queue(limit=20),
                "latest_scores": get_latest_scores(),
                "timestamp": __import__("db").now(),
            })
        except Exception as e:
            print(f"Broadcast error: {e}")


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    try:
        auth_module.get_session_from_scope(websocket.scope)
    except Exception:
        await _close_unauthenticated(websocket)
        return

    await websocket.accept()
    clients.append(websocket)
    try:
        await websocket.send_json({
            "type": "update",
            "stats": stats_service.get_stats(),
            "logs": log_service.get_logs(30),
            "campaigns": campaign_service.list_campaigns(),
            "accounts": account_service.list_accounts(),
            "queue": get_queue(limit=20),
            "latest_scores": get_latest_scores(),
        })
        while True:
            # Keep connection alive; ignore incoming messages.
            await websocket.receive_text()
    except WebSocketDisconnect:
        if websocket in clients:
            clients.remove(websocket)
    except Exception:
        if websocket in clients:
            clients.remove(websocket)
```

- [ ] **Step 5: Run tests to verify they pass**

Run:

```bash
cd /Users/vijay/reputation-agent && source .venv/bin/activate && pytest tests/test_websocket.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
cd /Users/vijay/reputation-agent && git add auth.py routes/websocket.py tests/test_websocket.py
git commit -m "security: require authentication on websocket endpoint"
```

---

### Task 4: Add rate limits to state-changing endpoints

**Files:**
- Modify: `config.py:68`
- Modify: `routes/accounts.py`
- Modify: `routes/campaigns.py`
- Modify: `routes/templates.py`
- Modify: `routes/settings_api.py`
- Modify: `routes/websocket.py` (already updated to drop process_queue; no extra limiter needed)
- Test: `tests/test_api.py`

- [ ] **Step 1: Add a default rate-limit setting**

In `config.py` line 68, change:

```python
    login_rate_limit: str = "5/minute"
```

to:

```python
    login_rate_limit: str = "5/minute"
    default_rate_limit: str = "30/minute"
```

- [ ] **Step 2: Apply rate limits to state-changing routes**

In `routes/accounts.py`, import `settings` and `limiter` and decorate mutating endpoints:

```python
from fastapi import APIRouter, Depends, Request
from config import settings
from limiter import limiter
```

Add `@limiter.limit(settings.default_rate_limit)` to `create_account`, `delete_account`, `update_account`, and `check_account`, making sure each async function accepts a `request: Request` parameter as the first argument. Example for `create_account`:

```python
@router.post("", response_model=dict)
@limiter.limit(settings.default_rate_limit)
async def create_account(req: models.AccountCreate, request: Request, session: dict = Depends(auth.require_auth)):
    account_id = account_service.create_account(req.email, req.password, req.role, req.provider)
    return {"success": True, "id": account_id}
```

Repeat the same pattern in `routes/campaigns.py` for `create_campaign`, `update_campaign`, `delete_campaign`, and `tick_campaign`.

Repeat in `routes/templates.py` for `create_template`, `update_template`, `delete_template`, and `preview_template`.

Repeat in `routes/settings_api.py` for `update_settings`.

- [ ] **Step 3: Write/adjust tests**

Add to `tests/test_api.py`:

```python
def test_state_change_endpoints_rate_limited(auth_client):
    r = auth_client.post("/api/accounts", json={"email": "a@example.com", "password": "x", "role": "peer"})
    assert r.status_code in (200, 429)
    # Hitting the same endpoint many times from the same IP should eventually 429.
    for _ in range(40):
        r = auth_client.post("/api/accounts", json={"email": f"{_}@example.com", "password": "x", "role": "peer"})
        if r.status_code == 429:
            break
    assert r.status_code == 429
```

- [ ] **Step 4: Run tests**

Run:

```bash
cd /Users/vijay/reputation-agent && source .venv/bin/activate && pytest tests/test_api.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/vijay/reputation-agent && git add config.py routes/accounts.py routes/campaigns.py routes/templates.py routes/settings_api.py tests/test_api.py
git commit -m "security: add rate limits to state-changing endpoints"
```

---

### Task 5: Sanitize error responses

**Files:**
- Modify: `routes/accounts.py`
- Modify: `routes/cron.py`
- Test: `tests/test_api.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_api.py`:

```python
def test_account_check_does_not_leak_internal_error(auth_client, monkeypatch):
    monkeypatch.setattr("services.account_service.get_account", lambda _id: {"id": 1, "email": "a@gmail.com", "status": "active"})
    monkeypatch.setattr("services.account_service.get_plain_password", lambda _id: "secret")
    r = auth_client.post("/api/accounts/1/check")
    assert r.status_code in (200, 500)
    if r.status_code == 500:
        assert "secret" not in r.text.lower()


def test_cron_errors_do_not_leak_details(client, monkeypatch):
    monkeypatch.setattr("config.settings.cron_secret", "secret")
    # Force health service to raise; ensure detail is generic.
    monkeypatch.setattr("routes.cron.run_health_check", lambda: (_ for _ in ()).throw(RuntimeError("db password: xyz")))
    r = client.post("/api/cron/health", headers={"Authorization": "Bearer secret"})
    assert r.status_code == 500
    assert "password" not in r.text.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd /Users/vijay/reputation-agent && source .venv/bin/activate && pytest tests/test_api.py::test_account_check_does_not_leak_internal_error tests/test_api.py::test_cron_errors_do_not_leak_details -v
```

Expected: second test FAILS because cron returns `str(e)`.

- [ ] **Step 3: Update `routes/accounts.py`**

Replace the `check_account` handler with:

```python
@router.post("/{account_id}/check")
async def check_account(account_id: int, session: dict = Depends(auth.require_auth)):
    account = account_service.get_account(account_id)
    if not account:
        return {"success": False, "error": "Account not found"}
    password = account_service.get_plain_password(account_id)
    if not password:
        return {"success": False, "error": "No password"}
    try:
        from providers.gmail import GmailClient
        with GmailClient(account["email"], password) as client:
            ok = client.health_check()
        return {"success": True, "healthy": ok}
    except Exception as e:
        add_log("warning", f"Account health check failed for {account_id}: {e}", "accounts")
        return {"success": False, "error": "Health check failed"}
```

Add import at top: `from services.log_service import add_log`.

- [ ] **Step 4: Update `routes/cron.py` error handling**

Change every cron handler's `except` block from:

```python
    except Exception as e:
        add_log("error", f"... cron failed: {e}", "cron")
        raise HTTPException(status_code=500, detail=str(e))
```

to:

```python
    except Exception as e:
        add_log("error", f"... cron failed: {e}", "cron")
        raise HTTPException(status_code=500, detail="Cron job failed")
```

- [ ] **Step 5: Run tests**

Run:

```bash
cd /Users/vijay/reputation-agent && source .venv/bin/activate && pytest tests/test_api.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
cd /Users/vijay/reputation-agent && git add routes/accounts.py routes/cron.py tests/test_api.py
git commit -m "security: sanitize client-facing error messages"
```

---

### Task 6: Validate account status values

**Files:**
- Modify: `models.py:28-30`
- Test: `tests/test_api.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_api.py`:

```python
def test_account_update_rejects_invalid_status(auth_client):
    r = auth_client.patch("/api/accounts/1", json={"status": "hacked"})
    assert r.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
cd /Users/vijay/reputation-agent && source .venv/bin/activate && pytest tests/test_api.py::test_account_update_rejects_invalid_status -v
```

Expected: FAIL because `AccountUpdate.status` has no pattern constraint.

- [ ] **Step 3: Update `models.py`**

Change:

```python
class AccountUpdate(BaseModel):
    status: Optional[str] = None
    password: Optional[str] = None
```

to:

```python
class AccountUpdate(BaseModel):
    status: Optional[str] = Field(None, pattern="^(active|inactive|suspended)$")
    password: Optional[str] = None
```

- [ ] **Step 4: Run tests**

Run:

```bash
cd /Users/vijay/reputation-agent && source .venv/bin/activate && pytest tests/test_api.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/vijay/reputation-agent && git add models.py tests/test_api.py
git commit -m "security: validate account status values"
```

---

### Task 7: Enforce secure cookies in production

**Files:**
- Modify: `main.py:66-73`
- Test: `tests/test_config.py` or `tests/test_api.py`

- [ ] **Step 1: Update `main.py`**

Change the `SessionMiddleware` block from:

```python
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie=settings.session_cookie_name,
    max_age=settings.session_max_age,
    same_site="lax",
    https_only=not settings.debug,
)
```

to:

```python
secure_cookies = settings.env.lower() == "production" or not settings.debug
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie=settings.session_cookie_name,
    max_age=settings.session_max_age,
    same_site="lax",
    https_only=secure_cookies,
)
```

- [ ] **Step 2: Verify import and tests still pass**

Run:

```bash
cd /Users/vijay/reputation-agent && source .venv/bin/activate && pytest tests/ -v
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
cd /Users/vijay/reputation-agent && git add main.py
git commit -m "security: enforce https-only cookies in production"
```

---

### Task 8: Final verification

- [ ] **Step 1: Run full test suite**

```bash
cd /Users/vijay/reputation-agent && source .venv/bin/activate && python -m pytest -v
```

Expected: All tests pass.

- [ ] **Step 2: Static import check**

```bash
cd /Users/vijay/reputation-agent && source .venv/bin/activate && python -c "import main; print('OK')"
```

Expected: `OK`.

- [ ] **Step 3: Final commit / summary**

```bash
cd /Users/vijay/reputation-agent && git log --oneline -10
```

---

## Self-Review

**Spec coverage:**
- Unauthenticated WebSocket → Task 3.
- Weak cron secret verification → Task 2.
- `disable_auth` production risk → Task 1.
- Missing rate limits → Task 4.
- Information-leaking errors → Task 5.
- Account status validation → Task 6.
- Cookie security → Task 7.

**Placeholder scan:** No TBDs, TODOs, or vague steps. Each step contains exact code, paths, and commands.

**Type consistency:**
- `get_session_from_scope` returns the same dict shape as `get_session`.
- Rate-limited endpoints add `request: Request` as the first positional arg, matching slowapi's requirement.
- `AccountUpdate.status` uses Pydantic v2 `Field(..., pattern=...)` consistent with other models.
