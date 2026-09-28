"""Test doubles for SMTP and the LLM. No test ever opens a real network connection."""

import smtplib


class FakeSMTPController:
    """Records every connection and message; can be told to fail at a given step."""

    def __init__(self):
        self.connections: list["FakeSMTP"] = []
        self.sent: list = []
        self.fail_on: str | None = None  # "connect" | "starttls" | "login" | "send"
        self.error: BaseException | None = None
        self.fail_times: int | None = None  # fail only the first N attempts (for retry tests)

    def maybe_fail(self, step: str):
        if self.fail_on == step and self.error is not None:
            if self.fail_times is None or self.fail_times > 0:
                if self.fail_times is not None:
                    self.fail_times -= 1
                raise self.error

    def factory(self, ssl: bool):
        controller = self

        class FakeSMTP:
            def __init__(self, host, port, timeout=None, context=None):
                self.host, self.port, self.timeout = host, port, timeout
                self.ssl = ssl
                self.started_tls = False
                self.logged_in_as = None
                self.password_used = None
                controller.connections.append(self)
                controller.maybe_fail("connect")

            def ehlo(self):
                return (250, b"ok")

            def starttls(self, context=None):
                controller.maybe_fail("starttls")
                self.started_tls = True

            def login(self, username, password):
                controller.maybe_fail("login")
                self.logged_in_as = username
                self.password_used = password

            def send_message(self, message):
                controller.maybe_fail("send")
                controller.sent.append(message)

            def quit(self):
                pass

        return FakeSMTP

    @property
    def last(self):
        return self.connections[-1]


class RecordingLLM:
    """LLM double that records each request and returns a fixed email (or raises)."""

    name = "recording"

    def __init__(self, subject="Generated subject", body="Hi Priya,\n\nGenerated body.", error=None):
        self.subject, self.body, self.error = subject, body, error
        self.requests = []

    def generate_email(self, request):
        from app.services.llm import GeneratedEmail

        self.requests.append(request)
        if self.error is not None:
            raise self.error
        return GeneratedEmail(subject=self.subject, body=self.body)

    @property
    def last(self):
        return self.requests[-1]


def install_fake_smtp(monkeypatch) -> FakeSMTPController:
    controller = FakeSMTPController()
    monkeypatch.setattr(smtplib, "SMTP", controller.factory(ssl=False))
    monkeypatch.setattr(smtplib, "SMTP_SSL", controller.factory(ssl=True))
    return controller
