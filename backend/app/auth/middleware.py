"""FastAPI dependency that gates routes behind admin authentication."""

from __future__ import annotations

from fastapi import HTTPException, Request, status


def require_admin(request: Request) -> str:
    """Dependency that allows the request only if the session has an admin user.

    Returns the username on success. Raises 401 otherwise. The session is
    populated by /api/auth/login and /api/auth/setup, both of which set
    request.session['user'] = {'username': ..., 'role': 'admin'}.
    """
    session = getattr(request, "session", None)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authentication required",
            headers={"WWW-Authenticate": "Session"},
        )
    user = session.get("user")
    if not user or user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="authentication required",
            headers={"WWW-Authenticate": "Session"},
        )
    return user.get("username", "admin")
