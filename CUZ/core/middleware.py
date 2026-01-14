# CUZ/ADMIN/core/
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from datetime import datetime, timezone
import uuid
from jose import jwt, JWTError

from CUZ.core.firebase import db
from CUZ.core.tokens import SECRET_KEY, ALGORITHM, is_refresh_token_valid, revoke_refresh_token

async def log_event(actor: str, action: str, role: str = None, ip: str = None, user_agent: str = None, metadata: dict = None):
    log_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    db.collection("audit_logs").document(log_id).set({
        "actor": actor,
        "action": action,
        "role": role,
        "ip": ip,
        "user_agent": user_agent,
        "timestamp": now.isoformat(),
        "metadata": metadata or {}
    })


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        ip = request.client.host
        ua = request.headers.get("user-agent")
        path = request.url.path
        method = request.method

        actor = "anonymous"
        role = None

        # If your auth dependency sets user info in request.scope
        if "user" in request.scope:
            actor = request.scope["user"].get("id", "unknown")
            role = request.scope["user"].get("role")

        # --- Refresh Token Enforcement ---
        if path.endswith("/refresh"):  # only check on refresh endpoint
            token = request.headers.get("authorization")
            if token and token.startswith("Bearer "):
                token = token.split(" ")[1]
                try:
                    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
                    jti = payload.get("jti")
                    uid = payload.get("sub")

                    # Check if token is revoked/expired
                    if not is_refresh_token_valid(jti):
                        await log_event(
                            actor=uid,
                            action="refresh_token_invalid",
                            role=role,
                            ip=ip,
                            user_agent=ua,
                            metadata={"reason": "revoked_or_expired"}
                        )
                        return Response("Invalid refresh token", status_code=401)

                    # Enforce IP + UA binding
                    doc = db.collection("REFRESH_TOKENS").document(jti).get()
                    if doc.exists:
                        data = doc.to_dict()
                        if data["ip"] != ip or data["user_agent"] != ua:
                            # revoke immediately
                            revoke_refresh_token(jti)
                            await log_event(
                                actor=uid,
                                action="refresh_token_ip_ua_mismatch",
                                role=role,
                                ip=ip,
                                user_agent=ua,
                                metadata={"expected_ip": data["ip"], "expected_ua": data["user_agent"]}
                            )
                            return Response("Suspicious refresh attempt", status_code=401)

                except JWTError:
                    await log_event(
                        actor="unknown",
                        action="refresh_token_decode_failed",
                        ip=ip,
                        user_agent=ua
                    )
                    return Response("Invalid token format", status_code=401)

        # --- Continue normal request flow ---
        response: Response = await call_next(request)

        # Log after response so we capture status
        await log_event(
            actor=actor,
            action=f"{method} {path}",
            role=role,
            ip=ip,
            user_agent=ua,
            metadata={"status_code": response.status_code}
        )

        return response
