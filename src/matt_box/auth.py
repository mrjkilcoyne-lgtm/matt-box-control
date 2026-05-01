"""Bearer token validation. Constant-time comparison."""

from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, status

PLACEHOLDER = "__SET_VIA_INSTALL_SCRIPT__"


def validate_bearer(expected: str, supplied: str | None) -> bool:
    """Constant-time compare of bearer tokens. Refuses placeholder values."""
    if not expected or expected == PLACEHOLDER:
        return False
    if not supplied:
        return False
    if not supplied.startswith("Bearer "):
        return False
    token = supplied[len("Bearer ") :]
    return hmac.compare_digest(expected.encode(), token.encode())


def make_bearer_dep(get_expected):
    """Returns a FastAPI dependency that enforces bearer auth.

    `get_expected` is a callable returning the current expected bearer
    (so config reload doesn't require re-binding).
    """

    async def _dep(authorization: str | None = Header(default=None)) -> None:
        if not validate_bearer(get_expected(), authorization):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid or missing bearer",
                headers={"WWW-Authenticate": "Bearer"},
            )

    return _dep
