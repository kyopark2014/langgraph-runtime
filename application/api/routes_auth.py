from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field

try:
    from application import cloudfront_cookies
except ImportError:
    import cloudfront_cookies

router = APIRouter(prefix="/api/session", tags=["session"])

SESSION_COOKIE = "agent_user_id"
SESSION_MAX_AGE = 60 * 60 * 24 * 30


class SessionRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)


class SessionResponse(BaseModel):
    user_id: str


def _cookie_secure(request: Request) -> bool:
    proto = (request.headers.get("x-forwarded-proto") or request.url.scheme or "").lower()
    return proto == "https"


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
    cloudfront_cookies.set_signed_cookies(
        response, secure=secure, max_age=SESSION_MAX_AGE
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
    cloudfront_cookies.set_signed_cookies(
        response,
        secure=_cookie_secure(request),
        max_age=SESSION_MAX_AGE,
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
