"""
GridWise Version 4 - User Accounts
=====================================

Handles registration, login, and account data. Uses the same SQLite
approach as services/history.py - fine for getting started, same
Postgres-migration note applies once this holds real user data at scale
(and matters more here, since this is now storing password hashes and
payment references, not just cached market snapshots).

Passwords are never stored in plain text - only a salted hash
(werkzeug's generate_password_hash / check_password_hash, industry
standard for Flask apps). GridWise itself never sees or stores raw card
numbers - that's handled entirely by Stripe (see services/billing.py);
this file only stores the Stripe customer/subscription IDs needed to
look up billing status.

account_type: "business", "student", or "domestic" - determines which
dashboard layout a user sees (see the "/" route in app.py).

tier: "free" or "premium" - determines which sections of that dashboard
are unlocked vs shown with an upgrade prompt.

SECURITY NOTE before this handles real payments/users in production:
- Add email verification (currently accounts are usable immediately on
  signup with no email confirmation step).
- Add rate limiting on /login and /register to slow down brute-force /
  spam signups.
- Add CSRF protection (Flask-WTF) on the login/register/upgrade forms.
- Get a proper security review before going live with real payments -
  this is a working foundation, not a production-hardened billing system.
"""

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

DB_PATH = os.getenv(
    "GRIDWISE_DB_PATH",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "gridwise_history.db"),
)

VALID_ACCOUNT_TYPES = ("business", "student", "domestic")
VALID_TIERS = ("free", "premium")

# Admin/master accounts - comma-separated list of emails in .env, e.g.
#   ADMIN_EMAILS=you@example.com,cofounder@example.com
# This is intentionally NOT a database column, so it works immediately on
# accounts that already exist without any migration - just add an email
# to .env and that account becomes admin on its next request, no DB
# changes needed. Downside: whoever can edit .env controls who's admin,
# same as any other secret in this file - keep server access locked down.
ADMIN_EMAILS = {
    email.strip().lower()
    for email in os.getenv("ADMIN_EMAILS", "").split(",")
    if email.strip()
}


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                name TEXT NOT NULL,
                account_type TEXT NOT NULL,
                tier TEXT NOT NULL DEFAULT 'free',
                stripe_customer_id TEXT,
                stripe_subscription_id TEXT,
                created_at TEXT NOT NULL
            )
        """)


class User(UserMixin):
    """Thin wrapper Flask-Login expects - id, plus the account fields
    templates/routes need to read directly (current_user.tier, etc.)"""

    def __init__(self, row):
        self.id = str(row["id"])
        self.email = row["email"]
        self.name = row["name"]
        self.account_type = row["account_type"]
        self.tier = row["tier"]
        self.stripe_customer_id = row["stripe_customer_id"]
        self.stripe_subscription_id = row["stripe_subscription_id"]
        self.created_at = row["created_at"]

    @property
    def is_premium(self):
        return self.tier == "premium"

    @property
    def is_admin(self):
        return self.email.lower() in ADMIN_EMAILS


def create_user(email, password, name, account_type):
    if account_type not in VALID_ACCOUNT_TYPES:
        raise ValueError(f"account_type must be one of {VALID_ACCOUNT_TYPES}")

    password_hash = generate_password_hash(password)

    with get_db() as conn:
        try:
            cursor = conn.execute(
                """
                INSERT INTO users (email, password_hash, name, account_type, tier, created_at)
                VALUES (?, ?, ?, ?, 'free', ?)
                """,
                (email.lower().strip(), password_hash, name, account_type,
                 datetime.utcnow().isoformat(timespec="minutes")),
            )
            return cursor.lastrowid
        except sqlite3.IntegrityError:
            raise ValueError("An account with this email already exists")


def verify_login(email, password):
    """Returns a User on success, or None if email/password don't match."""

    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email.lower().strip(),)
        ).fetchone()

    if row is None:
        return None

    if not check_password_hash(row["password_hash"], password):
        return None

    return User(row)


def get_user_by_id(user_id):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()

    return User(row) if row else None


def get_user_by_email(email):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE email = ?", (email.lower().strip(),)
        ).fetchone()

    return User(row) if row else None


def set_tier(user_id, tier):
    if tier not in VALID_TIERS:
        raise ValueError(f"tier must be one of {VALID_TIERS}")

    with get_db() as conn:
        conn.execute("UPDATE users SET tier = ? WHERE id = ?", (tier, user_id))


def set_stripe_ids(user_id, customer_id=None, subscription_id=None):
    with get_db() as conn:
        if customer_id is not None:
            conn.execute(
                "UPDATE users SET stripe_customer_id = ? WHERE id = ?",
                (customer_id, user_id),
            )
        if subscription_id is not None:
            conn.execute(
                "UPDATE users SET stripe_subscription_id = ? WHERE id = ?",
                (subscription_id, user_id),
            )


def get_user_by_stripe_customer_id(customer_id):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE stripe_customer_id = ?", (customer_id,)
        ).fetchone()

    return User(row) if row else None


# ---------------------------------------------------------------
# Admin - member list and stats
# ---------------------------------------------------------------

def get_all_users():
    """All users, newest first - for the admin members table."""

    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM users ORDER BY created_at DESC"
        ).fetchall()

    return [User(row) for row in rows]


def get_member_stats(premium_price_gbp=0):
    """
    Summary numbers for the admin dashboard: total members, breakdown by
    account type and tier, and an estimated MRR (Monthly Recurring
    Revenue) based on the premium count. premium_price_gbp should be
    passed in from the REAL live Stripe price (see billing.py's
    get_premium_price_display()) - defaults to 0 here rather than a
    guessed number, so a misconfigured Stripe setup shows £0 (an obvious
    "something's not set up" signal) rather than a silently wrong,
    made-up MRR figure.
    """

    users = get_all_users()

    total = len(users)
    premium_count = sum(1 for u in users if u.tier == "premium")
    free_count = total - premium_count

    by_type = {}
    for account_type in VALID_ACCOUNT_TYPES:
        by_type[account_type] = sum(1 for u in users if u.account_type == account_type)

    return {
        "total_members": total,
        "free_count": free_count,
        "premium_count": premium_count,
        "by_type": by_type,
        "estimated_mrr_gbp": round(premium_count * premium_price_gbp, 2),
    }
