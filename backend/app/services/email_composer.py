"""Builds MIME messages (plain text or HTML with a plain-text alternative)."""

import html
import re
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

from app.models.enums import EmailFormat

_HTML_TAG = re.compile(r"<\s*/?\s*(p|br|div|span|a|b|strong|i|em|ul|ol|li|table|h[1-6]|html|body)\b", re.I)


def looks_like_html(text: str) -> bool:
    return bool(_HTML_TAG.search(text))


def text_to_html(text: str) -> str:
    """Escape plain text and keep its paragraphs and line breaks."""
    paragraphs = re.split(r"\n\s*\n", text.strip())
    rendered = [f"<p>{html.escape(p).replace(chr(10), '<br>')}</p>" for p in paragraphs if p.strip()]
    return (
        '<div style="font-family: Arial, Helvetica, sans-serif; font-size: 14px; line-height: 1.5;">'
        + "".join(rendered)
        + "</div>"
    )


def html_to_text(markup: str) -> str:
    text = re.sub(r"(?i)<br\s*/?>", "\n", markup)
    text = re.sub(r"(?i)</p\s*>", "\n\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\n{3,}", "\n\n", html.unescape(text)).strip()


def build_message(
    *,
    sender_email: str,
    sender_name: str | None,
    recipient: str,
    subject: str,
    body: str,
    email_format: EmailFormat,
    cc: list[str],
    reply_to: str | None,
    signature: str | None,
) -> EmailMessage:
    """`signature` (plain text) is appended when given. BCC is never a header."""
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = formataddr((sender_name, sender_email)) if sender_name else sender_email
    message["To"] = recipient
    if cc:
        message["Cc"] = ", ".join(cc)
    if reply_to:
        message["Reply-To"] = reply_to
    message["Date"] = formatdate(localtime=False)
    message["Message-ID"] = make_msgid(domain=sender_email.split("@")[-1])

    if email_format == EmailFormat.PLAIN_TEXT:
        text = body if not signature else f"{body.rstrip()}\n\n{signature.strip()}"
        message.set_content(text)
        return message

    # HTML: accept either HTML written by the user or plain text (converted safely).
    if looks_like_html(body):
        html_body = body
        if signature:
            html_body += "<br><br>" + html.escape(signature.strip()).replace("\n", "<br>")
        text_body = html_to_text(html_body)
    else:
        text_body = body if not signature else f"{body.rstrip()}\n\n{signature.strip()}"
        html_body = text_to_html(text_body)
    message.set_content(text_body)
    message.add_alternative(html_body, subtype="html")
    return message
