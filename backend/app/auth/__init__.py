"""Single-user admin authentication.

The dashboard supports exactly one admin account at this time. The schema
already includes a `users` table with a `role` column to allow future
expansion to multiple users / roles without a migration churn.

Auth flow:
1. First visit ever to the dashboard: no admin user exists yet. The frontend
   detects this via GET /api/auth/me returning {setup_required: true} and
   shows a "set initial password" form. The user posts to /api/auth/setup,
   which creates the admin row and starts a session.
2. Subsequent visits: GET /api/auth/me returns {authenticated: false} when
   no session cookie is present. The frontend shows a login form. POST to
   /api/auth/login starts a session.
3. The session is a signed httpOnly cookie via Starlette's SessionMiddleware.
   The signing key lives at backend/data/.session_signing_key (auto-generated
   on first run, same pattern as the vault master key).
4. Sessions expire after auth.session_ttl_minutes (default 8 hours).
5. Login attempts are rate limited to 5 per IP per 15 minutes.
"""

from app.auth.middleware import require_admin
from app.auth.passwords import hash_password, verify_password
from app.auth.ratelimit import LoginRateLimiter
from app.auth.session import load_or_create_signing_key
from app.auth.users import (
    AdminUser,
    create_admin_user,
    get_admin_user,
    update_last_login,
)

__all__ = [
    "AdminUser",
    "LoginRateLimiter",
    "create_admin_user",
    "get_admin_user",
    "hash_password",
    "load_or_create_signing_key",
    "require_admin",
    "update_last_login",
    "verify_password",
]
