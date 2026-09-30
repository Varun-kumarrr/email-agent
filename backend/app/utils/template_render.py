"""Safe template rendering for email templates.

Only `{{ variable_name }}` placeholders are supported: a variable name is letters,
digits and underscores. There are no expressions, filters, attribute access, loops
or code execution, so a template can never run code or read server data (unlike
passing user text to Jinja/`str.format`). Anything else inside `{{ }}`, and any
`{% %}` block, is rejected when a template is saved.

Values are escaped for HTML templates, and line breaks are removed from values
rendered into subjects (a subject becomes an email header).
"""

import html
import re

from app.utils.text import to_single_line

MAX_VALUE_LENGTH = 1000
_NAME = r"[A-Za-z_][A-Za-z0-9_]{0,63}"
PLACEHOLDER = re.compile(r"\{\{\s*(" + _NAME + r")\s*\}\}")
_ANY_BRACES = re.compile(r"\{\{(.*?)\}\}", re.S)
_STATEMENT = re.compile(r"\{%.*?%\}", re.S)


class TemplateSyntaxError(ValueError):
    pass


def validate_template(text: str) -> None:
    """Raise TemplateSyntaxError if `text` contains anything but simple placeholders."""
    if _STATEMENT.search(text):
        raise TemplateSyntaxError("Template statements like {% ... %} are not supported")
    for match in _ANY_BRACES.finditer(text):
        if not re.fullmatch(r"\s*" + _NAME + r"\s*", match.group(1)):
            raise TemplateSyntaxError(
                f"Invalid placeholder '{{{{{match.group(1).strip()[:40]}}}}}': use {{{{ variable_name }}}} with letters, digits and underscores"
            )
    leftover = _ANY_BRACES.sub("", text)
    if "{{" in leftover or "}}" in leftover:
        raise TemplateSyntaxError("Unbalanced '{{' or '}}' in template")


def extract_variables(*texts: str) -> list[str]:
    names: list[str] = []
    for text in texts:
        for name in PLACEHOLDER.findall(text or ""):
            if name not in names:
                names.append(name)
    return names


def _clean_value(value, *, single_line: bool) -> str:
    text = str(value)[:MAX_VALUE_LENGTH]
    if single_line:
        text = to_single_line(text)
    return text


def render(text: str, values: dict, *, escape_html: bool = False, single_line: bool = False) -> tuple[str, list[str]]:
    """Substitute placeholders. Returns (rendered_text, missing_variable_names).

    Missing variables are left in place as `{{ name }}` so callers can decide whether
    to reject (strict preview), keep them for the AI to fill, or strip them.
    """
    missing: list[str] = []

    def substitute(match: re.Match) -> str:
        name = match.group(1)
        value = values.get(name)
        if value is None or str(value).strip() == "":
            if name not in missing:
                missing.append(name)
            return match.group(0)
        cleaned = _clean_value(value, single_line=single_line)
        return html.escape(cleaned) if escape_html else cleaned

    return PLACEHOLDER.sub(substitute, text), missing


def strip_placeholders(text: str) -> str:
    """Remove any unfilled placeholders and tidy the whitespace they leave behind."""
    text = PLACEHOLDER.sub("", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r" +([,.!?;:])", r"\1", text)
    return re.sub(r"[ \t]+\n", "\n", text).strip()
