"""
Account service
"""

import security
import db
from services.log_service import add_log


def create_account(email: str, password: str, role: str, provider: str = "gmail") -> int:
    encrypted = security.encrypt_secret(password or "")
    try:
        cur = db.execute(
            "INSERT INTO accounts (email, encrypted_password, role, provider) VALUES (?, ?, ?, ?) RETURNING id",
            (email, encrypted, role, provider),
        )
        add_log("info", f"Account added: {email} ({role})", "account_service")
        return cur.lastrowid
    except Exception as e:
        add_log("error", f"Failed to add account {email}: {e}", "account_service")
        raise ValueError("Account already exists or invalid data")


def bulk_create_accounts(items: list[dict]) -> dict:
    """Bulk import accounts. Items must contain email, role, provider, and optional password."""
    created = []
    failed = []
    skipped = []

    for item in items:
        email = (item.get("email") or "").strip().lower()
        role = (item.get("role") or "").strip().lower()
        provider = (item.get("provider") or "gmail").strip().lower()
        password = item.get("password") or ""

        if not email:
            failed.append({"item": item, "reason": "missing email"})
            continue
        if role not in ("sender", "peer"):
            failed.append({"item": item, "reason": "role must be sender or peer"})
            continue
        if role == "sender" and not password:
            failed.append({"item": item, "reason": "sender accounts require an app password"})
            continue

        existing = db.fetchone("SELECT id FROM accounts WHERE email = ?", (email,))
        if existing:
            skipped.append({"email": email, "reason": "already exists"})
            continue

        try:
            account_id = create_account(email, password, role, provider)
            created.append({"id": account_id, "email": email, "role": role})
        except Exception as e:
            failed.append({"item": item, "reason": str(e)})

    add_log("info", f"Bulk import: {len(created)} created, {len(failed)} failed, {len(skipped)} skipped", "account_service")
    return {"created": created, "failed": failed, "skipped": skipped}


def list_accounts() -> list:
    rows = db.fetchall("SELECT * FROM accounts ORDER BY created_at DESC")
    return [dict(r) for r in rows]


def get_account(account_id: int) -> dict:
    row = db.fetchone("SELECT * FROM accounts WHERE id = ?", (account_id,))
    return dict(row) if row else None


def get_sender() -> dict:
    row = db.fetchone(
        "SELECT * FROM accounts WHERE role = 'sender' AND status = 'active' ORDER BY health_score DESC, id LIMIT 1"
    )
    return dict(row) if row else None


def get_peers(campaign_id: int = None) -> list:
    if campaign_id:
        rows = db.fetchall(
            """SELECT a.* FROM accounts a
               JOIN campaign_peers cp ON a.id = cp.account_id
               WHERE cp.campaign_id = ? AND a.role = 'peer' AND a.status = 'active'
               ORDER BY a.health_score DESC""",
            (campaign_id,),
        )
    else:
        rows = db.fetchall(
            "SELECT * FROM accounts WHERE role = 'peer' AND status = 'active' ORDER BY health_score DESC"
        )
    return [dict(r) for r in rows]


def delete_account(account_id: int):
    db.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
    add_log("info", f"Account deleted: {account_id}", "account_service")


def update_account(account_id: int, status: str = None, password: str = None):
    if status:
        db.execute("UPDATE accounts SET status = ?, updated_at = ? WHERE id = ?",
                   (status, db.now(), account_id))
    if password is not None:
        encrypted = security.encrypt_secret(password)
        db.execute("UPDATE accounts SET encrypted_password = ?, updated_at = ? WHERE id = ?",
                   (encrypted, db.now(), account_id))


def get_plain_password(account_id: int) -> str:
    row = db.fetchone("SELECT encrypted_password FROM accounts WHERE id = ?", (account_id,))
    if not row:
        return None
    return security.decrypt_secret(row["encrypted_password"])


def update_health(account_id: int, health_score: int, error: str = None):
    db.execute(
        """UPDATE accounts SET health_score = ?, last_check = ?, last_error = ?,
           fail_count = CASE WHEN ? < 50 THEN fail_count + 1 ELSE 0 END,
           updated_at = ? WHERE id = ?""",
        (health_score, db.now(), error, health_score, db.now(), account_id),
    )
