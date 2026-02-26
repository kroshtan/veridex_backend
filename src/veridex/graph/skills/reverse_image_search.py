import contextlib
from urllib.parse import quote, urlparse

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

from veridex.graph.skills import Skill
from veridex.graph.skills._image_utils import extract_image_urls, select_product_images
from veridex.graph.state import AnalysisState

_MAX_IMAGES = 3
_BROWSER_TIMEOUT = 20_000  # ms

_GOOGLE_DOMAINS: frozenset[str] = frozenset(
    {
        "google.com",
        "googleapis.com",
        "gstatic.com",
        "googleusercontent.com",
        "youtube.com",
        "accounts.google.com",
    }
)

_DROPSHIP_DOMAINS: frozenset[str] = frozenset(
    {
        "temu.com",
        "aliexpress.com",
        "alibaba.com",
        "dhgate.com",
        "wish.com",
        "shein.com",
        "banggood.com",
        "gearbest.com",
        "joom.com",
        "lightinthebox.com",
        "dresslily.com",
        "zaful.com",
        "rosegal.com",
    }
)

def _extract_domain(url: str) -> str:
    """
    Return the registered domain (without www.) from a URL.

    :param url: A full URL string.
    :return: Domain string, e.g. ``"temu.com"``.
    """
    try:
        return urlparse(url).netloc.lower().removeprefix("www.")
    except Exception:  # noqa: BLE001
        return ""


def _is_google_domain(domain: str) -> bool:
    return any(domain == g or domain.endswith(f".{g}") for g in _GOOGLE_DOMAINS)


async def _reverse_image_search(image_url: str) -> list[str]:
    """
    Reverse-image-search via Google using a stealth Playwright browser.

    Navigates to Google's searchbyimage URL, waits for results, then collects
    all outbound link domains from the results page.

    :param image_url: Publicly accessible URL of the image to search for.
    :return: List of non-Google domain strings found in the results.
    """
    search_url = f"https://www.google.com/searchbyimage?image_url={quote(image_url)}&safe=off"

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await Stealth().apply_stealth_async(page)
            await page.goto(search_url, wait_until="domcontentloaded", timeout=_BROWSER_TIMEOUT)
            # Allow lazy-loaded results to settle
            with contextlib.suppress(Exception):
                await page.wait_for_selector("#search", timeout=5_000)

            html = await page.content()
        finally:
            await browser.close()

    soup = BeautifulSoup(html, "html.parser")
    domains: list[str] = []
    for a in soup.find_all("a", href=True):
        domain = _extract_domain(a["href"])
        if domain and not _is_google_domain(domain):
            domains.append(domain)
    return domains


class ReverseImageSearchSkill(Skill):
    """Reverse-image-search product images to detect dropship sourcing domains."""

    name = "reverse_image_search"
    description = "Reverse-image-searches product images to find dropship source domains."
    always_run = True

    async def run(self, state: AnalysisState) -> dict[str, list[str]]:
        """
        Identify product images, reverse-image-search them, and report dropship hits.

        :param state: Current graph state; uses ``page_content``.
        :return: Skill findings appended to ``skill_results``.
        """
        # Step 1 – extract candidate image URLs from raw HTML
        all_urls = extract_image_urls(state["page_content"])
        if not all_urls:
            return {"skill_results": ["[reverse_image_search]\nNo images found on page."]}

        # Step 2 – ask LLM to pick the product images
        product_urls = await select_product_images(all_urls, max_images=_MAX_IMAGES)

        # Step 3 – reverse-image-search each product image
        all_domains: list[str] = []
        for url in product_urls:
            with contextlib.suppress(Exception):
                all_domains.extend(await _reverse_image_search(url))

        total_hits = len(all_domains)
        found_dropship = sorted({d for d in all_domains if d in _DROPSHIP_DOMAINS})

        lines = [
            "[reverse_image_search]",
            f"Product images checked: {len(product_urls)}",
            f"Total reverse-image-search hits: {total_hits}",
        ]
        if found_dropship:
            lines.append(f"Known dropship domains found: {', '.join(found_dropship)}")
        else:
            lines.append("No known dropship domains detected in reverse image search results.")

        return {"skill_results": ["\n".join(lines)]}

