"""Tests for the deterministic (non-LLM) parts of the analysis skills."""

import io
import json
from datetime import UTC, datetime, timedelta

from PIL import Image

from veridex.graph.skills._image_utils import extract_image_urls
from veridex.graph.skills.domain_age import _domain_age_days
from veridex.graph.skills.exif_check import _extract_exif
from veridex.graph.skills.html_source_signals import _HARD_SIGNALS, _build_fingerprint
from veridex.graph.skills.reverse_image_search import _result_domains
from veridex.graph.skills.review_integrity import (
    _extract_from_jsonld,
    _extract_from_microdata,
    _find_reviews_url,
    _format_reviews,
)


def test_extract_image_urls_dedupes_and_filters() -> None:
    html = """
    <img src="https://cdn.shop.test/a.jpg">
    <img src="https://cdn.shop.test/a.jpg">
    <img data-src="https://cdn.shop.test/b.jpg">
    <img src="/relative.jpg">
    <img src="https://cdn.shop.test/logo.svg">
    """
    assert extract_image_urls(html) == ["https://cdn.shop.test/a.jpg", "https://cdn.shop.test/b.jpg"]


def test_hard_signals_detect_dropship_apps() -> None:
    html = '<script src="https://cdn.dsers.com/x.js"></script><img src="https://ae01.alicdn.com/kf/1.jpg">'
    hits = [label for pattern, label in _HARD_SIGNALS if pattern.search(html)]
    assert any("DSers" in h for h in hits)
    assert any("alicdn" in h for h in hits)


def test_build_fingerprint_collects_scripts_meta_and_comments() -> None:
    html = """
    <head>
      <meta name="generator" content="Shopify">
      <script src="https://apps.test/widget.js"></script>
      <!-- supplier: warehouse-cn-7 -->
    </head>
    """
    fingerprint = _build_fingerprint(html)
    assert "script src: https://apps.test/widget.js" in fingerprint
    assert "meta generator: Shopify" in fingerprint
    assert "comment: supplier: warehouse-cn-7" in fingerprint


def test_extract_reviews_from_jsonld_graph() -> None:
    data = {
        "@graph": [
            {
                "@type": "Product",
                "review": [
                    {
                        "@type": "Review",
                        "author": {"name": "Ann"},
                        "reviewRating": {"ratingValue": 5},
                        "datePublished": "2025-01-02",
                        "reviewBody": "Great fit.",
                    },
                    {"@type": "Review", "author": "Bob", "reviewRating": 2, "reviewBody": "Shrunk."},
                ],
            }
        ]
    }
    html = f'<script type="application/ld+json">{json.dumps(data)}</script>'
    assert _extract_from_jsonld(html) == [
        {"author": "Ann", "rating": "5", "date": "2025-01-02", "body": "Great fit."},
        {"author": "Bob", "rating": "2", "date": "", "body": "Shrunk."},
    ]


def test_extract_reviews_ignores_invalid_jsonld() -> None:
    assert _extract_from_jsonld('<script type="application/ld+json">{not json</script>') == []


def test_extract_reviews_from_microdata() -> None:
    html = """
    <div itemprop="review">
      <span itemprop="author">Cleo</span>
      <meta itemprop="ratingValue" content="4">
      <meta itemprop="datePublished" content="2025-03-04">
      <p itemprop="reviewBody">Solid.</p>
    </div>
    """
    assert _extract_from_microdata(html) == [{"author": "Cleo", "rating": "4", "date": "2025-03-04", "body": "Solid."}]


def test_find_reviews_url_resolves_relative_to_page() -> None:
    html = '<a href="reviews">See reviews</a>'
    assert _find_reviews_url(html, "https://shop.test/products/sweater") == "https://shop.test/products/reviews"
    assert _find_reviews_url("<a href='/about'>About</a>", "https://shop.test/") is None


def test_format_reviews() -> None:
    text = _format_reviews([{"author": "Ann", "rating": "5", "date": "2025-01-02", "body": "Nice"}])
    assert text == 'Review 1 | ★5 | 2025-01-02 | by Ann\n  "Nice"'


def test_domain_age_days() -> None:
    created = (datetime.now(tz=UTC) - timedelta(days=40)).strftime("%Y-%m-%d")
    assert _domain_age_days({"creation_date": created}) in {39, 40}
    assert _domain_age_days({"creation_date": "garbage"}) is None
    assert _domain_age_days({}) is None


def test_extract_exif_reads_interesting_tags() -> None:
    exif = Image.Exif()
    exif[0x010F] = "HiSilicon"  # Make
    exif[0x0131] = "Meitu"  # Software
    buf = io.BytesIO()
    Image.new("RGB", (4, 4)).save(buf, format="JPEG", exif=exif)
    assert _extract_exif(buf.getvalue()) == {"Make": "HiSilicon", "Software": "Meitu"}


def test_extract_exif_handles_garbage() -> None:
    assert _extract_exif(b"not an image") == {}


def test_result_domains_skips_google_and_relative_links() -> None:
    html = """
    <a href="https://www.aliexpress.com/item/1.html">a</a>
    <a href="https://maps.google.com/">g</a>
    <a href="/search?q=x">rel</a>
    """
    assert _result_domains(html) == ["aliexpress.com"]
