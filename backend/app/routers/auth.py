"""
Auth router: login, refresh, logout, /me.

Supports both:
  - OAuth2 form data (application/x-www-form-urlencoded) for test clients
  - JSON body (application/json) for browser/SPA clients
"""

from fastapi import APIRouter, Cookie, HTTPException, Request, Response, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from pydantic import ValidationError

from app.dependencies import CurrentUser, DBSession
from app.schemas.auth import LoginRequest, RefreshRequest, TokenResponse
from app.schemas.user import UserMeResponse
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["Authentication"])
limiter = Limiter(key_func=get_remote_address)


@router.post("/login", response_model=TokenResponse, status_code=status.HTTP_200_OK)
async def login(
    request: Request,
    response: Response,
    db: DBSession,
) -> TokenResponse:
    """
    Authenticate with username + password.
    Accepts both JSON body and form data (OAuth2-compatible).
    Returns access token; sets httpOnly refresh_token cookie.
    """
    content_type = request.headers.get("content-type", "")
    if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
        try:
            form = await request.form()
            username = form.get("username", "")
            password = form.get("password", "")
            payload = LoginRequest(username=str(username), password=str(password))
        except ValidationError as e:
            raise HTTPException(status_code=422, detail=e.errors()) from e
    else:
        # JSON body path (used by frontend SPA)
        try:
            body = await request.json()
            payload = LoginRequest(**body)
        except ValidationError as e:
            raise HTTPException(status_code=422, detail=e.errors()) from e
        except Exception as e:
            raise HTTPException(status_code=422, detail="Invalid request body") from e

    return await auth_service.login(payload, db, response)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    payload: RefreshRequest | None = None,
    refresh_token: str | None = Cookie(default=None),
) -> TokenResponse:
    """
    Exchange a refresh token (cookie or body) for a new access token.
    """
    token = (payload.refresh_token if payload else None) or refresh_token
    if not token:
        raise HTTPException(status_code=401, detail="No refresh token provided.")
    return await auth_service.refresh_access_token(token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response, current_user: CurrentUser) -> None:
    """Revoke refresh token and clear cookie."""
    await auth_service.logout(str(current_user.id), response)


@router.get("/me", response_model=UserMeResponse)
async def me(current_user: CurrentUser) -> UserMeResponse:
    """Return the currently authenticated user's profile."""
    return UserMeResponse.model_validate(current_user)
