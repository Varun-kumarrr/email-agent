"""Line-break helpers for text that ends up in email headers.

Python's email package rejects a header value when ``str.splitlines()`` finds more than
one line. That is not only CR and LF: vertical tab, form feed, the file/group/record
separators (\\x1c-\\x1e), NEL (\\x85) and the Unicode line/paragraph separators count too.
Header fields (sender name, subject) must be free of all of them.
"""

import re

# Every character str.splitlines() treats as a line boundary.
LINE_BREAKS = re.compile(r"[\r\n\v\f\x1c\x1d\x1e\x85  ]+")


def is_single_line(value: str) -> bool:
    """True when the text contains no line boundary of any kind."""
    return not LINE_BREAKS.search(value)


def to_single_line(value: str) -> str:
    """Replace line boundaries (and tabs) with single spaces."""
    return re.sub(r"[ \t]{2,}", " ", LINE_BREAKS.sub(" ", value).replace("\t", " ")).strip()
