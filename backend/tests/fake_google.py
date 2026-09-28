"""A fake Google (OAuth token endpoint, userinfo, Gmail API) for tests. No network access."""

import base64
import json
from email import message_from_bytes, policy
from urllib.parse import parse_qs

import httpx

from app.services import google_oauth


class FakeGoogle:
    def __init__(self):
        self.email = "sales.abctech@gmail.com"
        self.email_verified = True
        self.scope = "openid https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/gmail.send"
        self.issue_refresh_token = True
        self.token_error: str | None = None  # e.g. "invalid_grant" for code exchange
        self.refresh_error: str | None = None  # e.g. "invalid_grant" for a revoked refresh token
        self.send_statuses: list[int] = []  # queued Gmail API statuses; default 200
        self.counter = 0
        self.token_requests: list[dict] = []
        self.sent: list[dict] = []  # {"auth": header, "message": parsed MIME, "raw": bytes}
        self.requests: list[httpx.Request] = []

    # ----- helpers ---------------------------------------------------------------------------
    def _new_access_token(self) -> str:
        self.counter += 1
        return f"fake-access-token-{self.counter}"

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = str(request.url)
        if url == google_oauth.TOKEN_URL:
            return self._token(request)
        if url == google_oauth.USERINFO_URL:
            return httpx.Response(200, json={"sub": "123", "email": self.email, "email_verified": self.email_verified})
        if url == google_oauth.GMAIL_SEND_URL:
            return self._send(request)
        raise AssertionError(f"Unexpected Google URL {url}")

    def _token(self, request: httpx.Request) -> httpx.Response:
        form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
        self.token_requests.append(form)
        if form["grant_type"] == "authorization_code":
            if self.token_error:
                return httpx.Response(400, json={"error": self.token_error, "error_description": "Bad Request"})
            body = {"access_token": self._new_access_token(), "expires_in": 3599, "scope": self.scope, "token_type": "Bearer"}
            if self.issue_refresh_token:
                body["refresh_token"] = "fake-refresh-token"
            return httpx.Response(200, json=body)
        if form["grant_type"] == "refresh_token":
            if self.refresh_error:
                return httpx.Response(400, json={"error": self.refresh_error, "error_description": "Token has been expired or revoked."})
            return httpx.Response(200, json={"access_token": self._new_access_token(), "expires_in": 3599, "scope": self.scope})
        raise AssertionError("unknown grant_type")

    def _send(self, request: httpx.Request) -> httpx.Response:
        status = self.send_statuses.pop(0) if self.send_statuses else 200
        if status != 200:
            return httpx.Response(status, json={"error": {"code": status, "message": "fake failure"}})
        raw = base64.urlsafe_b64decode(json.loads(request.content)["raw"])
        self.sent.append(
            {
                "auth": request.headers.get("Authorization"),
                "raw": raw,
                "message": message_from_bytes(raw, policy=policy.default),
            }
        )
        return httpx.Response(200, json={"id": f"gmail-msg-{len(self.sent)}", "threadId": "t1", "labelIds": ["SENT"]})


def install_fake_google(monkeypatch) -> FakeGoogle:
    from app.core.config import settings
    from pydantic import SecretStr

    fake = FakeGoogle()
    monkeypatch.setattr(google_oauth, "TRANSPORT", httpx.MockTransport(fake.handler))
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", SecretStr("test-client-secret-value"))
    monkeypatch.setattr(settings, "GOOGLE_REDIRECT_URI", "http://localhost:8000/api/v1/oauth/gmail/callback")
    monkeypatch.setattr(settings, "FRONTEND_URL", "http://localhost:3000")
    return fake
