from fastapi import Header, HTTPException, status

from app.core.config import get_settings


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Optional lightweight protection for trusted internal deployments.

    A browser-bundled key is not a substitute for real authentication. For public
    deployment, place the app behind SSO, an identity-aware proxy, or another
    server-side authentication layer.
    """
    expected = get_settings().askme_api_key
    if expected and x_api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "UNAUTHORIZED", "message": "Invalid or missing API key."},
        )
