"""Optional API authentication for production deployments."""
from hmac import compare_digest

from fastapi import Request
from fastapi.responses import JSONResponse

from app.config import settings


def _extract_token(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    return request.headers.get("x-api-key", "").strip()


def _token_matches(token: str, expected: str) -> bool:
    return bool(token and expected and compare_digest(token, expected))


def _allowed_tokens_for_path(path: str) -> list[str]:
    tokens: list[str] = []
    if settings.API_AUTH_TOKEN:
        tokens.append(settings.API_AUTH_TOKEN)
    if path.startswith("/api/v1/archive") or path.startswith("/api/v1/config"):
        if settings.GATEWAY_API_TOKEN:
            tokens.append(settings.GATEWAY_API_TOKEN)
    return tokens


async def require_optional_api_auth(request: Request, call_next):
    """
    Protects API routes when tokens are configured.

    Local/demo behavior stays open when API_AUTH_TOKEN and GATEWAY_API_TOKEN are
    blank. Production can set one or both environment variables:
      - API_AUTH_TOKEN: operator/dashboard/API access
      - GATEWAY_API_TOKEN: gateway upload/config access
    """
    path = request.url.path
    if not path.startswith("/api/v1"):
        return await call_next(request)

    allowed_tokens = _allowed_tokens_for_path(path)
    if not allowed_tokens:
        return await call_next(request)

    supplied = _extract_token(request)
    if any(_token_matches(supplied, token) for token in allowed_tokens):
        return await call_next(request)

    return JSONResponse(
        status_code=401,
        content={"detail": "Authentication required"},
        headers={"WWW-Authenticate": "Bearer"},
    )
