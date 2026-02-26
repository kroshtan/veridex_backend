import re
from functools import cache

from bs4 import BeautifulSoup, Comment
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from veridex.config import settings
from veridex.graph.skills import Skill
from veridex.graph.state import AnalysisState

# ── Hard-coded signal patterns ────────────────────────────────────────────────
# Each entry is (compiled_regex, human_readable_label).
# Patterns are matched case-insensitively against the raw HTML source.
_HARD_SIGNALS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"oberlo", re.IGNORECASE), "Oberlo app (Shopify dropship fulfilment)"),
    (re.compile(r"dsers[.\-/]", re.IGNORECASE), "DSers app (AliExpress order management)"),
    (re.compile(r"autods", re.IGNORECASE), "AutoDS (automated dropshipping platform)"),
    (re.compile(r"spocket\.co", re.IGNORECASE), "Spocket (dropship supplier marketplace)"),
    (re.compile(r"dropified", re.IGNORECASE), "Dropified (dropshipping platform)"),
    (re.compile(r"cjdropshipping|cjpacket", re.IGNORECASE), "CJ Dropshipping / CJPacket fulfilment"),
    (re.compile(r"zendrop", re.IGNORECASE), "Zendrop (dropshipping platform)"),
    (re.compile(r"eprolo", re.IGNORECASE), "Eprolo (dropshipping platform)"),
    (re.compile(r"yakkyofy", re.IGNORECASE), "Yakkyofy (dropshipping platform)"),
    (re.compile(r"ae01\.alicdn\.com", re.IGNORECASE), "AliExpress product image CDN (ae01.alicdn.com)"),
    (re.compile(r"aliexpress\.com/item/", re.IGNORECASE), "Direct AliExpress product link in source"),
    (re.compile(r"temu\.com/", re.IGNORECASE), "Temu link in source"),
    (re.compile(r"dhgate\.com/product", re.IGNORECASE), "DHgate product link in source"),
]

_MAX_FINGERPRINT_CHARS = 5_000

_ANALYZE_SYSTEM = """\
You are an e-commerce fraud analyst reviewing the technical fingerprint of a product page's HTML source.

The fingerprint contains: external script sources, meta tags, and HTML comments.

Look for soft dropship signals such as:
- Shopify theme names or app scripts associated with dropshipping stores
- Currency converters or multi-currency widgets common in international dropship stores
- Shipping-time meta tags or template variables revealing supplier lead times
- Supplier-referencing hidden fields, data attributes, or comments (e.g. vendor IDs, warehouse codes)
- Fulfilment app SDK references (Printful, Printify, Modalyst, Syncee, Sup Dropshipping, etc.)
- Tracking pixels from platforms commonly used by dropshippers
- Anything that suggests the seller does not hold their own inventory

Be concise and factual. Report only genuine signals — do not speculate without evidence.\
"""


@cache
def _get_llm() -> ChatOpenAI:
    return ChatOpenAI(model="gpt-4o-mini", temperature=0, openai_api_key=settings.openai_api_key)


def _build_fingerprint(html: str) -> str:
    """
    Extract a condensed technical fingerprint from raw HTML for LLM analysis.

    Collects external script sources, meta tag pairs, and HTML comments, then
    truncates the result to ``_MAX_FINGERPRINT_CHARS``.

    :param html: Raw HTML source of the page.
    :return: Multi-line string summarising the page's technical metadata.
    """
    soup = BeautifulSoup(html, "html.parser")

    # External script sources
    lines: list[str] = [f"script src: {tag['src']}" for tag in soup.find_all("script", src=True)]

    # Meta tags
    for tag in soup.find_all("meta"):
        name = tag.get("name") or tag.get("property") or tag.get("http-equiv") or ""
        content = tag.get("content") or ""
        if name or content:
            lines.append(f"meta {name}: {content[:200]}")

    # HTML comments (first 120 chars each)
    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        snippet = str(comment).strip()[:120]
        if snippet:
            lines.append(f"comment: {snippet}")

    fingerprint = "\n".join(lines)
    return fingerprint[:_MAX_FINGERPRINT_CHARS]


class HtmlSourceSignalsSkill(Skill):
    """Scan raw HTML source for hard-coded and soft dropship signals."""

    name = "html_source_signals"
    description = "Scans page HTML source for dropship app scripts, supplier CDN links, and related signals."
    always_run = True

    async def run(self, state: AnalysisState) -> dict[str, list[str]]:
        """
        Check raw HTML for known dropship patterns and analyse the technical fingerprint.

        Step 1 performs fast regex matching against a curated list of high-confidence
        identifiers. Step 2 sends a condensed HTML fingerprint (script sources, meta
        tags, comments) to the LLM for softer pattern detection.

        :param state: Current graph state; uses ``page_content``.
        :return: Skill findings appended to ``skill_results``.
        """
        html = state["page_content"]

        # Step 1 – hard signal scan
        hits = [label for pattern, label in _HARD_SIGNALS if pattern.search(html)]

        # Step 2 – LLM soft-signal analysis on technical fingerprint
        fingerprint = _build_fingerprint(html)
        llm_finding = ""
        if fingerprint.strip():
            response = await _get_llm().ainvoke(
                [SystemMessage(content=_ANALYZE_SYSTEM), HumanMessage(content=fingerprint)]
            )
            llm_finding = str(response.content)

        # Compose result
        lines = ["[html_source_signals]"]
        if hits:
            lines.append("Hard dropship signals detected:")
            lines.extend(f"  • {h}" for h in hits)
        else:
            lines.append("No hard-coded dropship app or CDN signals detected.")
        if llm_finding:
            lines.append(f"\nSoft-signal analysis:\n{llm_finding}")

        return {"skill_results": ["\n".join(lines)]}
