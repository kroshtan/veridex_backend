import contextlib
import json
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from langchain_core.messages import HumanMessage, SystemMessage

from veridex.graph.skills import Skill
from veridex.graph.state import AnalysisState
from veridex.llm import get_llm
from veridex.net import fetch_public

_MAX_REVIEWS = 40
_MAX_REVIEW_CHARS = 400

_ANALYZE_SYSTEM = """\
You are a review integrity analyst for e-commerce products.

Given a set of product reviews (with ratings, dates, and bodies where available), analyse for authenticity:

Fake / manipulated patterns to flag:
- Generic praise with no product-specific detail ("great product!", "fast shipping", "love it!")
- Multiple reviews sharing nearly identical phrasing or sentence structure
- All or nearly all ratings are 5-star with suspiciously uniform positivity
- Reviews that do not mention the actual product being sold
- Burst of reviews all posted on the same date or within a very short window
- Very high review count for what appears to be a recently launched store
- Unnatural language that reads as machine-generated or translated

Legitimate signals to note:
- Mix of star ratings including occasional 3-4 star constructive feedback
- Reviews mention specific product features, dimensions, materials, or use cases
- Organic date distribution spanning weeks, months, or years
- Variety in writing style, length, and expressed opinions

Provide a concise, factual summary of patterns observed and your integrity assessment.\
"""


# ── Review extraction ─────────────────────────────────────────────────────────


def _safe_str(val: object) -> str:
    """
    Coerce a value to a non-None string.

    :param val: Any value from a parsed JSON or BeautifulSoup node.
    :return: String representation, or empty string if ``val`` is None.
    """
    return "" if val is None else str(val)


def _extract_from_jsonld(html: str) -> list[dict[str, str]]:
    """
    Extract reviews from JSON-LD ``<script>`` blocks in the page.

    Handles both top-level ``Review`` objects and ``Product`` objects that
    embed a ``review`` array, including nested ``@graph`` structures.

    :param html: Raw HTML source of the page.
    :return: List of review dicts with keys ``author``, ``rating``, ``date``, ``body``.
    """
    soup = BeautifulSoup(html, "html.parser")
    reviews: list[dict[str, str]] = []

    def _walk(node: object) -> None:
        if isinstance(node, list):
            for item in node:
                _walk(item)
        elif isinstance(node, dict):
            t = node.get("@type", "")
            if t == "Review" or (isinstance(t, list) and "Review" in t):
                author = node.get("author", {})
                rating = node.get("reviewRating", {})
                reviews.append(
                    {
                        "author": _safe_str(author.get("name") if isinstance(author, dict) else author),
                        "rating": _safe_str(rating.get("ratingValue") if isinstance(rating, dict) else rating),
                        "date": _safe_str(node.get("datePublished", "")),
                        "body": _safe_str(node.get("reviewBody", ""))[:_MAX_REVIEW_CHARS],
                    }
                )
            # Recurse into known container keys
            for key in ("review", "@graph", "itemListElement"):
                if key in node:
                    _walk(node[key])

    for script in soup.find_all("script", type="application/ld+json"):
        with contextlib.suppress(Exception):
            _walk(json.loads(script.string or ""))

    return reviews


def _extract_from_microdata(html: str) -> list[dict[str, str]]:
    """
    Extract reviews from HTML microdata (``itemprop`` attributes).

    :param html: Raw HTML source of the page.
    :return: List of review dicts with keys ``author``, ``rating``, ``date``, ``body``.
    """
    soup = BeautifulSoup(html, "html.parser")
    reviews: list[dict[str, str]] = []

    for container in soup.find_all(itemprop="review"):
        body_el = container.find(itemprop="reviewBody")
        author_el = container.find(itemprop="author")
        rating_el = container.find(itemprop="ratingValue")
        date_el = container.find(itemprop="datePublished")
        reviews.append(
            {
                "author": _safe_str(author_el.get_text(strip=True) if author_el else ""),
                "rating": _safe_str(rating_el.get("content") or rating_el.get_text(strip=True) if rating_el else ""),
                "date": _safe_str(date_el.get("content") or date_el.get_text(strip=True) if date_el else ""),
                "body": _safe_str(body_el.get_text(strip=True) if body_el else "")[:_MAX_REVIEW_CHARS],
            }
        )

    return reviews


def _find_reviews_url(html: str, page_url: str) -> str | None:
    """
    Heuristically locate a URL pointing to a dedicated reviews page or section.

    :param html: Raw HTML source of the page.
    :param page_url: Absolute URL of the current page (used to resolve relative links).
    :return: Absolute URL of the reviews page, or ``None`` if not found.
    """
    soup = BeautifulSoup(html, "html.parser")

    for a in soup.find_all("a", href=True):
        href = str(a["href"])
        text = a.get_text(strip=True).lower()
        if any(
            kw in text for kw in ("all reviews", "see reviews", "more reviews", "customer reviews", "all customer")
        ):
            return urljoin(page_url, href)
        if re.search(r"/reviews?/?(\?|#|$)|[?&]tab=reviews|#reviews?", href, re.IGNORECASE):
            return urljoin(page_url, href)

    return None


def _format_reviews(reviews: list[dict[str, str]]) -> str:
    """
    Render a list of review dicts as a compact, LLM-readable text block.

    :param reviews: Review dicts with ``author``, ``rating``, ``date``, ``body``.
    :return: Formatted string, one review per block.
    """
    lines: list[str] = []
    for i, r in enumerate(reviews[:_MAX_REVIEWS], start=1):
        parts = [f"Review {i}"]
        if r.get("rating"):
            parts.append(f"★{r['rating']}")
        if r.get("date"):
            parts.append(r["date"])
        if r.get("author"):
            parts.append(f"by {r['author']}")
        lines.append(" | ".join(parts))
        if r.get("body"):
            lines.append(f'  "{r["body"]}"')
    return "\n".join(lines)


class ReviewIntegritySkill(Skill):
    """Extract and analyse product reviews for fake/manipulated patterns."""

    name = "review_integrity"
    description = "Extracts product reviews from the page and analyses content and date patterns for integrity."
    always_run = True

    async def run(self, state: AnalysisState) -> dict[str, list[str]]:
        """
        Collect and analyse product reviews for fake or manipulated patterns.

        Extracts reviews from JSON-LD, microdata, and optionally a linked reviews
        page, then analyses content and date patterns for integrity signals.

        :param state: Current graph state; uses ``page_content`` and ``url``.
        :return: Skill findings appended to ``skill_results``.
        """
        html = state["page_content"]

        # Step 1 – extract reviews from the current page
        reviews = _extract_from_jsonld(html)
        source = "JSON-LD"

        if not reviews:
            reviews = _extract_from_microdata(html)
            source = "microdata"

        # Step 2 – if sparse, try fetching a dedicated reviews URL
        reviews_url: str | None = None
        if len(reviews) < 5 and state.get("url"):
            reviews_url = _find_reviews_url(html, state["url"])
            if reviews_url:
                with contextlib.suppress(Exception):
                    extra_html = (await fetch_public(reviews_url)).decode("utf-8", errors="replace")
                    extra = _extract_from_jsonld(extra_html) or _extract_from_microdata(extra_html)
                    if extra:
                        reviews = extra
                        source = f"reviews page ({reviews_url})"

        if not reviews:
            return {
                "skill_results": [
                    "[review_integrity]\n"
                    "No structured review data found on the page"
                    + (f" or at {reviews_url}" if reviews_url else "")
                    + "."
                ]
            }

        # Step 3 – LLM integrity analysis
        review_text = _format_reviews(reviews)
        total = len(reviews)
        prompt = f"Total reviews extracted: {total} (showing up to {_MAX_REVIEWS})\nSource: {source}\n\n{review_text}"
        response = await get_llm().ainvoke([SystemMessage(content=_ANALYZE_SYSTEM), HumanMessage(content=prompt)])

        lines = [
            "[review_integrity]",
            f"Reviews analysed: {min(total, _MAX_REVIEWS)} (source: {source})",
            f"\n{response.content}",
        ]
        return {"skill_results": ["\n".join(lines)]}
