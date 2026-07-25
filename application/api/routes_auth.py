import logging
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

try:
    from application import cloudfront_cookies
except ImportError:
    import cloudfront_cookies

logger = logging.getLogger("routes_auth")

router = APIRouter(prefix="/api/session", tags=["session"])

SESSION_COOKIE = "agent_user_id"
SESSION_MAX_AGE = 60 * 60 * 24 * 30


class SessionRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)


class SessionResponse(BaseModel):
    user_id: str


def _cookie_secure(request: Request) -> bool:
    # CloudFront→ALB is http-only, so ALB's X-Forwarded-Proto is often "http"
    # even when the viewer used HTTPS. Prefer CloudFront's viewer proto, then
    # treat CloudFront / sharing_url hosts as HTTPS viewers.
    proto = (
        request.headers.get("cloudfront-forwarded-proto")
        or request.headers.get("x-forwarded-proto")
        or request.url.scheme
        or ""
    ).lower()
    if proto == "https":
        return True
    host = (request.headers.get("host") or request.url.hostname or "").split(":")[0].lower()
    if host.endswith(".cloudfront.net"):
        return True
    try:
        try:
            from application import utils
        except ImportError:
            import utils

        sharing = (utils.load_config().get("sharing_url") or "").strip()
        parsed = urlparse(sharing)
        if parsed.scheme == "https" and (parsed.hostname or "").lower() == host:
            return True
    except Exception:
        pass
    return False


def _set_user_cookie(response: Response, request: Request, user_id: str) -> None:
    secure = _cookie_secure(request)
    response.set_cookie(
        key=SESSION_COOKIE,
        value=user_id,
        httponly=True,
        samesite="lax",
        secure=secure,
        max_age=SESSION_MAX_AGE,
    )
    if not cloudfront_cookies.set_signed_cookies(
        response, secure=secure, max_age=SESSION_MAX_AGE
    ):
        logger.warning(
            "CloudFront signed cookies not attached on login (signing material missing?)"
        )


@router.post("", response_model=SessionResponse)
def set_session(body: SessionRequest, request: Request, response: Response) -> SessionResponse:
    user_id = body.user_id.strip()
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")
    _set_user_cookie(response, request, user_id)
    return SessionResponse(user_id=user_id)


@router.get("", response_model=SessionResponse | None)
def get_session(request: Request, response: Response) -> SessionResponse | None:
    user_id = (request.cookies.get(SESSION_COOKIE) or "").strip()
    if not user_id:
        return None
    if not cloudfront_cookies.set_signed_cookies(
        response,
        secure=_cookie_secure(request),
        max_age=SESSION_MAX_AGE,
    ):
        logger.warning(
            "CloudFront signed cookies not attached on session refresh "
            "(signing material missing?)"
        )
    return SessionResponse(user_id=user_id)


@router.delete("", status_code=204)
def clear_session(request: Request, response: Response) -> None:
    secure = _cookie_secure(request)
    response.delete_cookie(key=SESSION_COOKIE, samesite="lax", secure=secure)
    cloudfront_cookies.clear_signed_cookies(response, secure=secure)


def require_user_id(request: Request) -> str:
    user_id = request.cookies.get(SESSION_COOKIE)
    if not user_id:
        raise HTTPException(status_code=401, detail="User session required")
    return user_id
