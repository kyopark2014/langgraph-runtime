from fastapi import APIRouter, Request

from application.api.routes_auth import get_optional_user_id
from application.services.config_service import (
    get_application_config,
    get_public_config,
)

router = APIRouter(prefix="/api/config", tags=["config"])


@router.get("")
def get_config(request: Request):
    """Return public auth bootstrap fields; full catalogs only when logged in.

    Unauthenticated clients get only what the login screen needs (project name).
    Model / MCP / skill catalogs require a session.
    """
    session_user = get_optional_user_id(request)
    if not session_user:
        return get_public_config()
    return get_application_config(session_user)
