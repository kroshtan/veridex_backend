from functools import cache

from bs4 import BeautifulSoup
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from veridex.config import settings

_MAX_CANDIDATE_URLS = 50

_IMAGE_SYSTEM = """\
You are given a list of image URLs extracted from an e-commerce product page.
Pick up to 3 URLs that are most likely the main product images (the item being sold).
Exclude logos, icons, banners, thumbnails of other products, and social media icons.
Return only exact URLs from the provided list.\
"""


class _ProductImageOutput(BaseModel):
    urls: list[str] = Field(description="Up to 3 image URLs most likely to be the main product images.")


@cache
def _get_image_select_llm() -> object:
    return ChatOpenAI(
        model="gpt-4o-mini", temperature=0, openai_api_key=settings.openai_api_key
    ).with_structured_output(_ProductImageOutput)


def extract_image_urls(html: str) -> list[str]:
    """
    Return deduplicated absolute HTTP image URLs from raw HTML.

    :param html: Raw HTML source of the page.
    :return: List of absolute image URLs in document order.
    """
    soup = BeautifulSoup(html, "html.parser")
    seen: set[str] = set()
    urls: list[str] = []
    for img in soup.find_all("img"):
        src: str | None = img.get("src") or img.get("data-src") or img.get("data-lazy-src")
        if src and src.startswith("http") and not src.lower().endswith(".svg") and src not in seen:
            seen.add(src)
            urls.append(src)
    return urls


async def select_product_images(all_urls: list[str], max_images: int = 3) -> list[str]:
    """
    Use an LLM to pick the most likely product images from a list of URLs.

    Falls back to the first available URL if the LLM returns no valid choices.

    :param all_urls: Candidate image URLs extracted from the page.
    :param max_images: Maximum number of product images to return.
    :return: Up to ``max_images`` URLs identified as main product images.
    """
    if not all_urls:
        return []
    url_list = "\n".join(all_urls[:_MAX_CANDIDATE_URLS])
    output: _ProductImageOutput = await _get_image_select_llm().ainvoke(  # type: ignore[union-attr,assignment]
        [
            SystemMessage(content=_IMAGE_SYSTEM),
            HumanMessage(content=f"Image URLs:\n{url_list}"),
        ]
    )
    all_url_set = set(all_urls)
    selected = [u for u in output.urls if u in all_url_set][:max_images]
    return selected or all_urls[:1]
