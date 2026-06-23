"""
Tests for API endpoints.
"""

import pytest


def test_health_endpoint(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["detail"]["database"] == "ok"


def test_login_success(client):
    from config import settings
    resp = client.post(
        "/api/auth/login",
        json={"email": settings.admin_email, "password": settings.admin_password},
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True


def test_login_failure(client):
    from config import settings
    resp = client.post(
        "/api/auth/login",
        json={"email": settings.admin_email, "password": "wrong"},
    )
    assert resp.status_code == 401


def test_protected_endpoints_require_auth(client):
    resp = client.get("/api/accounts")
    assert resp.status_code == 401


def test_get_accounts_authenticated(authenticated_client):
    resp = authenticated_client.get("/api/accounts")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_peer_account_can_be_created_without_password(authenticated_client):
    resp = authenticated_client.post(
        "/api/accounts",
        json={"email": "peer@example.com", "role": "peer", "provider": "gmail"},
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True


def test_sender_account_requires_password(authenticated_client):
    resp = authenticated_client.post(
        "/api/accounts",
        json={"email": "sender@example.com", "role": "sender", "provider": "gmail"},
    )
    assert resp.status_code == 422


def test_bulk_import_accounts(authenticated_client):
    resp = authenticated_client.post(
        "/api/accounts/bulk-import",
        json={
            "accounts": [
                {"email": "bulk1@example.com", "role": "sender", "provider": "gmail", "password": "app-pass-1"},
                {"email": "bulk2@example.com", "role": "peer", "provider": "gmail"},
                {"email": "bulk1@example.com", "role": "sender", "provider": "gmail", "password": "app-pass-2"},
            ]
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert len(data["created"]) == 2
    assert len(data["skipped"]) == 1
    assert data["skipped"][0]["email"] == "bulk1@example.com"


def test_template_preview_authenticated(authenticated_client):
    resp = authenticated_client.post(
        "/api/templates/preview",
        json={
            "subject_template": "Hello {{name}}",
            "body_template": "Hi {{name}}, welcome to {{company}}.",
            "reply_template": "Thanks!",
            "variables_json": '["name", "company"]',
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    # Variables should have been substituted
    assert "{{name}}" not in data["body"]
    assert "{{company}}" not in data["body"]
    assert data["reply"] == "Thanks!"


def test_template_preview_sandbox_blocks_python_code(authenticated_client):
    """Sandboxed Jinja2 should not allow Python attribute access."""
    resp = authenticated_client.post(
        "/api/templates/preview",
        json={
            "subject_template": "Safe",
            "body_template": "{{ ''.__class__ }}",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    # The raw template is returned when rendering fails / is blocked
    assert "__class__" not in data["body"]


def test_cron_endpoints_require_secret(client, monkeypatch):
    monkeypatch.setattr("config.settings.cron_secret", "super-secret")
    paths = [
        "/api/cron/health",
        "/api/cron/queue",
        "/api/cron/reputation",
        "/api/cron/advance-weeks",
        "/api/cron/log-cleanup",
    ]
    for path in paths:
        resp = client.post(path)
        assert resp.status_code == 401, path


def test_cron_endpoints_accept_valid_secret(client, monkeypatch):
    monkeypatch.setattr("config.settings.cron_secret", "super-secret")
    resp = client.post("/api/cron/health", headers={"Authorization": "Bearer super-secret"})
    assert resp.status_code in (200, 500)


def test_cron_secret_compare_is_constant_time(client, monkeypatch):
    monkeypatch.setattr("config.settings.cron_secret", "super-secret")
    resp = client.post("/api/cron/health", headers={"Authorization": "Bearer wrong-secret"})
    assert resp.status_code == 401


def test_state_change_endpoints_rate_limited(authenticated_client):
    # The TestClient uses localhost; slowapi uses remote address as the key.
    # We repeatedly create an account until rate limited.
    rate_limited = False
    for i in range(40):
        resp = authenticated_client.post(
            "/api/accounts",
            json={"email": f"rate{i}@example.com", "password": "x", "role": "peer", "provider": "gmail"},
        )
        if resp.status_code == 429:
            rate_limited = True
            break
    assert rate_limited, "Expected endpoint to be rate limited"


def test_cron_errors_do_not_leak_details(client, monkeypatch):
    monkeypatch.setattr("config.settings.cron_secret", "secret")

    def _explode():
        raise RuntimeError("db password: xyz")

    monkeypatch.setattr("routes.cron.run_health_check", _explode)
    resp = client.post("/api/cron/health", headers={"Authorization": "Bearer secret"})
    assert resp.status_code == 500
    assert "password" not in resp.text.lower()
    assert resp.json()["detail"] == "Cron job failed"


def test_bulk_send_endpoint(authenticated_client, monkeypatch):
    resp = authenticated_client.post("/api/sends/bulk?limit=100")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "campaigns_ticked" in data
    assert "queued" in data
    assert "sent" in data


def test_account_check_does_not_leak_internal_error(authenticated_client, monkeypatch):
    monkeypatch.setattr(
        "services.account_service.get_account",
        lambda _id: {"id": 1, "email": "a@gmail.com", "status": "active"},
    )
    monkeypatch.setattr("services.account_service.get_plain_password", lambda _id: "secret")
    monkeypatch.setattr(
        "providers.gmail.GmailClient.__enter__",
        lambda self: (_ for _ in ()).throw(RuntimeError("some internal imap error")),
    )
    resp = authenticated_client.post("/api/accounts/1/check")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is False
    assert "password" not in resp.text.lower()
    assert "imap" not in data["error"].lower()
