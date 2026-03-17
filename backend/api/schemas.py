"""
Shared Pydantic response schemas for all API routes.

Design rules:
- GET routes return the resource directly (no envelope wrapper).
- POST command routes always return CommandResult.
- Errors always surface as HTTPException — never as a 200 with {"error": "..."}.
"""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel


class CommandResult(BaseModel):
    """Standard response shape for all POST command endpoints."""

    success: bool
    detail: str | None = None   # human-readable message or error reason
    data: dict[str, Any] | None = None   # optional payload (e.g. eta_ticks, path_length)


def require_success(result: dict[str, Any]) -> dict[str, Any]:
    """
    Assert a simulation command dict succeeded.

    If the simulation returned {"success": False, "error": "..."}, raises
    HTTP 422 so the caller gets a consistent error response instead of a
    silent 200 with an error body.
    """
    if not result.get("success"):
        raise HTTPException(
            status_code=422,
            detail=result.get("error", "Command failed."),
        )
    return result
