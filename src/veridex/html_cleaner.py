import re

from bs4 import BeautifulSoup

# Tags that never contribute readable product information
_NOISE_TAGS = [
    "script",
    "style",
    "noscript",
    "iframe",
    "svg",
    "img",
    "header",
    "footer",
    "nav",
    "aside",
    "form",
    "button",
    "meta",
    "link",
    "head",
]

# Collapse any run of whitespace (spaces, tabs, newlines) to a single newline
_WHITESPACE_RE = re.compile(r"[ \t]+")
_BLANK_LINES_RE = re.compile(r"\n{3,}")


def clean_html(raw_html: str) -> str:
    """
    Strip noise from raw HTML and return plain text suitable for LLM input.

    Removes scripts, styles, navigation, and other non-content elements,
    then extracts visible text with collapsed whitespace.

    :param raw_html: The full HTML source of a web page.
    :return: Cleaned plain-text representation of the page content.
    """
    soup = BeautifulSoup(raw_html, "html.parser")

    for tag in soup(_NOISE_TAGS):
        tag.decompose()

    text = soup.get_text(separator="\n")
    text = _WHITESPACE_RE.sub(" ", text)
    text = _BLANK_LINES_RE.sub("\n\n", text)
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Extracted text is not a string")
    return text.strip()
