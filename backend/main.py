"""Backwards-compatible entry point.

The application now lives in the `app` package. This shim keeps the original
command working:

    uvicorn main:app --reload

The preferred command is:

    uvicorn app.main:app --reload
"""

from app.main import app  # noqa: F401
