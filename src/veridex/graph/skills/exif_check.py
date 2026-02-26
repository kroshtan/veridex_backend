import asyncio
import contextlib
import io
from functools import cache
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from PIL import Image
from PIL.ExifTags import GPSTAGS, TAGS

from veridex.config import settings
from veridex.graph.skills import Skill
from veridex.graph.skills._image_utils import extract_image_urls, select_product_images
from veridex.graph.state import AnalysisState

_MAX_IMAGES = 3
_FETCH_TIMEOUT = 10  # seconds

# EXIF tags that are most informative for listing-authenticity checks.
_INTERESTING_TAGS: frozenset[str] = frozenset(
    {
        "Make",
        "Model",
        "Software",
        "DateTime",
        "DateTimeOriginal",
        "DateTimeDigitized",
        "Artist",
        "Copyright",
        "ImageDescription",
        "GPSInfo",
    }
)

_ANALYZE_SYSTEM = """\
You are a product-listing authenticity analyst.

You are given:
1. The text of an e-commerce product listing.
2. EXIF metadata extracted from the product images (one block per image).

Look for discrepancies between the listing claims and the image metadata, such as:
- Photo creation date far older than the product's claimed release year or "new" status
- GPS coordinates inconsistent with the seller's claimed country or warehouse location
- Camera make/model suggesting a Chinese OEM factory floor \
  (e.g., HiSilicon-based phones common in AliExpress-style mass production)
- Editing software associated with bulk image processing (e.g., Meitu, 美图秀秀, or similar)
- Artist or Copyright fields that don't match the seller's brand or point to a third-party supplier
- Identical EXIF timestamps across images, suggesting batch-exported stock photos

If no EXIF data was recovered from any image, say so explicitly.
Provide a concise, factual summary of findings — no score, just evidence.\
"""


@cache
def _get_llm() -> ChatOpenAI:
    return ChatOpenAI(model="gpt-4o-mini", temperature=0, openai_api_key=settings.openai_api_key)


def _fetch_and_extract_exif(url: str) -> dict[str, str]:
    """
    Fetch an image by URL and return its interesting EXIF fields.

    Silently returns an empty dict if the image cannot be fetched or parsed,
    or if it contains no EXIF metadata.

    :param url: Public URL of the image to inspect.
    :return: Dict mapping EXIF tag names to string values.
    """
    try:
        req = UrlRequest(url, headers={"User-Agent": "Mozilla/5.0"})
        with urlopen(req, timeout=_FETCH_TIMEOUT) as resp:  # noqa: S310
            image_bytes = resp.read()
    except Exception:  # noqa: BLE001
        return {}

    try:
        img = Image.open(io.BytesIO(image_bytes))
        exif = img.getexif()
    except Exception:  # noqa: BLE001
        return {}

    if not exif:
        return {}

    result: dict[str, str] = {}
    for tag_id, value in exif.items():
        tag = TAGS.get(tag_id, str(tag_id))
        if tag not in _INTERESTING_TAGS:
            continue

        if tag == "GPSInfo":
            with contextlib.suppress(Exception):
                gps_ifd = exif.get_ifd(tag_id)
                gps = {GPSTAGS.get(k, str(k)): str(v) for k, v in gps_ifd.items()}
                result[tag] = str(gps)
        elif isinstance(value, bytes):
            with contextlib.suppress(Exception):
                result[tag] = value.decode("utf-8", errors="replace").strip("\x00")
        else:
            result[tag] = str(value)

    return result


class ExifCheckSkill(Skill):
    """Extract EXIF metadata from product images and check for listing discrepancies."""

    name = "exif_check"
    description = "Extracts EXIF metadata from product images and flags discrepancies with listing details."
    always_run = True

    async def run(self, state: AnalysisState) -> dict[str, list[str]]:
        """
        Fetch product images, extract EXIF data, and report discrepancies with the listing.

        :param state: Current graph state; uses ``page_content`` and ``cleaned_content``.
        :return: Skill findings appended to ``skill_results``.
        """
        # Step 1 – find product image URLs
        all_urls = extract_image_urls(state["page_content"])
        if not all_urls:
            return {"skill_results": ["[exif_check]\nNo images found on page."]}

        product_urls = await select_product_images(all_urls, max_images=_MAX_IMAGES)

        # Step 2 – fetch images and extract EXIF (sync I/O off the event loop)
        exif_blocks: list[str] = []
        for i, url in enumerate(product_urls, start=1):
            exif = await asyncio.to_thread(_fetch_and_extract_exif, url)
            if exif:
                fields = "\n".join(f"  {k}: {v}" for k, v in sorted(exif.items()))
                exif_blocks.append(f"Image {i} ({url}):\n{fields}")
            else:
                exif_blocks.append(f"Image {i} ({url}): no EXIF data")

        # Step 3 – LLM comparison against listing text
        exif_summary = "\n\n".join(exif_blocks)
        prompt = f"Product listing:\n{state['cleaned_content'][:6_000]}\n\nEXIF metadata:\n{exif_summary}"
        response = await _get_llm().ainvoke([SystemMessage(content=_ANALYZE_SYSTEM), HumanMessage(content=prompt)])

        return {"skill_results": [f"[exif_check]\n{response.content}"]}
